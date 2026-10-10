import time
from app.change_analyzer import analyze_changes
from app.change_detector import detect_changes
from app.health_monitor import APIHealthMonitor
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from typing import Any
from app.mock_apis import (
    SimulatedAPIError,
    call_weather_api,
    get_weather_response,
)
from app.observer import APIObserver
from app.resilience import call_with_retry

app = FastAPI(
    title="KintsuTech",
    description="API change detection and resilience monitoring.",
    version="0.1.0",
)

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
    """Check whether the backend is running."""
    return {
        "status": "ok",
        "service": "KintsuTech",
    }


@app.get("/api/v1/mock/weather")
def mock_weather(version: int = 1):
    """Return a simulated weather API response."""
    try:
        return get_weather_response(version=version)
    except ValueError as exc:
        raise HTTPException(
            status_code=400,
            detail=str(exc),
        ) from exc



@app.post("/api/v1/observe/weather")
def observe_weather(version: int = 1):
    """Observe a weather response and detect changes."""
    try:
        response = get_weather_response(version=version)
    except ValueError as exc:
        raise HTTPException(
            status_code=400,
            detail=str(exc),
        ) from exc

    observation = observer.capture("weather", response)

    return {
        "observation": observation,
    }


@app.post("/api/v1/observe/weather/reset")
def reset_weather_observation():
    """Reset the weather baseline to version 1."""
    baseline = get_weather_response(version=1)
    observer.update_baseline("weather", baseline)

    return {
        "status": "success",
        "message": "Weather baseline reset to version 1.",
        "baseline": baseline,
    }



@app.get("/api/v1/resilience/weather")
def resilient_weather(
    mode: str = "success",
    max_attempts: int = 3,
):
    """Call the simulated weather API with retries and track health."""
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
        # Invalid input isn't counted as an API failure.
        raise HTTPException(
            status_code=400,
            detail=str(exc),
        ) from exc

    except (
        TimeoutError,
        ConnectionError,
        SimulatedAPIError,
    ) as exc:
        elapsed_ms = (time.perf_counter() - start_time) * 1000
        health_monitor.record_failure(
            "weather",
            elapsed_ms,
            str(exc),
        )

        raise HTTPException(
            status_code=503,
            detail=f"Weather API failed after retries: {exc}",
        ) from exc

@app.get("/api/v1/monitor/health")
def get_weather_health():
    """Return health statistics for the weather API."""
    return health_monitor.get_service_health("weather")


@app.get("/api/v1/monitor/incidents")
def get_weather_incidents():
    """Return recent weather API incidents."""
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
    """Compare two API responses and return a risk analysis."""
    detection_result = detect_changes(baseline, current)
    return analyze_changes(detection_result)
