import asyncio
import base64
import json
import logging
import math
import struct
from typing import Any, Callable, Dict, List, Optional
from fastapi import WebSocket

logger = logging.getLogger("boloai.telephony")


def calculate_pcm_rms(pcm_bytes: bytes) -> float:
    """Calculates RMS energy of 16-bit signed PCM mono audio without external dependencies."""
    if not pcm_bytes or len(pcm_bytes) < 2:
        return 0.0
    num_samples = len(pcm_bytes) // 2
    if num_samples == 0:
        return 0.0
    samples = struct.unpack(f"<{num_samples}h", pcm_bytes[: num_samples * 2])
    sum_squares = sum(s * s for s in samples)
    return math.sqrt(sum_squares / num_samples)


class TelephonyAdapter:
    """Telephony provider adapter for Exotel VoiceBot bidirectional WebSocket streams.
    Handles message decoding, audio chunking (8kHz PCM), streaming back to caller,
    barge-in clearing, and event normalization.
    """

    def __init__(self, websocket: WebSocket, call_id: str, stream_sid: Optional[str] = None):
        self.ws = websocket
        self.call_id = call_id
        self.stream_sid = stream_sid
        self.is_playing: bool = False
        self._playback_task: Optional[asyncio.Task] = None

    def set_stream_sid(self, stream_sid: str) -> None:
        self.stream_sid = stream_sid

    async def send_audio_chunks(
        self,
        audio_bytes: bytes,
        chunk_size_bytes: int = 640,  # 640 bytes = 40ms of 16-bit 8kHz mono PCM
        delay_between_chunks: float = 0.035,
    ) -> None:
        """Streams audio bytes back to Exotel in properly sized media packets."""
        if not self.stream_sid:
            self.stream_sid = f"stream-{self.call_id}"

        self.is_playing = True
        try:
            total_len = len(audio_bytes)
            for offset in range(0, total_len, chunk_size_bytes):
                # Check for interruption
                if not self.is_playing:
                    logger.info(f"[{self.call_id}] Telephony playback halted mid-stream due to barge-in.")
                    break

                chunk = audio_bytes[offset : offset + chunk_size_bytes]
                payload = base64.b64encode(chunk).decode("ascii")

                msg = {
                    "event": "media",
                    "stream_sid": self.stream_sid,
                    "media": {
                        "payload": payload,
                    },
                }
                await self.ws.send_json(msg)
                await asyncio.sleep(delay_between_chunks)

            # Send playback completion mark
            if self.is_playing:
                await self.ws.send_json({
                    "event": "mark",
                    "stream_sid": self.stream_sid,
                    "mark": {"name": "response_finished"},
                })
        except Exception as exc:
            logger.warning(f"[{self.call_id}] Audio chunk send exception: {exc}")
        finally:
            self.is_playing = False

    async def interrupt_playback(self) -> None:
        """Sends clear event to Exotel to support immediate caller barge-in."""
        self.is_playing = False
        if self.stream_sid:
            try:
                logger.info(f"[{self.call_id}] Dispatched clear event to Exotel for stream {self.stream_sid}")
                await self.ws.send_json({
                    "event": "clear",
                    "stream_sid": self.stream_sid,
                })
            except Exception as exc:
                logger.warning(f"[{self.call_id}] Failed to send clear event: {exc}")

    @staticmethod
    def parse_event(raw_text: str) -> Dict[str, Any]:
        """Parses raw text incoming from telephony WebSocket into structured event dict."""
        try:
            return json.loads(raw_text)
        except Exception:
            return {"event": "malformed", "raw": raw_text}

    @staticmethod
    def decode_media_payload(media_dict: Dict[str, Any]) -> bytes:
        """Decodes base64 PCM payload from incoming media event."""
        payload = media_dict.get("payload", "")
        if not payload:
            return b""
        try:
            return base64.b64decode(payload)
        except Exception:
            return b""
