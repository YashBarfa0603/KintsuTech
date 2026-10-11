from unittest.mock import patch

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_transcription_success():
    with patch(
        "app.main._transcribe_local_audio",
        return_value="KintsuTech detects API failures.",
    ) as mock_transcribe:
        response = client.post(
            "/api/v1/agent/transcribe",
            files={"file": ("speech.wav", b"fake audio data", "audio/wav")},
        )

    assert response.status_code == 200
    assert response.json() == {
        "text": "KintsuTech detects API failures.",
        "engine": "mlx-whisper",
        "local_processing": True,
    }
    mock_transcribe.assert_called_once()


def test_transcription_rejects_unsupported_format():
    response = client.post(
        "/api/v1/agent/transcribe",
        files={"file": ("speech.txt", b"not audio", "text/plain")},
    )

    assert response.status_code == 415


def test_transcription_rejects_empty_audio():
    response = client.post(
        "/api/v1/agent/transcribe",
        files={"file": ("speech.wav", b"", "audio/wav")},
    )

    assert response.status_code == 400


def test_transcription_rejects_oversized_audio():
    oversized_audio = b"x" * (7 * 1024 * 1024 + 1)

    response = client.post(
        "/api/v1/agent/transcribe",
        files={"file": ("speech.wav", oversized_audio, "audio/wav")},
    )

    assert response.status_code == 413


def test_transcription_handles_no_recognized_speech():
    with patch("app.main._transcribe_local_audio", return_value=""):
        response = client.post(
            "/api/v1/agent/transcribe",
            files={"file": ("speech.wav", b"fake audio data", "audio/wav")},
        )

    assert response.status_code == 422


def test_transcription_sanitizes_model_errors():
    with patch(
        "app.main._transcribe_local_audio",
        side_effect=RuntimeError("internal model detail"),
    ):
        response = client.post(
            "/api/v1/agent/transcribe",
            files={"file": ("speech.wav", b"fake audio data", "audio/wav")},
        )

    assert response.status_code == 500
    assert response.json()["detail"] == (
        "Local transcription failed. Check backend logs and Whisper model."
    )
    assert "internal model detail" not in response.text


def test_transcription_unsupported_os_platform():
    with patch("app.main.sys.platform", "linux"):
        response = client.post(
            "/api/v1/agent/transcribe",
            files={"file": ("speech.wav", b"fake audio data", "audio/wav")},
        )

    assert response.status_code == 503
    assert "MLX Whisper requires macOS on Apple Silicon" in response.json()["detail"]


def test_transcription_unsupported_architecture():
    with patch("app.main.platform.machine", return_value="x86_64"):
        response = client.post(
            "/api/v1/agent/transcribe",
            files={"file": ("speech.wav", b"fake audio data", "audio/wav")},
        )

    assert response.status_code == 503
    assert "MLX Whisper requires macOS on Apple Silicon" in response.json()["detail"]


def test_transcription_missing_dependency():
    with patch.dict("sys.modules", {"mlx_whisper": None}):
        response = client.post(
            "/api/v1/agent/transcribe",
            files={"file": ("speech.wav", b"fake audio data", "audio/wav")},
        )

    assert response.status_code == 503
    assert "MLX Whisper dependency is not installed" in response.json()["detail"]


def test_transcription_middleware_rejects_body_exceeding_8mb():
    response = client.post(
        "/api/v1/agent/transcribe",
        headers={"content-length": str(9 * 1024 * 1024)},
        content=b"dummy",
    )

    assert response.status_code == 413
    assert "Request entity too large" in response.json()["detail"]

