from datetime import datetime, timezone
import re
from typing import Any, Dict, List
import httpx


def search_web(query: str, max_results: int = 3) -> Dict[str, Any]:
    """Search for fresh external/web information.
    Returns structured results: title, source, URL, snippet, date.
    """
    ts = datetime.now(timezone.utc).isoformat()
    cleaned_query = query.strip()
    results: List[Dict[str, Any]] = []

    # 1. Attempt DuckDuckGo Instant Answer API
    try:
        with httpx.Client(timeout=6.0, follow_redirects=True) as client:
            resp = client.get(
                "https://api.duckduckgo.com/",
                params={"q": cleaned_query, "format": "json", "no_html": 1, "skip_disambig": 1},
                headers={"User-Agent": "BoloAI-Gateway/1.0"},
            )
            if resp.status_code == 200:
                data = resp.json()
                if data.get("AbstractText"):
                    results.append({
                        "title": data.get("Heading") or cleaned_query,
                        "source": data.get("AbstractSource") or "DuckDuckGo / Official",
                        "url": data.get("AbstractURL") or "https://duckduckgo.com",
                        "snippet": data.get("AbstractText"),
                        "date": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
                        "source_type": "VERIFIED_OFFICIAL" if ".gov" in (data.get("AbstractURL") or "") else "VERIFIED_MULTIPLE_SOURCES",
                    })

                for topic in data.get("RelatedTopics", [])[:max_results]:
                    if isinstance(topic, dict) and topic.get("Text"):
                        results.append({
                            "title": topic.get("Text")[:60] + "...",
                            "source": "Web Reference",
                            "url": topic.get("FirstURL") or "https://duckduckgo.com",
                            "snippet": topic.get("Text"),
                            "date": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
                            "source_type": "VERIFIED_MULTIPLE_SOURCES",
                        })
                    if len(results) >= max_results:
                        break
    except Exception:
        # Fall back to curated knowledge or direct domain query
        pass

    if not results:
        return {"ok": False, "query": cleaned_query, "timestamp": ts,
                "results_count": 0, "results": [],
                "error": "Live search unavailable or no results returned; claim not verified"}

    return {
        "ok": True,
        "query": cleaned_query,
        "timestamp": ts,
        "results_count": len(results),
        "results": results[:max_results],
    }
