"""
Visual Regression Engine.

Captures full-page screenshots and compares them against stored baselines.
Reports pixel-level differences as a score and diff image.

Algorithm:
  1. Capture screenshot of each page at current commit
  2. Load baseline screenshot (stored in S3 / local fs)
  3. Resize both to same dimensions
  4. Compute per-pixel difference using numpy
  5. Generate a red-diff image highlighting changed regions
  6. Return diff_score (0.0 = identical, 1.0 = completely different)

Phase 2: pixel diff only.
Phase 4: add perceptual hash + AI "is this a real regression?" classifier.
"""

import asyncio
import base64
import hashlib
import io
import json
import logging
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from urllib.parse import urlparse

logger = logging.getLogger("jarviis.visual")


@dataclass
class ScreenshotResult:
    url: str
    screenshot_b64: str       # base64 JPEG
    width: int
    height: int
    captured_at: str


@dataclass
class DiffResult:
    url: str
    baseline_exists: bool
    diff_score: float          # 0.0 (identical) to 1.0 (completely different)
    diff_pixel_count: int
    diff_image_b64: Optional[str]   # base64 PNG with red highlights
    is_regression: bool        # True if diff_score > threshold
    threshold: float
    baseline_id: str
    message: str


class VisualRegressionEngine:

    def __init__(
        self,
        baseline_dir: str = "/tmp/jarviis/baselines",
        threshold: float = 0.02,       # 2% pixel change = regression
    ):
        self.baseline_dir = Path(baseline_dir)
        self.baseline_dir.mkdir(parents=True, exist_ok=True)
        self.threshold = threshold

    # ── Screenshot capture ────────────────────────────────────

    async def capture_pages(
        self,
        urls: List[str],
        viewport: Tuple[int, int] = (1280, 800),
        full_page: bool = True,
    ) -> List[ScreenshotResult]:
        """Capture screenshots of all URLs using Playwright."""
        from playwright.async_api import async_playwright
        from datetime import datetime, timezone
        results = []

        async with async_playwright() as pw:
            browser = await pw.chromium.launch(headless=True, args=["--no-sandbox", "--disable-dev-shm-usage"])
            context = await browser.new_context(viewport={"width": viewport[0], "height": viewport[1]})

            for url in urls:
                page = await context.new_page()
                try:
                    await page.goto(url, timeout=20000, wait_until="networkidle")
                    await page.wait_for_timeout(500)  # Let animations settle

                    screenshot_bytes = await page.screenshot(
                        type="png",
                        full_page=full_page,
                        animations="disabled",
                    )
                    b64 = base64.b64encode(screenshot_bytes).decode()

                    # Get actual dimensions
                    dims = await page.evaluate("() => [document.documentElement.scrollWidth, document.documentElement.scrollHeight]")

                    results.append(ScreenshotResult(
                        url=url,
                        screenshot_b64=b64,
                        width=dims[0] if full_page else viewport[0],
                        height=dims[1] if full_page else viewport[1],
                        captured_at=datetime.now(timezone.utc).isoformat(),
                    ))
                    logger.debug(f"Captured screenshot: {url}")
                except Exception as e:
                    logger.warning(f"Screenshot failed for {url}: {e}")
                finally:
                    await page.close()

            await browser.close()
        return results

    # ── Baseline management ───────────────────────────────────

    def save_baseline(self, project_id: str, url: str, screenshot_b64: str) -> str:
        """Save a screenshot as the new baseline. Returns baseline_id."""
        baseline_id = self._baseline_id(project_id, url)
        path = self.baseline_dir / f"{baseline_id}.png"
        img_bytes = base64.b64decode(screenshot_b64)
        path.write_bytes(img_bytes)
        logger.info(f"Saved baseline: {baseline_id} for {url}")
        return baseline_id

    def load_baseline(self, project_id: str, url: str) -> Optional[bytes]:
        """Load a baseline screenshot. Returns None if no baseline exists."""
        baseline_id = self._baseline_id(project_id, url)
        path = self.baseline_dir / f"{baseline_id}.png"
        if path.exists():
            return path.read_bytes()
        return None

    def _baseline_id(self, project_id: str, url: str) -> str:
        """Stable ID for a project+URL pair."""
        key = f"{project_id}:{url}"
        return hashlib.sha256(key.encode()).hexdigest()[:16]

    # ── Comparison ────────────────────────────────────────────

    def compare(
        self,
        project_id: str,
        url: str,
        current_b64: str,
    ) -> DiffResult:
        """Compare current screenshot against stored baseline."""
        try:
            from PIL import Image, ImageChops
            import numpy as np
        except ImportError:
            return DiffResult(url=url, baseline_exists=False, diff_score=0.0,
                              diff_pixel_count=0, diff_image_b64=None,
                              is_regression=False, threshold=self.threshold,
                              baseline_id="", message="Pillow/numpy not installed")

        baseline_id = self._baseline_id(project_id, url)
        baseline_bytes = self.load_baseline(project_id, url)

        if not baseline_bytes:
            return DiffResult(
                url=url, baseline_exists=False, diff_score=0.0,
                diff_pixel_count=0, diff_image_b64=None, is_regression=False,
                threshold=self.threshold, baseline_id=baseline_id,
                message="No baseline exists — this screenshot will become the baseline.",
            )

        # Load both images
        current_bytes = base64.b64decode(current_b64)
        img_current = Image.open(io.BytesIO(current_bytes)).convert("RGB")
        img_baseline = Image.open(io.BytesIO(baseline_bytes)).convert("RGB")

        # Resize to same dimensions (use larger of the two)
        target_w = max(img_current.width, img_baseline.width)
        target_h = max(img_current.height, img_baseline.height)
        img_current = img_current.resize((target_w, target_h), Image.LANCZOS)
        img_baseline = img_baseline.resize((target_w, target_h), Image.LANCZOS)

        # Pixel diff
        arr_current = np.array(img_current, dtype=np.int32)
        arr_baseline = np.array(img_baseline, dtype=np.int32)
        diff_arr = np.abs(arr_current - arr_baseline)

        # A pixel is "changed" if any channel differs by more than 10
        changed_mask = diff_arr.max(axis=2) > 10
        diff_pixel_count = int(changed_mask.sum())
        total_pixels = target_w * target_h
        diff_score = round(diff_pixel_count / total_pixels, 4)

        # Generate diff image (red highlights on grayscale base)
        diff_image_b64 = self._make_diff_image(img_baseline, changed_mask)

        is_regression = diff_score > self.threshold

        return DiffResult(
            url=url,
            baseline_exists=True,
            diff_score=diff_score,
            diff_pixel_count=diff_pixel_count,
            diff_image_b64=diff_image_b64,
            is_regression=is_regression,
            threshold=self.threshold,
            baseline_id=baseline_id,
            message=(
                f"{'⚠️ REGRESSION DETECTED' if is_regression else '✅ No regression'}: "
                f"{diff_score:.2%} pixels changed ({diff_pixel_count:,} px)"
            ),
        )

    def _make_diff_image(self, baseline_img, changed_mask) -> str:
        """Create a diff visualization: grayscale base + red highlights."""
        try:
            from PIL import Image
            import numpy as np

            # Grayscale base
            gray = np.array(baseline_img.convert("L"))
            h, w = gray.shape

            # RGB: gray background, red where changed
            rgb = np.stack([gray, gray, gray], axis=2)
            rgb[changed_mask, 0] = 255   # Red channel
            rgb[changed_mask, 1] = 0     # Clear green
            rgb[changed_mask, 2] = 0     # Clear blue

            diff_img = Image.fromarray(rgb.astype(np.uint8), "RGB")

            # Compress to JPEG for smaller payload
            buf = io.BytesIO()
            diff_img.save(buf, format="JPEG", quality=70)
            return base64.b64encode(buf.getvalue()).decode()
        except Exception as e:
            logger.warning(f"Diff image generation failed: {e}")
            return ""

    # ── Full run comparison ───────────────────────────────────

    async def run_comparison(
        self,
        project_id: str,
        run_id: str,
        urls: List[str],
        update_baselines: bool = False,
    ) -> List[DiffResult]:
        """Capture + compare all URLs. Optionally update baselines."""
        screenshots = await self.capture_pages(urls)
        results = []

        for shot in screenshots:
            if update_baselines or not self.load_baseline(project_id, shot.url):
                self.save_baseline(project_id, shot.url, shot.screenshot_b64)
                results.append(DiffResult(
                    url=shot.url, baseline_exists=False, diff_score=0.0,
                    diff_pixel_count=0, diff_image_b64=None, is_regression=False,
                    threshold=self.threshold,
                    baseline_id=self._baseline_id(project_id, shot.url),
                    message="Baseline created.",
                ))
            else:
                result = self.compare(project_id, shot.url, shot.screenshot_b64)
                results.append(result)

        regressions = sum(1 for r in results if r.is_regression)
        logger.info(f"Visual regression run {run_id}: {regressions}/{len(results)} regressions found")
        return results


visual_engine = VisualRegressionEngine()
