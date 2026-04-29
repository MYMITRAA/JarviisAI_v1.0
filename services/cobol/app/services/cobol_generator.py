"""
COBOL AI Test Generator.

Uses Claude to:
1. Read the analyzed COBOL program structure
2. Generate JCL test job stubs
3. Generate COBOL test driver programs
4. Document each paragraph in plain English
5. Identify high-risk areas for human review
6. Suggest GnuCOBOL-compatible unit tests
"""

import json
import logging
from typing import Dict, List, Optional, Any
from tenacity import retry, stop_after_attempt, wait_exponential

from app.services.cobol_analyzer import CobolProgram, CobolParagraph
from app.core.config import settings

logger = logging.getLogger("jarviis.cobol.generator")


class CobolTestGenerator:

    def __init__(self):
        self._client = None

    def _get_client(self):
        if not self._client and settings.ANTHROPIC_API_KEY:
            import anthropic
            self._client = anthropic.AsyncAnthropic(api_key=settings.ANTHROPIC_API_KEY)
        return self._client

    async def generate(self, program: CobolProgram, source_snippet: str = "") -> Dict[str, Any]:
        """
        Generate comprehensive test artifacts for a COBOL program.

        Returns:
          test_plan: What needs to be tested
          jcl_test_stub: JCL to run tests on mainframe
          cobol_driver: COBOL test driver program
          paragraph_docs: Plain English docs for each paragraph
          gnucobol_tests: GnuCOBOL unit test stubs (for local testing)
          risk_areas: High-risk areas requiring human attention
        """
        client = self._get_client()
        if not client:
            return self._offline_analysis(program)

        prompt = self._build_prompt(program, source_snippet)
        response = await self._call_claude(client, prompt)

        try:
            # Strip any markdown fences
            text = response.strip()
            if text.startswith("```"):
                text = text.split("```", 2)[1]
                if text.startswith("json"):
                    text = text[4:]
            text = text.rstrip("`").strip()
            return json.loads(text)
        except json.JSONDecodeError:
            logger.warning("Could not parse AI JSON response — returning structured fallback")
            return {
                "test_plan": {"summary": response[:1000], "total_test_cases": 0},
                "jcl_test_stub": self._default_jcl(program),
                "cobol_driver": self._default_driver(program),
                "paragraph_docs": {},
                "gnucobol_tests": "",
                "risk_areas": program.warnings,
                "raw_ai_response": response,
            }

    def _build_prompt(self, program: CobolProgram, source_snippet: str) -> str:
        para_summary = "\n".join(
            f"  - {p.name} (CC={p.cyclomatic_complexity}, PERFORMs={p.perform_count}, CALLs={p.calls})"
            for p in program.paragraphs[:30]
        )
        data_summary = "\n".join(
            f"  - {d.level:02d} {d.name} PIC {d.picture or 'GROUP'}"
            for d in program.data_items[:30]
        )

        return f"""You are an expert COBOL testing specialist with 30 years of mainframe experience.

Analyze this COBOL program and generate comprehensive test artifacts.

## Program: {program.program_id}
- Source file: {program.source_file}
- Total lines: {program.total_lines}
- Cyclomatic complexity: {program.cyclomatic_complexity}
- Called sub-programs: {program.called_programs}
- COPY members: {program.copy_members}
- Dead paragraphs: {program.dead_paragraphs}
- Warnings: {program.warnings}

## Paragraphs
{para_summary}

## Key Data Items
{data_summary}

## Source Snippet (first 50 lines)
{source_snippet[:3000]}

---

Generate a complete JSON response with these exact fields:

{{
  "test_plan": {{
    "summary": "Brief description of what this program does based on structure",
    "total_test_cases": 0,
    "test_categories": ["happy_path", "boundary", "error_handling", "integration"],
    "priority_paragraphs": ["list of 5 highest-risk paragraphs to test first"],
    "estimated_effort_days": 0
  }},
  "jcl_test_stub": "Complete JCL job to compile and run the COBOL program in test mode",
  "cobol_driver": "Complete COBOL test driver program (COBOL-85 compatible) that calls {program.program_id} with test data",
  "paragraph_docs": {{
    "PARAGRAPH-NAME": "Plain English description of what this paragraph does"
  }},
  "gnucobol_tests": "GnuCOBOL cobol-unit-test compatible test stubs (TAP output)",
  "risk_areas": ["list of specific high-risk areas requiring manual review"],
  "modernization_hints": ["suggested modernization steps if applicable"]
}}

IMPORTANT:
- Return ONLY the JSON object — no markdown, no explanation
- JCL must be syntactically correct IBM mainframe JCL
- COBOL driver must compile cleanly under COBOL-85
- Paragraph docs must be written for business analysts (non-technical)
- Risk areas should be specific (e.g. "CALC-TAX paragraph: complex nested IF with 8 conditions")
"""

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(min=1, max=8))
    async def _call_claude(self, client, prompt: str) -> str:
        response = await client.messages.create(
            model=settings.PRIMARY_MODEL,
            max_tokens=8192,
            temperature=0.1,
            system="You are a COBOL testing expert. Respond only with valid JSON.",
            messages=[{"role": "user", "content": prompt}],
        )
        return response.content[0].text

    def _offline_analysis(self, program: CobolProgram) -> Dict[str, Any]:
        """Fallback when AI is not available — generate basic artifacts from analysis."""
        docs = {p.name: f"Paragraph {p.name} — {len(p.lines)} lines, CC={p.cyclomatic_complexity}" for p in program.paragraphs}
        return {
            "test_plan": {
                "summary": f"COBOL program {program.program_id} — {program.total_lines} lines, {len(program.paragraphs)} paragraphs",
                "total_test_cases": len(program.paragraphs),
                "test_categories": ["unit", "integration"],
                "priority_paragraphs": [
                    p.name for p in sorted(program.paragraphs, key=lambda x: -x.cyclomatic_complexity)[:5]
                ],
                "estimated_effort_days": max(1, program.cyclomatic_complexity // 10),
            },
            "jcl_test_stub": self._default_jcl(program),
            "cobol_driver": self._default_driver(program),
            "paragraph_docs": docs,
            "gnucobol_tests": self._default_gnucobol(program),
            "risk_areas": program.warnings or [f"Review high-complexity paragraphs: {[p.name for p in program.paragraphs if p.cyclomatic_complexity > 5]}"],
            "modernization_hints": ["Consider structured walkthroughs for paragraphs using GO TO"],
        }

    def _default_jcl(self, prog: CobolProgram) -> str:
        return f"""//JARTEST  JOB (ACCT),'JARVIISAI TEST',CLASS=A,MSGCLASS=X
//**
//** GENERATED BY JARVIISAI - COBOL TEST JOB
//** PROGRAM: {prog.program_id}
//**
//COMPILE EXEC IGYWCL,
//         PARM.COBOL='RENT,LIB,OBJECT,XREF'
//COBOL.SYSIN DD *
* Test source inserted here
/*
//LKED.SYSLMOD DD DSN=TEST.LOADLIB({prog.program_id}),DISP=SHR
//GO.SYSOUT  DD SYSOUT=*
//GO.SYSIN   DD *
* Test input data
/*
//"""

    def _default_driver(self, prog: CobolProgram) -> str:
        return f"""       IDENTIFICATION DIVISION.
       PROGRAM-ID. {prog.program_id}TST.
       AUTHOR. JARVIISAI-GENERATED.
      *
      * AUTO-GENERATED TEST DRIVER FOR {prog.program_id}
      * Generated by JarviisAI COBOL Testing Engine
      *
       DATA DIVISION.
       WORKING-STORAGE SECTION.
       01 WS-TEST-NAME     PIC X(50).
       01 WS-TESTS-PASSED  PIC 9(4) VALUE ZEROS.
       01 WS-TESTS-FAILED  PIC 9(4) VALUE ZEROS.
       01 WS-RETURN-CODE   PIC 9(4) VALUE ZEROS.
       PROCEDURE DIVISION.
       000-MAIN.
           PERFORM 100-SETUP
           PERFORM 200-RUN-TESTS
           PERFORM 900-REPORT
           STOP RUN.
       100-SETUP.
           MOVE 'TEST SETUP' TO WS-TEST-NAME
           DISPLAY 'JarviisAI COBOL Test Runner'
           DISPLAY 'Program Under Test: {prog.program_id}'.
       200-RUN-TESTS.
           MOVE 'TEST-CASE-001' TO WS-TEST-NAME
           CALL '{prog.program_id}'
               ON EXCEPTION
                   ADD 1 TO WS-TESTS-FAILED
               NOT ON EXCEPTION
                   ADD 1 TO WS-TESTS-PASSED
           END-CALL.
       900-REPORT.
           DISPLAY 'Tests Passed: ' WS-TESTS-PASSED
           DISPLAY 'Tests Failed: ' WS-TESTS-FAILED.
"""

    def _default_gnucobol(self, prog: CobolProgram) -> str:
        return f"""# JarviisAI GnuCOBOL Tests for {prog.program_id}
# Run with: cobol-unit-test {prog.program_id.lower()}_test.cbl

TESTSUITE '{prog.program_id} Unit Tests'

TESTCASE 'Program initializes without error'
    CALL '{prog.program_id}'
    ASSERT EQUAL ZERO RETURN-CODE

TESTCASE 'Missing data handled gracefully'
    MOVE SPACES TO INPUT-AREA
    CALL '{prog.program_id}'
    ASSERT EQUAL ZERO RETURN-CODE
"""


generator = CobolTestGenerator()
