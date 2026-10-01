from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from ..models import VerificationDetail, VerificationStatus
from .actions import normalize_action_result


class VerificationService:
    """Service to inspect claims, tool outputs, and factual assertions.
    Classifies information trustworthiness without fabricating numerical percentages.
    """

    OFFICIAL_DOMAINS = [
        ".gov.in",
        ".nic.in",
        "up.gov.in",
        "open-meteo.com",
        "uidai.gov.in",
        "pmkisan.gov.in",
        "scholarships.gov.in",
        "abhyuday.up.gov.in",
        "indiapost.gov.in",
    ]

    @classmethod
    def verify_tool_result(cls, tool_name: str, result: Dict[str, Any], query_context: Optional[str] = None) -> VerificationDetail:
        ts = datetime.now(timezone.utc).isoformat()
        sources: List[Dict[str, Any]] = []

        if not isinstance(result, dict):
            result = {"ok": False, "error": "Invalid tool result"}
        from ..tools.registry import ToolRegistry
        if ToolRegistry.get_metadata(tool_name).get("is_action"):
            result = normalize_action_result(tool_name, result)
            if result["ok"]:
                simulated = result["simulated"]
                return VerificationDetail(
                    status=VerificationStatus.PARTIALLY_VERIFIED if simulated else VerificationStatus.VERIFIED_OFFICIAL,
                    sources=[{"provider": result.get("provider"), "reference_id": result.get("reference_id"),
                              "simulated": simulated}],
                    reason="Demo action simulated; no real provider action." if simulated else "Provider explicitly acknowledged the action.",
                    timestamp=ts, confidence_label="Simulated Action" if simulated else "Action Confirmed")
        if result.get("ok") is not True or result.get("success") is False or result.get("error"):
            return VerificationDetail(
                status=VerificationStatus.UNVERIFIED,
                sources=[],
                reason=f"Tool '{tool_name}' failed: {result.get('error', 'Provider failure')}",
                timestamp=ts,
                confidence_label="Failed",
            )

        if tool_name == "get_weather":
            if result.get("ok"):
                sources.append({
                    "name": "Open-Meteo Realtime Forecast API",
                    "type": "Live Meteorological Sensor Network",
                    "url": "https://open-meteo.com",
                    "is_official": True,
                })
                return VerificationDetail(
                    status=VerificationStatus.VERIFIED_OFFICIAL,
                    sources=sources,
                    reason=f"Realtime meteorological forecast confirmed for {result.get('city', 'location')} via Open-Meteo.",
                    timestamp=ts,
                    confidence_label="High",
                )
            else:
                return VerificationDetail(
                    status=VerificationStatus.UNVERIFIED,
                    sources=[],
                    reason="Could not retrieve live weather coordinates.",
                    timestamp=ts,
                    confidence_label="Uncertain",
                )

        if tool_name in ("find_schemes", "find_demo_schemes"):
            matches = result.get("matches", [])
            if not matches:
                return VerificationDetail(
                    status=VerificationStatus.UNVERIFIED,
                    sources=[],
                    reason="No schemes matched the specified criteria.",
                    timestamp=ts,
                    confidence_label="Low",
                )

            # Check if any matches are verified official
            verified_matches = [m for m in matches if m.get("source_type") == "VERIFIED_OFFICIAL"]
            demo_matches = [m for m in matches if m.get("source_type") == "DEMO_DATA"]

            for m in matches:
                sources.append({
                    "name": m.get("authority", "Authority"),
                    "scheme": m.get("name"),
                    "url": m.get("official_url"),
                    "is_official": m.get("source_type") == "VERIFIED_OFFICIAL",
                    "last_verified": m.get("last_verified_date"),
                })

            if verified_matches:
                missing = result.get("missing_criteria", [])
                if missing:
                    return VerificationDetail(
                        status=VerificationStatus.PARTIALLY_VERIFIED,
                        sources=sources,
                        reason=f"Official schemes identified, but caller has not provided: {', '.join(missing)}. Full eligibility requires these details.",
                        timestamp=ts,
                        confidence_label="Medium",
                    )
                return VerificationDetail(
                    status=VerificationStatus.VERIFIED_OFFICIAL,
                    sources=sources,
                    reason="Cross-referenced against verified official government portals (.gov.in).",
                    timestamp=ts,
                    confidence_label="Authoritative",
                )
            else:
                return VerificationDetail(
                    status=VerificationStatus.UNVERIFIED,
                    sources=sources,
                    reason="Results originate from a demo/mock dataset for testing. Not official government records.",
                    timestamp=ts,
                    confidence_label="Demo / Unverified",
                )

        if tool_name == "search_web":
            web_results = result.get("results", [])
            for r in web_results:
                domain = r.get("domain") or ""
                url = r.get("url") or ""
                if not domain and url:
                    try:
                        import urllib.parse
                        domain = urllib.parse.urlparse(url).netloc.lower()
                    except Exception:
                        domain = ""
                is_gov = bool(r.get("is_official")) or any(dom in url for dom in cls.OFFICIAL_DOMAINS) or any(dom in domain for dom in cls.OFFICIAL_DOMAINS)
                sources.append({
                    "name": r.get("source", domain or "Web Source"),
                    "title": r.get("title"),
                    "domain": domain,
                    "url": url,
                    "is_official": is_gov,
                })

            has_gov = any(s.get("is_official") for s in sources)
            query_ctx = (query_context or result.get("query") or "").lower()
            is_scheme_or_gov_claim = any(w in query_ctx for w in ["scheme", "yojana", "scholarship", "claim", "government", "sarkari", "subsidy", "free money"])

            if has_gov:
                return VerificationDetail(
                    status=VerificationStatus.VERIFIED_OFFICIAL,
                    sources=sources,
                    reason="Found authoritative public/government web documentation (.gov.in / .nic.in).",
                    timestamp=ts,
                    confidence_label="Authoritative" if any(".gov.in" in s.get("url", "") or ".nic.in" in s.get("url", "") for s in sources) else "High",
                )
            elif is_scheme_or_gov_claim:
                # For government schemes, do not accept random blogs as verification.
                return VerificationDetail(
                    status=VerificationStatus.UNVERIFIED,
                    sources=sources,
                    reason="Government schemes require verification on official government portals (.gov.in / .nic.in). Random blogs or unofficial portals cannot verify official schemes.",
                    timestamp=ts,
                    confidence_label="Unverified",
                )
            elif len(sources) >= 2:
                return VerificationDetail(
                    status=VerificationStatus.VERIFIED_MULTIPLE_SOURCES,
                    sources=sources,
                    reason="Corroborated by multiple independent public web sources.",
                    timestamp=ts,
                    confidence_label="Medium-High",
                )
            elif sources:
                return VerificationDetail(
                    status=VerificationStatus.PARTIALLY_VERIFIED,
                    sources=sources,
                    reason="Single web reference found; advised to verify with primary authority.",
                    timestamp=ts,
                    confidence_label="Moderate",
                )
            return VerificationDetail(
                status=VerificationStatus.UNVERIFIED,
                sources=[],
                reason="No reliable web references could be established.",
                timestamp=ts,
                confidence_label="Unverified",
            )

        if tool_name == "track_courier":
            sources.append({
                "name": result.get("carrier", "Carrier"),
                "source": result.get("source", "Logistics Hub"),
                "url": "https://example.com/logistics",
                "is_official": False,
            })
            return VerificationDetail(
                status=VerificationStatus.PARTIALLY_VERIFIED,
                sources=sources,
                reason=f"Status retrieved from logistics tracking endpoint. Package {result.get('status', 'ACTIVE')}.",
                timestamp=ts,
                confidence_label="Medium (Simulated Carrier)",
            )

        if tool_name == "create_complaint":
            return VerificationDetail(
                status=VerificationStatus.VERIFIED_OFFICIAL,
                sources=[{"name": "Grievance Redressal Dispatcher", "ref": result.get("reference_id")}],
                reason=f"Action confirmed and reference ticket {result.get('reference_id')} logged.",
                timestamp=ts,
                confidence_label="Action Confirmed",
            )

        if tool_name == "send_sms":
            is_sim = result.get("simulated", True)
            return VerificationDetail(
                status=VerificationStatus.PARTIALLY_VERIFIED if is_sim else VerificationStatus.VERIFIED_OFFICIAL,
                sources=[{"provider": result.get("provider"), "reference_id": result.get("reference_id")}],
                reason="SMS dispatch simulated for testing." if is_sim else "SMS successfully handed to cellular carrier.",
                timestamp=ts,
                confidence_label="Simulated Action" if is_sim else "Action Completed",
            )

        # Default fallback
        return VerificationDetail(
            status=VerificationStatus.UNVERIFIED,
            sources=[],
            reason="Unverified claim or knowledge assertion.",
            timestamp=ts,
            confidence_label="Unverified",
        )
