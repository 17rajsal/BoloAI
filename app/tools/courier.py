from datetime import datetime, timezone
import random
from typing import Any, Dict, Optional


def track_courier(tracking_id: str) -> Dict[str, Any]:
    """Look up shipping and delivery status for a courier package.
    Simulated demo service showing live parcel tracking.
    """
    cleaned_id = tracking_id.strip().upper()
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    # Seeded details for common demo tracking IDs
    is_delayed = True
    hub = "New Delhi Sorting Hub (Okhla)"
    carrier = "SpeedPost Express"
    expected = "Tomorrow by 6:00 PM"
    status_text = "Delayed in transit due to route congestion at central sorting hub"

    if "DEL" in cleaned_id:
        status_text = "Out for delivery with delivery executive Rajesh Kumar"
        is_delayed = False
        expected = "Today by 2:00 PM"

    return {
        "ok": True,
        "simulated": True,
        "tool_label": "SIMULATED_DEMO",
        "tracking_id": cleaned_id,
        "carrier": carrier,
        "status": "DELAYED" if is_delayed else "OUT_FOR_DELIVERY",
        "status_description": status_text,
        "current_location": hub,
        "expected_delivery": expected,
        "last_update": ts,
        "can_file_complaint": is_delayed,
        "source": "Mock National Logistics Gateway (Simulated Demo)",
    }


def create_complaint(
    tracking_id: str,
    reason: str = "Delivery delayed beyond promised SLA",
    caller_phone: Optional[str] = None,
) -> Dict[str, Any]:
    """Register an official grievance/complaint regarding a delayed parcel or service issue.
    Generates a unique reference ticket ID.
    """
    if not isinstance(tracking_id, str) or not tracking_id.strip():
        return {"ok": False, "simulated": True, "reference_id": None, "error": "Tracking ID is required"}
    ts = datetime.now(timezone.utc).isoformat()
    random_num = random.randint(1000, 9999)
    ref_id = f"BOL-CMP-2026-{random_num}"

    return {
        "ok": True,
        "simulated": True,
        "tool_label": "SIMULATED_ACTION",
        "action_type": "REGISTER_COMPLAINT",
        "reference_id": ref_id,
        "tracking_id": tracking_id.strip().upper(),
        "reason": reason,
        "caller_phone": caller_phone or "+91-98******21",
        "status": "REGISTERED",
        "priority": "HIGH",
        "sla_resolution_hours": 24,
        "timestamp": ts,
        "message": f"Demo complaint simulated with reference {ref_id}; no real courier complaint was filed.",
    }
