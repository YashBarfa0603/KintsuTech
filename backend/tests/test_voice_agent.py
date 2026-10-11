"""
Comprehensive tests for KintsuTech voice agent pipeline:
Audio validation, STT normalization, Ollama reasoning with fallback,
safe voice alert acknowledgment, TTS synthesis, and voice status.
"""

import io
import os
import wave
from unittest.mock import MagicMock, patch
import pytest
from fastapi.testclient import TestClient

from app.auth import AuthenticatedUser, get_current_user
from app.main import app
from app.storage import storage_registry
from app.voice import (
    AudioValidationError,
    SpeechToTextService,
    TextToSpeechService,
    VoiceReasoningEngine,
    normalize_transcript,
    validate_audio_file,
    voice_engine,
    voice_stt,
    voice_tts,
)

client = TestClient(app)


def _generate_valid_wav_bytes(duration_s: float = 0.2) -> bytes:
    """Helper to produce a small valid PCM WAV byte stream."""
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wav_file:
        wav_file.setnchannels(1)
        wav_file.setsampwidth(2)
        wav_file.setframerate(16000)
        num_samples = int(16000 * duration_s)
        wav_file.writeframes(b"\x00\x00" * num_samples)
    return buf.getvalue()


# ============================================================================
# E. Voice-Agent Tests
# ============================================================================

def test_valid_audio_is_accepted_and_suffix_resolved():
    wav_bytes = _generate_valid_wav_bytes()
    suffix = validate_audio_file(wav_bytes, filename="sample.wav", content_type="audio/wav")
    assert suffix == ".wav"


def test_empty_audio_is_rejected():
    with pytest.raises(AudioValidationError) as exc:
        validate_audio_file(b"")
    assert "empty" in str(exc.value).lower()


def test_corrupt_or_tiny_audio_is_rejected():
    with pytest.raises(AudioValidationError) as exc:
        validate_audio_file(b"corrupt")
    assert "too small" in str(exc.value).lower() or "corrupt" in str(exc.value).lower()


def test_oversized_audio_is_rejected():
    oversized = b"x" * (16 * 1024 * 1024)
    with pytest.raises(AudioValidationError) as exc:
        validate_audio_file(oversized, filename="large.wav")
    assert "exceeds" in str(exc.value).lower()


def test_transcription_output_is_normalized():
    raw = "   hello   there  from   kinsu tech   "
    normalized = normalize_transcript(raw)
    assert normalized == "hello there from KintsuTech"


def test_whisper_unavailable_returns_clear_status(monkeypatch):
    stt = SpeechToTextService()
    monkeypatch.setattr(stt, "is_available", lambda: False)
    with pytest.raises(RuntimeError) as exc:
        stt.transcribe("some_path.wav")
    assert "not installed or stt is disabled" in str(exc.value).lower()


def test_voice_status_endpoint_reports_component_readiness():
    res = client.get("/api/v1/voice/status")
    assert res.status_code == 200
    data = res.json()
    assert "stt" in data
    assert "llm" in data
    assert "tts" in data
    assert "telephony" in data
    assert data["telephony"]["enabled"] is False


def test_ambiguous_voice_acknowledgment_requests_clarification():
    user = AuthenticatedUser(id="user_voice_ambig", email="v@kintsu.io")
    # Create two pending alerts
    storage_registry.create_alert(user_id=user.id, title="Alert 1", message="M1")
    storage_registry.create_alert(user_id=user.id, title="Alert 2", message="M2")

    engine = VoiceReasoningEngine(storage_registry)
    result = engine.process_voice_turn(
        transcript="I acknowledge the alert",
        user_id=user.id,
    )
    assert result["intent"] == "acknowledge"
    assert result["clarification_required"] is True
    assert "which one" in result["response_text"].lower()


def test_valid_voice_acknowledgment_targets_only_intended_alert():
    user = AuthenticatedUser(id="user_voice_valid", email="vv@kintsu.io")
    alert = storage_registry.create_alert(user_id=user.id, title="Database drift", message="M")

    engine = VoiceReasoningEngine(storage_registry)
    result = engine.process_voice_turn(
        transcript=f"Acknowledge alert {alert['id']}",
        user_id=user.id,
    )
    assert result["intent"] == "acknowledge"
    assert result["clarification_required"] is False
    assert alert["id"] in result["relevant_alert_ids"]
    assert result["action_taken"] is not None

    # Check alert in storage is acknowledged
    updated = storage_registry.get_alert(alert["id"])
    assert updated["status"] == "acknowledged"

    # Check audit history
    history = storage_registry.get_alert_history(alert["id"], user_id=user.id)
    assert any("Voice Agent" in (h.get("details", {}).get("note", "")) for h in history)


def test_llm_cannot_bypass_authorization_or_acknowledge_other_users_alert():
    user_owner = AuthenticatedUser(id="user_voice_owner", email="owner@kintsu.io")
    user_intruder = AuthenticatedUser(id="user_voice_intruder", email="intruder@kintsu.io")

    alert = storage_registry.create_alert(user_id=user_owner.id, title="Secret Alert", message="Confidential")

    engine = VoiceReasoningEngine(storage_registry)
    # Intruder tries acknowledging owner's alert
    result = engine.process_voice_turn(
        transcript=f"Acknowledge alert {alert['id']}",
        user_id=user_intruder.id,
    )
    assert "access denied" in result["response_text"].lower() or "not found" in result["response_text"].lower()

    # Owner's alert status must NOT change
    unchanged = storage_registry.get_alert(alert["id"])
    assert unchanged["status"] == "pending"


def test_ollama_fallback_when_unavailable_or_timeout(monkeypatch):
    engine = VoiceReasoningEngine(storage_registry)
    monkeypatch.setattr(engine, "llm_enabled", True)
    # Mock httpx to throw timeout
    def mock_post(*args, **kwargs):
        raise Exception("Connection refused / timed out")

    monkeypatch.setattr("httpx.Client.post", mock_post)

    user = AuthenticatedUser(id="user_ollama_fallback", email="ofb@kintsu.io")
    storage_registry.create_alert(user_id=user.id, title="Test Drift", message="Drift msg")

    result = engine.process_voice_turn(
        transcript="List my alerts",
        user_id=user.id,
    )
    assert result["intent"] == "list_alerts"
    assert "active alert" in result["response_text"].lower()


def test_tts_synthesis_returns_playable_audio():
    tts = TextToSpeechService()
    audio = tts.synthesize("Alert acknowledged")
    assert len(audio) > 44
    assert audio[:4] == b"RIFF"
    assert audio[8:12] == b"WAVE"


def test_voice_respond_endpoint():
    user = AuthenticatedUser(id="user_endpoint_voice", email="epv@kintsu.io")
    app.dependency_overrides[get_current_user] = lambda: user

    alert = storage_registry.create_alert(user_id=user.id, title="Single Alert", message="M")

    res = client.post(
        "/api/v1/voice/respond",
        json={"transcript": "acknowledge the alert", "synthesize_audio": True},
    )
    assert res.status_code == 200
    data = res.json()
    assert data["intent"] == "acknowledge"
    assert alert["id"] in data["relevant_alert_ids"]
    assert data["audio_available"] is True
    assert data["audio_base64"] is not None


def test_voice_synthesize_endpoint():
    user = AuthenticatedUser(id="user_synth_test", email="synth@kintsu.io")
    app.dependency_overrides[get_current_user] = lambda: user

    res = client.post(
        "/api/v1/voice/synthesize",
        json={"text": "Alert acknowledged successfully."},
    )
    assert res.status_code == 200
    assert res.headers["content-type"] == "audio/wav"
    assert len(res.content) > 44
    assert res.content[:4] == b"RIFF"
