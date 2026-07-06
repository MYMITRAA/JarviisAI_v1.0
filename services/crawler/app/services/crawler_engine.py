"""
JarviisAI Web Crawler Engine.

Crawls any web application using Playwright headless Chromium:
1. Launches browser, navigates to URL
2. Extracts all interactive elements, forms, links
3. Follows links up to max depth
4. Captures screenshots per page
5. Builds a structured app map for AI test generation

Handles: SPAs (React/Vue/Angular), auth-protected routes, infinite scroll,
AJAX content, shadow DOM, lazy-loaded elements.
"""

import asyncio
import json
import logging
import re
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set, Any
from collections import deque
from urllib.parse import urljoin, urlparse

from playwright.async_api import async_playwright, Browser, Page, ElementHandle
from urllib.robotparser import RobotFileParser

from app.core.config import settings

logger = logging.getLogger("jarviis.crawler")


@dataclass
class PageElement:
    """Represents a single interactive element found on a page."""
    element_type: str       # button | input | select | link | form | textarea
    tag: str
    text: Optional[str]
    placeholder: Optional[str]
    aria_label: Optional[str]
    role: Optional[str]
    name: Optional[str]
    id: Optional[str]
    classes: List[str]
    href: Optional[str]
    input_type: Optional[str]
    is_required: bool
    is_visible: bool
    selector: str           # best CSS selector for this element
    xpath: Optional[str]
    position: Dict[str, float]  # {x, y, width, height}


@dataclass
class CrawledPage:
    """Represents a fully analyzed page."""
    url: str
    title: str
    status_code: int
    page_type: str          # homepage | form | listing | detail | auth | dashboard | error
    depth: int
    elements: List[Dict]
    forms: List[Dict]
    links_found: List[str]
    screenshot_base64: Optional[str]
    load_time_ms: int
    framework_detected: Optional[str]  # React | Vue | Angular | Next.js | plain
    meta: Dict[str, Any]


@dataclass
class CrawlResult:
    """Complete crawl result for an application."""
    base_url: str
    pages_crawled: int
    pages: List[Dict]
    sitemap: List[str]
    element_count: int
    form_count: int
    app_framework: Optional[str]
    crawl_duration_ms: int
    errors: List[str]
    app_context: Dict[str, Any]
    navigation_graph: List[Dict] = field(default_factory=list)  # Structured context for AI


class CrawlerEngine:
    """
    Main crawler — uses Playwright to fully render and analyze web apps.
    """

    def __init__(self):
        self.visited_urls: Set[str] = set()
        self.pages: List[CrawledPage] = []
        self.errors: List[str] = []
        self.navigation_graph: List[Dict] = []
        self.explored_paths = set()
        self.semaphore = asyncio.Semaphore(5)
        self.detected_bugs = []
        self.is_authenticated = False
        self.start_url = ""
        self.failed_api_calls = []
        self.failed_network_requests = []
        self.slow_api_calls = []
        self.api_request_counter = {}
        self.large_payloads = []
        self.mixed_content = []
        self.accessibility_scanned_urls = set()
        self.render_blocking_resources = []
        self.large_js_bundles = []
        self.failed_images = []

    def _add_bug(
        self,
        bug_type,
        severity,
        page_url,
        description
    ):
        self.detected_bugs.append({
            "type": bug_type,
            "severity": severity,
            "url": page_url,
            "description": description,
        })

        logger.warning(
            f"BUG DETECTED | {bug_type} | {severity} | {page_url}"
        )

    async def crawl(
        self,
        url: str,
        max_depth: int = 3,
        max_pages: int = 50,
        auth_config: Optional[Dict] = None,
        timeout_seconds: int = 120,
    ) -> CrawlResult:
        """
        Main entry point. Crawls a URL and returns a complete app map.
        """
        import time
        start = time.time()

        async with async_playwright() as pw:
            browser = await pw.chromium.launch(
                headless=True,
                args=[
                    "--no-sandbox",
                    "--disable-setuid-sandbox",
                    "--disable-dev-shm-usage",
                    "--disable-web-security",
                    "--disable-features=VizDisplayCompositor",
                ],
            )

            context = await browser.new_context(
                viewport={"width": 1280, "height": 800},
                user_agent="Mozilla/5.0 (compatible; JarviisAI/1.0; +https://jarviis.ai/bot)",
                ignore_https_errors=True,
                java_script_enabled=True,
            )
            self.start_url = url
            logger.info(
                f"AUTH CONFIG: {auth_config}"
            )
            # Start BFS crawl
            await self._crawl_bfs(
                context=context,
                start_url=url,
                max_depth=max_depth,
                max_pages=max_pages,
                auth_config=auth_config,
            )

            await browser.close()

        duration_ms = int((time.time() - start) * 1000)
        app_framework = self._detect_framework()
        app_context = self._build_app_context(url)

        return CrawlResult(
            base_url=url,
            pages_crawled=len(self.pages),
            pages=[self._page_to_dict(p) for p in self.pages],
            sitemap=list(self.visited_urls),
            element_count=sum(len(p.elements) for p in self.pages),
            form_count=sum(len(p.forms) for p in self.pages),
            app_framework=app_framework,
            crawl_duration_ms=duration_ms,
            errors=self.errors,
            app_context=app_context,
            navigation_graph=self.navigation_graph,
        )


    async def _check_robots_allowed(self, url: str, base_url: str) -> bool:
        """Check robots.txt to see if URL is allowed for crawling."""
        try:
            from urllib.parse import urlparse
            parsed = urlparse(base_url)
            robots_url = f"{parsed.scheme}://{parsed.netloc}/robots.txt"
            rp = RobotFileParser()
            rp.set_url(robots_url)
            rp.read()
            return rp.can_fetch("JarviisAI-Crawler/1.0", url)
        except Exception:
            return True  # Allow if robots.txt is unreachable

    async def _crawl_bfs(
        self, context, start_url: str, max_depth: int, max_pages: int, auth_config=None,
    ) -> None:
        """Breadth-first crawl."""
        queue: List[tuple] = [(start_url, 0)]  # (url, depth)
        base_domain = urlparse(start_url).netloc

        while queue and len(self.pages) < max_pages:
            queue.sort(
                key=lambda x: self._score_page(x[0]),
                reverse=True,
            )

            batch = []

            while queue and len(batch) < 5:

                url, depth = queue.pop(0)

                batch.append(
                    self._crawl_worker(
                        context,
                        url,
                        depth,
                        max_depth,
                        base_domain,
                        queue,
                        auth_config,
                    )
                )

            await asyncio.gather(*batch)
    async def _crawl_worker(
        self,
        context,
        url,
        depth,
        max_depth,
        base_domain,
        queue,
        auth_config=None,
    ):
        async with self.semaphore:

            if url in self.visited_urls:
                return

            if depth > max_depth:
                return

            if not self._is_same_domain(url, base_domain):
                return

            self.visited_urls.add(url)

            try:
                page_data = await self._analyze_page(
                    context,
                    url,
                    depth,
                    auth_config,
                )

                if page_data:

                    self.pages.append(page_data)

                    for link in page_data.links_found:
                        bad_patterns = [
                            "?share=",
                            "&nb=",
                            "facebook.com",
                            "linkedin.com",
                            "reddit.com",
                            "x.com",
                            "twitter.com",
                            "threads.net",
                            "telegram.me",
                            "t.me",
                        ]

                        if any(
                            pattern in link
                            for pattern in bad_patterns
                        ):
                            continue

                        if link not in self.visited_urls:
                            queue.append((link, depth + 1))

            except Exception as e:
                logger.warning(
                    f"Failed to crawl {url}: {e}"
                )

                self.errors.append(
                    f"{url}: {str(e)}"
                )
    async def _perform_login(
        self,
        page,
        auth_config
    ):

        try:

            logger.info(
                "STARTING AUTHENTICATION"
            )
            logger.info(
                f"CURRENT PAGE: {page.url}"
            )
            await page.wait_for_timeout(2000)
            try:
                await page.wait_for_load_state(
                    "networkidle",
                    timeout=5000
                )
            except:
                pass

            username_selectors = [
                "input[name='username']",
                "input[name*='user']",
                "input[id*='user']",
                "input[placeholder*='Username']",
                "input[placeholder*='username']",
                "input[placeholder*='Email']",
                "input[placeholder*='email']",
                "input[type='email']",
                "input[name*='email']",
                "input[name*='login']",
                "input[type='text']"
            ]

            username_field = None

            for selector in username_selectors:

                try:

                    field = await page.query_selector(
                        selector
                    )

                    if field:

                        username_field = field

                        logger.info(
                            f"USERNAME FIELD FOUND: {selector}"
                        )

                        break

                except:
                    pass
            password_inputs = await page.query_selector_all(
                """
                input[type='password'],
                input[name*='password'],
                input[placeholder*='Password'],
                input[placeholder*='password']
                """
            )
            logger.info(
                f"PASSWORD INPUT COUNT: {len(password_inputs)}"
            )
            if not password_inputs:

                logger.info(
                    "NO LOGIN PAGE DETECTED"
                )

                return False
            logger.info(
                "LOGIN PAGE DETECTED"
            )
            password_field = await page.query_selector(
                "input[type='password']"
            )
            logger.info(
                "PASSWORD FIELD DETECTED"
            )

            if not username_field:

                logger.warning(
                    "USERNAME FIELD NOT FOUND"
                )

                return False

            if not password_field:

                logger.warning(
                    "PASSWORD FIELD NOT FOUND"
                )

                return False


            await username_field.fill(
                auth_config["username"]
            )

            await password_field.fill(
                auth_config["password"]
            )

            logger.info(
                "CREDENTIALS FILLED"
            )

            login_button = None

            buttons = await page.query_selector_all(
                "button, input[type='submit']"
            )

            keywords = [
                "login",
                "sign in",
                "log in",
                "continue",
                 "submit"
            ]

            for btn in buttons:

                try:

                    text = (
                        await btn.inner_text()
                        or ""
                    ).lower()

                    if any(
                        k in text
                        for k in keywords
                    ):

                        login_button = btn

                        logger.info(
                            f"LOGIN BUTTON FOUND: {text}"
                        )

                        break

                except:
                    pass

            old_url = page.url

            if login_button:

                await login_button.click()

            else:

                await page.keyboard.press(
                    "Enter"
                )

            logger.info(
                "LOGIN SUBMITTED"
            )

            try:

                await page.wait_for_function(
                    "(oldUrl) => window.location.href !== oldUrl",
                    old_url,
                    timeout=10000
                )

            except:
                pass

            await page.wait_for_timeout(3000)

            logger.info(
                f"POST LOGIN URL: {page.url}"
            )
            cookies = await page.context.cookies()

            logger.info(
                f"AUTH COOKIES COUNT: {len(cookies)}"
            )
            if page.url == old_url:

                self._add_bug(
                    bug_type="LOGIN_FAILURE",
                    severity="HIGH",
                    page_url=page.url,
                    description="Login submitted but URL did not change"
                )
                return False
        
            logger.info(
                "AUTHENTICATION SUCCESS"
            )
            self.is_authenticated = True

            return True

        except Exception as e:

            logger.warning(
                f"LOGIN FAILED: {e}"
            )

            return False

    async def _analyze_page(self, context, url: str, depth: int, auth_config=None,) -> Optional[CrawledPage]:
        """Open a page and extract all elements, forms, and links."""
        import time
        start = time.time()

        try:
            page = await context.new_page()
            console_errors = []
            failed_images = []
            failed_network_requests = []
            self.failed_api_calls = []
            self.slow_api_calls = []
            self.api_request_counter = {}
            self.large_payloads = []
            self.mixed_content = []
            self._seen_large_payloads = set()
            page_errors = []
            browser_js_errors = []

            page.on(
                "console",
                lambda msg: (
                    console_errors.append(msg.text)
                    if msg.type == "error"
                    else None
                )
            )
            page.on(
                "pageerror",
                lambda error: page_errors.append({
                    "message": str(error),
                    "stack": getattr(error, "stack", "")
                })
            )
            async def handle_response(response):

                try:
                    content_type = (
                        response.headers.get(
                            "content-type",
                            ""
                        ).lower()
                    )
                    if (
                        (
                            response.request.resource_type == "image"
                            or "image/" in content_type
                        )
                        and response.status in [
                                400,
                                401,
                                403,
                                404,
                                410,
                                500,
                                502,
                                503
                        ]
                    ):

                        self.failed_images.append(
                            {
                                "url": response.url,
                                "status": response.status
                            }
                        )
                    resource_type = (
                        response.request.resource_type
                    )

                    if resource_type in [
                        "xhr",
                        "fetch"
                    ]:
                        logger.info(
                            f"API CALL: "
                            f"{response.status} "
                            f"{response.request.resource_type} "
                            f"{response.url}"
                        )
                    resource_type = (
                        response.request.resource_type
                    )

                    if (
                        resource_type in [
                            "xhr",
                            "fetch"
                        ]
                        and response.status >= 400
                    ):
                        logger.info(
                            f"FAILED API DETECTED: "
                            f"{response.status} "
                            f"{response.url}"
                        )
                        self.failed_api_calls.append({
                            "url": response.url,
                            "status": response.status
                        })

                except Exception:
                    pass
                try:

                    resource_type = (
                        response.request.resource_type
                    )

                    content_type = (
                        response.headers.get(
                            "content-type",
                            ""
                        ).lower()
                    )

                    size = int(
                        response.headers.get(
                            "content-length",
                            0
                        )
                    )

                    if (
                        resource_type == "script"
                        and
                        size > 500 * 1024
                    ):

                        self.large_js_bundles.append(
                            {
                                "url": response.url,
                                "size": size
                            }
                        )

                except Exception:
                    pass
                try:

                    resource_type = (
                        response.request.resource_type
                    )

                    if resource_type in [
                        "script",
                        "stylesheet"
                    ]:

                        self.render_blocking_resources.append(
                            {
                                "url": response.url,
                                "type": resource_type
                            }
                        )

                except Exception:
                    pass
                try:

                    timing = response.request.timing

                    if timing:

                        duration = (
                            timing.get("responseEnd", 0)
                            -
                            timing.get("requestStart", 0)
                        )

                        if duration > 2000:

                            self.slow_api_calls.append(
                                {
                                    "url": response.url,
                                    "duration": duration
                                }
                            )

                except Exception:
                    pass
                from urllib.parse import urlparse

                parsed = urlparse(response.url)

                url = (
                    f"{parsed.scheme}://"
                    f"{parsed.netloc}"
                    f"{parsed.path}"
                )

                self.api_request_counter[url] = (
                    self.api_request_counter.get(url, 0)
                    + 1
                )
                try:

                    headers = response.headers

                    size = int(
                        headers.get(
                            "content-length",
                            0
                        )
                    )

                    if (
                        size > 1024 * 1024
                        and response.request.resource_type
                        in ["xhr", "fetch"]
                    ):

                        key = (
                            response.url,
                            size
                        )

                    if not hasattr(
                        self,
                        "_seen_large_payloads"
                    ):
                        self._seen_large_payloads = set()

                    if key not in self._seen_large_payloads:

                        self._seen_large_payloads.add(
                            key
                        )

                        self.large_payloads.append(
                            {
                                "url": response.url,
                                "size": size
                            }
                        )
                except:
                    pass
                if (
                    page.url.startswith("https")
                    and
                    response.url.startswith("http:")
                ):

                    self.mixed_content.append(
                        response.url
                    )
 
            page.on(
                "response",
                handle_response
            )
            async def handle_request_failed(request):

                try:

                    failed_network_requests.append({
                        "url": request.url,
                        "resource_type": request.resource_type,
                        "error": (
                            request.failure.get("errorText")
                            if request.failure
                            else "Unknown"
                        )
                    })

                except Exception:
                    pass
            page.on(
                "requestfailed",
                handle_request_failed
            )
            if not url.startswith(("http://", "https://")):
                url = f"https://{url}"

            # Navigate with network idle wait for SPA
            await page.add_init_script("""
            window.__jarviisJsErrors = [];

            window.addEventListener(
                'unhandledrejection',
                function(event) {

                    window.__jarviisJsErrors.push({
                        type: 'unhandled_promise_rejection',
                        message: String(event.reason)
                    });

                }
            );
            window.addEventListener(
                'error',
                function(event) {

                    if (
                        event.target &&
                        (event.target.src || event.target.href)
                    ) {

                        window.__jarviisJsErrors.push({
                            type: 'resource_load_failure',
                            url: event.target.src || event.target.href
                        });

                    }

                },
                true
            );
            document.addEventListener(
                'securitypolicyviolation',
                function(event) {

                    window.__jarviisJsErrors.push({
                        type: 'csp_violation',
                        blocked: event.blockedURI,
                        directive: event.violatedDirective
                    });

                }
            );
            """)
            response = await page.goto(
                url,
                timeout=settings.PAGE_LOAD_TIMEOUT_MS,
                wait_until="domcontentloaded",
            )
            try:

                await page.wait_for_load_state(
                    "networkidle"
                )

            except Exception:
                pass

            await page.wait_for_timeout(
                2000
            )
            
            try:
                browser_js_errors = await page.evaluate(
                    "() => window.__jarviisJsErrors || []"
                )

            except Exception as e:
                logger.warning(
                    f"JS ERROR COLLECTION FAILED: {e}"
                )

                browser_js_errors = []
            seen_images = set()

            for image in failed_images:

                key = (
                    image["url"],
                    image["status"]
                )
                if key in seen_images:
                    continue

                seen_images.add(key)

                self._add_bug(
                    bug_type="BROKEN_IMAGE",
                    severity="MEDIUM",
                    page_url=page.url,
                    description=(
                        f"Broken image detected: "
                        f"{image['url']} "
                        f"(HTTP {image['status']})"
                    )
                )
            seen_api_calls = set()
            if self.failed_api_calls:
                logger.info(
                    f"FAILED API COUNT: {len(self.failed_api_calls)}"
                )

            for api in self.failed_api_calls:

                key = (
                    api["url"],
                    api["status"]
                )

                if key in seen_api_calls:
                    continue
                seen_api_calls.add(key)
                logger.warning(
                    f"FAILED API: "
                    f"{api['status']} "
                    f"{api['url']}"
                )
                self._add_bug(
                    bug_type="API_FAILURE",
                    severity="HIGH",
                    page_url=page.url,
                    description=(
                        f"API failed: "
                        f"{api['url']} "
                        f"(HTTP {api['status']})"
                    )
                )
                status = api["status"]

                if 400 <= status < 500:

                    self._add_bug(
                        bug_type="API_4XX_ERROR",
                        severity="HIGH",
                        page_url=page.url,
                        description=(
                            f"Client Error {status}: "
                            f"{api['url']}"
                        )
                    )
                elif status >= 500:

                    self._add_bug(
                        bug_type="API_5XX_ERROR",
                        severity="CRITICAL",
                        page_url=page.url,
                        description=(
                            f"Server Error {status}: "
                            f"{api['url']}"
                        )
                    )
                if api["status"] in [401, 403]:

                    self._add_bug(
                    bug_type="AUTH_API_FAILURE",
                    severity="CRITICAL",
                    page_url=page.url,
                    description=(
                        f"Authentication failure "
                        f"{api['status']} "
                        f"on "
                        f"{api['url']}"
                    )
                )
            for api in self.slow_api_calls:

                severity = "MEDIUM"

                if api["duration"] > 5000:
                    severity = "HIGH"

                self._add_bug(
                    bug_type="SLOW_API_RESPONSE",
                    severity=severity,
                    page_url=page.url,
                    description=(
                        f"Slow API response "
                        f"{api['duration']}ms "
                        f"for "
                        f"{api['url']}"
                    )
                )
            seen_excessive = set()

            for url, count in self.api_request_counter.items():

                if url in seen_excessive:
                    continue

                seen_excessive.add(url)

                if count >= 15:

                    self._add_bug(
                        bug_type="EXCESSIVE_API_CALLS",
                        severity="HIGH",
                        page_url=page.url,
                        description=(
                            f"{count} requests "
                            f"made to "
                            f"{url}"
                        )
                    )
            seen_payloads = set()

            for payload in self.large_payloads:

                key = payload["url"]

                if key in seen_payloads:
                    continue

                seen_payloads.add(key)

                self._add_bug(
                    bug_type="LARGE_PAYLOAD_RESPONSE",
                    severity="MEDIUM",
                    page_url=page.url,
                    description=(
                        f"Payload size "
                        f"{payload['size']} bytes "
                        f"from "
                        f"{payload['url']}"
                    )
                )
            seen_mixed = set()

            for url in self.mixed_content:

                if url in seen_mixed:
                    continue

                seen_mixed.add(url)

                self._add_bug(...)
            seen_network_errors = set()
            if failed_network_requests:
                logger.info(
                    f"FAILED NETWORK COUNT: {len(failed_network_requests)}"
                )
            for network_error in failed_network_requests:

                key = (
                    network_error["url"],
                    network_error["error"]
                )

                if key in seen_network_errors:
                    continue

                seen_network_errors.add(key)
                error_text = (
                    network_error["error"]
                ).lower()

                severity = "HIGH"

                if "timed_out" in error_text:
                    severity = "MEDIUM"

                if "aborted" in error_text:
                    severity = "LOW"

                self._add_bug(
                    bug_type="NETWORK_FAILURE",
                    severity=severity,
                    page_url=page.url,
                    description=(
                        f"{network_error['error']} "
                        f"on "
                        f"{network_error['url']}"
                    )
                )
                if "cors" in error_text:

                    self._add_bug(
                        bug_type="CORS_FAILURE",
                        severity="HIGH",
                        page_url=page.url,
                        description=(
                            f"CORS blocked request: "
                            f"{network_error['url']}"
                        )
                    )
            from urllib.parse import urlparse

            current_domain = urlparse(
                page.url
            ).netloc

            base_domain = urlparse(
                self.start_url
            ).netloc

            if current_domain == base_domain:
                seen_js_errors = set()
                
                for error in page_errors:
                    error_message = error.get("message", "")
                    error_stack = error.get("stack", "")
                    file_name = "Unknown"
                    line_number = "Unknown"
                    column_number = "Unknown"
                    import re
                    match = re.search(
                        r'([^\s]+(?:\.js|<anonymous>)):(\d+):(\d+)',
                        error_stack
                    )
                    if match:
                        file_name = match.group(1)
                        line_number = match.group(2)
                        column_number = match.group(3)
                    if error_message in seen_js_errors:
                        continue

                    seen_js_errors.add(error_message)
                    self._add_bug(
                        bug_type="JS_ERROR",
                        severity="CRITICAL",
                        page_url=page.url,
                        description=(
                            f"Runtime Exception: {error_message[:500]}"
                            f"\nFile: {file_name}"
                            f"\nLine: {line_number}"
                            f"\nColumn: {column_number}"
                            f"\nStack: {error_stack[:1000]}"
                        )
                    )
                    
                for error in browser_js_errors:
                    error_message = str(error)

                    if error_message in seen_js_errors:
                        continue

                    seen_js_errors.add(error_message)

                    self._add_bug(
                        bug_type="JS_ERROR",
                        severity="HIGH",
                        page_url=page.url,
                        description=str(error)[:500],
                    )
                for error in console_errors:
                    error_message = str(error)

                    if error_message in seen_js_errors:
                        continue

                    seen_js_errors.add(error_message)
                    error_text = str(error).lower()

                    if (
                        "failed to load resource" in error_text
                        and any(
                            status in error_text
                            for status in [
                                "400",
                                "401",
                                "403",
                                "404",
                                "409",
                                "500",
                                "502",
                                "503"
                            ]
                        )
                    ):
                        continue

                    self._add_bug(
                        bug_type="JS_ERROR",
                        severity="HIGH",
                        page_url=page.url,
                        description=f"Console Error: {error_message[:500]}",
                    )
            if response and response.status >= 400:

                self._add_bug(
                    bug_type="HTTP_ERROR",
                    severity="HIGH",
                    page_url=url,
                    description=f"HTTP Status {response.status}"
                )
            # Set up auth if provided
            if auth_config and not self.is_authenticated:

                await self._perform_login(
                    page,
                    auth_config,
                )
            status_code = response.status if response else 200

            # Skip error pages, assets, and binary files
            if status_code >= 400:
                logger.debug(f"Skip {url} — status {status_code}")
                return None

            # Wait for JS frameworks to hydrate
            await page.wait_for_timeout(800)
            await self._wait_for_spa_ready(page)

            load_time_ms = int((time.time() - start) * 1000)
            title = await page.title()
            # Smart click exploration
            # Smart click exploration
            try:

                clickable_elements = await page.query_selector_all(
                    """
                    a[href],
                    button,
                    input[type='submit'],
                    input[type='button']
                    """
                )
            except Exception as e:

                logger.warning(
                    f"CLICKABLE EXTRACTION FAILED: {e}"
                )

                clickable_elements = []
            for i in range(
                min(len(clickable_elements), 10)
            ):

                try:
                    try:

                        await page.wait_for_load_state(
                            "domcontentloaded",
                            timeout=3000
                        )

                    except:
                        pass

                    # re-fetch fresh element
                    try:

                        clickable_elements = (
                            await page.query_selector_all(
                                """
                                a[href],
                                button,
                                input[type='submit'],
                                input[type='button']
                                """
                            )
                        )

                    except Exception as e:

                        if (
                            "Execution context was destroyed"
                            in str(e)
                        ):

                            logger.info(
                                "PAGE NAVIGATING - SKIPPING ITERATION"
                            )

                            continue

                        raise

                    if i >= len(clickable_elements):
                        continue

                    element = clickable_elements[i]
                    try:
                        await element.scroll_into_view_if_needed()
                    except:
                        continue
                    try:
                        is_visible = await element.is_visible()
                    except:
                        continue

                    if not is_visible:
                        continue

                    try:

                        text = (
                            await element.text_content()
                            or "UNKNOWN"
                        ).strip()

                    except:
                        text = "UNKNOWN"

        # skip useless elements
                    bad_texts = [
                        "",
                        "unknown",
                        "skip to content",
                        'press "enter" to skip to content'
                    ]

                    if text.lower().strip() in bad_texts:
                        continue

                    previous_url = page.url
                    path_key = text.lower().strip()

                    if path_key in self.explored_paths:

                        continue

                    self.explored_paths.add(path_key)
                    if text.startswith("http"):
                        continue
                    logout_keywords = [
                        "logout",
                        "log out",
                        "sign out",
                        "signout",
                        "exit"
                    ]

                    if any(
                        keyword in text.lower()
                        for keyword in logout_keywords
                    ):
                        continue
                    logger.info(
                        f"EXPLORING CLICKABLE: {text}"
                    )

                    try:

                        await element.scroll_into_view_if_needed()

                    except:
                        pass

                    try:
                        href = await element.get_attribute(
                            "href"
                        )

                        if href:

                            from urllib.parse import (
                                urljoin,
                                urlparse
                            )

                            target_url = urljoin(
                                page.url,
                                href
                            )

                            base_domain = urlparse(
                                self.start_url
                            ).netloc

                            target_domain = urlparse(
                                target_url
                            ).netloc

                            if (
                                target_domain
                                and target_domain != base_domain
                            ):
                                continue

                        await element.scroll_into_view_if_needed()

                        await page.wait_for_timeout(300)

                        await element.click(
                            timeout=5000,
                            no_wait_after=True
                        )

                    except Exception as click_error:

                        logger.warning(
                            f"CLICK FAILED: {click_error}"
                        )

                        continue

                    try:

                        await page.wait_for_load_state(
                            "domcontentloaded",
                            timeout=4000
                        )

                    except:
                        pass

                    try:
                        await page.wait_for_load_state(
                            "networkidle",
                            timeout=2000
                        )
                    except:
                        pass

                    new_url = page.url
                    try:
                        await page.wait_for_load_state(
                            "domcontentloaded",
                            timeout=5000
                        )

                    except:
                        pass

                    await page.wait_for_timeout(1000)
                    if page.is_closed():
                        continue
                    if new_url == previous_url:
                        logger.info(
                            f"SAME PAGE CLICK SKIPPED: {text}"
                        )
                        await page.wait_for_timeout(1500)
                        continue
                    from urllib.parse import urlparse

                    base_domain = urlparse(
                        self.start_url
                    ).netloc

                    new_domain = urlparse(
                        new_url
                    ).netloc

                    if (
                        new_domain
                        and new_domain != base_domain
                    ):

                        logger.info(
                            f"EXTERNAL DOMAIN BLOCKED: {new_url}"
                        )

                        await page.go_back()

                        continue

                    self.navigation_graph.append({
                        "from": previous_url,
                        "to": new_url,
                        "action": text,
                    })

                    logger.info(
                        f"WORKFLOW PATH: "
                        f"{previous_url} -> {new_url}"
                    )

                    logger.info(
                        f"CLICK SUCCESS: {text}"
                    )

                except Exception as e:

                    logger.warning(
                        f"EXPLORATION FAILED: {e}"
                    )
            try:

                await page.wait_for_load_state(
                    "domcontentloaded",
                    timeout=5000
                )

            except:
                pass

            try:

                await page.wait_for_load_state(
                    "networkidle",
                    timeout=3000
                )

            except:
                pass

            await page.wait_for_timeout(500)

            # Extract all interactive elements
            try:
                elements = await self._extract_elements(page)
            except Exception:
                elements = []
            try:
                forms = await self._extract_forms(page)
            except Exception:
                forms = []
            try:
                if page.url not in self.accessibility_scanned_urls:
                    self.accessibility_scanned_urls.add(
                        page.url
                    )
                    await self._run_accessibility_checks(
                        page
                    )
                    await self._run_uiux_checks(
                        page
                    )
                    await self._run_performance_checks(
                        page
                    )
                    await self._run_visual_checks(
                        page
                    )
            except Exception as e:
                logger.warning(
                    f"ACCESSIBILITY CHECK FAILED: {e}"
                )
            try:
                links = await self._extract_links(page, url)
            except Exception:
                links = []
            try:
                framework = await self._detect_page_framework(page)
            except Exception:
                framework = "Unknown"
            page_type = self._classify_page(url, title, elements, forms)

            # Screenshot (compressed, small)
            screenshot_b64 = None
            try:
                screenshot_bytes = await page.screenshot(
                    type="jpeg", quality=50,
                    clip={"x": 0, "y": 0, "width": 1280, "height": 800}
                )
                import base64
                screenshot_b64 = base64.b64encode(screenshot_bytes).decode()
            except Exception:
                pass

            return CrawledPage(
                url=url,
                title=title,
                status_code=status_code,
                page_type=page_type,
                depth=depth,
                elements=elements,
                forms=forms,
                links_found=links,
                screenshot_base64=screenshot_b64,
                load_time_ms=load_time_ms,
                framework_detected=framework,
                meta={"depth": depth, "element_count": len(elements)},
            )

        except Exception as e:
            logger.warning(f"Error analyzing {url}: {e}")
            self.errors.append(f"analyze:{url}:{str(e)}")
            return None
        finally:
            await page.close()

    async def _extract_elements(self, page) -> List[Dict]:
        """Extract interactive elements from page."""
        try:

            await page.wait_for_load_state(
                "domcontentloaded",
                timeout=3000
            )

        except:
            pass

        try:

            await page.wait_for_load_state(
                "networkidle",
                timeout=1000
            )
        except:
            pass

        try:

            raw = await page.evaluate("""
            () => {
                const selectors = `
                    button,
                    input,
                    select,
                    textarea,
                    form,
                    a[href],
                    [role="button"],
                    [type="submit"],
                    [aria-expanded]
                `;

                return Array.from(
                    document.querySelectorAll(selectors)
                ).slice(0, 200).map(el => ({
                    tag: el.tagName.toLowerCase(),

                    text: (
                        el.innerText ||
                        el.textContent ||
                        el.value ||
                        el.getAttribute('aria-label') ||
                        ''
                    ).trim(),

                    type: el.type || null,

                    placeholder:
                        el.placeholder ||
                        el.getAttribute('aria-label') ||
                        null,

                    href: el.href || null,

                    id: el.id || null,

                    name: el.name || null,

                    role: el.getAttribute('role') || null,

                    action: el.getAttribute('action') || null,

                    visible: !!(
                        el.offsetWidth ||
                        el.offsetHeight ||
                        el.getClientRects().length
                    )
                }));
            }
            """)

        except Exception as e:

            logger.warning(
                f"ELEMENT EXTRACTION FAILED: {e}"
            )

            raw = []
        elements = []
        forms_detected = 0
        inputs_detected = 0
        buttons_detected = 0

        for el in raw or []:

            if not el.get("visible"):
                continue
            if el.get("tag") == "form":
                forms_detected += 1

            if el.get("tag") == "input":
                inputs_detected += 1

            if el.get("tag") == "button":
                buttons_detected += 1

            elements.append({
                "element_type": el.get("tag"),
                "selector": (
                    f"#{el.get('id')}"
                    if el.get("id")
                    else el.get("tag")
                ),
                "tag": el.get("tag"),
                "text": el.get("text"),
                "type": el.get("type"),
                "placeholder": el.get("placeholder"),
                "href": el.get("href"),
                "id": el.get("id"),
                "name": el.get("name"),
            })
        logger.info(
            f"FORMS={forms_detected} "
            f"INPUTS={inputs_detected} "
            f"BUTTONS={buttons_detected}"
        )

        return elements


    def _score_page(self, url: str):

        score = 0

        important = [
            "dashboard",
            "checkout",
            "login",
            "settings",
            "admin",
        ]

        for word in important:

            if word in url.lower():
                score += 10

        return score

    async def _extract_forms(self, page: Page) -> List[Dict]:
        """Extract all forms with their fields."""
        try:

            forms = await page.evaluate("""
            () => {
                return Array.from(document.querySelectorAll('form')).map(form => {
                    const fields = Array.from(
                        form.querySelectorAll(
                            'input, select, textarea'
                        )
                    ).map(f => ({
                        name: f.name || f.id || null,
                        type: f.type || 'text',
                        placeholder: f.placeholder || null,
                        required: f.required,
                        options: f.tagName === 'SELECT'
                            ? Array.from(f.options).map(o => o.text)
                            : null,
                    }));

                    const submitBtn = form.querySelector(
                        'button[type="submit"], input[type="submit"], button:last-child'
                    );

                    return {
                        action: form.action || null,
                        method: form.method || 'GET',
                        id: form.id || null,
                        fields: fields,
                        submit_text: submitBtn
                            ? (submitBtn.textContent || '').trim()
                            : null,
                        field_count: fields.length,
                    };
                });
            }
            """)

        except Exception as e:

            logger.warning(
                f"FORM EXTRACTION FAILED: {e}"
            )

            forms = []

        return forms or []

    async def _extract_links(self, page: Page, current_url: str) -> List[str]:
        """Extract all internal links for crawl queue."""
        try:

            hrefs = await page.evaluate("""
            () => Array.from(
                document.querySelectorAll('a[href]')
            ).map(a => a.href)
            """)

        except Exception as e:

            logger.warning(
                f"HREF EXTRACTION FAILED: {e}"
            )

            hrefs = []

        base = urlparse(current_url)
        links = []
        for href in (hrefs or []):
            try:
                parsed = urlparse(href)
                # Only same-domain HTTP links, no anchors/JS/mailto
                if (parsed.scheme in ("http", "https") and
                    parsed.netloc == base.netloc and
                    not href.startswith("javascript:") and
                    "#" not in href.split("?")[0]):
                    # Remove fragments
                    clean = href.split("#")[0]
                    links.append(clean)
            except Exception:
                pass

        return list(dict.fromkeys(links))[:30]  # Dedupe, limit
    
    async def _run_accessibility_checks(
        self,
        page
    ):   #phase 1
        await self._detect_missing_alt_text(page)
        await self._detect_missing_labels(page)
        await self._detect_empty_buttons(page)
        await self._detect_empty_links(page)
        await self._detect_missing_aria(page)
        await self._detect_missing_h1(page)
        await self._detect_missing_lang(page)
        await self._detect_duplicate_ids(page)

        # phase 2
        await self._detect_color_contrast(page)
        await self._detect_focus_visible(page)
        await self._detect_tab_order(page)
        await self._detect_keyboard_trap(page)
        await self._detect_skip_link(page)
        await self._detect_form_error_association(page)

        #phase 3
        await self._detect_heading_hierarchy(page)
        await self._detect_page_title(page)
        await self._detect_landmarks(page)
        await self._detect_iframe_title(page)
        await self._detect_dialog_accessibility(page)
        await self._detect_table_headers(page)
        await self._detect_aria_role_validation(page)
        await self._detect_touch_target_size(page)
        await self._detect_link_purpose(page)
        await self._detect_region_labels(page)
        await self._detect_autocomplete(page)
        await self._detect_form_grouping(page)
        await self._detect_required_field_indication(page)
        await self._detect_media_captions(page)
        await self._detect_audio_transcript(page)

    async def _detect_missing_alt_text(
        self,
        page
    ):

        try:

            images = await page.evaluate("""
            () => {
                return Array.from(
                    document.querySelectorAll("img")
                )
                .filter(img => {

                    const alt =
                        img.getAttribute(
                            "alt"
                        );

                    return (
                        alt === null ||
                        alt.trim() === ""
                    );
                })
                .map(img => ({
                    src: img.src
                }));
            }
            """)
            logger.info(
                f"MISSING ALT COUNT: {len(images)}"
            )

            for img in images:
                logger.info(
                    f"BUG DESCRIPTION: "
                    f"Image missing alt text: "
                    f"{img['src']}"
                )
                self._add_bug(
                    bug_type="ACCESSIBILITY_MISSING_ALT",
                    severity="HIGH",
                    page_url=page.url,
                    description=(
                        f"Image missing alt text: "
                        f"{img['src']}"
                    )
                )

        except Exception as e:

            logger.warning(
                f"MISSING ALT CHECK FAILED: {e}"
            )
    async def _detect_missing_labels(
        self,
        page
    ):

        try:

            inputs = await page.evaluate("""
            () => {

                return Array.from(
                    document.querySelectorAll(
                        "input:not([type='hidden']), textarea, select"
                    )
                )
                .filter(el => {

                    const id = el.id;

                    const hasLabel =
                        id &&
                        document.querySelector(
                            `label[for="${id}"]`
                        );
                    const hasWrappedLabel =
                        el.closest("label");
                    const hasNearbyLabel =
                        !!(
                            el.parentElement?.querySelector(
                                "label"
                            ) ||
                            el.closest("div")?.querySelector(
                                "label"
                            )
                        );
                    const ariaLabel =
                        el.getAttribute(
                            "aria-label"
                        );

                    const ariaLabelledBy =
                        el.getAttribute(
                            "aria-labelledby"
                        );

                    if (
                        ariaLabel ||
                        ariaLabelledBy
                    ) {
                        return false;
                    }
                    const placeholder =
                        el.placeholder || "";
                    const previousLabel =
                        el.previousElementSibling &&
                        el.previousElementSibling.tagName === "LABEL";

                    const closestFormGroup =
                        el.closest(
                            ".form-group, .input-group, .oxd-input-group"
                        );

                    const groupLabel =
                        closestFormGroup?.querySelector(
                            "label"
                        );
                    if (
                        ["submit", "button", "hidden"]
                        .includes(el.type)
                    ) {
                        return false;
                    }
                    return (
                        !hasLabel &&
                        !hasWrappedLabel &&
                        !hasNearbyLabel &&
                        !previousLabel &&
                        !groupLabel &&
                        placeholder.trim() === "" &&
                        placeholder.toLowerCase() !== "search" &&
                        !el.hasAttribute(
                            "aria-label"
                        ) &&
                        !el.hasAttribute(
                            "aria-labelledby"
                        )
                    );
                })
                .map(input => ({
                    id: input.id || "",
                    name: input.name || "",
                    placeholder: input.placeholder || "",
                    type: input.type || ""
                }));
            }
            """)

            if inputs:

                logger.warning(
                    f"MISSING LABEL COUNT: "
                    f"{len(inputs)} | "
                    f"{page.url}"
                )

                for item in inputs:
                    description = (
                        f"Input missing label | "
                        f"id={item['id']} | "
                        f"name={item['name']} | "
                        f"placeholder={item['placeholder']} | "
                        f"type={item['type']}"
                    )
                    logger.info(
                        f"BUG DESCRIPTION: {description}"
                    )
                    self._add_bug(
                        bug_type=
                        "ACCESSIBILITY_MISSING_LABEL",
                        severity="HIGH",
                        page_url=page.url,
                        description=description
                    )
        except Exception as e:

            logger.warning(
                f"MISSING LABEL CHECK FAILED: {e}"
            )
    async def _detect_empty_buttons(
        self,
        page
    ):
        try:

            buttons = await page.evaluate("""
            () => {

                return Array.from(
                    document.querySelectorAll(
                        "button"
                    )
                )
                .filter(btn => {

                    const text =
                        btn.innerText.trim();

                    const aria =
                        btn.getAttribute(
                            "aria-label"
                        );

                    const title =
                        btn.getAttribute(
                            "title"
                        );
                    const hasSvg =
                        btn.querySelector(
                            "svg"
                        );

                    const hasImg =
                        btn.querySelector(
                            "img"
                        );

                    const hasIcon =
                        btn.querySelector(
                            "i"
                        );
                    return (
                        text.length === 0 &&
                        !aria &&
                        !title &&
                        !hasSvg &&
                        !hasImg &&
                        !hasIcon
                    );
                })
                .map(btn => ({
                    id: btn.id || "",
                    className: btn.className || ""
                }));
            }
            """)
            logger.info(
                f"EMPTY BUTTON COUNT: {len(buttons)}"
            )
            if buttons:
                for item in buttons:
                    description = (
                        f"Empty button detected | "
                        f"id={item['id']} | "
                        f"class={item['className']}"
                    )
                    logger.info(
                        f"BUG DESCRIPTION: {description}"
                    )
                    self._add_bug(
                        bug_type=
                        "ACCESSIBILITY_EMPTY_BUTTON",
                        severity="HIGH",
                        page_url=page.url,
                        description=description
                    )

        except Exception as e:

            logger.warning(
                f"EMPTY BUTTON CHECK FAILED: {e}"
            )

    async def _detect_empty_links(
        self,
        page
    ):
        logger.info(
            "RUNNING EMPTY LINK DETECTOR"
        )
        
        try:

            links = await page.evaluate("""
            () => {

                return Array.from(
                    document.querySelectorAll(
                        "a"
                    )
                )
                .filter(link => {

                    const text =
                        link.innerText.trim();

                    const aria =
                        link.getAttribute(
                            "aria-label"
                        );

                    const title =
                        link.getAttribute(
                            "title"
                        );

                    const hasImg =
                        link.querySelector(
                            "img"
                        );

                    const hasSvg =
                        link.querySelector(
                            "svg"
                        );

                    return (
                        text.length === 0 &&
                        !aria &&
                        !title &&
                        !hasImg &&
                        !hasSvg
                    );
                })
                .map(link => ({
                    href: link.href || "",
                    id: link.id || ""
                }));
            }
            """)
            logger.info(
                f"EMPTY LINK COUNT: {len(links)}"
            )

            if links:

                for item in links:
                    description = (
                        f"Empty link detected | "
                        f"href={item['href']} | "
                        f"id={item['id']}"
                    )
                    logger.info(
                        f"BUG DESCRIPTION: {description}"
                    )
                    self._add_bug(
                        bug_type=
                        "ACCESSIBILITY_EMPTY_LINK",
                        severity="HIGH",
                        page_url=page.url,
                        description=description
                    )

        except Exception as e:

            logger.warning(
                f"EMPTY LINK CHECK FAILED: {e}"
            )

    async def _detect_missing_aria(
        self,
        page
    ):
        try:

            elements = await page.evaluate("""
            () => {

                return Array.from(
                    document.querySelectorAll(
                        `
                        button,
                        a,
                        input,
                        select,
                        textarea
                        `
                    )
                )
                .filter(el => {

                    const aria =
                        el.getAttribute(
                            "aria-label"
                        );

                    const title =
                        el.getAttribute(
                            "title"
                        );
                    const ariaLabelledBy =
                        el.getAttribute(
                            "aria-labelledby"
                        );

                    const text =
                        (
                            el.innerText ||
                            el.value ||
                            ""
                        ).trim();
                    if (
                        text.length > 0
                    ) {
                        return false;
                    }
                    const role =
                        el.getAttribute(
                            "role"
                        );

                    if (
                        role === "presentation" ||
                        role === "none"
                    ) {
                        return false;
                    }
                    const ariaHidden =
                        el.getAttribute(
                            "aria-hidden"
                        );

                    if (
                        ariaHidden === "true"
                    ) {
                        return false;
                    }

                    const hasIcon =
                        el.querySelector?.(
                            `
                            svg,
                            img,
                            i,
                            .icon,
                            [class*="icon"]
                            `
                        );
                    const parentButton =
                        el.closest(
                            "button"
                        );

                    if (
                        parentButton &&
                        el.tagName === "A"
                    ) {
                        return false;
                    }
                    const accessibleText =
                        (
                            el.textContent ||
                            ""
                        ).trim();

                    if (
                        accessibleText.length > 0
                    ) {
                        return false;
                    }
                    const hasSvg =
                        el.querySelector(
                            "svg,img"
                        );

                    if (
                        hasSvg
                    ) {
                        return false;
                    }
                    const disabled =
                        el.disabled;

                    if (
                        disabled
                    ) {
                        return false;
                    }

                    const hidden =
                        el.offsetParent === null;

                    if (
                        hidden
                    ) {
                        return false;
                    }
                    if (
                        role === "button" ||
                        role === "link"
                    ) {
                        return false;
                    }
                    return (
                        !aria &&
                        !ariaLabelledBy &&
                        !title &&
                        text.length === 0 &&                                          
                        hasIcon
                    );
                })
                .map(el => ({
                    tag: el.tagName,
                    id: el.id || "",
                    className: el.className || "",
                    outerHTML:
                        el.outerHTML.substring(
                            0,
                            200
                        )
                    }));
                }
                """)

            if elements:

                logger.warning(
                    f"MISSING ARIA COUNT: "
                    f"{len(elements)} | "
                    f"{page.url}"
                )
                severity = (
                    "HIGH"
                    if len(elements) >= 5
                    else "MEDIUM"
                )
                seen_aria = set()
                for item in elements:
                    key = (
                        item["tag"],
                        item["className"],
                        item["id"]
                    )

                    if key in seen_aria:
                        continue

                    seen_aria.add(key)
                    logger.info(
                        f"MISSING ARIA DETAILS | "
                        f"tag={item['tag']} | "
                        f"id={item['id']} | "
                        f"class={item['className']}"
                    )
                    logger.info(
                        f"MISSING ARIA HTML: "
                        f"{item['outerHTML']}"
                    )
                    description = (
                        f"Missing aria-label | "
                        f"tag={item['tag']} | "
                        f"id={item['id']}"
                    )

                    logger.info(
                        f"BUG DESCRIPTION: {description}"
                    )
                    self._add_bug(
                        bug_type=
                        "ACCESSIBILITY_MISSING_ARIA",
                        severity=severity,
                        page_url=page.url,
                        description=description
                    )

        except Exception as e:

            logger.warning(
                f"MISSING ARIA CHECK FAILED: {e}"
            )

    async def _detect_missing_h1(
        self,
        page
    ):
        try:

            h1_count = await page.locator(
                "h1"
            ).count()

            heading_count = await page.locator(
                """
                h1,
                [role='heading'][aria-level='1'],
                .page-title,
                .page-header,
                .oxd-topbar-header-title
                """
            ).count()

            h2_count = await page.locator(
                "h2"
            ).count()

            if heading_count == 0:

                logger.warning(
                    f"MISSING H1: {page.url}"
                )

                title = await page.title()
 
                description = (
                    f"Page missing primary heading | "
                    f"title={title}"
                )

                logger.info(
                    f"BUG DESCRIPTION: {description}"
                )

                self._add_bug(
                    bug_type=
                    "ACCESSIBILITY_MISSING_H1",
                    severity="LOW",
                    page_url=page.url,
                    description=description
                )

            elif h1_count > 1:

                logger.warning(
                    f"MULTIPLE H1 COUNT: "
                    f"{h1_count} | {page.url}"
                )

                title = await page.title()

                description = (
                    f"Multiple H1 headings found | "
                    f"title={title} | "
                    f"count={h1_count}"
                )

                logger.info(
                    f"BUG DESCRIPTION: {description}"
                )

                self._add_bug(
                    bug_type=
                    "ACCESSIBILITY_MULTIPLE_H1",
                    severity="LOW",
                    page_url=page.url,
                    description=description
                )

        except Exception as e:

            logger.warning(
                f"MISSING H1 CHECK FAILED: {e}"
            )

    async def _detect_missing_lang(
        self,
        page
    ):

        try:

            lang = await page.evaluate("""
            () => {
                return (
                    document.documentElement
                        .getAttribute("lang")
                );
            }
            """)

            if not lang:

                logger.warning(
                    f"MISSING LANG: {page.url}"
                )
                description = (
                    "HTML lang attribute missing"
                )
                logger.info(
                    f"BUG DESCRIPTION: {description}"
                )
                self._add_bug(
                    bug_type=
                    "ACCESSIBILITY_MISSING_LANG",
                    severity="MEDIUM",
                    page_url=page.url,
                    description=description
                )

        except Exception as e:

            logger.warning(
                f"MISSING LANG CHECK FAILED: {e}"
            )
    async def _detect_duplicate_ids(
        self,
        page
    ):

        try:

            duplicate_ids = await page.evaluate("""
            () => {

                const ids = {};

                document
                    .querySelectorAll("[id]")
                    .forEach(el => {

                        const id = el.id;
                        const tag =
                            el.tagName
                                ?.toLowerCase();
                        if (
                            [
                                "svg",
                                "path",
                                "g",
                                "defs",
                                "clippath",
                                "mask",
                                "symbol",
                                "use",
                                "lineargradient",
                                "radialgradient",
                                "filter",
                                "pattern",
                                "marker"
                            ].includes(tag)
                        ) {
                            return;
                        }
                        if (
                            el.closest("svg")
                        ) {
                            return;
                        }
                        if (!id) {
                            return;
                        }

                        ids[id] =
                            (ids[id] || 0) + 1;
                    });

                return Object.entries(ids)
                    .filter(
                        ([_, count]) =>
                            count > 1
                    )
                    .map(
                        ([id, count]) => ({
                            id,
                            count
                        })
                    );
            }
            """)

            if duplicate_ids:

                logger.warning(
                    f"DUPLICATE ID COUNT: "
                    f"{len(duplicate_ids)} | "
                    f"{page.url}"
                )

                severity = (
                    "HIGH"
                    if len(duplicate_ids) >= 5
                    else "MEDIUM"
                )

                for item in duplicate_ids:
                    description = (
                        f"Duplicate ID detected | "
                        f"id={item['id']} | "
                        f"count={item['count']}"
                    )

                    logger.info(
                        f"BUG DESCRIPTION: {description}"
                    )
                    self._add_bug(
                        bug_type=
                        "ACCESSIBILITY_DUPLICATE_ID",
                        severity=severity,
                        page_url=page.url,
                        description= description
                    )
        except Exception as e:

            logger.warning(
                f"DUPLICATE ID CHECK FAILED: {e}"
            )
    async def _detect_color_contrast(
        self,
        page
    ):

        try:

            logger.info(
                f"RUNNING COLOR CONTRAST CHECK: {page.url}"
            )
            issues = await page.evaluate("""
            () => {

                function parseRGB(color) {

                    if (!color) return null;

                    const match = color.match(
                        /rgba?\\((\\d+),\\s*(\\d+),\\s*(\\d+)/
                    );

                    if (!match) {
                        return null;
                    }
                    return [
                        parseInt(match[1]),
                        parseInt(match[2]),
                        parseInt(match[3])
                    ];
                }

                function getEffectiveBackground(element) {

                    let current = element;

                    while (current) {

                        const bg =
                            getComputedStyle(
                                current
                            ).backgroundColor;

                        if (
                            bg &&
                            bg !== "transparent" &&
                            bg !== "rgba(0, 0, 0, 0)"
                        ) {
                            return bg;
                        }

                        current = current.parentElement;
                    }

                    const bodyBg =
                        getComputedStyle(
                            document.body
                        ).backgroundColor;

                    return (
                        bodyBg &&
                        bodyBg !== "transparent"
                    )
                        ? bodyBg
                        : "rgb(255,255,255)";
                    }

                function luminance(r,g,b) {

                    const values =
                        [r,g,b].map(v => {

                            v = v / 255;

                            return v <= 0.03928
                                ? v / 12.92
                                : Math.pow(
                                    (v + 0.055) / 1.055,
                                    2.4
                                );
                        });

                    return (
                        0.2126 * values[0] +
                        0.7152 * values[1] +
                        0.0722 * values[2]
                    );
                }

                function contrastRatio(fg,bg) {

                    const l1 =
                        luminance(
                            fg[0],
                            fg[1],
                            fg[2]
                        );
                    const l2 =
                        luminance(
                            bg[0],
                            bg[1],
                            bg[2]
                        );

                    const lighter =
                        Math.max(l1,l2);

                    const darker =
                        Math.min(l1,l2);

                    return (
                        (lighter + 0.05) /
                        (darker + 0.05)
                    );
                }

                const results = [];

                const elements =
                    Array.from(
                        document.querySelectorAll(
                            `
                            p,
                            label,
                            a,
                            button,
                            h1,
                            h2,
                            h3,
                            h4,
                            h5,
                            h6,
                            td,
                            th,
                            small,
                            strong
                            `
                        )
                    );

                elements.forEach(el => {

                    const text =
                        (
                            el.innerText || ""
                        ).trim();
                    if (
                        /^\\d{4}-\\d{2}-\\d{2}/
                            .test(text)
                    ) {
                        return;
                    }
                    
                    if (
                        text.includes("©") ||
                        text.includes("All rights reserved")
                    ) {
                        return;
                    }
                    if (
                        !text ||
                        text.length < 2
                    ) {
                        return;
                    }
                    const navParent =
                        el.closest(
                            "nav, .menu, .sidebar"
                        );

                    if (navParent) {
                        return;
                    }

                    const style =
                        getComputedStyle(el);
                    
                    if (
                        el.disabled
                    ) {
                        return;
                    }
                    

                    if (
                        el.getAttribute("aria-hidden") === "true"
                    ) {
                        return;
                    }

                    if (
                        style.display === "none" ||
                        style.visibility === "hidden"
                    ) {
                        return;
                    }
                    const rect =
                        el.getBoundingClientRect();

                    if(
                        rect.width === 0 ||
                        rect.height === 0
                    ) {
                        return;
                    }

                    const fontSize =
                        parseFloat(
                            style.fontSize
                        );
                    if (
                        fontSize < 10
                    ) {
                        return;
                    }

                    const fontWeight =
                        parseInt(
                            style.fontWeight
                        ) || 400;

                    const fg =
                        parseRGB(
                            style.color
                        );

                    const bg =
                        parseRGB(
                            getEffectiveBackground(
                                el
                            )
                        );

                    if (
                        !fg ||
                        !bg
                    ) {
                        return;
                    }
                    if (
                        fg[0] === bg[0] &&
                        fg[1] === bg[1] &&
                        fg[2] === bg[2]
                    ) {
                        return;
                    }

                    const ratio =
                        contrastRatio(
                            fg,
                            bg
                        );

                    const isLargeText =
                        (
                            fontSize >= 24
                        ) ||
                        (
                            fontSize >= 18.66 &&
                            fontWeight >= 700
                        );

                    const required =
                        isLargeText
                        ? 3.0
                        : 4.5;

                    if (
                        ratio < required &&
                        ratio > 1.2 &&
                        (required - ratio) > 0.1
                    ){

                        const key =
                            el.tagName +
                            "|" +
                            text.substring(0, 50) +
                            "|" +
                            ratio.toFixed(2);

                        if (
                            !window.__jarviisContrastSeen
                        ) {
                            window.__jarviisContrastSeen =
                                new Set();
                        }

                        if (
                            window.__jarviisContrastSeen.has(
                                key
                            )
                        ) {
                            return;
                        }

                        window.__jarviisContrastSeen.add(
                            key
                        );
                        const hasSvg =
                            el.querySelector("svg,img");

                        if (
                            hasSvg &&
                            text.length < 15
                        ) {
                            return;
                        }
                        results.push({

                            text:
                                text.substring(
                                    0,
                                    120
                                ),

                            ratio:
                                ratio.toFixed(2),

                            required,

                            fontSize,

                            fontWeight,

                            foreground:
                                style.color,

                            background:
                                getEffectiveBackground(
                                    el
                                ),

                            tag:
                                el.tagName,

                            id:
                                el.id || ""
                        });
                    }
                });
                return results.slice(0, 15);
            }
            """)

            logger.info(
                f"COLOR CONTRAST COUNT: {len(issues)}"
            )

            for issue in issues:

                ratio = float(
                    issue["ratio"]
                )

                if ratio < 1.5:
                    severity = "CRITICAL"

                elif ratio < 2.5:
                    severity = "HIGH"

                elif ratio < 4:
                    severity = "MEDIUM"

                else:
                    severity = "LOW"

                description = (
                    f"Low color contrast detected | "
                    f"ratio={issue['ratio']} | "
                    f"required={issue['required']} | "
                    f"tag={issue['tag']} | "
                    f"id={issue['id']} | "
                    f"fontSize={issue['fontSize']} | "
                    f"text={issue['text']}"
                )

                logger.info(
                    f"BUG DESCRIPTION: {description}"
                )

                self._add_bug(
                    bug_type=
                    "ACCESSIBILITY_COLOR_CONTRAST",
                    severity=severity,
                    page_url=page.url,
                    description=description
                )

        except Exception as e:

            logger.warning(
                f"COLOR CONTRAST CHECK FAILED: {e}"
            )

    async def _detect_focus_visible(
        self,
        page
    ):

        try:

            logger.info(
                f"RUNNING FOCUS VISIBLE CHECK: {page.url}"
            )

            issues = await page.evaluate("""
            () => {

                const results = [];

                const elements =
                    Array.from(
                        document.querySelectorAll(
                            `
                            a,
                            button,
                            input,
                            select,
                            textarea,
                            [tabindex]
                            `
                        )
                    );

                elements.forEach(el => {

                    if (
                        el.disabled
                    ) {
                        return;
                    }

                    if (
                        el.getAttribute(
                            "tabindex"
                        ) === "-1"
                    ) {
                        return;
                    }

                    const style =
                        getComputedStyle(el);
                    const beforeBorderColor =
                        style.borderColor;
                    const beforeBackgroundColor =
                        style.backgroundColor;

                    if (
                        style.display === "none" ||
                        style.visibility === "hidden"
                    ) {
                        return;
                    }
                    el.focus();
                    const focusStyle =
                        getComputedStyle(el);
                    const outlineWidth =
                    parseFloat(
                        focusStyle.outlineWidth
                    ) || 0;
                    const outlineStyle =
                        focusStyle.outlineStyle;
                    const boxShadow =
                        focusStyle.boxShadow;
                    const hasOutline =
                        (
                            outlineWidth > 0 &&
                            outlineStyle !== "none"
                        );
                    const hasBoxShadow =
                        (
                            boxShadow &&
                            boxShadow !== "none"
                        );
                    const hasBorderChange =
                        (
                            focusStyle.borderColor !==
                            beforeBorderColor
                        );

                    const hasBackgroundChange =
                        (
                            focusStyle.backgroundColor !==
                            beforeBackgroundColor
                        );
                    const hasFocusIndicator =
                        hasOutline ||
                        hasBoxShadow ||
                        hasBorderChange ||
                        hasBackgroundChange;
                    if (
                        !hasFocusIndicator
                    ){
                                         
                        const text =
                            (
                                el.innerText ||
                                el.value ||
                                ""
                            ).trim();

                        const hasSvg =
                            el.querySelector(
                                "svg,img"
                            );

                        if (
                            hasSvg &&
                            text.length < 10
                        ) {
                            return;
                        }
                        if (
                            el.tagName === "DIV" &&
                            !el.hasAttribute(
                                "tabindex"
                            )
                        ) {
                            return;
                        }
                        if (
                            text === "-- Select --"
                        ) {
                            return;
                        }

                        if (
                            text.length === 0 &&
                            el.tagName === "BUTTON"
                        ) {
                            return;
                        }
                        if (
                            el.tagName === "BUTTON"
                        ) {
                            return;
                        }
                        if (
                            el.tagName === "DIV" &&
                            text.length > 0
                        ) {
                           return;
                        }
                        if (
                            el.tagName === "INPUT" &&
                            !el.value &&
                            el.placeholder
                        ) {
                            return;
                        }
                        results.push({

                            tag:
                                el.tagName,

                            id:
                                el.id || "",

                            text:
                                (
                                    el.innerText ||
                                    el.value ||
                                    ""
                                )
                                .trim()
                                .substring(
                                    0,
                                    50
                                )
                        });
                    }

                });

                return results.slice(
                    0,
                    20
                );
            }
            """)

            logger.info(
                f"FOCUS VISIBLE COUNT: {len(issues)}"
            )

            for issue in issues:

                description = (
                    f"Focus indicator missing | "
                    f"tag={issue['tag']} | "
                    f"id={issue['id']} | "
                    f"text={issue['text']}"
                )

                logger.info(
                    f"BUG DESCRIPTION: {description}"
                )

                self._add_bug(

                    bug_type="ACCESSIBILITY_FOCUS_VISIBLE",
                    severity="HIGH",
                    page_url=page.url,
                    description=description
                )

        except Exception as e:

            logger.warning(
                f"FOCUS VISIBLE CHECK FAILED: {e}"
            )
    async def _detect_tab_order(
        self,
        page
    ):

        try:

            logger.info(
                f"RUNNING TAB ORDER CHECK: {page.url}"
            )

            issues = await page.evaluate("""
            () => {

                const results = [];
                const elements =
                    Array.from(
                        document.querySelectorAll(
                            `
                            a,
                            button,
                            input,
                            select,
                            textarea,
                            [tabindex]
                            `
                        )
                    );

                const focusable =
                    elements.filter(el => {

                        const style =
                            getComputedStyle(el);

                        if (
                            style.display === "none" ||
                            style.visibility === "hidden"
                        ) {
                            return false;
                        }

                        if (
                            el.disabled
                        ) {
                            return false;
                        }

                        return true;
                    });

                focusable.forEach(
                    (el, index) => {

                        const tabindex =
                            parseInt(
                                el.getAttribute(
                                    "tabindex"
                                ) || "0"
                            );

                        if (
                            tabindex > 0
                        ) {

                            results.push({

                                tag:
                                    el.tagName,

                                id:
                                    el.id || "",

                                tabindex,

                                position:
                                    index,

                                text:
                                    (
                                        el.innerText ||
                                        el.value ||
                                        ""
                                    )
                                    .trim()
                                    .substring(
                                        0,
                                        50
                                    )
                            });
                        }
                    }
                );

                return results.slice(
                    0,
                    20
                );
            }
            """)

            logger.info(
                f"TAB ORDER COUNT: {len(issues)}"
            )

            for issue in issues:

                description = (
                    f"Custom tabindex detected | "
                    f"tag={issue['tag']} | "
                    f"id={issue['id']} | "
                    f"tabindex={issue['tabindex']} | "
                    f"text={issue['text']}"
                )

                logger.info(
                    f"BUG DESCRIPTION: {description}"
                )

                self._add_bug(

                    bug_type="ACCESSIBILITY_TAB_ORDER",
                    severity="MEDIUM",
                    page_url=page.url,
                    description=description
                )

        except Exception as e:

            logger.warning(
                f"TAB ORDER CHECK FAILED: {e}"
            )
    async def _detect_skip_link(
        self,
        page
    ):

        try:

            logger.info(
                f"RUNNING SKIP LINK CHECK: {page.url}"
            )

            result = await page.evaluate("""
            () => {

                const skipLink =
                    document.querySelector(
                        'a[href="#main"], a[href="#content"], a.skip-link'
                    );

                return !!skipLink;
            }
            """)

            if not result:

                self._add_bug(
                    bug_type="ACCESSIBILITY_SKIP_LINK",
                    severity="INFO",
                    page_url=page.url,
                    description="Skip navigation link not found"
                )

        except Exception as e:

            logger.warning(
                f"SKIP LINK CHECK FAILED: {e}"
            )
    async def _detect_form_error_association(
        self,
        page
    ):

        try:

            logger.info(
                f"RUNNING FORM ERROR ASSOCIATION CHECK: {page.url}"
            )

            issues = await page.evaluate("""
            () => {

                const results = [];

                const fields =
                    document.querySelectorAll(
                        'input,textarea,select'
                    );

                fields.forEach(field => {

                    const invalid =
                        field.getAttribute(
                            'aria-invalid'
                        ) === 'true';

                    if (!invalid) {
                        return;
                    }

                    const describedBy =
                        field.getAttribute(
                            'aria-describedby'
                        );

                    const errorMessage =
                        field.getAttribute(
                            'aria-errormessage'
                        );

                    if (
                        !describedBy &&
                        !errorMessage
                    ) {

                        results.push({

                            tag:
                                field.tagName,
                            id:
                                field.id || "",
                            name:
                                field.name || ""
                        });
                    }
                });

                return results;
            }
            """)

            logger.info(
                f"FORM ERROR ASSOCIATION COUNT: {len(issues)}"
            )

            for issue in issues:

                self._add_bug(

                    bug_type="ACCESSIBILITY_FORM_ERROR_ASSOCIATION",
                    severity="MEDIUM",
                    page_url=page.url,
                    description=
                    (
                        f"Validation error not associated "
                        f"with accessible error message | "
                        f"id={issue['id']} | "
                        f"name={issue['name']}"
                    )
                )

        except Exception as e:

            logger.warning(
                f"FORM ERROR ASSOCIATION CHECK FAILED: {e}"
            )
    async def _detect_keyboard_trap(
        self,
        page
    ):
        try:
            logger.info(
                f"KEYBOARD TRAP CHECK STARTED: {page.url}"
            )

            logger.info(
                f"RUNNING KEYBOARD TRAP CHECK: {page.url}"
            )

            focusable_count = await page.evaluate("""
            () => {

                const elements =
                    Array.from(
                        document.querySelectorAll(
                            `
                            a[href],
                            button,
                            input,
                            select,
                            textarea,
                            [tabindex]:not([tabindex="-1"])
                            `
                        )
                    );

                return elements
                    .filter(el => {

                        const style =
                            getComputedStyle(el);

                        return (
                            !el.disabled &&
                            style.display !== "none" &&
                            style.visibility !== "hidden"
                        );
                    })
                    .length;
            }
            """)
            logger.info(
                f"FOCUSABLE COUNT: {focusable_count}"
            )

            if focusable_count < 2:
                return

            first_focus = await page.evaluate("""
            () => {

                const elements =
                    Array.from(
                        document.querySelectorAll(
                            `
                            a[href],
                            button,
                            input,
                            select,
                            textarea,
                            [tabindex]:not([tabindex="-1"])
                            `
                        )
                    );

                const visible =
                    elements.filter(el => {

                        const style =
                            getComputedStyle(el);

                        return (
                            !el.disabled &&
                            style.display !== "none" &&
                            style.visibility !== "hidden"
                        );
                    });

                if (
                    visible.length === 0
                ) {
                    return null;
                }

                visible[0].focus();

                return (
                    document.activeElement?.outerHTML || ""
                );
            }
            """)
            logger.info(
                f"FIRST FOCUS CAPTURED"
            )

            for _ in range(
                min(
                    focusable_count + 5,
                    50
                )
            ):
                await page.keyboard.press(
                    "Tab"
                )

            final_focus = await page.evaluate("""
            () => {
                return (
                    document.activeElement?.outerHTML || ""
                );
            }
            """)
            logger.info(
                f"FINAL FOCUS CAPTURED"
            )
            if (
                focusable_count >= 15 and
                first_focus and
                final_focus and
                first_focus == final_focus
            ):

                description = (
                    "Potential keyboard trap detected | "
                    f"focusable_count={focusable_count}"
                )

                logger.warning(
                    description
                )

                self._add_bug(
                    bug_type=
                    "ACCESSIBILITY_KEYBOARD_TRAP",
                    severity="HIGH",
                    page_url=page.url,
                    description=description
                )

        except Exception as e:

            logger.warning(
                f"KEYBOARD TRAP CHECK FAILED: {e}"
            )
    async def _detect_heading_hierarchy(
        self,
        page
    ):
        try:

            logger.info(
                f"RUNNING HEADING HIERARCHY CHECK: {page.url}"
            )

            issues = await page.evaluate("""
            () => {

                const headings =
                    Array.from(
                        document.querySelectorAll(
                            "h1,h2,h3,h4,h5,h6"
                        )
                    );
 
                const results = [];

                let previous = 0;

                headings.forEach(h => {

                    const current =
                        parseInt(
                            h.tagName.substring(1)
                        );

                    if (
                        previous > 0 &&
                        current > previous + 1
                    ) {
                        results.push({

                            heading:
                                h.innerText
                                .trim()
                                .substring(0,100),

                            previous,

                            current
                       });
                    }

                    previous = current;
                });

                return results;
            }
            """)

            logger.info(
                f"HEADING HIERARCHY COUNT: {len(issues)}"
            )

            for issue in issues:

                description = (
                    f"Heading hierarchy skipped level | "
                    f"h{issue['previous']} -> "
                    f"h{issue['current']} | "
                    f"text={issue['heading']}"
                )

                self._add_bug(
                    bug_type=
                    "ACCESSIBILITY_HEADING_HIERARCHY",
                    severity="LOW",
                    page_url=page.url,
                    description=description
                )

        except Exception as e:

            logger.warning(
                f"HEADING HIERARCHY CHECK FAILED: {e}"
            )
    async def _detect_page_title(
        self,
        page
    ):
        try:

            logger.info(
                f"RUNNING PAGE TITLE CHECK: {page.url}"
            )

            title = await page.title()

            if (
                not title or
                len(title.strip()) < 3
            ):

                description = (
                    "Page title missing or empty"
                )

                self._add_bug(
                    bug_type=
                    "ACCESSIBILITY_PAGE_TITLE",
                    severity="HIGH",
                    page_url=page.url,
                    description=description
                )

            elif (
                title.lower() in
                [
                    "home",
                    "dashboard",
                    "untitled page"
                ]
            ):

                description = (
                    f"Generic page title detected | "
                    f"title={title}"
                )

                self._add_bug(
                    bug_type=
                    "ACCESSIBILITY_PAGE_TITLE",
                    severity="LOW",
                    page_url=page.url,
                    description=description
                )

        except Exception as e:

            logger.warning(
                f"PAGE TITLE CHECK FAILED: {e}"
            )
    async def _detect_landmarks(
        self,
        page
    ):
        try:

            logger.info(
                f"RUNNING LANDMARK CHECK: {page.url}"
            )

            result = await page.evaluate("""
            () => {

                const hasMain =
                    document.querySelector(
                        `
                        main,
                        [role='main'],
                        .main-content,
                        #main,
                        [class*='content'],
                        [class*='container']                              
                        `
                    );

                const hasNav =
                    document.querySelector(
                        `
                        nav,
                        [role='navigation'],
                        .sidebar,
                        .navbar,
                        [class*='menu']
                        `
                    );

                return {
                    hasMain: !!hasMain,
                    hasNav: !!hasNav
                };
            }
            """)

            if not result["hasMain"]:

                self._add_bug(
                    bug_type=
                    "ACCESSIBILITY_LANDMARKS",
                    severity="LOW",
                    page_url=page.url,
                    description=
                   "Main landmark missing"
                )

            if not result["hasNav"]:

                self._add_bug(
                    bug_type=
                    "ACCESSIBILITY_LANDMARKS",
                    severity="LOW",
                    page_url=page.url,
                    description=
                    "Navigation landmark missing"
                )

        except Exception as e:

            logger.warning(
                f"LANDMARK CHECK FAILED: {e}"
            )
    async def _detect_iframe_title(
        self,
        page
    ):
        try:

            logger.info(
                f"RUNNING IFRAME TITLE CHECK: {page.url}"
            )

            issues = await page.evaluate("""
            () => {

                return Array.from(
                    document.querySelectorAll(
                        "iframe"
                    )
                )
                .filter(frame => {

                    const title =
                        frame.getAttribute(
                            "title"
                        );

                    return (
                        !title ||
                        !title.trim()
                    );
                })
                .map(frame => ({
                    src:
                        frame.src || ""
                }));
            }
            """)

            for issue in issues:

                self._add_bug(
                    bug_type=
                    "ACCESSIBILITY_IFRAME_TITLE",
                    severity="MEDIUM",
                    page_url=page.url,
                    description=
                        f"Iframe missing title | src={issue['src']}"
                )

        except Exception as e:

            logger.warning(
                f"IFRAME TITLE CHECK FAILED: {e}"
            )
    async def _detect_dialog_accessibility(
        self,
        page
    ):
        try:

            logger.info(
                f"RUNNING DIALOG ACCESSIBILITY CHECK: {page.url}"
            )

            issues = await page.evaluate("""
            () => {

                return Array.from(
                    document.querySelectorAll(
                        `
                        [role='dialog'],
                        dialog
                        `
                    )
                )
                .filter(dialog => {

                    const hidden =
                        dialog.offsetParent === null;

                    if (
                        hidden
                    ) {
                        return false;
                    }

                    const ariaLabel =
                        dialog.getAttribute(
                            "aria-label"
                        );

                    const ariaLabelledBy =
                        dialog.getAttribute(
                            "aria-labelledby"
                        );

                    return (
                        !ariaLabel &&
                        !ariaLabelledBy
                    );
                })
                .map(dialog => ({
                    id:
                        dialog.id || ""
                }));
            }
            """)

            for issue in issues:

                self._add_bug(
                    bug_type=
                    "ACCESSIBILITY_DIALOG_ACCESSIBILITY",
                    severity="HIGH",
                    page_url=page.url,
                    description=
                        f"Dialog missing accessible name | id={issue['id']}"
                )

        except Exception as e:

            logger.warning(
                f"DIALOG ACCESSIBILITY CHECK FAILED: {e}"
            )
    async def _detect_table_headers(
        self,
        page
    ):
        try:

            logger.info(
                f"RUNNING TABLE HEADER CHECK: {page.url}"
            )

            issues = await page.evaluate("""
            () => {

                return Array.from(
                    document.querySelectorAll(
                        "table"
                    )
                )
                .filter(table => {

                    const visibleRows =
                        table.querySelectorAll(
                            "tr"
                        );

                    if (
                        visibleRows.length < 2
                    ) {
                        return false;
                    }

                    const hasHeaders =
                        table.querySelector(
                            "th"
                        );

                    return !hasHeaders;
                })
                .map(table => ({

                    rows:
                        table.querySelectorAll(
                            "tr"
                        ).length,

                    cols:
                        table.querySelector(
                            "tr"
                        )?.children.length || 0
                }));
            }
            """)

            logger.info(
                f"TABLE HEADER COUNT: {len(issues)}"
            )

            for issue in issues:

                description = (
                    f"Table missing header cells | "
                    f"rows={issue['rows']} | "
                    f"cols={issue['cols']}"
                )

                self._add_bug(
                    bug_type=
                    "ACCESSIBILITY_TABLE_HEADERS",
                    severity="MEDIUM",
                    page_url=page.url,
                    description=description
                )

        except Exception as e:

            logger.warning(
                f"TABLE HEADER CHECK FAILED: {e}"
            )
    async def _detect_aria_role_validation(
        self,
        page
    ):
        try:

            logger.info(
                f"RUNNING ARIA ROLE VALIDATION: {page.url}"
            )

            issues = await page.evaluate("""
            () => {

                const validRoles = [
                    "alert",
                    "alertdialog",
                    "application",
                    "article",
                    "banner",
                    "button",
                    "cell",
                    "checkbox",
                    "columnheader",
                    "combobox",
                    "complementary",
                    "contentinfo",
                    "definition",
                    "dialog",
                    "directory",
                    "document",
                    "feed",
                    "figure",
                    "form",
                    "grid",
                    "gridcell",
                    "group",
                    "heading",
                    "img",
                    "link",
                    "list",
                    "listbox",
                    "listitem",
                    "log",
                    "main",
                    "marquee",
                    "math",
                    "menu",
                    "menubar",
                    "menuitem",
                    "menuitemcheckbox",
                    "menuitemradio",
                    "navigation",
                    "none",
                    "note",
                    "option",
                    "presentation",
                    "progressbar",
                    "radio",
                    "radiogroup",
                    "region",
                    "row",
                    "rowgroup",
                    "rowheader",
                    "scrollbar",
                    "search",
                    "searchbox",
                    "separator",
                    "slider",
                    "spinbutton",
                    "status",
                    "switch",
                    "tab",
                    "table",
                    "tablist",
                    "tabpanel",
                    "term",
                    "textbox",
                    "timer",
                    "toolbar",
                    "tooltip",
                    "tree",
                    "treegrid",
                    "treeitem"
                ];

                return Array.from(
                    document.querySelectorAll(
                        "[role]"
                    )
                )
                .filter(el => {

                    const role =
                        el.getAttribute(
                            "role"
                        );

                    return (
                        role &&
                        !validRoles.includes(
                            role
                        )
                    );
                })
                .map(el => ({

                    role:
                        el.getAttribute(
                            "role"
                        ),

                    tag:
                        el.tagName,

                    id:
                        el.id || ""
                }));
            }
            """)
 
            logger.info(
                f"ARIA ROLE COUNT: {len(issues)}"
            )
            seen_roles = set()

            for issue in issues:
                role = issue["role"]

                if role in seen_roles:
                    continue

                seen_roles.add(role)
                logger.info(
                    f"ARIA ROLE FOUND: "
                    f"{issue['role']}"
                )

                description = (
                    f"Invalid ARIA role detected | "
                    f"role={issue['role']} | "
                    f"tag={issue['tag']} | "
                    f"id={issue['id']}"
                )

                self._add_bug(
                    bug_type=
                    "ACCESSIBILITY_ARIA_ROLE_VALIDATION",
                    severity="MEDIUM",
                    page_url=page.url,
                    description=description
                )

        except Exception as e:

            logger.warning(
                f"ARIA ROLE VALIDATION FAILED: {e}"
            )
    async def _detect_touch_target_size(
        self,
        page
    ):
        try:

            logger.info(
                f"RUNNING TOUCH TARGET CHECK: {page.url}"
            )

            issues = await page.evaluate("""
            () => {

                return Array.from(
                    document.querySelectorAll(
                        `
                        button,
                        a,
                        input,
                        select,
                        textarea,
                        [role='button']
                        `
                    )
                )
                .filter(el => {

                    const style =
                        getComputedStyle(el);
 
                    if (
                        style.display === "none" ||
                        style.visibility === "hidden"
                    ) {
                        return false;
                    }

                    const rect =
                        el.getBoundingClientRect();
                    if (
                        rect.width === 0 ||
                        rect.height === 0
                    ) {
                        return false;
                    }
                    const text =
                        (
                            el.innerText ||
                            ""
                        ).trim();
                    const ariaLabel =
                        el.getAttribute(
                            "aria-label"
                        ) || "";

                    const title =
                        el.getAttribute(
                            "title"
                        ) || "";
                    const hasSvg =
                        el.querySelector(
                            "svg"
                        );

                    if (
                        !text &&
                        !hasSvg &&
                        !ariaLabel &&
                        !title
                    ) {
                        return false;
                    }

                    return (
                        rect.width > 0 &&
                        rect.height > 0 &&
                        (
                            rect.width < 44 &&
                            rect.height < 44
                        )
                    );
                })
                .map(el => {

                    const rect =
                        el.getBoundingClientRect();
                    
                    const text =
                        (
                            el.innerText ||
                            ""
                        ).trim();

                    const hasSvg =
                        el.querySelector(
                            "svg"
                        );
                    
                    return {

                        tag:
                            el.tagName,

                        id:
                            el.id || "",

                        width:
                            Math.round(
                                rect.width
                            ),

                        height:
                            Math.round(
                                rect.height
                            ),
                        text
                    };
                });
            }
            """)

            logger.info(
                f"TOUCH TARGET COUNT: {len(issues)}"
            )

            for issue in issues:
                logger.info(
                    f"TOUCH TARGET DETAILS | "
                    f"tag={issue['tag']} | "
                    f"id={issue['id']} | "
                    f"width={issue['width']} | "
                    f"height={issue['height']}"
                )

                description = (
                    f"Touch target too small | "
                    f"tag={issue['tag']} | "
                    f"id={issue['id']} | "
                    f"size={issue['width']}x{issue['height']}"
                )

                self._add_bug(
                    bug_type=
                    "ACCESSIBILITY_TOUCH_TARGET_SIZE",
                    severity="LOW",
                    page_url=page.url,
                    description=description
                )

        except Exception as e:

            logger.warning(
                f"TOUCH TARGET CHECK FAILED: {e}"
            )
    async def _detect_link_purpose(
        self,
        page
    ):
        try:

            logger.info(
                f"RUNNING LINK PURPOSE CHECK: {page.url}"
            )

            issues = await page.evaluate("""
            () => {

                const badTexts = [

                    "click here",
                    "here",
                    "more",
                    "read more",
                    "details",
                    "link",
                    "view",
                    "learn more"
                ];

                return Array.from(
                    document.querySelectorAll(
                        "a"
                    )
                )
                .filter(link => {

                    const text =
                        (
                            link.innerText ||
                            ""
                         )
                        .trim()
                        .toLowerCase();

                    if (!text) {
                        return false;
                    }

                    return badTexts.includes(
                        text
                    );
                })
                .map(link => ({

                    text:
                        link.innerText,

                    href:
                        link.href || ""
                }));
            }
            """)

            logger.info(
                f"LINK PURPOSE COUNT: {len(issues)}"
            )

            for issue in issues:

                description = (
                    f"Ambiguous link text detected | "
                    f"text={issue['text']} | "
                    f"href={issue['href']}"
                )

                self._add_bug(
                    bug_type=
                    "ACCESSIBILITY_LINK_PURPOSE",
                    severity="LOW",
                    page_url=page.url,
                    description=description
                )

        except Exception as e:

            logger.warning(
                f"LINK PURPOSE CHECK FAILED: {e}"
            )
    async def _detect_region_labels(
        self,
        page
    ):
        try:

            logger.info(
                f"RUNNING REGION LABEL CHECK: {page.url}"
            )

            issues = await page.evaluate("""
            () => {

                return Array.from(
                    document.querySelectorAll(
                       `
                       section,
                       aside,
                       article
                       `
                    )
                )
                .filter(region => {

                    const ariaLabel =
                        region.getAttribute(
                            "aria-label"
                        );

                    const ariaLabelledBy =
                        region.getAttribute(
                            "aria-labelledby"
                        );

                    const heading =
                        region.querySelector(
                            "h1,h2,h3,h4,h5,h6"
                        );

                    return (
                        !ariaLabel &&
                        !ariaLabelledBy &&
                        !heading
                    );
                })
                .map(region => ({

                    tag:
                        region.tagName,

                    id:
                        region.id || ""
                }));
            }
            """)

            logger.info(
                f"REGION LABEL COUNT: {len(issues)}"
            )

            for issue in issues:
                logger.info(
                    f"REGION LABEL DETAILS | "
                    f"tag={issue['tag']} | "
                    f"id={issue['id']}"
                )

                description = (
                    f"Region missing accessible label | "
                    f"tag={issue['tag']} | "
                    f"id={issue['id']}"
                )

                self._add_bug(
                    bug_type=
                    "ACCESSIBILITY_REGION_LABELS",
                    severity="INFO",
                    page_url=page.url,
                    description=description
                )

        except Exception as e:

            logger.warning(
                f"REGION LABEL CHECK FAILED: {e}"
            )
    async def _detect_autocomplete(
        self,
        page
    ):
        try:

            logger.info(
                f"RUNNING AUTOCOMPLETE CHECK: {page.url}"
            )

            issues = await page.evaluate("""
            () => {

                const mappings = {

                    email: "email",
                    tel: "tel",
                    password: "current-password",
                    search: "search"
                };

                return Array.from(
                    document.querySelectorAll(
                        "input"
                    )
                )
                .filter(input => {

                    const type =
                        input.type;

                    if (
                        !mappings[type]
                    ) {
                        return false;
                    }

                    return !input.hasAttribute(
                        "autocomplete"
                    );
                })
                .map(input => ({

                    type:
                        input.type,

                    name:
                        input.name || "",

                    id:
                        input.id || ""
                }));
            }
            """)

            for issue in issues:

                self._add_bug(
                    bug_type=
                    "ACCESSIBILITY_AUTOCOMPLETE",
                    severity="LOW",
                    page_url=page.url,
                    description=
                        f"Autocomplete missing | type={issue['type']} | id={issue['id']}"
                )

        except Exception as e:

            logger.warning(
                f"AUTOCOMPLETE CHECK FAILED: {e}"
            )
    async def _detect_form_grouping(
        self,
        page
    ):
        try:

            logger.info(
                f"RUNNING FORM GROUPING CHECK: {page.url}"
            )

            issues = await page.evaluate("""
            () => {

                return Array.from(
                    document.querySelectorAll(
                        `
                        input[type="radio"],
                        input[type="checkbox"]
                        `
                    )
                )
                .filter(el => {

                    const hidden =
                        el.offsetParent === null;

                    if (
                        hidden
                    ) {
                        return false;
                    }

                    const checkboxes =
                        document.querySelectorAll(
                            `input[type="checkbox"][name="${el.name || ""}"]`
                        );

                    if (
                        checkboxes.length <= 1
                    ) {
                        return false;
                    } 

                    return !el.closest(
                        "fieldset"
                    );
                })
                .map(el => ({

                    type:
                        el.type,

                    name:
                        el.name || "",

                    id:
                        el.id || ""
                }));
            }
            """)

            for issue in issues:
                logger.info(
                    f"FORM GROUP DETAILS | "
                    f"type={issue['type']} | "
                    f"name={issue['name']} | "
                    f"id={issue['id']}"
                )

                self._add_bug(
                    bug_type=
                    "ACCESSIBILITY_FORM_GROUPING",
                    severity="LOW",
                    page_url=page.url,
                    description=
                        f"{issue['type']} not grouped in fieldset | name={issue['name']}"
                )

        except Exception as e:

            logger.warning(
                "FORM GROUPING CHECK FAILED: {e}"
            )
    async def _detect_required_field_indication(
        self,
        page
    ):
        try:

            logger.info(
                f"RUNNING REQUIRED FIELD CHECK: {page.url}"
            )

            issues = await page.evaluate("""
            () => {

                return Array.from(
                    document.querySelectorAll(
                        `
                        input[required],
                        select[required],
                        textarea[required]
                        `
                    )
                )
                .filter(el => {

                    const label =
                        document.querySelector(
                            `label[for="${el.id}"]`
                        );

                    const labelText =
                        (
                            label?.innerText || ""
                        );

                    const ariaRequired =
                        el.getAttribute(
                            "aria-required"
                        );

                    return (
                        !labelText.includes("*") &&
                        ariaRequired !== "true"
                    );
                })
                .map(el => ({

                    id:
                        el.id || "",

                    name:
                        el.name || ""
                }));
            }
            """)

            for issue in issues:

                self._add_bug(
                    bug_type=
                    "ACCESSIBILITY_REQUIRED_FIELD_INDICATION",
                    severity="LOW",
                    page_url=page.url,
                    description=
                        f"Required field not clearly indicated | id={issue['id']}"
                )

        except Exception as e:

            logger.warning(
                f"REQUIRED FIELD CHECK FAILED: {e}"
            )
    async def _detect_media_captions(
        self,
        page
    ):
        try:

            logger.info(
                f"RUNNING MEDIA CAPTIONS CHECK: {page.url}"
            )

            issues = await page.evaluate("""
            () => {

                return Array.from(
                    document.querySelectorAll(
                        "video"
                    )
                )
                .filter(video => {

                    const tracks =
                        video.querySelectorAll(
                            'track[kind="captions"]'
                        );

                    return (
                        tracks.length === 0
                    );
                })
                .map(video => ({

                    src:
                        video.currentSrc ||
                        video.src ||
                        ""
                }));
            }
            """)

            for issue in issues:

                self._add_bug(
                    bug_type=
                    "ACCESSIBILITY_MEDIA_CAPTIONS",
                    severity="MEDIUM",
                    page_url=page.url,
                    description=
                        f"Video missing captions | src={issue['src']}"
                )

        except Exception as e:

            logger.warning(
                f"MEDIA CAPTIONS CHECK FAILED: {e}"
            )
    async def _detect_audio_transcript(
        self,
        page
    ):
        try:

            logger.info(
                f"RUNNING AUDIO TRANSCRIPT CHECK: {page.url}"
            )

            issues = await page.evaluate("""
            () => {

                return Array.from(
                    document.querySelectorAll(
                        "audio"
                    )
                )
                .filter(audio => {

                    const parentText =
                        (
                            audio.parentElement
                            ?.innerText || ""
                        ).toLowerCase();

                    return (
                        !parentText.includes(
                            "transcript"
                        )
                    );
                })
                .map(audio => ({

                    src:
                        audio.currentSrc ||
                        audio.src ||
                        ""
                }));
            }
            """)

            for issue in issues:

                self._add_bug(
                    bug_type=
                    "ACCESSIBILITY_AUDIO_TRANSCRIPT",
                    severity="MEDIUM",
                    page_url=page.url,
                    description=
                        f"Audio transcript not found | src={issue['src']}"
                )

        except Exception as e:

            logger.warning(
                f"AUDIO TRANSCRIPT CHECK FAILED: {e}"
            )
     #UI-uX MODULE DETECTION
    async def _run_uiux_checks(
        self,
        page
    ):
        logger.info(
            f"RUNNING UI/UX CHECKS: {page.url}"
        )
        await self._detect_broken_navigation(page)
        await self._detect_text_overflow(page)
        await self._detect_horizontal_scroll(page)
        await self._detect_duplicate_cta(page)
        await self._detect_hidden_elements(page)
        await self._detect_empty_state(page)
        await self._detect_mobile_responsiveness(page)
        await self._detect_layout_shift(page)


    async def _detect_broken_navigation(
        self,
        page
    ):
        try:

            logger.info(
                f"RUNNING BROKEN NAVIGATION CHECK: "
                f"{page.url}"
            )

            issues = await page.evaluate("""
            () => {

                return Array.from(
                    document.querySelectorAll(
                        "a[href]"
                    )
                )
                .filter(link => {

                    const href =
                        link.getAttribute(
                            "href"
                        );

                    return (
                        href &&
                        (
                            href === "#" ||
                            href === "javascript:void(0)" ||
                            href === "javascript:;"
                        )
                    );

                })
                .map(link => ({

                    text:
                        link.innerText
                        .trim(),

                    href:
                        link.getAttribute(
                            "href"
                        )
                    }));
            }
            """)

            logger.info(
                f"BROKEN NAVIGATION COUNT: "
                f"{len(issues)}"
            )

            for issue in issues:

                self._add_bug(
                    bug_type=
                    "UIUX_BROKEN_NAVIGATION",
                    severity="MEDIUM",
                    page_url=page.url,
                    description=(
                        f"Broken navigation link "
                        f"text='{issue['text']}' "
                        f"href='{issue['href']}'"
                    )
                )

        except Exception as e:

            logger.warning(
                f"BROKEN NAVIGATION FAILED: {e}"
            )
    async def _detect_text_overflow(
        self,
        page
    ):
        try:

            logger.info(
                f"RUNNING TEXT OVERFLOW CHECK: "
                f"{page.url}"
            )

            issues = await page.evaluate("""
            () => {
  
                return Array.from(
                   document.querySelectorAll("*")
                )
                .filter(el => {

                    const style =
                        window.getComputedStyle(el);

                    return (
                        el.scrollWidth >
                        el.clientWidth + 20
                        &&
                        el.clientWidth > 100
                        &&
                        el.innerText
                        &&
                        el.innerText.trim().length > 0
                        &&
                        style.display !== "inline"
                    );

                })
                .map(el => ({

                    tag:
                        el.tagName,

                    text:
                        el.innerText
                        .trim()
                        .substring(0,100)
                }));
            }
            """)

            logger.info(
                f"TEXT OVERFLOW COUNT: "
                f"{len(issues)}"
            )

            for issue in issues:

                self._add_bug(
                    bug_type=
                    "UIUX_TEXT_OVERFLOW",
                    severity="MEDIUM",
                    page_url=page.url,
                    description=(
                        f"Text overflow detected "
                        f"| tag={issue['tag']} "
                        f"| text={issue['text']}"
                    )
                )

        except Exception as e:

            logger.warning(
                f"TEXT OVERFLOW FAILED: {e}"
            )
    async def _detect_horizontal_scroll(
        self,
        page
    ):
        try:

            logger.info(
                f"RUNNING HORIZONTAL SCROLL CHECK: "
                f"{page.url}"
            )

            issue = await page.evaluate("""
            () => {

                return (
                    document.documentElement.scrollWidth >
                    window.innerWidth + 5
                );
            }
            """)

            if issue:

                self._add_bug(
                    bug_type=
                    "UIUX_HORIZONTAL_SCROLL",
                    severity="HIGH",
                    page_url=page.url,
                    description=(
                        "Page causes horizontal scrolling"
                    )
                )

                logger.warning(
                    f"HORIZONTAL SCROLL FOUND: "
                    f"{page.url}"
                )

        except Exception as e:

            logger.warning(
                f"HORIZONTAL SCROLL FAILED: {e}"
            )
    async def _detect_duplicate_cta(
        self,
        page
    ):
        try:

            logger.info(
                f"RUNNING DUPLICATE CTA CHECK: "
                f"{page.url}"
            )

            issues = await page.evaluate("""
            () => {

                const ctas = {};

                document
                    .querySelectorAll(
                        "button,a"
                    )
                    .forEach(el => {

                        const text =
                            el.innerText
                            .trim()
                            .toLowerCase();

                        if (
                            text.length < 2
                        ){
                            return;
                        }

                        ctas[text] =
                            (ctas[text] || 0) + 1;
                    });

                return Object.entries(
                    ctas
                )
                .filter(
                    ([text,count]) =>
                        count >= 3
                )
                .map(
                    ([text,count]) => ({
                        text,
                        count
                    })
                );
            }
            """)

            logger.info(
                f"DUPLICATE CTA COUNT: "
                f"{len(issues)}"
            )

            for issue in issues:

                self._add_bug(
                    bug_type=
                    "UIUX_DUPLICATE_CTA",
                    severity="LOW",
                    page_url=page.url,
                    description=(
                        f"CTA '{issue['text']}' "
                        f"appears "
                        f"{issue['count']} times"
                    )
                )

        except Exception as e:

            logger.warning(
                f"DUPLICATE CTA FAILED: {e}"
            )
    async def _detect_hidden_elements(
        self,
        page
    ):
        try:

            logger.info(
                f"RUNNING HIDDEN ELEMENT CHECK: "
                f"{page.url}"
            )
            seen_hidden = set()
            issues = await page.evaluate("""
            () => {

                return Array.from(
                    document.querySelectorAll(
                        "button,input,select,textarea,a"
                    )
                )
                .filter(el => {

                    const style =
                        window.getComputedStyle(
                            el
                        );

                    const rect =
                        el.getBoundingClientRect();

                    return (
                        (
                            style.display === "none"
                            ||
                            style.visibility === "hidden"
                            ||
                            parseFloat(
                                style.opacity
                            ) === 0
                        )
                        &&
                        rect.width > 0
                        &&
                        rect.height > 0
                    );
                })
                .map(el => ({

                    tag:
                        el.tagName,

                    text:
                        (
                            el.innerText ||
                            el.value ||
                            ""
                        )
                        .trim()
                        .substring(
                            0,
                            100
                        )
                }));
            }
            """)

            logger.info(
                f"HIDDEN ELEMENT COUNT: "
                f"{len(issues)}"
            )

            if issues:

                hidden_details = []

            for issue in issues:
 
                hidden_details.append(
                    f"tag={issue['tag']} "
                    f"text={issue['text']}"
                )

                self._add_bug(
                    bug_type=
                    "UIUX_HIDDEN_ELEMENTS",
                    severity="LOW",
                    page_url=page.url,
                    description=(
                        f"{len(issues)} hidden interactive "
                        f"elements found:\n"
                        +
                        "\n".join(hidden_details[:10])
                    )
                )

        except Exception as e:

            logger.warning(
                f"HIDDEN ELEMENT FAILED: {e}"
            )
    async def _detect_empty_state(
        self,
        page
    ):
        try:

            logger.info(
                f"RUNNING EMPTY STATE CHECK: {page.url}"
            )

            issues = await page.evaluate("""
            () => {

                const emptyKeywords = [
                    "no records found",
                    "no data available",
                    "no results found",
                    "nothing found"
                ];

                return Array.from(
                    document.querySelectorAll(
                        "table, tbody, .table, .grid, .list")
                )
                .filter(el => {

                    const text =
                        (
                            el.innerText || ""
                        )
                        .toLowerCase()
                        .trim();

                    return emptyKeywords.some(
                        keyword =>
                            text.includes(keyword)
                    );

                })
                .map(el => ({
                    text:
                        el.innerText
                        .trim()
                        .substring(0,150)
                }));
            }
            """)

            logger.info(
                f"EMPTY STATE COUNT: {len(issues)}"
            )

            for issue in issues:

                self._add_bug(
                    bug_type="UIUX_EMPTY_STATE",
                    severity="INFO",
                    page_url=page.url,
                    description=(
                        f"Empty state displayed: "
                        f"{issue['text']}"
                    )
                )

        except Exception as e:

            logger.warning(
                f"EMPTY STATE CHECK FAILED: {e}"
            )
    async def _detect_mobile_responsiveness(
        self,
        page
    ):
        try:

            logger.info(
                f"RUNNING MOBILE RESPONSIVENESS CHECK: "
                f"{page.url}"
            )

            issue = await page.evaluate("""
            () => {

                const viewportMeta =
                    document.querySelector(
                        'meta[name="viewport"]'
                    );

                return !viewportMeta;
            }
            """)

            if issue:

                self._add_bug(
                    bug_type=
                    "UIUX_MOBILE_RESPONSIVENESS",
                    severity="HIGH",
                    page_url=page.url,
                    description=
                        "Viewport meta tag missing"
                )

                logger.warning(
                    f"MOBILE RESPONSIVENESS ISSUE: "
                    f"{page.url}"
                )

        except Exception as e:

            logger.warning(
                f"MOBILE RESPONSIVENESS FAILED: {e}"
            )
    async def _detect_layout_shift(
        self,
        page
    ):
        try:

            logger.info(
                f"RUNNING LAYOUT SHIFT CHECK: "
                f"{page.url}"
            )

            issue = await page.evaluate("""
            () => {
 
                return Array.from(
                    document.images
                )
                .filter(img => {

                    return (
                        !img.width ||
                        !img.height
                    );

                }).length;

            }
            """)

            if issue > 0:

                self._add_bug(
                    bug_type=
                    "UIUX_LAYOUT_SHIFT",
                    severity="MEDIUM",
                    page_url=page.url,
                    description=(
                        '${issue} images may cause layout shift'
                    )
                )
                logger.warning(
                    "LAYOUT SHIFT COUNT: {issue}"
                )

        except Exception as e:

            logger.warning(
                f"LAYOUT SHIFT FAILED: {e}"
            )
        #performance detection module
    async def _run_performance_checks(
        self,
        page
    ):
        logger.info(
            f"RUNNING PERFORMANCE CHECKS: "
            f"{page.url}"
        )
        await self._detect_slow_page_load(page)
        await self._detect_large_dom_size(page)
        await self._detect_render_blocking_resources(page)
        await self._detect_large_js_bundle(page)
        await self._detect_lcp(page)
        await self._detect_cls(page)
        await self._detect_inp(page)
        await self._detect_excessive_network_requests(page)
        await self._detect_large_images(page)
        await self._detect_dom_depth(page)
        await self._detect_resource_load_failures(page)
        self.render_blocking_resources.clear()
        self.large_js_bundles.clear()
    
    async def _detect_slow_page_load(
        self,
        page
    ):
        try:

            load_time = await page.evaluate("""
            () => {

                const nav =
                    performance.getEntriesByType(
                        "navigation"
                    )[0];

                return nav
                    ? nav.loadEventEnd
                    : 0;
            }
            """)

            if load_time > 7000:

                self._add_bug(
                    bug_type=
                    "PERFORMANCE_SLOW_PAGE_LOAD",
                    severity="HIGH",
                    page_url=page.url,
                    description=
                        f"Page load time: "
                        f"{load_time:.0f} ms"
                    )

        except Exception as e:

            logger.warning(
                f"SLOW PAGE LOAD FAILED: {e}"
            )
    async def _detect_large_dom_size(
        self,
        page
    ):
        try:

            dom_size = await page.evaluate("""
            () => {

                return document
                    .querySelectorAll("*")
                    .length;
            }
            """)

            logger.info(
                f"DOM SIZE: {dom_size}"
            )

            if dom_size > 2500:

                self._add_bug(
                    bug_type=
                    "PERFORMANCE_LARGE_DOM",
                    severity="MEDIUM",
                    page_url=page.url,
                    description=
                        f"DOM contains "
                        f"{dom_size} elements"
                )

        except Exception as e:

            logger.warning(
                f"LARGE DOM FAILED: {e}"
            )
    async def _detect_render_blocking_resources(
        self,
        page
    ):
        try:

            logger.info(
                f"RUNNING RENDER BLOCKING CHECK: "
                f"{page.url}"
            )

            seen_resources = set()

            for resource in (
                self.render_blocking_resources
            ):

                key = (
                    resource["url"],
                    resource["type"]
                )

                if key in seen_resources:
                    continue

                seen_resources.add(key)
                logger.info(
                    f"RESOURCE URL: {resource['url']}"
                )

                logger.info(
                    f"RESOURCE TYPE: {resource['type']}"
                )

                self._add_bug(
                    bug_type=
                    "PERFORMANCE_RENDER_BLOCKING_RESOURCE",
                    severity="LOW",
                    page_url=page.url,
                    description=(
                        f"{resource['type']} "
                        f"may block rendering: "
                        f"{resource['url']}"
                    )
                )

            logger.info(
                f"RENDER BLOCKING COUNT: "
                f"{len(seen_resources)}"
            )

        except Exception as e:

            logger.warning(
                f"RENDER BLOCKING CHECK FAILED: "
                f"{e}"
            )
    async def _detect_large_js_bundle(
        self,
        page
    ):
        try:

            seen_scripts = set()

            for script in self.large_js_bundles:

                if script["url"] in seen_scripts:
                    continue

                seen_scripts.add(
                    script["url"]
                )
                logger.info(
                    f"SCRIPT URL: {script['url']}"
                )
                logger.info(
                    f"SCRIPT SIZE: {script['size']}"
                )
                self._add_bug(
                    bug_type=
                    "PERFORMANCE_LARGE_JS_BUNDLE",
                    severity="MEDIUM",
                    page_url=page.url,
                    description=
                        f"{script['url']} "
                        f"size="
                        f"{round(script['size']/1024,2)} KB"
                )

        except Exception as e:

            logger.warning(
                f"LARGE JS BUNDLE FAILED: {e}"
            )
    async def _detect_lcp(
        self,
        page
    ):
        try:

            lcp = await page.evaluate("""
            async () => {

                return new Promise(
                    resolve => {

                        let lcpValue = 0;

                        const observer =
                            new PerformanceObserver(
                                entryList => {

                                    const entries =
                                        entryList.getEntries();

                                    const lastEntry =
                                        entries[
                                            entries.length - 1
                                        ];

                                    lcpValue =
                                        lastEntry.renderTime ||
                                        lastEntry.loadTime ||
                                        0;
                                }
                            );

                        observer.observe({
                            type:
                            "largest-contentful-paint",
                            buffered:
                            true
                        });

                        setTimeout(() => {

                            observer.disconnect();

                            resolve(
                                lcpValue
                            );

                        },3000);
                    }
                );
            }
            """)

            logger.info(
                f"LCP VALUE: {lcp}"
            )

            severity = "MEDIUM"
            if lcp > 4000:
                severity = "HIGH"

                self._add_bug(
                    bug_type=
                    "PERFORMANCE_LCP",
                    severity=severity,
                    page_url=page.url,
                    description=
                        f"LCP = {lcp} ms"
                )

        except Exception as e:

            logger.warning(
                f"LCP CHECK FAILED: {e}"
            )
    async def _detect_cls(
        self,
        page
    ):
        try:

            cls = await page.evaluate("""
            async () => {

                return new Promise(
                    resolve => {

                        let clsValue = 0;

                        const observer =
                            new PerformanceObserver(
                                list => {

                                    for (
                                        const entry
                                        of list.getEntries()
                                    ) {

                                        if (
                                            !entry.hadRecentInput
                                        ) {

                                            clsValue +=
                                                entry.value;
                                        }
                                    }
                                }
                            );

                        observer.observe({
                            type:
                            "layout-shift",
                            buffered:
                            true
                        });

                        setTimeout(() => {

                            observer.disconnect();

                            resolve(
                                clsValue
                            );

                        },3000);
                    }
                );
            }
            """)

            logger.info(
                f"CLS VALUE: {cls}"
            )

            severity = "MEDIUM"
            if cls > 0.25:
                severity = "HIGH"

                self._add_bug(
                    bug_type=
                    "PERFORMANCE_CLS",
                    severity=severity,
                    page_url=page.url,
                    description=
                        f"CLS = {cls}"
                )

        except Exception as e:

            logger.warning(
                f"CLS CHECK FAILED: {e}"
            )
    async def _detect_inp(
        self,
        page
    ):
        try:

            inp = await page.evaluate("""
            () => {

                const entries =
                    performance.getEntriesByType(
                        "event"
                    );

                if (
                    !entries.length
                ) {

                    return 0;
                }

                return Math.max(
                    ...entries.map(
                        e =>
                        e.duration || 0
                    )
                );
            }
            """)

            logger.info(
                f"INP VALUE: {inp}"
            )

            severity = "LOW"
            if inp > 500:
                severity = "HIGH"
            elif inp > 300:
                severity = "MEDIUM"

                self._add_bug(
                    bug_type=
                    "PERFORMANCE_INP",
                    severity=severity,
                    page_url=page.url,
                    description=
                        f"INP = {inp} ms"
                )

        except Exception as e:

            logger.warning(
                f"INP CHECK FAILED: {e}"
            )

    async def _detect_excessive_network_requests(
        self,
        page
    ):
        try:

            request_count = await page.evaluate("""
            () => performance
                .getEntriesByType(
                    "resource"
                )
                .length
            """)

            logger.info(
                f"NETWORK REQUEST COUNT: "
                f"{request_count}"
            )

            if request_count > 100:

                self._add_bug(
                    bug_type=
                    "PERFORMANCE_EXCESSIVE_NETWORK_REQUESTS",
                    severity="MEDIUM",
                    page_url=page.url,
                    description=
                        f"{request_count} "
                        f"network requests detected"
                )

        except Exception as e:

            logger.warning(
                f"NETWORK REQUEST CHECK FAILED: {e}"
            )
    async def _detect_large_images(
        self,
        page
    ):
        try:

            images = await page.evaluate("""
            () => {

                return Array.from(
                    document.images
                )
                .map(img => ({
                    src: img.src,
                    width: img.naturalWidth,
                    height: img.naturalHeight
                }));
            }
            """)

            for img in images:

                if (
                    img["width"] > 2000
                    or
                    img["height"] > 2000
                ):

                    self._add_bug(
                       bug_type=
                       "PERFORMANCE_LARGE_IMAGE",
                       severity="LOW",
                       page_url=page.url,
                       description=
                            f"Large image: "
                            f"{img['src']}"
                    )

        except Exception as e:

            logger.warning(
                f"LARGE IMAGE CHECK FAILED: {e}"
            )
    async def _detect_dom_depth(
        self,
        page
    ):
        try:

            depth = await page.evaluate("""
            () => {

                let maxDepth = 0;

                function walk(
                    node,
                    currentDepth
                ){

                    maxDepth =
                        Math.max(
                            maxDepth,
                            currentDepth
                        );

                    for(
                        const child
                        of node.children
                    ){

                        walk(
                            child,
                            currentDepth + 1
                        );
                    }
                }

                walk(
                    document.body,
                    0
                );

                return maxDepth;
            }
            """)

            logger.info(
                f"DOM DEPTH: {depth}"
            )

            if depth > 20:

                self._add_bug(
                    bug_type=
                    "PERFORMANCE_DOM_DEPTH",
                    severity="LOW",
                    page_url=page.url,
                    description=
                        f"DOM depth = {depth}"
                )

        except Exception as e:

            logger.warning(
                f"DOM DEPTH CHECK FAILED: {e}"
            )
    async def _detect_resource_load_failures(
        self,
        page
    ):
        try:

            seen = set()

            for failure in (
                self.failed_network_requests
            ):

                if failure["url"] in seen:
                    continue

                seen.add(
                    failure["url"]
                )

                self._add_bug(
                    bug_type=
                    "PERFORMANCE_RESOURCE_LOAD_FAILURE",
                    severity="HIGH",
                    page_url=page.url,
                    description=
                        failure["url"]
                )

        except Exception as e:

            logger.warning(
                f"RESOURCE FAILURE CHECK FAILED: {e}"
            )

     #Visual Regression & UI Consistency Module detection

    async def _run_visual_checks(
        self,
        page
    ):
        logger.info(
            f"RUNNING VISUAL CHECKS: "
            f"{page.url}"
        )

        await self._detect_layout_break(page)
        await self._detect_overlapping_elements(page)
        await self._detect_cropped_text(page)
        await self._detect_missing_images(page)
        await self._detect_z_index_conflicts(page)
        await self._detect_sticky_overlay(page)
        await self._detect_offscreen_content(page)
        await self._detect_responsive_breakpoint_issue(page)
        self.failed_images.clear()

    async def _detect_layout_break(
        self,
        page
    ):
        try:

            issues = await page.evaluate("""
            () => {

                return Array.from(
                    document.querySelectorAll("*")
                )
                .filter(el => {

                    const rect =
                        el.getBoundingClientRect();

                    return (
                        rect.width >
                        window.innerWidth * 1.5
                    );

                })
                .map(el => ({
                    tag:
                        el.tagName
                }));
            }
            """)

            logger.info(
                f"LAYOUT BREAK COUNT: "
                f"{len(issues)}"
            )

            for issue in issues:

                self._add_bug(
                    bug_type=
                    "VISUAL_LAYOUT_BREAK",
                    severity="HIGH",
                    page_url=page.url,
                    description=
                        f"Element exceeds viewport width | "
                        f"{issue['tag']}"
                )

        except Exception as e:

            logger.warning(
                f"LAYOUT BREAK FAILED: {e}"
            )
    async def _detect_overlapping_elements(
        self,
        page
    ):
        try:

            overlaps = await page.evaluate("""
            () => {

                const elements =
                    Array.from(
                        document.querySelectorAll(
                            "*"
                        )
                    );

                let count = 0;

                for(
                    let i=0;
                    i<elements.length;
                    i++
                ){

                    const a =
                        elements[i]
                        .getBoundingClientRect();

                    for(
                        let j=i+1;
                        j<elements.length;
                        j++
                    ){

                        const b =
                            elements[j]
                            .getBoundingClientRect();

                        if(
                            a.left < b.right &&
                            a.right > b.left &&
                            a.top < b.bottom &&
                            a.bottom > b.top
                        ){
                            count++;
                        }
                    }
                }

                return count;
            }
            """)

            if overlaps > 20:

                self._add_bug(
                    bug_type=
                    "VISUAL_OVERLAPPING_ELEMENTS",
                    severity="MEDIUM",
                    page_url=page.url,
                    description=
                        f"{overlaps} overlaps detected"
                )

        except Exception as e:

            logger.warning(
                f"OVERLAP CHECK FAILED: {e}"
            )
    
    async def _detect_cropped_text(
        self,
        page
    ):
        try:

            issues = await page.evaluate("""
            () => {

                return Array.from(
                    document.querySelectorAll("*")
                )
                .filter(el => {

                    return (
                        el.scrollHeight >
                        el.clientHeight + 10
                    )
                    &&
                    (
                        el.innerText ||
                        ""
                    ).trim().length > 20;

                }).length;
            }
            """)

            if issues:

                self._add_bug(
                    bug_type=
                    "VISUAL_CROPPED_TEXT",
                    severity="MEDIUM",
                    page_url=page.url,
                    description=
                        f"{issues} cropped text blocks"
                )

        except Exception as e:

            logger.warning(
                f"CROPPED TEXT FAILED: {e}"
            )

    async def _detect_missing_images(
        self,
        page
    ):
        try:
            logger.info(
                f"RUNNING MISSING IMAGE CHECK: {page.url}"
            )
            seen = set()

            for img in self.failed_images:

                if img["url"] in seen:
                    continue

                seen.add(
                    img["url"]
                )

                self._add_bug(
                    bug_type=
                    "VISUAL_MISSING_IMAGE",
                    severity="HIGH",
                    page_url=page.url,
                    description=
                        f"{img['url']} "
                        f"({img['status']})"
                )

        except Exception as e:

            logger.warning(
                f"MISSING IMAGE FAILED: {e}"
            )
    async def _detect_z_index_conflicts(
        self,
        page
    ):
        try:
            logger.info(
                f"RUNNING Z INDEX CHECK: {page.url}"
            )
            count = await page.evaluate("""
            () => {

                return Array.from(
                    document.querySelectorAll("*")
                )
                .filter(el => {

                    const z =
                        parseInt(
                            getComputedStyle(el)
                            .zIndex
                        );

                    return (
                        z > 9999
                    );

                }).length;
            }
            """)

            if count:

                self._add_bug(
                    bug_type=
                    "VISUAL_Z_INDEX_CONFLICT",
                    severity="LOW",
                    page_url=page.url,
                    description=
                        f"{count} high z-index elements"
                )

        except Exception as e:

            logger.warning(
                f"Z INDEX FAILED: {e}"
            )
    async def _detect_sticky_overlay(
        self,
        page
    ):
        try:
            logger.info(
                f"RUNNING STICKY OVERLAY CHECK: {page.url}"
            )
            count = await page.evaluate("""
            () => {

                return Array.from(
                    document.querySelectorAll("*")
                )
                .filter(el => {

                    const style =
                        getComputedStyle(el);

                    return (
                        style.position ===
                        "fixed"
                    );

                }).length;
            }
            """)

            if count > 5:

                self._add_bug(
                    bug_type=
                    "VISUAL_STICKY_ELEMENT_OVERLAY",
                    severity="LOW",
                    page_url=page.url,
                    description=
                        f"{count} fixed elements"
                )

        except Exception as e:

            logger.warning(
                f"STICKY OVERLAY FAILED: {e}"
            )
    async def _detect_offscreen_content(
        self,
        page
    ):
        try:
            logger.info(
                f"RUNNING OFFSCREEN CONTENT CHECK: {page.url}"
            )
            count = await page.evaluate("""
            () => {

                return Array.from(
                    document.querySelectorAll("*")
                )
                .filter(el => {

                    const rect =
                        el.getBoundingClientRect();

                    return (
                        rect.left < -50
                        ||
                        rect.right >
                        (
                            window.innerWidth
                            + 50
                        )
                    );

                }).length;
            }
            """)

            if count:

                self._add_bug(
                    bug_type=
                    "VISUAL_OFFSCREEN_CONTENT",
                    severity="MEDIUM",
                    page_url=page.url,
                    description=
                        f"{count} offscreen elements"
                )

        except Exception as e:

            logger.warning(
                f"OFFSCREEN FAILED: {e}"
            )
    async def _detect_responsive_breakpoint_issue(
        self,
        page
    ):
        try:
            logger.info(
                f"RUNNING RESPONSIVE CHECK: {page.url}"
            )
            viewport = page.viewport_size
            if (
                viewport
                and
                viewport["width"] < 768
            ):
                scroll_width = await page.evaluate("""
                    () =>
                        document
                        .documentElement
                        .scrollWidth
                    """)

                if (
                    scroll_width >
                    viewport["width"]
                ):

                    self._add_bug(
                        bug_type=
                        "VISUAL_RESPONSIVE_BREAKPOINT_ISSUE",
                        severity="HIGH",
                        page_url=page.url,
                        description=
                            "Mobile layout overflow detected"
                    )

        except Exception as e:

            logger.warning(
                f"RESPONSIVE CHECK FAILED: {e}"
            )
    async def _wait_for_spa_ready(self, page: Page) -> None:
        """Wait for React/Vue/Angular to finish rendering."""
        try:
            # Check if common SPA frameworks are present and wait for them
            await page.wait_for_function(
                """() => {
                    // React hydration done
                    if (window.__REACT_DEVTOOLS_GLOBAL_HOOK__) return true;
                    // Vue mounted
                    if (window.__VUE__) return true;
                    // General: no pending AJAX
                    return document.readyState === 'complete';
                }""",
                timeout=3000,
            )
        except Exception:
            pass  # Timeout is fine — page may not be a SPA

    async def _detect_page_framework(self, page: Page) -> Optional[str]:
        """Detect JS framework used on the page."""
        try:

            return await page.evaluate("""
            () => {
                if (
                    window.React ||
                    document.querySelector('[data-reactroot]') ||
                    document.querySelector('#__NEXT_DATA__')
                ) {
                    return 'Next.js/React';
                }

                if (
                    window.__VUE__ ||
                    document.querySelector('[data-v-]')
                ) {
                    return 'Vue.js';
                }

                if (
                    window.ng ||
                    document.querySelector('[ng-version]') ||
                    document.querySelector('app-root')
                ) {
                    return 'Angular';
                }

                if (window.Svelte) {
                    return 'Svelte';
                }

                return null;
            }
            """)

        except Exception as e:

            logger.warning(
                f"FRAMEWORK DETECTION FAILED: {e}"
            )

            return "Unknown"

    async def _setup_auth(self, context, url: str, auth_config: Dict, browser) -> None:
        """Perform login before crawling authenticated routes."""
        if auth_config.get("type") == "form":
            page = await context.new_page()
            try:
                login_url = auth_config.get("login_url") or urljoin(url, "/login")
                if not login_url.startswith(("http://", "https://")):
                    login_url = f"https://{login_url}"
                await page.goto(login_url, wait_until="networkidle")
                await page.fill(auth_config.get("email_selector", "input[type='email']"), auth_config.get("email", ""))
                await page.fill(auth_config.get("password_selector", "input[type='password']"), auth_config.get("password", ""))
                await page.click(auth_config.get("submit_selector", "button[type='submit']"))
                await page.wait_for_timeout(2000)
                logger.info("Form auth completed")
            except Exception as e:
                logger.warning(f"Auth setup failed: {e}")
            finally:
                await page.close()

    def _build_selector(self, el: Dict) -> str:
        """Build the most stable CSS selector for an element."""
        if el.get("id"):
            return f"#{el['id']}"
        if el.get("aria_label"):
            return f"[aria-label='{el['aria_label']}']"
        if el.get("name"):
            return f"[name='{el['name']}']"
        if el.get("placeholder"):
            return f"[placeholder='{el['placeholder']}']"
        if el.get("text") and len(el["text"]) < 40 and el.get("tag") in ("button", "a"):
            return f"{el['tag']}:has-text('{el['text']}')"
        return el.get("tag", "div")

    def _classify_element(self, el: Dict) -> str:
        tag = el.get("tag", "")
        if tag == "button" or el.get("role") == "button":
            return "button"
        if tag == "a":
            return "link"
        if tag == "input":
            t = el.get("type", "text")
            return f"input_{t}" if t != "text" else "input"
        if tag == "select":
            return "select"
        if tag == "textarea":
            return "textarea"
        return "interactive"

    def _classify_page(self, url: str, title: str, elements: List, forms: List) -> str:
        url_lower = url.lower()
        title_lower = title.lower()
        if any(kw in url_lower for kw in ("login", "signin", "auth", "register", "signup")):
            return "auth"
        if any(kw in url_lower for kw in ("dashboard", "home", "overview")):
            return "dashboard"
        if any(kw in url_lower for kw in ("checkout", "payment", "cart")):
            return "checkout"
        if forms:
            return "form"
        if any(kw in url_lower for kw in ("list", "search", "browse", "catalog")):
            return "listing"
        return "page"
    
    def _detect_possible_actions(
        self,
        elements: List[Dict],
        forms: List[Dict],
        url: str,
    ) -> List[str]:

        actions = []

        url_lower = url.lower()

        texts = [
            (e.get("text") or "").lower()
            for e in elements
        ]

        placeholders = [
            (e.get("placeholder") or "").lower()
            for e in elements
        ]

    # Login detection
        if (
            "login" in url_lower or
            "signin" in url_lower or
            any("login" in t for t in texts)
        ):
            actions.append("login")

    # Signup detection
        if (
            "signup" in url_lower or
            "register" in url_lower or
            any("register" in t for t in texts)
        ):
            actions.append("signup")

    # Search detection
        if any("search" in p for p in placeholders):
            actions.append("search")

    # Form submission
        if forms:
            actions.append("submit_form")

    # Checkout detection
        if any(k in url_lower for k in ["checkout", "payment", "cart"]):
            actions.append("checkout")

        return list(set(actions))

    def _is_same_domain(self, url: str, base_domain: str) -> bool:
        try:
            return urlparse(url).netloc == base_domain
        except Exception:
            return False

    def _detect_framework(self) -> Optional[str]:
        """Determine the most common framework from all pages."""
        frameworks = [p.framework_detected for p in self.pages if p.framework_detected]
        if not frameworks:
            return None
        return max(set(frameworks), key=frameworks.count)

    def _build_app_context(self, base_url: str) -> Dict[str, Any]:
        """Build structured context for AI test generation."""
        pages_summary = []
        for p in self.pages:
            pages_summary.append({
                "url": p.url,
                "title": p.title,
                "page_type": p.page_type,
                "element_count": len(p.elements),
                "form_count": len(p.forms),
                "has_auth": p.page_type == "auth",
                "interactive_elements": [
                    {"type": e["element_type"], "text": e.get("text"), "selector": e["selector"]}
                    for e in p.elements[:20]
                ],
                "forms": [
                    {"fields": [f["name"] for f in form.get("fields", [])],
                     "submit_text": form.get("submit_text")}
                    for form in p.forms
                ],
                "possible_actions": self._detect_possible_actions(
                    p.elements,
                    p.forms,
                    p.url
                ),
            })

        return {
            "base_url": base_url,
            "total_pages": len(self.pages),
            "app_framework": self._detect_framework(),
            "has_auth": any(p.page_type == "auth" for p in self.pages),
            "has_forms": any(p.forms for p in self.pages),
            "has_checkout": any(p.page_type == "checkout" for p in self.pages),
            "pages": pages_summary,
        }

    def _page_to_dict(self, page: CrawledPage) -> Dict:
        return {
            "url": page.url,
            "title": page.title,
            "status_code": page.status_code,
            "page_type": page.page_type,
            "depth": page.depth,
            "elements": page.elements,
            "forms": page.forms,
            "links_found": page.links_found,
            "load_time_ms": page.load_time_ms,
            "framework_detected": page.framework_detected,
        }
