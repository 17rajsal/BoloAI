import re
from typing import Optional, Tuple


FORBIDDEN_PATTERNS = [
    r"\b(otp|one[ -]time[ -]password)\b",
    r"\b(upi[ -]?pin|atm[ -]?pin|mpin)\b",
    r"\b(cvv|cvv2|card[ -]verification)\b",
    r"\b(password|passcode|netbanking|bank[ -]password|atm[ -]password)\b",
    r"\b(debit card pin|credit card pin|secret pin)\b",
]

HINDI_FORBIDDEN_WORDS = [
    "ओटीपी", "पासवर्ड", "पिन", "सीवीवी", "सी.वी.वी", "पासकोड"
]

MEDICAL_PATTERNS = [
    r"\b(heart attack|chest pain|stroke|bleeding profusely|overdose|poisoning)\b",
    r"\b(suicide|self[ -]harm|kill myself|depressed want to die)\b",
    r"\b(prescription|dosage|take this medicine|which injection)\b",
]

FINANCIAL_HIGH_RISK_PATTERNS = [
    r"\b(stock tip|guaranteed return|invest here|double money|crypto scheme)\b",
    r"\b(give bank details|transfer money now|lottery prize claim)\b",
]


class SafetyService:
    @staticmethod
    def inspect_text_for_sensitive_leak(text: str) -> bool:
        """Returns True if the text prompts for or asks to collect sensitive credentials."""
        lowered = text.lower()
        for pat in FORBIDDEN_PATTERNS:
            if re.search(pat, lowered):
                return True
        for hw in HINDI_FORBIDDEN_WORDS:
            if hw in text:
                return True
        return False

    @staticmethod
    def sanitize_credentials(text: str) -> str:
        """Sanitizes sensitive secret numbers/passwords so they never survive in logs or history."""
        sanitized = text
        for pat in [r"\b\d{3,6}\b", r"SampleSecret\w*"]:
            sanitized = re.sub(pat, "[REDACTED_SECRET]", sanitized)
        return sanitized

    @staticmethod
    def check_high_risk_intent(text: str) -> Tuple[Optional[str], Optional[str]]:
        """Identifies medical/legal/financial high-risk categories and returns (category, spoken_disclaimer)."""
        lowered = text.lower()

        # Check self-harm or emergency
        if any(re.search(p, lowered) for p in [r"\bsuicide\b", r"\bself[ -]harm\b", r"\bwant to die\b"]):
            return (
                "EMERGENCY_CRISIS",
                "Agar aap ya koi pareshani mein hain, kripya turant national helpline 14416 (Tele-MANAS) ya 112 par call karein. Hum aapki madad ke liye prarthna karte hain.",
            )

        # Check acute medical emergency
        for pat in MEDICAL_PATTERNS:
            if re.search(pat, lowered):
                return (
                    "MEDICAL_ADVICE",
                    "Yeh ek aam jankari hai aur doctor ki salah nahi hai. Kripya turant nazdeeki doctor ya 108 emergency service se sampark karein.",
                )

        # Check financial speculation / fraud
        for pat in FINANCIAL_HIGH_RISK_PATTERNS:
            if re.search(pat, lowered):
                return (
                    "FINANCIAL_CAUTION",
                    "Dhyan dein: BoloAI kabhi bhi investment tips ya guaranteed returns suggest nahi karta. Kisi ke kehne par OTP ya paise transfer na karein.",
                )

        return (None, None)

    @staticmethod
    def requires_confirmation(action_type: str) -> bool:
        """Determines if an action requires explicit user permission before execution."""
        return action_type in ("create_complaint", "send_sms", "external_submission")
