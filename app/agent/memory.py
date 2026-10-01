import re
from typing import Any, Dict, Optional, Tuple


INDIAN_STATES = [
    "Uttar Pradesh", "Bihar", "Rajasthan", "Madhya Pradesh", "Maharashtra",
    "Delhi", "Haryana", "Punjab", "Gujarat", "Karnataka", "Tamil Nadu",
    "West Bengal", "Odisha", "Kerala", "Assam", "Jharkhand", "Uttarakhand"
]

COURSES = [
    "BTech", "B.Tech", "Engineering", "Diploma", "BSc", "B.Sc", "BA", "B.A",
    "MBBS", "12th", "10th", "Postgraduate", "Graduate", "Coaching", "Polytechnic"
]

KNOWN_CITIES = {
    "delhi": "Delhi",
    "jaipur": "Jaipur",
    "lucknow": "Lucknow",
    "mumbai": "Mumbai",
    "bhopal": "Bhopal",
    "patna": "Patna",
    "kolkata": "Kolkata",
    "bengaluru": "Bengaluru",
    "bangalore": "Bengaluru",
    "chennai": "Chennai",
    "hyderabad": "Hyderabad",
    "pune": "Pune",
    "kanpur": "Kanpur",
    "agra": "Agra",
    "varanasi": "Varanasi",
    "ahmedabad": "Ahmedabad",
    "chandigarh": "Chandigarh",
    "noida": "Noida",
    "gurgaon": "Gurugram",
    "gurugram": "Gurugram",
    "indore": "Indore",
    "surat": "Surat",
    "nagpur": "Nagpur",
    "amritsar": "Amritsar",
    "shimla": "Shimla",
    "dehradun": "Dehradun",
    "ranchi": "Ranchi",
    "guwahati": "Guwahati",
    "जयपुर": "Jaipur",
    "दिल्ली": "Delhi",
    "लखनऊ": "Lucknow",
    "मुंबई": "Mumbai",
}


def detect_language(text: str) -> str:
    """Detects primary language: Hindi, Hinglish, or English."""
    # Check for Devanagari script
    if re.search(r"[\u0900-\u097F]", text):
        return "Hindi"

    lowered = text.lower()
    hindi_markers = [
        "mein", "kya", "hai", "hain", "karo", "batao", "hogi", "hoon", "mere", "meri",
        "chahiye", "kar do", "kaise", "kab", "kahan", "kaha", "kisko", "nahi", "nahin",
        "baarish", "barish", "mausam", "bataiye", "kitna", "hota", "paas", "bhej",
        "iska", "aur", "do", "kuch", "tum", "aap", "kaun", "bhi", "ko", "se", "par",
        "ke", "ki", "ka", "namaste", "bhai", "samjhao", "banao", "raha", "rahe", "rahi"
    ]
    matches = sum(1 for m in hindi_markers if re.search(rf"\b{m}\b", lowered))
    if matches >= 1:
        return "Hinglish"
    return "English"


def extract_context(text: str, current_context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Extracts slot entities (state, course, year, income, tracking_id, city, phone) from caller utterance."""
    ctx = dict(current_context or {})
    lowered = text.lower()

    # 0. User correction detection (e.g. "Nahi, Jaipur", "No, Mumbai", "Actually Lucknow")
    m_corr = re.search(r"\b(?:nahi|nahin|no|not|wait|actually|instead of)\s*,?\s*([A-Za-z]{3,20})\b", text, re.I)
    if m_corr:
        cand = m_corr.group(1).lower()
        if cand in KNOWN_CITIES:
            ctx["city"] = KNOWN_CITIES[cand]
        elif cand not in ("kal", "aaj", "parso", "mausam", "weather", "barish", "batao", "karo", "theek", "shikayat", "complaint", "sms"):
            ctx["city"] = cand.title()

    # 1. State detection
    for st in INDIAN_STATES:
        if st.lower() in lowered:
            ctx["state"] = st
            break
    if not ctx.get("state"):
        if re.search(r"\bup\b", lowered) or "u.p." in lowered:
            ctx["state"] = "Uttar Pradesh"
        elif re.search(r"\bmp\b", lowered) or "m.p." in lowered:
            ctx["state"] = "Madhya Pradesh"

    # 2. Course / Education
    for c in COURSES:
        if c.lower() in lowered:
            ctx["course"] = "BTech" if "btech" in c.lower() or "b.tech" in c.lower() or "engineering" in c.lower() else c
            break

    # 3. Year of study
    m_year = re.search(r"\b(first|second|third|fourth|1st|2nd|3rd|4th)\s+year\b", lowered)
    if m_year:
        ctx["year"] = m_year.group(1).title()

    # 4. Income detection (e.g. 1.8L, 1.8 lakh, 180000, 2 lakh, 250000)
    m_inc_lakh = re.search(r"(\d+(?:\.\d+)?)\s*(?:lakh|lakhs|l)\b", lowered)
    if m_inc_lakh:
        ctx["income"] = float(m_inc_lakh.group(1)) * 100000.0
    else:
        m_inc_num = re.search(r"\b([1-9]\d{4,6})\b", text)
        if m_inc_num and not any(w in lowered for w in ["otp", "pin", "cvv", "password"]):
            ctx["income"] = float(m_inc_num.group(1))

    # 5. Tracking ID (e.g. ABC123, BL9921, DEL409)
    m_track = re.search(r"\b([A-Za-z]{2,4}\d{3,6})\b", text)
    if m_track:
        ctx["tracking_id"] = m_track.group(1).upper()

    # 6. City (weather / location)
    for k_city, norm_city in KNOWN_CITIES.items():
        if k_city in lowered or k_city in text:
            ctx["city"] = norm_city
            break

    if not ctx.get("city"):
        # Pattern like "weather in Mumbai", "in Delhi", "Delhi ka", "Jaipur mein"
        m_post = re.search(r"\b([A-Za-z]{3,15})\s+(?:mein|me|ka|ki|ke|weather|mausam)\b", text, re.I)
        if m_post and m_post.group(1).title() not in ("Kal", "Aaj", "Parso", "Bolo", "Weather", "Mausam", "Barish", "State"):
            ctx["city"] = m_post.group(1).title()
        else:
            m_pre = re.search(r"(?:in|near|for|around)\s+([A-Za-z]{3,15})\b", text, re.I)
            if m_pre and m_pre.group(1).title() not in ("Kal", "Aaj", "Parso", "Bolo", "Weather", "Barish"):
                ctx["city"] = m_pre.group(1).title()

    # 7. Mobile phone number
    m_phone = re.search(r"\b([6-9]\d{9})\b", text)
    if m_phone:
        ctx["phone"] = m_phone.group(1)

    # 8. Concept tracking for follow-ups
    if any(w in lowered for w in ["photosynthesis", "prakash sanshleshan", "प्रकाश संश्लेषण", "पौधे", "भोजन कैसे"]):
        ctx["last_concept"] = "photosynthesis"
    elif "cloud computing" in lowered:
        ctx["last_concept"] = "cloud_computing"
    elif any(w in lowered for w in ["ai agent", "agent kya hota", "agent kya hai"]):
        ctx["last_concept"] = "ai_agent"
    elif any(w in lowered for w in ["python", "c++"]):
        ctx["last_concept"] = "python_cpp"

    return ctx


def detect_caller_intent(text: str, context: Dict[str, Any]) -> Tuple[str, Optional[str], Dict[str, Any]]:
    """Classifies user intent and returns (intent_key, goal_description, flags)."""
    lowered = text.lower()
    flags: Dict[str, Any] = {}

    # Check negative/prohibition intent first
    if re.search(r"\b(do not|don't|mat karo|nahi karna|never|stop)\b", lowered):
        flags["prohibited"] = True

    # 1. Ambiguous utterances
    if any(p in lowered or p in text for p in ["woh kar do", "help me", "वह भेज दो", "kuch karo", "help karo"]):
        if len(text.strip().split()) <= 4 and not any(w in lowered for w in ["weather", "scholarship", "sms", "parcel", "courier"]):
            return ("ambiguous", "Ambiguous service request requiring clarification", flags)

    # 1b. Document / Poster Upload Request
    if any(w in lowered for w in ["poster", "photo", "document", "tasveer", "image", "tasveer"]) and any(w in lowered for w in ["verify", "check", "batao", "dekh", "paas", "karna"]):
        return ("REQUEST_UPLOAD", "Send photo upload link to verify poster/document", flags)

    # 2. Uncertain Claim / Verification
    if any(w in lowered for w in ["verify this claim", "genuine", "is this", "asli hai", "fake to nahi", "claim:"]) or \
       (any(w in lowered for w in ["milenge", "free money", "paise milenge"]) and "?" in text):
        return ("VERIFY_INFORMATION", "Verify factual claim or authenticity", flags)

    # 3. Weather (including multi-turn follow-ups: "Aur parso?", "Kal ka?", and city correction "Nahi, Jaipur")
    is_weather_explicit = any(w in lowered for w in ["weather", "baarish", "barish", "mausam", "temperature", "forecast"]) or \
                          any(w in text for w in ["मौसम", "बारिश"])
    is_weather_followup = (any(w in lowered for w in ["parso", "parson", "day after tomorrow", "kal ka", "aaj ka", "aur parso"]) or \
                          (re.search(r"\b(nahi|no|wait|actually)\b", lowered) and any(k in lowered for k in KNOWN_CITIES))) and \
                          (bool(context.get("city")) or context.get("last_intent") == "WEATHER_QUERY")

    if is_weather_explicit or is_weather_followup:
        city = context.get("city")
        return ("WEATHER_QUERY", f"Check live weather forecast for {city or 'city'}", flags)

    # 4. SMS Actions
    if any(w in lowered for w in ["sms", "link bhej", "send link", "send the link", "message kar"]):
        return ("SEND_SMS_LINK", "Send official application portal link via SMS", flags)

    # 5. Complaints / Grievance Actions
    if any(w in lowered for w in ["complaint", "shikayat", "grievance", "register a complaint"]):
        return ("FILE_COMPLAINT", "File official service grievance for delayed courier", flags)

    # 6. Courier Tracking
    if any(w in lowered for w in ["parcel", "courier", "package", "tracking", "track", "kaha hai", "kahan hai"]):
        tid = context.get("tracking_id", "consignment")
        return ("COURIER_TRACKING", f"Track shipping status for parcel {tid}", flags)

    # 7. Government Schemes (including multi-turn followups when answering missing income or course)
    is_scheme_explicit = any(w in lowered for w in ["scholarship", "scheme", "yojana", "financial aid", "fee reimbursement"]) or \
                         any(w in text for w in ["छात्रवृत्ति", "योजना"])
    is_scheme_followup = (context.get("last_intent") == "SCHEME_SEARCH" or (context.get("state") and context.get("course"))) and \
                         (context.get("income") is not None or any(w in lowered for w in ["income", "lakh", "year", "btech", "course", "rupaye"]))

    if is_scheme_explicit or is_scheme_followup:
        st = context.get("state", "India")
        return ("SCHEME_SEARCH", f"Identify eligible government schemes in {st}", flags)

    # 8. Education / Explanation (Photosynthesis, Cloud computing, AI agents, Python vs C++, etc.)
    is_concept_followup = (context.get("last_intent") == "CONCEPT_EXPLAIN" or bool(context.get("last_concept"))) and \
                          any(w in lowered for w in ["example", "udaharan", "simple", "easy", "aur batao", "explain", "samjhao", "aur easy", "iska aur"])

    if "cloud computing" in lowered:
        return ("CONCEPT_EXPLAIN", "Explain cloud computing concept in simple words", {**flags, "concept": "cloud_computing"})

    if any(w in lowered for w in ["ai agent", "agent kya hota", "agent kya hai", "what is an ai agent"]):
        return ("CONCEPT_EXPLAIN", "Explain AI agent concept in simple words", {**flags, "concept": "ai_agent"})

    if any(w in lowered for w in ["python aur c++", "python vs c++", "python and c++", "python ya c++", "difference between python"]):
        return ("CONCEPT_EXPLAIN", "Compare Python and C++ concisely", {**flags, "concept": "python_cpp"})

    is_photo_query = any(w in lowered for w in ["photosynthesis", "prakash sanshleshan", "प्रकाश संश्लेषण", "पौधे", "भोजन कैसे"])
    if is_photo_query or is_concept_followup:
        active_concept = context.get("last_concept", "photosynthesis")
        return ("CONCEPT_EXPLAIN", f"Explain {active_concept} in simple words", {**flags, "concept": active_concept})

    # 9. Small Talk, Greetings & Capabilities
    if re.search(r"^(hello|hi|hey|namaste|pranam|ram ram|kya haal|kaise ho)\b", lowered) or \
       (any(w in lowered for w in ["hello boloai", "hi boloai", "namaste boloai"]) and not any(w in lowered for w in ["weather", "scholarship", "parcel", "scheme"])):
        return ("GENERAL_INQUIRY", "Conversational greeting and welcome", {**flags, "sub_intent": "greeting"})

    if any(w in lowered for w in ["kya kya kar sakte ho", "tum kya kar sakte ho", "aap kya kar sakte ho", "what can you do", "features kya hai", "capabilities"]):
        return ("GENERAL_INQUIRY", "Describe BoloAI capabilities concisely", {**flags, "sub_intent": "capabilities"})

    if re.search(r"\b(thank you|thanks|shukriya|dhanyawad|dhanyavad)\b", lowered):
        return ("GENERAL_INQUIRY", "Polite closing acknowledgement", {**flags, "sub_intent": "gratitude"})

    if "resume" in lowered and any(w in lowered for w in ["improve", "kaise", "banao", "tips", "better"]):
        return ("GENERAL_INQUIRY", "Provide concise resume improvement advice", {**flags, "sub_intent": "resume"})

    # 10. General Knowledge
    if any(w in lowered for w in ["gravity", "what is", "kitna hota hai", "plus 2", "capital of"]):
        return ("GENERAL_INQUIRY", "General knowledge information inquiry", flags)

    return ("GENERAL_INQUIRY", "Digital services assistance", flags)

