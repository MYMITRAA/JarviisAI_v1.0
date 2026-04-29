"""
COBOL Source Analyzer.

Parses COBOL source files (COBOL-85, COBOL 2002, COBOL 2014) to extract:
  - PROGRAM-ID, divisions, sections, paragraphs
  - DATA DIVISION items (WORKING-STORAGE, FILE SECTION, LINKAGE SECTION)
  - PROCEDURE DIVISION paragraphs and their logic
  - CALL statements (sub-program dependencies)
  - Complexity metrics (McCabe cyclomatic, lines of code)
  - Batch JCL job step dependencies

This information feeds Claude AI for:
  1. Generating unit test stubs (JCL + COBOL test drivers)
  2. Identifying dead code and unreachable paragraphs
  3. Documenting program logic in plain English
  4. Suggesting modernization targets

Note: Full COBOL execution testing requires a mainframe or
GnuCOBOL/IBM COBOL compiler environment.
"""

import re
import logging
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any

logger = logging.getLogger("jarviis.cobol.analyzer")


@dataclass
class CobolDataItem:
    level: int
    name: str
    picture: Optional[str]
    value: Optional[str]
    occurs: Optional[int]
    redefines: Optional[str]
    section: str   # WORKING-STORAGE | FILE | LINKAGE


@dataclass
class CobolParagraph:
    name: str
    lines: List[str]
    perform_count: int        # how many times PERFORMed from elsewhere
    calls: List[str]          # external CALLs made
    gotos: List[str]          # GOTO targets (complexity indicator)
    cyclomatic_complexity: int


@dataclass
class CobolProgram:
    program_id: str
    source_file: str
    total_lines: int
    comment_lines: int

    # Divisions
    identification_items: Dict[str, str]
    data_items: List[CobolDataItem]
    paragraphs: List[CobolParagraph]

    # Dependencies
    called_programs: List[str]
    copy_members: List[str]   # COPY statements

    # Metrics
    cyclomatic_complexity: int
    dead_paragraphs: List[str]
    warnings: List[str]


class CobolAnalyzer:

    def analyze(self, source: str, filename: str = "program.cbl") -> CobolProgram:
        """Parse a COBOL source file and return structured metadata."""
        lines = source.splitlines()
        clean_lines = self._normalize(lines)

        program_id = self._extract_program_id(clean_lines)
        ident_items = self._extract_identification(clean_lines)
        data_items = self._extract_data_items(clean_lines)
        paragraphs = self._extract_paragraphs(clean_lines)
        called_programs = self._extract_calls(clean_lines)
        copy_members = self._extract_copy(clean_lines)
        dead = self._find_dead_paragraphs(paragraphs, clean_lines)
        warnings = self._generate_warnings(paragraphs, data_items, clean_lines)

        total_complexity = sum(p.cyclomatic_complexity for p in paragraphs)
        comment_count = sum(1 for l in lines if l[6:7] == "*" if len(l) > 6)

        return CobolProgram(
            program_id=program_id,
            source_file=filename,
            total_lines=len(lines),
            comment_lines=comment_count,
            identification_items=ident_items,
            data_items=data_items,
            paragraphs=paragraphs,
            called_programs=called_programs,
            copy_members=copy_members,
            cyclomatic_complexity=total_complexity,
            dead_paragraphs=dead,
            warnings=warnings,
        )

    def _normalize(self, lines: List[str]) -> List[str]:
        """Strip sequence numbers (cols 1-6), indicator (col 7), and continuation markers."""
        result = []
        for line in lines:
            if len(line) < 7:
                result.append(line.strip())
                continue
            indicator = line[6:7]
            if indicator == "*":   # Comment
                result.append("")
                continue
            # Fixed format: cols 8-72 are the program text
            content = line[7:72].rstrip() if len(line) > 7 else ""
            result.append(content.strip())
        return result

    def _extract_program_id(self, lines: List[str]) -> str:
        for line in lines:
            m = re.match(r"PROGRAM-ID\s*\.\s*(\S+)", line, re.IGNORECASE)
            if m:
                return m.group(1).rstrip(".")
        return "UNKNOWN"

    def _extract_identification(self, lines: List[str]) -> Dict[str, str]:
        items = {}
        keywords = ["AUTHOR", "INSTALLATION", "DATE-WRITTEN", "DATE-COMPILED", "SECURITY"]
        for line in lines:
            for kw in keywords:
                m = re.match(rf"{kw}\s*\.\s*(.+)", line, re.IGNORECASE)
                if m:
                    items[kw] = m.group(1).strip()
        return items

    def _extract_data_items(self, lines: List[str]) -> List[CobolDataItem]:
        items = []
        current_section = "WORKING-STORAGE"
        in_data_div = False

        for line in lines:
            upper = line.upper()
            if "DATA DIVISION" in upper:
                in_data_div = True
            if "PROCEDURE DIVISION" in upper:
                break
            if not in_data_div:
                continue

            if "WORKING-STORAGE SECTION" in upper:
                current_section = "WORKING-STORAGE"
            elif "FILE SECTION" in upper:
                current_section = "FILE"
            elif "LINKAGE SECTION" in upper:
                current_section = "LINKAGE"

            # Data item: level + name + optional PIC/VALUE
            m = re.match(r"(\d{2})\s+(\S+)(.*)", line)
            if m:
                level = int(m.group(1))
                name = m.group(2).rstrip(".")
                rest = m.group(3).upper()

                pic = None
                pic_m = re.search(r"PIC(?:TURE)?\s+(?:IS\s+)?(\S+)", rest)
                if pic_m:
                    pic = pic_m.group(1)

                val = None
                val_m = re.search(r"VALUE\s+(?:IS\s+)?(.+?)(?:\s*\.|$)", rest)
                if val_m:
                    val = val_m.group(1).strip()

                occ = None
                occ_m = re.search(r"OCCURS\s+(\d+)", rest)
                if occ_m:
                    occ = int(occ_m.group(1))

                red = None
                red_m = re.search(r"REDEFINES\s+(\S+)", rest)
                if red_m:
                    red = red_m.group(1)

                items.append(CobolDataItem(
                    level=level, name=name, picture=pic,
                    value=val, occurs=occ, redefines=red,
                    section=current_section,
                ))
        return items

    def _extract_paragraphs(self, lines: List[str]) -> List[CobolParagraph]:
        paragraphs = []
        in_proc = False
        current_para = None
        current_lines = []

        for line in lines:
            upper = line.upper()
            if "PROCEDURE DIVISION" in upper:
                in_proc = True
                continue
            if not in_proc:
                continue

            # Paragraph header: a label at col 8 followed by a period
            m = re.match(r"^([A-Z][A-Z0-9\-]+)\s*\.", line, re.IGNORECASE)
            if m and not any(kw in upper for kw in ("PERFORM", "MOVE", "IF", "EVALUATE", "ADD", "SUBTRACT")):
                if current_para:
                    paragraphs.append(self._build_paragraph(current_para, current_lines))
                current_para = m.group(1)
                current_lines = []
            elif current_para:
                current_lines.append(line)

        if current_para and current_lines:
            paragraphs.append(self._build_paragraph(current_para, current_lines))

        # Mark PERFORM counts
        all_text = "\n".join(lines).upper()
        for para in paragraphs:
            para.perform_count = len(re.findall(rf"\bPERFORM\s+{re.escape(para.name)}\b", all_text))

        return paragraphs

    def _build_paragraph(self, name: str, lines: List[str]) -> CobolParagraph:
        text = "\n".join(lines).upper()
        calls = re.findall(r"\bCALL\s+'?\"?([A-Z0-9\-]+)'?\"?", text)
        gotos = re.findall(r"\bGO\s+TO\s+([A-Z0-9\-]+)", text)

        # Cyclomatic = 1 + number of decision points
        decisions = (
            len(re.findall(r"\bIF\b", text)) +
            len(re.findall(r"\bWHEN\b", text)) +
            len(re.findall(r"\bUNTIL\b", text)) +
            len(re.findall(r"\bAT\s+END\b", text)) +
            len(re.findall(r"\bON\s+(?:EXCEPTION|OVERFLOW|SIZE\s+ERROR)\b", text))
        )

        return CobolParagraph(
            name=name,
            lines=lines,
            perform_count=0,  # will be set after all paragraphs extracted
            calls=list(set(calls)),
            gotos=list(set(gotos)),
            cyclomatic_complexity=1 + decisions,
        )

    def _extract_calls(self, lines: List[str]) -> List[str]:
        calls = []
        for line in lines:
            for m in re.finditer(r"\bCALL\s+'?\"?([A-Z0-9\-]+)'?\"?", line, re.IGNORECASE):
                calls.append(m.group(1))
        return list(set(calls))

    def _extract_copy(self, lines: List[str]) -> List[str]:
        members = []
        for line in lines:
            m = re.search(r"\bCOPY\s+([A-Z0-9\-]+)", line, re.IGNORECASE)
            if m:
                members.append(m.group(1))
        return list(set(members))

    def _find_dead_paragraphs(self, paragraphs: List[CobolParagraph], lines: List[str]) -> List[str]:
        all_text = "\n".join(lines).upper()
        dead = []
        for para in paragraphs:
            if para.name in ("MAIN-LOGIC", "MAIN", "START", "000-MAIN", "HOUSEKEEPING"):
                continue
            if para.perform_count == 0:
                # Check if referenced in any PERFORM or GO TO
                if not re.search(rf"\b(?:PERFORM|GO\s+TO)\s+{re.escape(para.name)}\b", all_text):
                    dead.append(para.name)
        return dead

    def _generate_warnings(
        self, paragraphs: List[CobolParagraph], data: List[CobolDataItem], lines: List[str]
    ) -> List[str]:
        warnings = []
        text = "\n".join(lines).upper()

        # High complexity
        for para in paragraphs:
            if para.cyclomatic_complexity > 10:
                warnings.append(f"HIGH_COMPLEXITY: {para.name} (CC={para.cyclomatic_complexity})")
            if para.gotos:
                warnings.append(f"GOTO_USAGE: {para.name} uses GO TO — consider structured rewrite")

        # Global GOTO (ALTERCABLE)
        if re.search(r"\bALTER\b", text):
            warnings.append("ALTER_USED: ALTER statement found — extremely difficult to test")

        # Long programs
        if len(lines) > 3000:
            warnings.append(f"LONG_PROGRAM: {len(lines)} lines — consider splitting")

        # PIC X/9 mismatch indicators
        move_count = len(re.findall(r"\bMOVE\b", text))
        if move_count > 200:
            warnings.append(f"EXCESSIVE_MOVES: {move_count} MOVE statements — potential data flow issue")

        return warnings


analyzer = CobolAnalyzer()
