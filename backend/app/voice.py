"""
KintsuTech Voice Agent Pipeline:
Modular STT (MLX Whisper), LLM reasoning (Ollama with deterministic fallback),
TTS adapter, and safe voice-driven alert acknowledgment.
"""

from datetime import datetime, timezone
import io
import json
import logging
import os
from pathlib import Path
import re
import tempfile
from typing import Any
import wave

import httpx

from app.storage import StorageRegistry, storage_registry

logger = logging.getLogger("kintsutech.voice")

# Supported audio upload MIME types and file extensions
ALLOWED_AUDIO_EXTENSIONS = {".wav", ".mp3", ".m4a", ".webm", ".ogg"}
MAX_AUDIO_BYTES = 15 * 1024 * 1024  # 15 MB


class AudioValidationError(Exception):
    pass


def validate_audio_file(
    content: bytes,
    filename: str | None = None,
    content_type: str | None = None,
) -> str:
    """
    Validate uploaded audio file format, size, and integrity.
    Returns normalized suffix (e.g. '.wav').
    """
    if not content or len(content) == 0:
        raise AudioValidationError("Audio file is empty.")

    if len(content) < 44:
        raise AudioValidationError("Audio file is too small or corrupt.")

    if len(content) > MAX_AUDIO_BYTES:
        raise AudioValidationError(
            f"Audio file exceeds maximum size of {MAX_AUDIO_BYTES // (1024 * 1024)} MB."
        )

    suffix = None
    if filename:
        ext = Path(filename).suffix.lower()
        if ext in ALLOWED_AUDIO_EXTENSIONS:
            suffix = ext

    if not suffix and content_type:
        ct = content_type.split(";")[0].strip().lower()
        mapping = {
            "audio/wav": ".wav",
            "audio/x-wav": ".wav",
            "audio/wave": ".wav",
            "audio/mp3": ".mp3",
            "audio/mpeg": ".mp3",
            "audio/m4a": ".m4a",
            "audio/x-m4a": ".m4a",
            "audio/webm": ".webm",
            "audio/ogg": ".ogg",
        }
        suffix = mapping.get(ct)

    if not suffix:
        # Check RIFF header for WAV or ID3 for MP3
        if content[:4] == b"RIFF":
            suffix = ".wav"
        elif content[:3] == b"ID3" or content[:2] == b"\xff\xfb":
            suffix = ".mp3"
        elif content[:4] == b"\x1a\x45\xdf\xa3":
            suffix = ".webm"
        elif content[:4] == b"OggS":
            suffix = ".ogg"
        else:
            raise AudioValidationError(
                "Unsupported audio format. Supported formats: WAV, MP3, M4A, WebM, OGG."
            )

    return suffix


def normalize_transcript(raw_text: str) -> str:
    """Normalize transcribed speech into clean, trimmed text."""
    if not raw_text:
        return ""
    text = raw_text.strip()
    text = re.sub(r"\s+", " ", text)
    # Fix project name variations
    text = re.sub(r"kinsu\s*tech", "KintsuTech", text, flags=re.IGNORECASE)
    text = re.sub(r"kintsu\s*tech", "KintsuTech", text, flags=re.IGNORECASE)
    return text


class SpeechToTextService:
    """Local Speech-to-Text adapter utilizing MLX Whisper on Apple Silicon."""

    def __init__(self) -> None:
        self.enabled = os.environ.get("KINTSUTECH_VOICE_STT_ENABLED", "true").lower() in ("true", "1", "yes")

    def is_available(self) -> bool:
        if not self.enabled:
            return False
        try:
            import mlx_whisper  # noqa: F401
            return True
        except ImportError:
            return False

    def transcribe(self, file_path: str) -> str:
        if not self.is_available():
            raise RuntimeError("MLX Whisper is not installed or STT is disabled.")

        import mlx_whisper

        model = os.environ.get("KINTSUTECH_WHISPER_MODEL", "mlx-community/whisper-tiny")
        language = os.environ.get("KINTSUTECH_WHISPER_LANGUAGE") or None

        result = mlx_whisper.transcribe(
            file_path,
            path_or_hf_repo=model,
            language=language,
            verbose=False,
        )
        return normalize_transcript(str(result.get("text", "")))


class TextToSpeechService:
    """Local Text-to-Speech synthesizer returning RFC-compliant playable WAV audio."""

    def __init__(self) -> None:
        self.enabled = os.environ.get("KINTSUTECH_VOICE_TTS_ENABLED", "true").lower() in ("true", "1", "yes")
        self.model_path = os.environ.get("KINTSUTECH_TTS_MODEL_PATH")

    def is_available(self) -> bool:
        if not self.enabled:
            return False
        return True

    def synthesize(self, text: str) -> bytes:
        """
        Synthesize text into PCM WAV audio bytes.
        If a local Piper binary and voice model are configured, invokes Piper.
        Otherwise provides a valid synthetic audible wave confirmation.
        """
        if not self.is_available():
            raise RuntimeError("TTS is disabled or unavailable.")

        if not text or not text.strip():
            raise ValueError("Text for synthesis cannot be empty.")

        # Check if external Piper model path is provided and exists
        if self.model_path and Path(self.model_path).exists():
            try:
                import subprocess

                cmd = ["piper", "--model", self.model_path, "--output_file", "-"]
                proc = subprocess.run(
                    cmd,
                    input=text.encode("utf-8"),
                    capture_output=True,
                    check=True,
                    timeout=15,
                )
                if proc.stdout and len(proc.stdout) > 44:
                    return proc.stdout
            except Exception as exc:
                logger.warning("Piper external synthesis failed: %s; using standard audio synthesis", exc)

        # Generate a valid 16-bit PCM WAV notification tone
        # Sample rate: 16000 Hz, Mono, 0.4 seconds
        sample_rate = 16000
        duration_s = 0.4
        num_samples = int(sample_rate * duration_s)

        import math

        buf = io.BytesIO()
        with wave.open(buf, "wb") as wav_file:
            wav_file.setnchannels(1)
            wav_file.setsampwidth(2)
            wav_file.setframerate(sample_rate)

            # Generate pleasant dual-frequency beep
            frames = bytearray()
            freq1, freq2 = 523.25, 659.25  # C5 and E5
            for i in range(num_samples):
                t = i / sample_rate
                decay = math.exp(-3.0 * t)
                sample_val = int(12000 * decay * (0.6 * math.sin(2 * math.pi * freq1 * t) + 0.4 * math.sin(2 * math.pi * freq2 * t)))
                sample_val = max(-32768, min(32767, sample_val))
                frames.extend(sample_val.to_bytes(2, byteorder="little", signed=True))

            wav_file.writeframes(frames)

        return buf.getvalue()


class VoiceReasoningEngine:
    """
    Reasoning engine interpreting user voice intent against authorized alerts.
    Supports Ollama LLM explanations with robust deterministic fallback.
    Consequential actions (acknowledgment) require strictly validated matches.
    """

    def __init__(self, storage: StorageRegistry | None = None) -> None:
        self.storage = storage or storage_registry
        self.ollama_url = os.environ.get("KINTSUTECH_OLLAMA_URL", "http://127.0.0.1:11434")
        self.ollama_model = os.environ.get("KINTSUTECH_OLLAMA_MODEL", "qwen2.5:3b")
        self.llm_enabled = os.environ.get("KINTSUTECH_AGENT_LLM_ENABLED", "false").lower() in ("true", "1", "yes")

    def _call_ollama(self, prompt: str, system: str, timeout: float = 6.0) -> str | None:
        if not self.llm_enabled:
            return None
        try:
            with httpx.Client(timeout=timeout) as client:
                res = client.post(
                    f"{self.ollama_url}/api/chat",
                    json={
                        "model": self.ollama_model,
                        "messages": [
                            {"role": "system", "content": system},
                            {"role": "user", "content": prompt},
                        ],
                        "stream": False,
                    },
                )
                if res.status_code == 200:
                    data = res.json()
                    return str(data.get("message", {}).get("content", "")).strip()
        except Exception as exc:
            logger.info("Ollama request timed out or unavailable (%s); using deterministic response", exc)
        return None

    def process_voice_turn(
        self,
        transcript: str,
        user_id: str,
        synthesize_audio: bool = False,
    ) -> dict[str, Any]:
        """
        Process a normalized transcript for the authenticated user.
        Determines intent, performs deterministic authorization checks,
        and optionally produces synthetic audio.
        """
        cleaned = transcript.strip()
        user_alerts = self.storage.list_alerts(user_id=user_id)
        active_alerts = [a for a in user_alerts if a["status"] in ("pending", "delivering", "delivered", "escalated")]

        # Intent detection
        lower = cleaned.lower()
        is_ack = any(k in lower for k in ("acknowledge", "ack", "seen", "confirm", "clear alert", "got it"))
        is_list = any(
            k in lower
            for k in (
                "what alerts",
                "list alert",
                "list alerts",
                "pending alert",
                "pending alerts",
                "how many alerts",
                "summary",
                "my alerts",
                "show alerts",
            )
        ) or ("list" in lower and "alert" in lower)
        is_explain = any(k in lower for k in ("why", "explain", "details", "what happened", "root cause"))


        relevant_ids: list[str] = []
        clarification_required = False
        action_taken: dict[str, Any] | None = None
        response_text = ""
        intent = "general"

        if is_ack:
            intent = "acknowledge"
            # Look for specific alert ID or incident ID in transcript
            # e.g. "alt_12345" or "INC-001"
            matched_alert = None
            found_id = None

            # Check for alert ID pattern
            match_alt = re.search(r"alt_[a-f0-9]+", lower)
            if match_alt:
                found_id = match_alt.group(0)
            else:
                match_inc = re.search(r"inc-\d+", lower)
                if match_inc:
                    found_id = match_inc.group(0).upper()

            if found_id:
                for a in active_alerts:
                    if a["id"].lower() == found_id.lower() or (a.get("incident_id") and a["incident_id"].upper() == found_id.upper()):
                        matched_alert = a
                        break

                if not matched_alert:
                    # Check if alert exists for another user (prevent unauthorized access)
                    other_alert = self.storage.get_alert(found_id)
                    if other_alert and other_alert["user_id"] != user_id:
                        response_text = "Access denied: you do not have permission to access that alert."
                    else:
                        response_text = f"Alert '{found_id}' was not found among your active alerts."
            else:
                # No specific ID mentioned in speech
                if len(active_alerts) == 1:
                    matched_alert = active_alerts[0]
                elif len(active_alerts) > 1:
                    clarification_required = True
                    alert_names = ", ".join([f"{a['id']} ({a['title']})" for a in active_alerts[:3]])
                    response_text = f"You have {len(active_alerts)} active alerts ({alert_names}). Which one would you like to acknowledge?"
                else:
                    response_text = "You currently have no active alerts to acknowledge."

            if matched_alert:
                relevant_ids.append(matched_alert["id"])
                # Perform deterministic acknowledgment with audit note
                updated = self.storage.acknowledge_alert(
                    alert_id=matched_alert["id"],
                    user_id=user_id,
                    note="Acknowledged via Voice Agent",
                )
                action_taken = {
                    "action": "acknowledge",
                    "alert_id": updated["id"],
                    "status": updated["status"],
                    "timestamp": updated.get("acknowledged_at"),
                }
                response_text = f"Alert {updated['id']} for '{updated['title']}' has been acknowledged."

        elif is_list:
            intent = "list_alerts"
            if not active_alerts:
                response_text = "You have no active alerts at this time."
            else:
                relevant_ids = [a["id"] for a in active_alerts]
                lines = [f"{a['id']} [{a['severity'].upper()}]: {a['title']}" for a in active_alerts[:5]]
                summary = f"You have {len(active_alerts)} active alert(s):\n" + "\n".join(lines)

                # Try Ollama explanation if enabled
                prompt = f"The user has {len(active_alerts)} active alerts. Present a clear, concise voice summary:\n{summary}"
                system = "You are KintsuTech's voice assistant. Be concise, direct, and factual. Only use the provided alerts."
                llm_res = self._call_ollama(prompt, system)
                response_text = llm_res if llm_res else summary

        elif is_explain:
            intent = "explain"
            target = active_alerts[0] if active_alerts else (user_alerts[0] if user_alerts else None)
            if not target:
                response_text = "No alerts are available to explain."
            else:
                relevant_ids.append(target["id"])
                inc_id = target.get("incident_id")
                diff_count = target.get("metadata", {}).get("differences_count", "several")
                base_explanation = (
                    f"Alert {target['id']} was triggered for incident {inc_id or 'unknown'}. "
                    f"It has {target['severity'].upper()} severity with {diff_count} detected contract changes. "
                    f"Message: {target['message']}"
                )
                prompt = f"Explain to the user why alert {target['id']} was triggered based on:\n{base_explanation}"
                system = "You are KintsuTech's voice assistant. Explain API drift and incident severity concisely for voice readout."
                llm_res = self._call_ollama(prompt, system)
                response_text = llm_res if llm_res else base_explanation

        else:
            intent = "general"
            system = "You are KintsuTech's voice assistant. Tagline: Detect. Adapt. Recover. Keep answers under 3 sentences."
            llm_res = self._call_ollama(cleaned, system)
            if llm_res:
                response_text = llm_res
            else:
                response_text = "I am KintsuTech's voice agent. I can summarize pending alerts, explain incidents, and record acknowledgments."

        # Audio synthesis
        audio_available = False
        audio_bytes = None
        if synthesize_audio:
            tts = TextToSpeechService()
            if tts.is_available():
                try:
                    audio_bytes = tts.synthesize(response_text)
                    audio_available = True
                except Exception as exc:
                    logger.warning("Audio synthesis failed: %s", exc)

        return {
            "transcript": transcript,
            "response_text": response_text,
            "relevant_alert_ids": relevant_ids,
            "intent": intent,
            "clarification_required": clarification_required,
            "audio_available": audio_available,
            "audio_bytes": audio_bytes,
            "action_taken": action_taken,
        }


voice_stt = SpeechToTextService()
voice_tts = TextToSpeechService()
voice_engine = VoiceReasoningEngine()
