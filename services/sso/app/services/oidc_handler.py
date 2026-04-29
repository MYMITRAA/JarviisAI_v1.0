"""
OIDC Handler — OpenID Connect 1.0 / OAuth2 Authorization Code flow.

Supports: Okta, Azure AD, Auth0, Google Workspace, Ping Identity, Keycloak.
Uses PKCE for security. Validates id_token signature using IdP JWKS.
"""

import base64
import hashlib
import json
import logging
import os
import re
import secrets
import time
from typing import Dict, Optional, Tuple
from urllib.parse import urlencode

import httpx
from jose import jwt, JWTError

logger = logging.getLogger("jarviis.sso.oidc")


class OIDCHandler:

    def __init__(self):
        self._discovery_cache: Dict[str, dict] = {}
        self._jwks_cache: Dict[str, dict] = {}

    def build_authorization_url(
        self,
        discovery_url: str,
        client_id: str,
        redirect_uri: str,
        scopes: list,
        state: str,
        nonce: str,
    ) -> Tuple[str, str, str]:
        """
        Build an OIDC authorization URL with PKCE.
        Returns (url, code_verifier, state)
        """
        # PKCE code challenge
        code_verifier = base64.urlsafe_b64encode(os.urandom(40)).decode().rstrip("=")
        code_challenge = base64.urlsafe_b64encode(
            hashlib.sha256(code_verifier.encode()).digest()
        ).decode().rstrip("=")

        params = {
            "response_type": "code",
            "client_id": client_id,
            "redirect_uri": redirect_uri,
            "scope": " ".join(scopes or ["openid", "email", "profile"]),
            "state": state,
            "nonce": nonce,
            "code_challenge": code_challenge,
            "code_challenge_method": "S256",
        }

        # We need the authorization_endpoint from discovery
        auth_endpoint = f"{discovery_url}/authorize"  # Fallback
        # In real flow, fetch_discovery() would be called first

        url = f"{auth_endpoint}?{urlencode(params)}"
        return url, code_verifier, state

    async def exchange_code(
        self,
        code: str,
        client_id: str,
        client_secret: str,
        redirect_uri: str,
        code_verifier: str,
        token_endpoint: str,
    ) -> Dict:
        """Exchange authorization code for tokens."""
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.post(token_endpoint, data={
                "grant_type": "authorization_code",
                "code": code,
                "client_id": client_id,
                "client_secret": client_secret,
                "redirect_uri": redirect_uri,
                "code_verifier": code_verifier,
            })
            resp.raise_for_status()
            return resp.json()

    async def validate_id_token(
        self,
        id_token: str,
        client_id: str,
        issuer: str,
        jwks_uri: str,
        nonce: Optional[str] = None,
    ) -> Dict:
        """Validate and decode an OIDC id_token using the IdP's JWKS."""
        try:
            # Fetch JWKS
            jwks = await self._get_jwks(jwks_uri)

            # Decode without verification first to get the key ID
            header = jwt.get_unverified_header(id_token)
            kid = header.get("kid")

            # Find the matching key
            key = None
            for k in jwks.get("keys", []):
                if k.get("kid") == kid or kid is None:
                    key = k
                    break

            if not key:
                return {"valid": False, "error": "No matching JWKS key found"}

            # Validate token
            claims = jwt.decode(
                id_token,
                key,
                algorithms=["RS256", "RS384", "RS512", "ES256", "HS256"],
                audience=client_id,
                issuer=issuer,
            )

            # Validate nonce
            if nonce and claims.get("nonce") != nonce:
                return {"valid": False, "error": "Nonce mismatch"}

            return {
                "valid": True,
                "sub": claims.get("sub"),
                "email": claims.get("email"),
                "email_verified": claims.get("email_verified", False),
                "given_name": claims.get("given_name"),
                "family_name": claims.get("family_name"),
                "name": claims.get("name"),
                "picture": claims.get("picture"),
                "groups": claims.get("groups", []),
                "claims": claims,
            }
        except JWTError as e:
            return {"valid": False, "error": f"JWT validation error: {e}"}
        except Exception as e:
            return {"valid": False, "error": f"Token validation error: {e}"}

    async def fetch_discovery(self, issuer_or_discovery_url: str) -> Dict:
        """Fetch OpenID Connect discovery document."""
        if issuer_or_discovery_url in self._discovery_cache:
            return self._discovery_cache[issuer_or_discovery_url]

        # Try well-known endpoint
        if not issuer_or_discovery_url.endswith("well-known/openid-configuration"):
            discovery_url = f"{issuer_or_discovery_url.rstrip('/')}/.well-known/openid-configuration"
        else:
            discovery_url = issuer_or_discovery_url

        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(discovery_url)
            resp.raise_for_status()
            doc = resp.json()

        self._discovery_cache[issuer_or_discovery_url] = doc
        return doc

    async def _get_jwks(self, jwks_uri: str) -> Dict:
        if jwks_uri in self._jwks_cache:
            return self._jwks_cache[jwks_uri]
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(jwks_uri)
            resp.raise_for_status()
            jwks = resp.json()
        self._jwks_cache[jwks_uri] = jwks
        return jwks

    async def get_userinfo(self, access_token: str, userinfo_endpoint: str) -> Dict:
        """Fetch user info from OIDC userinfo endpoint."""
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(
                userinfo_endpoint,
                headers={"Authorization": f"Bearer {access_token}"},
            )
            resp.raise_for_status()
            return resp.json()


oidc_handler = OIDCHandler()
