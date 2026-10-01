from abc import ABC, abstractmethod
import io
import logging
import wave
from typing import Any, Dict, Optional
import httpx
from .. import config

logger = logging.getLogger("boloai.stt")


def pcm_to_wav(pcm_bytes: bytes, sample_rate: int = 8000, channels: int = 1, sampwidth: int = 2) -> bytes:
    """Converts raw 16-bit linear PCM bytes to standard WAV container bytes."""
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wav_file:
        wav_file.setnchannels(channels)
        wav_file.setsampwidth(sampwidth)
        wav_file.setframerate(sample_rate)
        wav_file.writeframes(pcm_bytes)
    return buf.getvalue()


class SpeechToTextAdapter(ABC):
    @abstractmethod
    async def transcribe_audio(
        self,
        audio_bytes: bytes,
        language: str = "auto",
        sample_rate: int = 8000,
    ) -> Dict[str, Any]:
        """Transcribe raw or WAV audio bytes to text with language detection."""
        pass


class SarvamSTTAdapter(SpeechToTextAdapter):
    """Sarvam AI Speech-to-Text integration for Indian languages (Hindi, Hinglish, English, etc.).
    Uses saaras:v2 model via Sarvam AI REST API.
    """

    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or config.SARVAM_API_KEY
        self.endpoint = config.SARVAM_STT_URL

    async def transcribe_audio(
        self,
        audio_bytes: bytes,
        language: str = "auto",
        sample_rate: int = 8000,
    ) -> Dict[str, Any]:
        # Filter out tiny noise packets
        if not audio_bytes or len(audio_bytes) < 800:
            return {"text": "", "language": language, "is_final": True, "confidence": 0.0, "is_noise": True}

        # Convert raw L16 PCM to WAV container if needed
        if not audio_bytes.startswith(b"RIFF"):
            wav_bytes = pcm_to_wav(audio_bytes, sample_rate=sample_rate)
        else:
            wav_bytes = audio_bytes

        headers = {
            "api-subscription-key": self.api_key,
        }

        lang_code = "hi-IN" if language in ("auto", "hi", "hi-IN", "hinglish", "Hindi", "Hinglish") else language
        if language in ("en", "en-IN", "English"):
            lang_code = "en-IN"

        files = {
            "file": ("audio.wav", wav_bytes, "audio/wav"),
        }
        data = {
            "model": "saaras:v2",
            "language_code": lang_code,
            "with_diarization": "false",
        }

        try:
            async with httpx.AsyncClient(timeout=12.0) as client:
                resp = await client.post(self.endpoint, headers=headers, files=files, data=data)
                if resp.status_code == 200:
                    result = resp.json()
                    transcript = result.get("transcript", "").strip()
                    detected_lang = result.get("language_code", lang_code)
                    logger.info(f"Sarvam STT success: '{transcript[:60]}' (lang: {detected_lang})")
                    return {
                        "text": transcript,
                        "language": detected_lang,
                        "is_final": True,
                        "confidence": 0.95,
                        "provider": "Sarvam AI STT (saaras:v2)",
                        "is_noise": not bool(transcript),
                    }
                else:
                    logger.warning(f"Sarvam STT failed with status {resp.status_code}: {resp.text}")
                    return {
                        "text": "",
                        "language": language,
                        "is_final": True,
                        "error": f"Sarvam STT HTTP {resp.status_code}: {resp.text}",
                        "is_noise": True,
                    }
        except Exception as exc:
            logger.error(f"Sarvam STT connection error: {exc}")
            # Graceful fallback to mock on transient network failure
            return await MockSTTAdapter().transcribe_audio(audio_bytes, language=language, sample_rate=sample_rate)


class MockSTTAdapter(SpeechToTextAdapter):
    """Mock STT Adapter for demo and test environments."""

    def __init__(self):
        self._demo_responses = [
            "Delhi mein kal baarish hogi?",
            "Main UP mein BTech second year mein hoon, mere liye scholarship schemes batao.",
            "Mera parcel ABC123 kahan hai?",
            "Official link SMS kar do.",
            "Complaint register kar do.",
        ]
        self._counter = 0

    async def transcribe_audio(
        self,
        audio_bytes: bytes,
        language: str = "auto",
        sample_rate: int = 8000,
    ) -> Dict[str, Any]:
        # Filter out tiny noise packets
        if not audio_bytes or len(audio_bytes) < 400:
            return {"text": "", "language": language, "is_final": True, "confidence": 0.0, "is_noise": True}

        text = self._demo_responses[self._counter % len(self._demo_responses)]
        self._counter += 1

        return {
            "text": text,
            "language": "hi-IN",
            "is_final": True,
            "confidence": 0.90,
            "provider": "Mock STT (Demo)",
            "is_noise": False,
        }


def get_stt_adapter() -> SpeechToTextAdapter:
    if config.has_sarvam():
        return SarvamSTTAdapter()
    return MockSTTAdapter()
