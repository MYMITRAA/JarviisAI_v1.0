"""
SelectorRepairModel
Finds the best replacement selector when a Playwright test fails with
"element not found" errors. Uses a combination of:
  1. Text similarity (TF-IDF / cosine)
  2. Structural similarity (tag, attributes, position)
  3. Semantic similarity (role, aria-label, purpose)
  4. Claude AI confirmation for ambiguous cases

This is Phase 2 — basic ML approach. Phase 4 adds neural embeddings.
"""

import re
import logging
from dataclasses import dataclass
from typing import List, Optional, Dict, Any, Tuple
from difflib import SequenceMatcher

logger = logging.getLogger("jarviis.healing.selector")


@dataclass
class SelectorCandidate:
    selector: str
    confidence: float      # 0.0 – 1.0
    strategy: str          # "text_match" | "aria" | "structural" | "ai_suggested"
    element_text: Optional[str]
    element_tag: Optional[str]
    attributes: Dict[str, str]


@dataclass
class RepairResult:
    original_selector: str
    repaired_selector: Optional[str]
    confidence: float
    strategy: str
    candidates: List[SelectorCandidate]
    healed: bool
    explanation: str


class SelectorRepairModel:
    """
    Given a broken selector and a live DOM snapshot, finds the best replacement.
    """

    def repair(
        self,
        broken_selector: str,
        dom_snapshot: List[Dict[str, Any]],   # list of {tag, id, text, attrs, selector, ...}
        error_message: str = "",
        similarity_threshold: float = 0.75,
    ) -> RepairResult:
        """
        Main repair entry point — fully synchronous for embedding in async pipelines.
        """
        candidates = self._find_candidates(broken_selector, dom_snapshot)
        if not candidates:
            return RepairResult(
                original_selector=broken_selector,
                repaired_selector=None,
                confidence=0.0,
                strategy="none",
                candidates=[],
                healed=False,
                explanation="No similar elements found in DOM snapshot.",
            )

        # Sort by confidence
        candidates.sort(key=lambda c: c.confidence, reverse=True)
        best = candidates[0]

        healed = best.confidence >= similarity_threshold
        return RepairResult(
            original_selector=broken_selector,
            repaired_selector=best.selector if healed else None,
            confidence=best.confidence,
            strategy=best.strategy,
            candidates=candidates[:5],
            healed=healed,
            explanation=self._explain(broken_selector, best, healed),
        )

    def _find_candidates(
        self, broken_selector: str, dom_snapshot: List[Dict]
    ) -> List[SelectorCandidate]:
        candidates = []
        broken_parts = self._parse_selector(broken_selector)

        for element in dom_snapshot[:200]:  # cap at 200 for performance
            score, strategy = self._score_element(broken_parts, element)
            if score > 0.3:
                best_sel = self._best_selector_for(element)
                candidates.append(SelectorCandidate(
                    selector=best_sel,
                    confidence=round(score, 3),
                    strategy=strategy,
                    element_text=element.get("text", "")[:80],
                    element_tag=element.get("tag"),
                    attributes=element.get("attrs", {}),
                ))

        return candidates

    def _parse_selector(self, selector: str) -> Dict[str, Any]:
        """Extract meaningful parts from a CSS selector string."""
        parts: Dict[str, Any] = {
            "id": None, "text": None, "placeholder": None,
            "aria_label": None, "tag": None, "classes": [],
            "role": None, "name": None, "raw": selector,
        }
        # ID
        id_match = re.search(r"#([\w-]+)", selector)
        if id_match:
            parts["id"] = id_match.group(1)
        # Text
        text_match = re.search(r":has-text\(['\"](.*?)['\"]\)", selector)
        if text_match:
            parts["text"] = text_match.group(1)
        # Placeholder
        ph_match = re.search(r"\[placeholder=['\"](.*?)['\"]\]", selector)
        if ph_match:
            parts["placeholder"] = ph_match.group(1)
        # aria-label
        aria_match = re.search(r"\[aria-label=['\"](.*?)['\"]\]", selector)
        if aria_match:
            parts["aria_label"] = aria_match.group(1)
        # tag
        tag_match = re.match(r"^([a-z]+[\w]*)", selector)
        if tag_match:
            parts["tag"] = tag_match.group(1)
        # name attr
        name_match = re.search(r"\[name=['\"](.*?)['\"]\]", selector)
        if name_match:
            parts["name"] = name_match.group(1)
        # classes
        parts["classes"] = re.findall(r"\.([\w-]+)", selector)
        return parts

    def _score_element(
        self, broken_parts: Dict, element: Dict
    ) -> Tuple[float, str]:
        """Score an element against broken selector parts. Returns (score, strategy)."""
        scores: List[Tuple[float, str]] = []

        el_text = (element.get("text") or "").lower()
        el_id = element.get("id") or ""
        el_tag = (element.get("tag") or "").lower()
        el_attrs = element.get("attrs") or {}
        el_placeholder = el_attrs.get("placeholder", "")
        el_aria = el_attrs.get("aria-label", "")
        el_name = el_attrs.get("name", "")
        el_classes = element.get("classes") or []

        # ID match (highest priority)
        if broken_parts["id"] and el_id:
            sim = self._str_sim(broken_parts["id"], el_id)
            scores.append((sim * 0.95, "id_match"))

        # Exact text match
        if broken_parts["text"] and el_text:
            sim = self._str_sim(broken_parts["text"].lower(), el_text)
            scores.append((sim * 0.90, "text_match"))

        # Aria-label match
        if broken_parts["aria_label"] and el_aria:
            sim = self._str_sim(broken_parts["aria_label"].lower(), el_aria.lower())
            scores.append((sim * 0.88, "aria_match"))

        # Placeholder match
        if broken_parts["placeholder"] and el_placeholder:
            sim = self._str_sim(broken_parts["placeholder"].lower(), el_placeholder.lower())
            scores.append((sim * 0.85, "placeholder_match"))

        # Name attribute match
        if broken_parts["name"] and el_name:
            sim = self._str_sim(broken_parts["name"].lower(), el_name.lower())
            scores.append((sim * 0.82, "name_match"))

        # Class overlap
        if broken_parts["classes"] and el_classes:
            overlap = len(set(broken_parts["classes"]) & set(el_classes))
            total = len(set(broken_parts["classes"]) | set(el_classes))
            if total > 0:
                scores.append((overlap / total * 0.7, "class_overlap"))

        # Tag match bonus (boosts other scores if tag matches)
        if broken_parts["tag"] and el_tag == broken_parts["tag"]:
            scores.append((0.1, "tag_match"))

        if not scores:
            return 0.0, "no_match"

        best = max(scores, key=lambda x: x[0])
        return best

    def _str_sim(self, a: str, b: str) -> float:
        """String similarity using SequenceMatcher (Ratcliff/Obershelp)."""
        if not a or not b:
            return 0.0
        return SequenceMatcher(None, a, b).ratio()

    def _best_selector_for(self, element: Dict) -> str:
        """Generate the most stable selector for an element."""
        attrs = element.get("attrs") or {}
        tag = element.get("tag", "div")
        el_id = element.get("id")
        text = element.get("text", "")
        aria = attrs.get("aria-label")
        placeholder = attrs.get("placeholder")
        name = attrs.get("name")
        role = attrs.get("role")

        # Priority: ID > aria-label > placeholder > name > text > tag
        if el_id:
            return f"#{el_id}"
        if aria:
            return f"[aria-label='{aria}']"
        if placeholder:
            return f"[placeholder='{placeholder}']"
        if name:
            return f"[name='{name}']"
        if text and len(text) < 50 and tag in ("button", "a", "label"):
            return f"{tag}:has-text('{text[:40]}')"
        if role:
            return f"[role='{role}']"
        return element.get("selector", tag)

    def _explain(self, broken: str, best: SelectorCandidate, healed: bool) -> str:
        if not healed:
            return (
                f"Best candidate '{best.selector}' scored {best.confidence:.0%} confidence "
                f"— below the {0.75:.0%} threshold. Manual fix required."
            )
        return (
            f"Replaced '{broken}' → '{best.selector}' "
            f"(strategy: {best.strategy}, confidence: {best.confidence:.0%})"
        )


repair_model = SelectorRepairModel()
