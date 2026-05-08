import asyncio
import httpx
from fastapi import FastAPI
from pydantic import BaseModel

app = FastAPI()

PROJECTS_URL = "http://projects:8002"

HEADERS = {
    "X-Internal-Secret": "s2a3d4f5g6h7j8k9l1w2e3s4f5v3c6n3cfds23"
}


class ExecuteRequest(BaseModel):
    run_id: str
    project_id: str | None = None


async def run_test(run_id: str, project_id: str | None = None):

    async with httpx.AsyncClient() as client:

        print("Starting run:", run_id)

        # update running
        res = await client.patch(
            f"{PROJECTS_URL}/api/v1/internal/runs/{run_id}/status",
            json={"status": "running"},
            headers=HEADERS
        )

        print("STATUS:", res.status_code, res.text)

        print("Running test...")
        await asyncio.sleep(5)

        # fake result
        passed_tests = 50
        failed_tests = 0

        status = "failed" if failed_tests > 0 else "passed"

        print("FINAL STATUS SENT:", status)

        # complete run
        res = await client.post(
            f"{PROJECTS_URL}/api/v1/internal/runs/{run_id}/complete",
            json={
                "project_id": project_id or "fca467e9-0621-4896-bc6a-47e3808711d3",
                "status": status,
                "total_tests": 50,
                "passed_tests": passed_tests,
                "failed_tests": failed_tests,
                "skipped_tests": 0
            },
            headers=HEADERS
        )

        print("COMPLETE:", res.status_code, res.text)

        print("Run completed")


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.post("/api/v1/execute")
async def execute(data: ExecuteRequest):

    asyncio.create_task(
        run_test(data.run_id, data.project_id)
    )

    return {
        "message": "Execution started",
        "run_id": data.run_id
    }