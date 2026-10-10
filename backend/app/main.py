import sys
import time
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from app.ai_adapter import AIAdapter
from app.ai_adapter import analyze_changes as analyze_with_adapter
from app.change_analyzer import analyze_changes
from app.change_detector import detect_changes
from app.health_monitor import APIHealthMonitor
from app.integration_schemas import ChangeAnalysisRequest, ChangeAnalysisResponse
from app.mock_apis import (
    SimulatedAPIError,
    call_weather_api,
    get_weather_response,
)
from app.observer import APIObserver
from app.resilience import call_with_retry


# Import the AI engine
PROJECT_ROOT = Path(__file__).resolve().parents[2]
AI_ENGINE_PATH = PROJECT_ROOT / "ai_engine"

if str(AI_ENGINE_PATH) not in sys.path:
    sys.path.insert(0, str(AI_ENGINE_PATH))

from change_workflow import run_change_workflow


# Request model for AI analysis
class AIAnalyzeRequest(BaseModel):
    baseline: dict[str, Any]
    current: dict[str, Any]
    behavior_report: dict[str, Any] | None = None
    text_diff: list[dict[str, str]] | None = None
    pagination_reports: list[dict[str, Any]] | None = None
    rate_limit_reports: list[dict[str, Any]] | None = None
    run_behavior_tests: bool = False


app = FastAPI(
    title="KintsuTech",
    description="API change detection and resilience monitoring.",
    version="0.1.0",
)

ai_adapter = AIAdapter(run_change_workflow)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://127.0.0.1:3000",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

observer = APIObserver()
health_monitor = APIHealthMonitor()


@app.get("/api/v1/health")
def health_check():
    return {
        "status": "ok",
        "service": "KintsuTech",
    }


@app.get("/api/v1/mock/weather")
def mock_weather(version: int = 1):
    try:
        return get_weather_response(version=version)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/api/v1/observe/weather")
def observe_weather(version: int = 1):
    try:
        response = get_weather_response(version=version)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    observation = observer.capture("weather", response)
    return {"observation": observation}


@app.post("/api/v1/observe/weather/reset")
def reset_weather_observation():
    baseline = get_weather_response(version=1)
    observer.update_baseline("weather", baseline)

    return {
        "status": "success",
        "message": "Weather baseline reset to version 1.",
        "baseline": baseline,
    }


@app.get("/api/v1/resilience/weather")
def resilient_weather(mode: str = "success", max_attempts: int = 3):
    start_time = time.perf_counter()

    try:
        response = call_with_retry(
            lambda: call_weather_api(mode),
            max_attempts=max_attempts,
        )

        elapsed_ms = (time.perf_counter() - start_time) * 1000
        health_monitor.record_success("weather", elapsed_ms)

        return {
            "status": "success",
            "attempt_limit": max_attempts,
            "data": response,
        }

    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    except (TimeoutError, ConnectionError, SimulatedAPIError) as exc:
        elapsed_ms = (time.perf_counter() - start_time) * 1000
        health_monitor.record_failure("weather", elapsed_ms, str(exc))

        raise HTTPException(
            status_code=503,
            detail=f"Weather API failed after retries: {exc}",
        ) from exc


@app.get("/api/v1/monitor/health")
def get_weather_health():
    return health_monitor.get_service_health("weather")


@app.get("/api/v1/monitor/incidents")
def get_weather_incidents():
    incidents = health_monitor.get_recent_incidents()

    return {
        "service": "weather",
        "incident_count": len(incidents),
        "incidents": incidents,
    }


@app.post("/api/v1/analyze/changes")
def analyze_api_changes(
    baseline: dict[str, Any],
    current: dict[str, Any],
):
    detection_result = detect_changes(baseline, current)
    return analyze_changes(detection_result)


@app.post("/api/v1/analyze/changes/ai")
def analyze_api_changes_with_ai(
    baseline: dict[str, Any],
    current: dict[str, Any],
):
    """Analyze API changes using the AI adapter."""
    try:
        detection_result = detect_changes(baseline, current)

        return analyze_with_adapter(
            service="weather",
            baseline=baseline,
            current=current,
            detected_changes=detection_result,
        )
    except Exception as exc:
        raise HTTPException(
            status_code=503,
            detail="AI change analysis is temporarily unavailable.",
        ) from exc


@app.post(
    "/api/v1/integrations/change-analysis",
    response_model=ChangeAnalysisResponse,
)
def integration_change_analysis(
    request: ChangeAnalysisRequest,
) -> ChangeAnalysisResponse:
    detection = detect_changes(request.baseline, request.current)
    analysis = analyze_changes(detection)

    return ChangeAnalysisResponse(
        service=request.service,
        has_changes=analysis["has_changes"],
        overall_risk=analysis["overall_risk"],
        change_count=analysis["change_count"],
        severity_counts=analysis["severity_counts"],
        changes=analysis["changes"],
    )


@app.post("/api/v1/ai/analyze")
def analyze_with_ai(payload: AIAnalyzeRequest):
    """Run unified API change detection and the gated repair workflow."""
    try:
        return run_change_workflow(
            baseline=payload.baseline,
            current=payload.current,
            behavior_report=payload.behavior_report,
            text_diff=payload.text_diff,
            pagination_reports=payload.pagination_reports,
            rate_limit_reports=payload.rate_limit_reports,
            run_behavior_tests=payload.run_behavior_tests,
        )
    except Exception as exc:
        raise HTTPException(
            status_code=503,
            detail="AI analysis is temporarily unavailable.",
        ) from exc
