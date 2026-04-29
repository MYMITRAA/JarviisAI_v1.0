"""
OpenAPI Spec Parser.
Ingests OpenAPI 3.x / Swagger 2.0 / Postman collections.
Extracts endpoints, schemas, auth requirements, and example payloads.
"""

import json
import logging
import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional
from urllib.parse import urljoin

import httpx
import yaml
from jsonschema import validate, ValidationError

logger = logging.getLogger("jarviis.api.parser")


@dataclass
class ParsedEndpoint:
    method: str
    path: str
    operation_id: Optional[str]
    summary: Optional[str]
    description: Optional[str]
    tags: List[str]
    parameters: List[Dict]            # path/query/header params
    request_body_schema: Optional[Dict]
    request_body_example: Optional[Any]
    response_schemas: Dict[str, Dict] # status_code → schema
    security: List[Dict]
    auth_required: bool
    deprecated: bool


@dataclass
class ParsedSpec:
    title: str
    version: str
    base_url: str
    format: str
    endpoints: List[ParsedEndpoint]
    global_security: List[Dict]
    security_schemes: Dict[str, Dict]
    servers: List[str]
    tags: List[str]
    raw: Dict


class OpenAPIParser:

    def parse_url(self, url: str) -> ParsedSpec:
        """Fetch and parse a spec from a URL."""
        content = self._fetch(url)
        return self.parse_content(content)

    def parse_content(self, content: str) -> ParsedSpec:
        """Parse a spec from raw YAML or JSON string."""
        try:
            spec = yaml.safe_load(content)
        except Exception:
            spec = json.loads(content)

        version_str = str(spec.get("openapi", spec.get("swagger", "2.0")))
        if version_str.startswith("3"):
            return self._parse_openapi3(spec)
        else:
            return self._parse_swagger2(spec)

    def _parse_openapi3(self, spec: Dict) -> ParsedSpec:
        info = spec.get("info", {})
        servers = [s.get("url", "") for s in spec.get("servers", [])]
        base_url = servers[0] if servers else ""
        global_security = spec.get("security", [])
        security_schemes = spec.get("components", {}).get("securitySchemes", {})
        components = spec.get("components", {})

        endpoints = []
        paths = spec.get("paths", {})
        for path, path_item in paths.items():
            path_params = path_item.get("parameters", [])
            for method in ("get", "post", "put", "patch", "delete", "head", "options"):
                op = path_item.get(method)
                if not op:
                    continue

                # Resolve $refs in schemas
                req_body = op.get("requestBody", {})
                req_schema = None
                req_example = None
                if req_body:
                    content = req_body.get("content", {})
                    for media_type, media_obj in content.items():
                        if "json" in media_type:
                            req_schema = self._resolve_ref(media_obj.get("schema", {}), components)
                            req_example = media_obj.get("example") or self._generate_example(req_schema)
                            break

                # Parse responses
                response_schemas = {}
                for status_code, resp_obj in op.get("responses", {}).items():
                    resp_content = resp_obj.get("content", {})
                    for media_type, media_obj in resp_content.items():
                        if "json" in media_type:
                            response_schemas[str(status_code)] = self._resolve_ref(
                                media_obj.get("schema", {}), components
                            )
                            break

                security = op.get("security", global_security)
                endpoints.append(ParsedEndpoint(
                    method=method.upper(),
                    path=path,
                    operation_id=op.get("operationId"),
                    summary=op.get("summary"),
                    description=op.get("description"),
                    tags=op.get("tags", []),
                    parameters=path_params + op.get("parameters", []),
                    request_body_schema=req_schema,
                    request_body_example=req_example,
                    response_schemas=response_schemas,
                    security=security,
                    auth_required=bool(security),
                    deprecated=op.get("deprecated", False),
                ))

        return ParsedSpec(
            title=info.get("title", "API"),
            version=info.get("version", "1.0.0"),
            base_url=base_url,
            format="openapi_3",
            endpoints=endpoints,
            global_security=global_security,
            security_schemes=security_schemes,
            servers=servers,
            tags=list({t for ep in endpoints for t in ep.tags}),
            raw=spec,
        )

    def _parse_swagger2(self, spec: Dict) -> ParsedSpec:
        """Minimal Swagger 2.0 parser — converts to ParsedSpec format."""
        info = spec.get("info", {})
        host = spec.get("host", "localhost")
        base_path = spec.get("basePath", "/")
        schemes = spec.get("schemes", ["https"])
        base_url = f"{schemes[0]}://{host}{base_path}"
        definitions = spec.get("definitions", {})
        components = {"schemas": definitions}

        endpoints = []
        for path, path_item in spec.get("paths", {}).items():
            for method in ("get", "post", "put", "patch", "delete"):
                op = path_item.get(method)
                if not op:
                    continue

                # Body parameter
                req_schema = None
                for param in op.get("parameters", []):
                    if param.get("in") == "body":
                        req_schema = self._resolve_ref(param.get("schema", {}), components)
                        break

                # Responses
                response_schemas = {}
                for code, resp in op.get("responses", {}).items():
                    if "schema" in resp:
                        response_schemas[str(code)] = self._resolve_ref(resp["schema"], components)

                endpoints.append(ParsedEndpoint(
                    method=method.upper(),
                    path=path,
                    operation_id=op.get("operationId"),
                    summary=op.get("summary"),
                    description=op.get("description"),
                    tags=op.get("tags", []),
                    parameters=op.get("parameters", []),
                    request_body_schema=req_schema,
                    request_body_example=self._generate_example(req_schema) if req_schema else None,
                    response_schemas=response_schemas,
                    security=op.get("security", []),
                    auth_required=bool(op.get("security")),
                    deprecated=op.get("deprecated", False),
                ))

        return ParsedSpec(
            title=info.get("title", "API"),
            version=info.get("version", "1.0.0"),
            base_url=base_url,
            format="openapi_2",
            endpoints=endpoints,
            global_security=spec.get("security", []),
            security_schemes=spec.get("securityDefinitions", {}),
            servers=[base_url],
            tags=list({t for ep in endpoints for t in ep.tags}),
            raw=spec,
        )

    def parse_postman(self, content: str) -> ParsedSpec:
        """Parse a Postman Collection v2.1 JSON."""
        data = json.loads(content)
        info = data.get("info", {})
        endpoints = []

        def walk_items(items, prefix=""):
            for item in items:
                if "item" in item:  # folder
                    walk_items(item["item"], prefix + item.get("name", "") + "/")
                elif "request" in item:
                    req = item["request"]
                    url_obj = req.get("url", {})
                    if isinstance(url_obj, str):
                        path = "/" + "/".join(url_obj.split("/")[3:])
                    else:
                        path = "/" + "/".join(url_obj.get("path", []))

                    body = req.get("body", {})
                    req_schema = None
                    if body.get("mode") == "raw" and body.get("raw"):
                        try:
                            req_schema = {"example": json.loads(body["raw"])}
                        except Exception:
                            pass

                    endpoints.append(ParsedEndpoint(
                        method=req.get("method", "GET").upper(),
                        path=path,
                        operation_id=None,
                        summary=item.get("name"),
                        description=req.get("description"),
                        tags=[prefix.rstrip("/")],
                        parameters=[
                            {"name": p.get("key"), "in": "query", "value": p.get("value")}
                            for p in url_obj.get("query", []) if isinstance(url_obj, dict)
                        ],
                        request_body_schema=req_schema,
                        request_body_example=None,
                        response_schemas={},
                        security=[],
                        auth_required=bool(req.get("auth")),
                        deprecated=False,
                    ))

        walk_items(data.get("item", []))
        return ParsedSpec(
            title=info.get("name", "Postman Collection"),
            version="1.0.0",
            base_url="",
            format="postman",
            endpoints=endpoints,
            global_security=[],
            security_schemes={},
            servers=[],
            tags=list({t for ep in endpoints for t in ep.tags}),
            raw=data,
        )

    def validate_response(self, schema: Dict, response_body: Any, components: Dict = None) -> List[str]:
        """Validate a response body against a JSON schema. Returns list of errors."""
        if not schema:
            return []
        try:
            resolved = self._resolve_ref(schema, {"schemas": components or {}})
            validate(instance=response_body, schema=resolved)
            return []
        except ValidationError as e:
            return [e.message]
        except Exception as e:
            return [str(e)]

    def _resolve_ref(self, schema: Dict, components: Dict) -> Dict:
        """Recursively resolve $ref references."""
        if not isinstance(schema, dict):
            return schema
        if "$ref" in schema:
            ref_path = schema["$ref"]
            # #/components/schemas/Foo or #/definitions/Foo
            parts = ref_path.lstrip("#/").split("/")
            resolved = components
            for part in parts:
                if isinstance(resolved, dict):
                    resolved = resolved.get(part, {})
            return self._resolve_ref(resolved, components)
        result = {}
        for k, v in schema.items():
            if isinstance(v, dict):
                result[k] = self._resolve_ref(v, components)
            elif isinstance(v, list):
                result[k] = [self._resolve_ref(i, components) if isinstance(i, dict) else i for i in v]
            else:
                result[k] = v
        return result

    def _generate_example(self, schema: Optional[Dict]) -> Optional[Any]:
        """Generate a minimal example value from a JSON schema."""
        if not schema:
            return None
        t = schema.get("type", "object")
        if schema.get("example") is not None:
            return schema["example"]
        if t == "object":
            return {
                k: self._generate_example(v)
                for k, v in schema.get("properties", {}).items()
                if k in schema.get("required", list(schema.get("properties", {}).keys()))
            }
        if t == "array":
            item_ex = self._generate_example(schema.get("items", {}))
            return [item_ex] if item_ex is not None else []
        if t == "string":
            fmt = schema.get("format", "")
            if fmt == "email": return "user@example.com"
            if fmt == "date-time": return "2026-01-01T00:00:00Z"
            if fmt == "uuid": return "550e8400-e29b-41d4-a716-446655440000"
            return schema.get("enum", [None])[0] or "string"
        if t == "integer": return schema.get("minimum", 1)
        if t == "number": return schema.get("minimum", 1.0)
        if t == "boolean": return True
        return None

    def _fetch(self, url: str) -> str:
        resp = httpx.get(url, timeout=15, follow_redirects=True)
        resp.raise_for_status()
        return resp.text


parser = OpenAPIParser()
