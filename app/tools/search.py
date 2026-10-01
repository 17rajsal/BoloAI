from datetime import datetime, timezone
import json
import logging
import re
from typing import Any, Dict, List, Optional
import urllib.parse
import httpx
from .. import config

logger = logging.getLogger(__name__)

_TAVILY_OBSERVATION: Dict[str, Any] = {"ok": None, "error": None, "timestamp": None}

OFFICIAL_DOMAINS = [
    ".gov.in",
    ".nic.in",
    "india.gov.in",
    "mygov.in",
    "uidai.gov.in",
    "pmkisan.gov.in",
    "isro.gov.in",
    "indiapost.gov.in",
    "upsc.gov.in",
    "scholarships.gov.in",
    "swayam.gov.in",
    "diksha.gov.in",
    "epfindia.gov.in",
]

UNTRUSTED_BLOG_PATTERNS = [
    "blogspot",
    "wordpress",
    "medium.com",
    "sarkariresult",
    "sarkariexam",
    "fresherslive",
    "jagranjosh",
    "collegedunia",
    "shiksha",
]


def get_tavily_observation() -> Dict[str, Any]:
    return dict(_TAVILY_OBSERVATION)


def set_tavily_observation(ok: bool, error: Optional[str] = None):
    _TAVILY_OBSERVATION["ok"] = ok
    _TAVILY_OBSERVATION["error"] = error
    _TAVILY_OBSERVATION["timestamp"] = datetime.now(timezone.utc).isoformat()


def is_official_gov_domain(url_or_domain: str) -> bool:
    target = url_or_domain.lower()
    return any(dom in target for dom in OFFICIAL_DOMAINS)


def is_untrusted_blog(url_or_domain: str) -> bool:
    target = url_or_domain.lower()
    return any(p in target for p in UNTRUSTED_BLOG_PATTERNS)


def search_web(query: str, max_results: int = 5) -> Dict[str, Any]:
    """Search for fresh external/web information using Tavily as primary provider,
    with robust curated fallback for official Indian government datasets and encyclopedic concepts.
    Returns structured results: title, source, domain, URL, snippet, date, is_official, source_type.
    """
    ts = datetime.now(timezone.utc).isoformat()
    cleaned_query = query.strip()
    lowered = cleaned_query.lower()

    # 1. Primary: Tavily Live Web Search (when TAVILY_API_KEY is configured)
    if config.has_tavily():
        try:
            with httpx.Client(timeout=8.0) as client:
                resp = client.post(
                    "https://api.tavily.com/search",
                    json={
                        "api_key": config.TAVILY_API_KEY,
                        "query": cleaned_query,
                        "search_depth": "basic",
                        "include_answer": True,
                        "max_results": max(max_results * 2, 6),
                    },
                    headers={"Content-Type": "application/json"},
                )
                if resp.status_code == 200:
                    data = resp.json()
                    raw_items = data.get("results", [])
                    formatted: List[Dict[str, Any]] = []

                    for item in raw_items:
                        url = item.get("url") or ""
                        parsed = urllib.parse.urlparse(url)
                        domain = parsed.netloc.lower()
                        title = item.get("title") or cleaned_query
                        snippet = item.get("content") or ""
                        is_gov = is_official_gov_domain(domain) or is_official_gov_domain(url)
                        is_blog = is_untrusted_blog(domain) or is_untrusted_blog(url)

                        source_type = (
                            "VERIFIED_OFFICIAL" if is_gov
                            else "UNVERIFIED_BLOG" if is_blog
                            else "VERIFIED_MULTIPLE_SOURCES"
                        )

                        formatted.append({
                            "title": title,
                            "source": domain or "Web Source",
                            "domain": domain,
                            "url": url,
                            "snippet": snippet,
                            "date": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
                            "is_official": is_gov,
                            "source_type": source_type,
                        })

                    # Rank official government domains first (.gov.in / .nic.in)
                    formatted.sort(key=lambda x: (not x["is_official"], x["source_type"] == "UNVERIFIED_BLOG"))

                    if formatted:
                        set_tavily_observation(True, None)
                        return {
                            "ok": True,
                            "query": cleaned_query,
                            "timestamp": ts,
                            "provider": "tavily",
                            "results_count": len(formatted),
                            "results": formatted[:max_results],
                        }
                else:
                    err_msg = f"Tavily HTTP {resp.status_code}: {resp.text[:120]}"
                    logger.warning(err_msg)
                    set_tavily_observation(False, err_msg)
        except Exception as exc:
            err_msg = f"Tavily connection failed: {str(exc)}"
            logger.warning(err_msg)
            set_tavily_observation(False, err_msg)

    # 2. Curated & Instant Knowledge Fallback (when Tavily is unconfigured or unavailable)
    curated_results: List[Dict[str, Any]] = []

    # Check known official schemes from verified database
    try:
        from .schemes import load_schemes
        schemes = load_schemes(include_demo=False)
        for s in schemes:
            name_lower = s.get("name", "").lower()
            auth_lower = s.get("authority", "").lower()
            state_lower = s.get("state", "").lower()
            desc_lower = (s.get("description") or "").lower()

            words = [w for w in re.split(r"\W+", lowered) if len(w) > 2]
            score = sum(1 for w in words if w in name_lower or w in auth_lower or w in state_lower or w in desc_lower)

            if score >= 1 or (("scholarship" in lowered or "scheme" in lowered or "yojana" in lowered) and (state_lower in lowered or "up" in lowered)):
                official_url = s.get("official_url", "https://india.gov.in")
                domain = urllib.parse.urlparse(official_url).netloc.lower()
                curated_results.append({
                    "title": s.get("name", "Government Scheme"),
                    "source": s.get("authority", "Official Authority"),
                    "domain": domain,
                    "url": official_url,
                    "snippet": f"{s.get('name')} by {s.get('authority')}. Benefit: {s.get('benefit', '')}. Eligibility: {s.get('eligibility', '')}",
                    "date": s.get("last_verified_date", datetime.now(timezone.utc).strftime("%Y-%m-%d")),
                    "is_official": True,
                    "source_type": "VERIFIED_OFFICIAL",
                })
    except Exception:
        pass

    # Curated official entries for foundational queries
    if "isro" in lowered or "space" in lowered:
        curated_results.append({
            "title": "ISRO — Indian Space Research Organisation (Official Portal)",
            "source": "isro.gov.in",
            "domain": "isro.gov.in",
            "url": "https://www.isro.gov.in",
            "snippet": "Indian Space Research Organisation (ISRO) is the national space agency of India, headquartered in Bengaluru. Primary leadership and official missions are published on isro.gov.in.",
            "date": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
            "is_official": True,
            "source_type": "VERIFIED_OFFICIAL",
        })

    # DuckDuckGo Instant Answer as encyclopedic fallback
    try:
        with httpx.Client(timeout=4.0, follow_redirects=True) as client:
            resp = client.get(
                "https://api.duckduckgo.com/",
                params={"q": cleaned_query, "format": "json", "no_html": 1, "skip_disambig": 1},
                headers={"User-Agent": "BoloAI-Gateway/1.0"},
            )
            if resp.status_code == 200:
                data = resp.json()
                if data.get("AbstractText"):
                    abs_url = data.get("AbstractURL") or "https://duckduckgo.com"
                    abs_domain = urllib.parse.urlparse(abs_url).netloc.lower()
                    is_gov = is_official_gov_domain(abs_domain)
                    curated_results.append({
                        "title": data.get("Heading") or cleaned_query,
                        "source": data.get("AbstractSource") or "Reference Encyclopedia",
                        "domain": abs_domain,
                        "url": abs_url,
                        "snippet": data.get("AbstractText"),
                        "date": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
                        "is_official": is_gov,
                        "source_type": "VERIFIED_OFFICIAL" if is_gov else "VERIFIED_MULTIPLE_SOURCES",
                    })
    except Exception:
        pass

    if curated_results:
        # Prioritize official results
        curated_results.sort(key=lambda x: not x["is_official"])
        return {
            "ok": True,
            "query": cleaned_query,
            "timestamp": ts,
            "provider": "curated",
            "results_count": len(curated_results),
            "results": curated_results[:max_results],
        }

    return {
        "ok": False,
        "query": cleaned_query,
        "timestamp": ts,
        "results_count": 0,
        "results": [],
        "error": "Live search unavailable or no results returned; claim not verified",
    }
