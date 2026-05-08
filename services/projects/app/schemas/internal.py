from pydantic import BaseModel
from typing import Optional, Dict, Any, List


class CompleteRequest(BaseModel):
    project_id: str
    status: str
    total_tests: int
    passed_tests: int
    failed_tests: int
    skipped_tests: int
    duration_seconds: Optional[float] = None
    error_message: Optional[str] = None
    test_cases: List[dict] = []