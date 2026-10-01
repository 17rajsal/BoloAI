from abc import ABC, abstractmethod
import base64
import io
import logging
import math
import struct
import wave
from typing import Any, Dict, Optional
import httpx
from .. import config

logger = logging.getLogger("boloai.tts")


def generate_mock_pcm_audio(duration_sec: float = 1.5, sample_rate: int = 8000, frequency: float = 440.0) -> bytes:
    """Generates synthetic 16-bit PCM audio frames at sample_rate (default 8kHz for telephony)."""
    num_samples = int(duration_sec * sample_rate)
    frames = bytearray()
    for i in range(num_samples):
        t = i / sample_rate
        envelope = math.sin(math.pi * i / num_samples)  # smooth fade in and fade out
        val = int(2000 * envelope * math.sin(2 * math.pi * frequency * t))
        frames.extend(struct.pack("<h", val))
    return bytes(frames)


class TextToSpeechAdapter(ABC):
    @abstractmethod
    async def synthesize(
        self,
        text: str,
        language: str = "hi-IN",
        sample_rate: int = 8000,
    ) -> Dict[str, Any]:
        """Synthesize text into telephony-ready audio bytes (8kHz linear PCM)."""
        pass


class SarvamTTSAdapter(TextToSpeechAdapter):
    """Sarvam AI Text-to-Speech integration supporting Indian accents and languages.
    Uses bulbul:v1 model via Sarvam AI REST API.
    """

    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or config.SARVAM_API_KEY
        self.endpoint = config.SARVAM_TTS_URL

    async def synthesize(
        self,
        text: str,
        language: str = "hi-IN",
        sample_rate: int = 8000,
    ) -> Dict[str, Any]:
        cleaned_text = text.strip()
        if not cleaned_text:
            return {"audio_bytes": b"", "sample_rate": sample_rate, "encoding": "audio/x-l16"}

        lang_code = "hi-IN" if language in ("auto", "hi", "hi-IN", "hinglish", "Hindi", "Hinglish") else language
        if language in ("en", "en-IN", "English"):
            lang_code = "en-IN"

        payload = {
            "inputs": [cleaned_text],
            "target_language_code": lang_code,
            "speaker": config.SARVAM_DEFAULT_SPEAKER,
            "speech_sample_rate": sample_rate,
            "enable_preprocessing": True,
            "model": "bulbul:v1",
        }

        headers = {
            "api-subscription-key": self.api_key,
            "Content-Type": "application/json",
        }

        try:
            async with httpx.AsyncClient(timeout=12.0) as client:
                resp = await client.post(self.endpoint, json=payload, headers=headers)
                if resp.status_code == 200:
                    data = resp.json()
                    audios = data.get("audios", [])
                    if audios:
                        raw_audio = base64.b64decode(audios[0])
                        # If Sarvam returns WAV container, extract raw PCM frames for telephony streaming
                        if raw_audio.startswith(b"RIFF"):
                            try:
                                with wave.open(io.BytesIO(raw_audio), "rb") as wf:
                                    pcm_bytes = wf.readframes(wf.getnframes())
                            except Exception:
                                pcm_bytes = raw_audio
                        else:
                            pcm_bytes = raw_audio

                        logger.info(f"Sarvam TTS generated {len(pcm_bytes)} PCM bytes for text '{cleaned_text[:40]}...'")
                        return {
                            "audio_bytes": pcm_bytes,
                            "sample_rate": sample_rate,
                            "encoding": "audio/x-l16",
                            "provider": "Sarvam AI TTS (bulbul:v1)",
                            "text": cleaned_text,
                        }

                logger.warning(f"Sarvam TTS failed with status {resp.status_code}: {resp.text}")
        except Exception as exc:
            logger.error(f"Sarvam TTS exception: {exc}")

        # Fallback to mock audio on API error
        return MockTTSAdapter().synthesize_sync(cleaned_text, language=language, sample_rate=sample_rate)


class MockTTSAdapter(TextToSpeechAdapter):
    """Mock TTS Adapter generating synthetic telephony PCM audio frames."""

    def synthesize_sync(self, text: str, language: str = "hi-IN", sample_rate: int = 8000) -> Dict[str, Any]:
        duration = max(1.0, min(4.0, len(text) / 15.0))
        audio = generate_mock_pcm_audio(duration_sec=duration, sample_rate=sample_rate)
        return {
            "audio_bytes": audio,
            "sample_rate": sample_rate,
            "encoding": "audio/x-l16",
            "provider": "Mock TTS (Demo)",
            "text": text,
            "duration_sec": duration,
        }

    async def synthesize(
        self,
        text: str,
        language: str = "hi-IN",
        sample_rate: int = 8000,
    ) -> Dict[str, Any]:
        return self.synthesize_sync(text, language=language, sample_rate=sample_rate)


def get_tts_adapter() -> TextToSpeechAdapter:
    if config.has_sarvam():
        return SarvamTTSAdapter()
    return MockTTSAdapter()
