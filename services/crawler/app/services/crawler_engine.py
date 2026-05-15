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
    app_context: Dict[str, Any]  # Structured context for AI


class CrawlerEngine:
    """
    Main crawler — uses Playwright to fully render and analyze web apps.
    """

    def __init__(self):
        self.visited_urls: Set[str] = set()
        self.pages: List[CrawledPage] = []
        self.errors: List[str] = []

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

            # Set up auth if provided
            if auth_config:
                await self._setup_auth(context, url, auth_config, browser)

            # Start BFS crawl
            await self._crawl_bfs(
                context=context,
                start_url=url,
                max_depth=max_depth,
                max_pages=max_pages,
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
        self, context, start_url: str, max_depth: int, max_pages: int
    ) -> None:
        """Breadth-first crawl."""
        queue: List[tuple] = [(start_url, 0)]  # (url, depth)
        base_domain = urlparse(start_url).netloc

        while queue and len(self.pages) < max_pages:
            url, depth = queue.pop(0)

            if url in self.visited_urls:
                continue
            if depth > max_depth:
                continue
            if not self._is_same_domain(url, base_domain):
                continue

            self.visited_urls.add(url)

            try:
                page_data = await self._analyze_page(context, url, depth)
                if page_data:
                    self.pages.append(page_data)
                    # Add discovered links to queue
                    for link in page_data.links_found:
                        if link not in self.visited_urls:
                            queue.append((link, depth + 1))
            except Exception as e:
                logger.warning(f"Failed to crawl {url}: {e}")
                self.errors.append(f"{url}: {str(e)}")

    async def _analyze_page(self, context, url: str, depth: int) -> Optional[CrawledPage]:
        """Open a page and extract all elements, forms, and links."""
        import time
        page = await context.new_page()
        start = time.time()

        try:
            if not url.startswith(("http://", "https://")):
                url = f"https://{url}"

            # Navigate with network idle wait for SPA
            response = await page.goto(
                url,
                timeout=settings.PAGE_LOAD_TIMEOUT_MS,
                wait_until="domcontentloaded",
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

            # Extract all interactive elements
            elements = await self._extract_elements(page)
            forms = await self._extract_forms(page)
            links = await self._extract_links(page, url)
            framework = await self._detect_page_framework(page)
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

    async def _extract_links(self, page, base_url: str) -> List[str]:


        raw_links = await page.eval_on_selector_all(
            "a[href]",
            """
            elements => elements.map(
                e => e.getAttribute('href')
            )
            """
        )

        clean_links = []

        base_domain = urlparse(base_url).netloc

        for link in raw_links:

            if not link:
                continue

        # Skip invalid links
            if (
                link.startswith("#")
                or link.startswith("javascript:")
                or link.startswith("mailto:")
                or link.startswith("tel:")
            ):
                continue

            absolute = urljoin(base_url, link)

            absolute = absolute.split("#")[0]

            parsed = urlparse(absolute)

        # Only crawl same domain
            if parsed.netloc != base_domain:
                continue

            if absolute not in clean_links:
                clean_links.append(absolute)

        logger.info(
            f"EXTRACTED {len(clean_links)} LINKS FROM {base_url}"
        )
#
        return clean_links

    async def _extract_forms(self, page: Page) -> List[Dict]:
        """Extract all forms with their fields."""
        forms = await page.evaluate("""
        () => {
            return Array.from(document.querySelectorAll('form')).map(form => {
                const fields = Array.from(form.querySelectorAll('input, select, textarea')).map(f => ({
                    name: f.name || f.id || null,
                    type: f.type || 'text',
                    placeholder: f.placeholder || null,
                    required: f.required,
                    options: f.tagName === 'SELECT' ? Array.from(f.options).map(o => o.text) : null,
                }));
                const submitBtn = form.querySelector('button[type="submit"], input[type="submit"], button:last-child');
                return {
                    action: form.action || null,
                    method: form.method || 'GET',
                    id: form.id || null,
                    fields: fields,
                    submit_text: submitBtn ? (submitBtn.textContent || '').trim() : null,
                    field_count: fields.length,
                };
            });
        }
        """)
        return forms or []

    async def _extract_links(self, page: Page, current_url: str) -> List[str]:
        """Extract all internal links for crawl queue."""
        hrefs = await page.evaluate("""
        () => Array.from(document.querySelectorAll('a[href]')).map(a => a.href)
        """)

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
        return await page.evaluate("""
        () => {
            if (window.React || document.querySelector('[data-reactroot]') || document.querySelector('#__NEXT_DATA__')) return 'Next.js/React';
            if (window.__VUE__ || document.querySelector('[data-v-]')) return 'Vue.js';
            if (window.ng || document.querySelector('[ng-version]') || document.querySelector('app-root')) return 'Angular';
            if (window.Svelte) return 'Svelte';
            return null;
        }
        """)

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
