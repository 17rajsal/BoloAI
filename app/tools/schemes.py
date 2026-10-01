import json
from pathlib import Path
from typing import Any, Dict, List, Optional
from ..models import SchemeItem, SourceType

DATA_DIR = Path(__file__).parent.parent / "data"


def load_schemes(include_demo: bool = True) -> List[Dict[str, Any]]:
    schemes: List[Dict[str, Any]] = []

    # 1. Authoritative verified official schemes
    verified_file = DATA_DIR / "verified_schemes.json"
    if verified_file.exists():
        try:
            records = json.loads(verified_file.read_text(encoding="utf-8"))
            for r in records:
                r["source_type"] = SourceType.VERIFIED_OFFICIAL.value
                schemes.append(r)
        except Exception:
            pass

    # 2. Mock demo schemes
    if include_demo:
        demo_file = DATA_DIR / "demo_schemes.json"
        if demo_file.exists():
            try:
                demo_records = json.loads(demo_file.read_text(encoding="utf-8"))
                for r in demo_records:
                    r["source_type"] = SourceType.DEMO_DATA.value
                    schemes.append(r)
            except Exception:
                pass

    return schemes


def find_schemes(
    state: Optional[str] = None,
    education: Optional[str] = None,
    income: Optional[float] = None,
    category: Optional[str] = None,
    include_demo: bool = False,
) -> Dict[str, Any]:
    """Finds matching government schemes based on user state, education, and family income.
    Clearly tags each record as VERIFIED_OFFICIAL or DEMO_DATA.
    """
    all_schemes = load_schemes(include_demo=include_demo)
    matches: List[Dict[str, Any]] = []
    missing_criteria: List[str] = []

    if not state:
        missing_criteria.append("state (e.g. Uttar Pradesh, Bihar)")
    if not education:
        missing_criteria.append("education level (e.g. BTech, 12th, Graduate)")
    if income is None:
        missing_criteria.append("annual family income (e.g. ₹2,00,000)")

    for s in all_schemes:
        # State check
        scheme_state = s.get("state", "All-India").lower()
        if state and scheme_state not in ("all-india", "all", state.lower()):
            continue

        # Education check
        if education:
            edu_lower = education.lower()
            elig_lower = s.get("eligibility", "").lower()
            cat_lower = s.get("category", "").lower()
            # If scheme specifies higher education or courses, check match
            if not any(k in elig_lower or k in cat_lower for k in [edu_lower, "student", "education", "college", "all"]):
                continue

        # Income check
        limit = s.get("income_criteria")
        if income is not None and limit is not None:
            if income > limit:
                continue

        # Category check
        if category and category.lower() not in s.get("category", "").lower():
            pass

        matches.append(s)

    has_verified = any(m.get("source_type") == SourceType.VERIFIED_OFFICIAL.value for m in matches)

    return {
        "ok": True,
        "count": len(matches),
        "matches": matches,
        "missing_criteria": missing_criteria,
        "has_verified_sources": has_verified,
        "prudent_statement": (
            "Based on the information you provided, you appear to match these conditions. "
            "Final verification requires uploading documents on the official portal."
        ),
        "verified_warning": None if has_verified else "Only demo mock schemes found. Real official scheme match requires verified records.",
    }
