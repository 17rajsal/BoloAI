import base64
import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional
from .. import config

logger = logging.getLogger("boloai.multimodal")


class MultimodalAnalysisAdapter:
    """Multimodal analysis adapter for inspecting uploaded photos, posters, and documents.
    Extracts text, entities, and claims, but relies on the VerificationService to validate facts.
    """

    @classmethod
    async def analyze_document(
        cls,
        file_path: str,
        mime_type: str,
        caller_question: Optional[str] = None,
        context: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        path = Path(file_path)
        if not path.exists():
            return {"ok": False, "error": f"File '{file_path}' not found"}

        # If live OpenAI key is configured and not in demo mode, invoke vision model
        if config.has_openai() and not config.DEMO_MODE and mime_type.startswith("image/"):
            try:
                return await cls._analyze_with_openai_vision(path, mime_type, caller_question)
            except Exception as exc:
                logger.warning("Live image analysis failed; no claims were extracted.")
                return {"ok": False, "error": "Image analysis unavailable; no image contents verified",
                        "claims": [], "simulated": False}

        if not config.DEMO_MODE:
            return {"ok": False, "error": "Image analysis provider unavailable or document type unsupported",
                    "claims": [], "simulated": False}

        # Fallback / Demo Document Understanding Engine
        return cls._analyze_demo_document(path, caller_question)

    @classmethod
    async def _analyze_with_openai_vision(
        cls,
        path: Path,
        mime_type: str,
        caller_question: Optional[str],
    ) -> Dict[str, Any]:
        from openai import OpenAI
        client = OpenAI(api_key=config.OPENAI_API_KEY)

        file_bytes = path.read_bytes()
        base64_img = base64.b64encode(file_bytes).decode("ascii")

        system_instruction = (
            "You are an Indian document understanding model for BoloAI. "
            "Extract visible text, entity attributes, and explicit factual claims from this image/poster. "
            "Do NOT judge whether the scheme is real or fake; extract the factual claims objectively so the "
            "verification tool can verify them. Return JSON with keys: "
            "extracted_text, scheme_name, claimed_benefit, registration_fee, official_url, helpline_phone, claims."
        )

        response = client.chat.completions.create(
            model=config.OPENAI_MODEL,
            response_format={"type": "json_object"},
            messages=[
                {"role": "system", "content": system_instruction},
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": f"Caller question: {caller_question or 'Please inspect and extract claims from this document.'}"},
                        {
                            "type": "image_url",
                            "image_url": {"url": f"data:{mime_type};base64,{base64_img}"},
                        },
                    ],
                },
            ],
        )

        raw_json = response.choices[0].message.content or "{}"
        parsed = json.loads(raw_json)
        if not isinstance(parsed, dict) or not any(parsed.get(k) for k in ("extracted_text", "claims", "scheme_name")):
            return {"ok": False, "simulated": False, "claims": [], "error": "Image provider returned no usable analysis"}

        claims = parsed.get("claims", [])
        if not claims and parsed.get("scheme_name"):
            claims.append(f"Scheme Name: {parsed.get('scheme_name')}")
        if parsed.get("claimed_benefit"):
            claims.append(f"Claimed Benefit: {parsed.get('claimed_benefit')}")
        if parsed.get("registration_fee"):
            claims.append(f"Registration Fee: {parsed.get('registration_fee')}")

        return {
            "ok": True,
            "provider": "OpenAI Vision API",
            "file_name": path.name,
            "extracted_text": parsed.get("extracted_text", ""),
            "scheme_name": parsed.get("scheme_name"),
            "claimed_benefit": parsed.get("claimed_benefit"),
            "registration_fee": parsed.get("registration_fee"),
            "official_url": parsed.get("official_url"),
            "phone": parsed.get("helpline_phone"),
            "claims": claims,
            "confidence": "High",
            "requires_verification": True,
        }

    @classmethod
    def _analyze_demo_document(cls, path: Path, caller_question: Optional[str]) -> Dict[str, Any]:
        """Deterministic extractor for hackathon demo scenarios."""
        return {
            "ok": True,
            "provider": "Curated Multimodal Extractor (Demo)",
            "simulated": True,
            "demo": True,
            "notice": "Synthetic demo example; actual uploaded contents have not been analyzed.",
            "file_name": path.name,
            "extracted_text": (
                "Pradhan Mantri Kanya Kalyan Yojna 2026. "
                "Get INR 50,000 grant directly in bank account. "
                "Registration fee: INR 500. Apply at www.pmkanyaupdates.org"
            ),
            "scheme_name": "Pradhan Mantri Kanya Kalyan Yojna (Unverified Poster)",
            "claimed_benefit": "₹50,000 cash grant to all applicants",
            "registration_fee": "₹500 application fee",
            "official_url": "www.pmkanyaupdates.org (Unofficial domain)",
            "phone": "+91-9876543210",
            "claims": [
                "Claims to be a central government scheme offering ₹50,000 cash grant.",
                "Demands an upfront ₹500 registration fee.",
                "Directs users to an unofficial commercial domain (pmkanyaupdates.org instead of .gov.in).",
            ],
            "red_flags": [
                "Government schemes never charge an online registration fee to personal accounts.",
                "Domain is not an official government portal (.gov.in or .nic.in).",
            ],
            "confidence": "Demo Extractor",
            "requires_verification": True,
        }
