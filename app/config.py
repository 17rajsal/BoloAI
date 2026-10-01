import os
from dotenv import load_dotenv

load_dotenv()

# Mode & Server
DEMO_MODE: bool = os.getenv("DEMO_MODE", "true").lower() in ("true", "1", "yes")
HACKATHON_DEMO_MODE: bool = os.getenv("HACKATHON_DEMO_MODE", "true").lower() in ("true", "1", "yes")
PUBLIC_BASE_URL: str = os.getenv("PUBLIC_BASE_URL", "http://localhost:8000")
PUBLIC_WS_BASE: str = os.getenv("PUBLIC_WS_BASE", "ws://localhost:8000")
HOST: str = os.getenv("HOST", "0.0.0.0")
PORT: int = int(os.getenv("PORT", "8000"))

# OpenAI Configuration
OPENAI_API_KEY: str = os.getenv("OPENAI_API_KEY", "")
OPENAI_MODEL: str = os.getenv("OPENAI_MODEL", "gpt-4o-mini")

# Exotel Telephony Configuration
EXOTEL_ACCOUNT_SID: str = os.getenv("EXOTEL_ACCOUNT_SID", "")
EXOTEL_API_KEY: str = os.getenv("EXOTEL_API_KEY", "")
EXOTEL_API_TOKEN: str = os.getenv("EXOTEL_API_TOKEN", "")
EXOTEL_EXOPHONE: str = os.getenv("EXOTEL_EXOPHONE", "")

# Sarvam AI (Indian Speech STT / TTS)
SARVAM_API_KEY: str = os.getenv("SARVAM_API_KEY", "")
SARVAM_STT_URL: str = os.getenv("SARVAM_STT_URL", "https://api.sarvam.ai/speech-to-text")
SARVAM_TTS_URL: str = os.getenv("SARVAM_TTS_URL", "https://api.sarvam.ai/text-to-speech")
SARVAM_DEFAULT_LANGUAGE: str = os.getenv("SARVAM_DEFAULT_LANGUAGE", "hi-IN")
SARVAM_DEFAULT_SPEAKER: str = os.getenv("SARVAM_DEFAULT_SPEAKER", "meera")

# Search & Upload Security
SEARCH_API_KEY: str = os.getenv("SEARCH_API_KEY", "")
UPLOAD_TOKEN_SECRET: str = os.getenv("UPLOAD_TOKEN_SECRET", "")

# SMS Provider Configuration
SMS_PROVIDER: str = os.getenv("SMS_PROVIDER", "mock")  # 'exotel', 'twilio', 'mock'

def has_openai() -> bool:
    return bool(OPENAI_API_KEY and OPENAI_API_KEY.strip())

def has_sarvam() -> bool:
    return bool(SARVAM_API_KEY and SARVAM_API_KEY.strip())

def has_exotel() -> bool:
    return bool(EXOTEL_ACCOUNT_SID and EXOTEL_API_KEY and EXOTEL_API_TOKEN)
