
import subprocess
import sys
import time
from pathlib import Path

import httpx

from pagination_runner import run_pagination


PROJECT_ROOT = Path(__file__).resolve().parents[2]
API_SCRIPT = PROJECT_ROOT / "ai_engine" / "local_test_api.py"


def test_local_api_real_http_pagination():
    process = subprocess.Popen(
        [sys.executable, str(API_SCRIPT)],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )

    try:
        base_url = "http://127.0.0.1:8765"
        server_ready = False

        for _ in range(50):
            if process.poll() is not None:
                raise AssertionError("Local test API exited unexpectedly.")

            try:
                response = httpx.get(
                    f"{base_url}/products?limit=20",
                    timeout=0.2,
                )
                if response.status_code == 200:
                    server_ready = True
                    break
            except httpx.HTTPError:
                time.sleep(0.1)

        assert server_ready, "Local test API did not start in time."

        with httpx.Client(base_url=base_url, timeout=2) as client:
            result = run_pagination(
                client,
                "/products",
                query={"limit": 20},
                items_field="products",
            )

        assert result["status"] == "COMPLETED"
        assert result["pages_fetched"] == 2
        assert result["total_items"] == 2
        assert result["stop_reason"] == "last_page"
        assert result["pages"][0]["items"][0]["id"] == 1
        assert result["pages"][0]["next_cursor"] == "page-2"
        assert result["pages"][1]["items"][0]["id"] == 2
        assert result["pages"][1]["has_next_page"] is False

    finally:
        process.terminate()
        try:
            process.wait(timeout=3)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait()
