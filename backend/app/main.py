from app.mock_apis import call_weather_api
from app.resilience import call_with_retry
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from app.mock_apis import get_weather_response
from app.observer import APIObserver

app = FastAPI(
    title="KintsuTech",
    description="Autonomous API Resilience Platform",
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

observer = APIObserver()


@app.get("/api/v1/health")
def health():
    return {
        "status": "ok",
        "service": "KintsuTech",
        "version": "0.1.0",
    }


@app.get("/api/v1/mock/weather")
def mock_weather(version: int = 1):
    try:
        return get_weather_response(version)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/api/v1/observe/weather")
def observe_weather(version: int = 1):
    try:
        response = get_weather_response(version)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    result = observer.capture("weather", response)

    return {
        "observed_response": response,
        "observation": result,
    }


@app.post("/api/v1/observe/weather/reset")
def reset_weather_baseline():
    """Reset the weather baseline using version 1."""
    observer.update_baseline("weather", get_weather_response(1))

    return {
        "status": "ok",
        "message": "Weather baseline reset to version 1",
    }


@app.get("/api/v1/resilience/weather")
def resilient_weather(mode: str = "success", max_attempts: int = 3):
    try:
        response = call_with_retry(
            lambda: call_weather_api(mode),
            max_attempts=max_attempts,
        )
        return {
            "status": "success",
            "attempt_limit": max_attempts,
            "data": response,
        }
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except (TimeoutError, ConnectionError, Exception) as exc:
        raise HTTPException(
            status_code=503,
            detail=f"Weather API failed after retries: {exc}",
        ) from exc
