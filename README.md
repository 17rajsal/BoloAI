# BoloAI 🇮🇳
### Bharat's Voice-First Agentic AI Assistant

**Internet nahi? Bas bolo.**

BoloAI is a voice-first Agentic AI assistant built for Bharat. Users can speak naturally in Hindi, Hinglish, or English, and BoloAI can understand the request, reason about it, use tools, verify information, perform permitted actions, remember conversational context, and reply back through voice and text.

🌐 **Live Demo:** https://boloai-web.onrender.com/

## What BoloAI can do

- 🎙️ Voice-first Hindi, Hinglish & English interaction
- 🧠 Conversational AI with multi-turn memory
- 🌦️ Live weather information
- 🎓 Government scheme and scholarship discovery
- 🔎 Search and information verification
- 📦 Service/courier workflow demonstrations
- 📄 Image/document upload workflows
- 🔊 Automatic spoken AI responses
- 🛡️ Safety and confirmation guardrails
- 🧰 Agentic tool selection and execution

## Agentic Workflow

Understand → Reason → Plan → Use Tools → Verify → Act → Deliver

---

## Truthful Provider Status

BoloAI never claims integrations are live unless real credentials are confirmed:

| Subsystem | Live Status | Fallback / Simulated Status | Condition |
|---|---|---|---|
| **Exotel Telephony** | `LIVE` | `NOT_CONFIGURED` | Requires `EXOTEL_ACCOUNT_SID`, `API_KEY`, `API_TOKEN` |
| **Sarvam STT** | `LIVE` | `MOCK` | Requires `SARVAM_API_KEY` (`saaras:v2`) |
| **Sarvam TTS** | `LIVE` | `MOCK` | Requires `SARVAM_API_KEY` (`bulbul:v1`) |
| **AI Brain** | `LIVE` | `FALLBACK` | Requires `OPENAI_API_KEY` and `DEMO_MODE=false` |
| **Search** | `LIVE` | `CURATED` | Requires `SEARCH_API_KEY`; defaults to curated verified database |
| **SMS Gateway** | `LIVE` | `SIMULATED` | Requires Exotel credentials and `SMS_PROVIDER=exotel` |
| **Verification** | `READY` | `DEGRADED` | Active official domain auditor (.gov.in / .nic.in) |

Check live status anytime at `GET /health`.

---

## Architecture & Pipeline

```
 +-------------------------------------------------------------------------------+
 |                               CALLER EXPERIENCE                               |
 |   Standard Mobile Phone / Feature Phone / Landline (No App, No Internet)      |
 +---------------------------------------+---------------------------------------+
                                         |
                                         | Cellular Voice Call (PSTN)
                                         v
 +-------------------------------------------------------------------------------+
 |                               EXOTEL TELEPHONY                                |
 |   - Inbound Call Management & DTMF Handling                                   |
 |   - Webhook Resolver: GET /exotel/resolve                                     |
 |   - Bidirectional Audio Stream: WS /ws/exotel/{call_id}                      |
 +---------------------------------------+---------------------------------------+
                                         |
                       Streaming Audio   |   Streaming Audio
                       (8kHz L16 PCM)    |   (8kHz L16 PCM)
                                         v   ^
 +-------------------------------------------------------------------------------+
 |                            BOLOAI FASTAPI BACKEND                             |
 |                                                                               |
 |  [ TelephonyAdapter ] <--------> Interruption & Barge-in Clear Stream         |
 |         |                                                                     |
 |         v                                                                     |
 |  [ SpeechToTextAdapter ]                                                      |
 |     ├── Sarvam AI STT (`saaras:v2`, hi-IN, en-IN)                             |
 |     └── MockSTTAdapter (Deterministic Demo Fallback)                          |
 |         |                                                                     |
 |         v (Caller Utterance)                                                  |
 |  [ Master Agent Orchestrator ] <----------------> [ Session Memory Manager ]  |
 |     ├── Intent & Language Detection                  - Slot context (State,   |
 |     ├── Slot Extraction (Context Memory)               Course, Income, ID)    |
 |     ├── Clarification Decision Engine                - Event Audit Timeline   |
 |     └── Dynamic Tool Selection                                                |
 |         |                                                                     |
 |         +----------------------+-----------------------+                      |
 |         |                      |                       |                      |
 |         v                      v                       v                      |
 |  [ ToolRegistry ]       [ VerificationService ]   [ Safety Guardrails ]       |
 |   - Open-Meteo Weather    - VERIFIED_OFFICIAL       - OTP/PIN Blocking        |
 |   - Govt Schemes (.gov)   - VERIFIED_MULTIPLE       - Redaction in memory     |
 |   - Courier Tracking      - PARTIALLY_VERIFIED      - Crisis Disclaimers      |
 |   - Complaint Action      - UNVERIFIED / DEMO       - Action Confirmation     |
 |   - SMS Dispatch Action                                                       |
 |   - Document Upload Token                                                     |
 |         |                                                                     |
 |         v (Voice-Friendly Concierge Response)                                 |
 |  [ TextToSpeechAdapter ]                                                      |
 |     ├── Sarvam AI TTS (`bulbul:v1`, 8000Hz, Meera/Arvind)                    |
 |     └── MockTTSAdapter (8kHz Telephony PCM Generator)                         |
 |                                                                               |
 +---------------------------------------+---------------------------------------+
                                         |
                                         | Realtime WebSocket Push
                                         v
 +-------------------------------------------------------------------------------+
 |                    BRIGHT SAAS HACKATHON DASHBOARD (UI)                       |
 |   - Real-time Subsystem Readiness Indicators (Voice, Speech, AI, Search, ...) |
 |   - Live Call Card with Audio Waveform & Call States                          |
 |   - Live Agent Operational Trace Timeline (Judges Inspection)                 |
 |   - Verified Sources & Portal Inspector (Dedicated Source Cards)              |
 |   - Slide-out Call History Drawer                                             |
 |   - 1-Click Interactive Demo Stories (Scholarship, Weather, Courier, Upload)  |
 +-------------------------------------------------------------------------------+
```

---

## 4 End-to-End Demo Scenarios

Test these in the UI via the **1-Click Demo Buttons** or by typing in the simulator:

### Demo 1 — Higher Education Scholarship & SMS Action
- **Caller:** *"Main UP mein BTech second year mein hoon. Mere liye scholarship hai?"*
- **BoloAI:**
  - Extracts slots: `State: Uttar Pradesh`, `Course: BTech`, `Year: Second Year`.
  - Invokes `find_schemes` tool ➔ Matches *"UP Post-Matric Scholarship & Fee Reimbursement"*.
  - Verification service audits official domain `scholarship.up.gov.in`.
  - Spoken Hindi response: *"Uttar Pradesh mein BTech ke liye 'UP Post-Matric Scholarship' uplabdh hai... Kya main official link SMS kar doon?"*
- **Caller Follow-up:** *"Official link SMS kar do."*
- **BoloAI:**
  - Dispatches `send_sms` action tool with portal URL `https://scholarship.up.gov.in`.
  - Logs action approval and generates reference ID `SIM-SMS-XXXX`.

### Demo 2 — Live Weather via Open-Meteo
- **Caller:** *"Kal Jaipur mein baarish hogi?"*
- **BoloAI:**
  - Identifies `WEATHER_QUERY` intent for city `Jaipur`.
  - Executes `get_weather("Jaipur")` tool querying live Open-Meteo sensor APIs.
  - Verification service flags `VERIFIED_OFFICIAL`.
  - Spoken reply: *"Jaipur mein kal baarish ki sambhavna lagbhag 0% hai. Mausam saaf rahega."*

### Demo 3 — Courier Tracking & Complaint Action
- **Caller:** *"Mera parcel ABC123 kaha hai?"*
- **BoloAI:**
  - Executes `track_courier("ABC123")` ➔ Returns parcel delayed at Okhla sorting hub.
  - Spoken reply: *"Aapka parcel ABC123 abhi New Delhi Sorting Hub par delay chal raha hai... Kya aap complaint darj karwana chahte hain?"*
- **Caller Follow-up:** *"Complaint register kar do."*
- **BoloAI:**
  - Obtains voice confirmation ➔ Invokes `create_complaint` action tool.
  - Generates formal grievance ticket `DEMO-CMP-001`.
  - Dashboard logs `action.completed` event with reference ID.

### Demo 4 — Multimodal Poster Verification & Mobile Upload Handoff
- **Caller:** *"Mere paas ek scheme ka poster hai, check karna hai."*
- **BoloAI:**
  - Detects `REQUEST_UPLOAD` intent.
  - Generates short-lived upload token and sends SMS with link `/u/{token}`.
  - Spoken reply: *"Main aapko photo upload karne ka link SMS kar raha hoon. Link par photo upload karein, main call par hi verify karke batata hoon."*
- **Multimodal Pipeline:**
  - Caller opens mobile upload page ➔ Uploads poster image.
  - Multimodal adapter analyzes text and extracts claims (grant amount, upfront fee).
  - Verification service detects scam red flags (upfront fee required, unverified non-gov domain).
  - BoloAI speaks verdict: *"Maine aapka poster check kiya hai: Ismein upfront fee maangi gayi hai jo fake scheme ka sanket hai. Official government portals par aisi koi certified scheme nahi mili."*

---

## Quickstart & Setup

### Prerequisites
- Python 3.10+
- Git

### 1. Clone & Install Dependencies

```bash
git clone https://github.com/17rajsal/BoloAI.git
cd BoloAI

# Create virtual environment
python -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate

# Install requirements
pip install -r requirements.txt
```

### 2. Configure Environment

Copy `.env.example` to `.env`:

```bash
cp .env.example .env
```

To run in **immediate demo mode** (zero API keys required):
```env
DEMO_MODE=true
HACKATHON_DEMO_MODE=true
```

To enable live OpenAI reasoning and Sarvam Indian Speech:
```env
DEMO_MODE=false
OPENAI_API_KEY=your_openai_api_key_here
SARVAM_API_KEY=your_sarvam_api_key_here
```

### 3. Launch the Application

```bash
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

Open your browser at `http://localhost:8000`.

---

## Docker Deployment

```bash
# Build the Docker image
docker build -t boloai:latest .

# Run the container
docker run -d -p 8000:8000 --name boloai-server --env-file .env boloai:latest

# Health check
curl http://localhost:8000/health
```

---

## Automated Tests & Verification

```bash
# 1. Pytest Integration Suite (94 items)
python -m pytest -v

# 2. Safety & Fallback Evaluation Runner (38/38 PASS)
python -m evals.runner

# 3. Demo Readiness Master Runner
python scripts/run_demo_tests.py
```

---

## Real Call Verification Procedure

To run a live phone call test when Exotel credentials are configured:
1. Configure `EXOTEL_ACCOUNT_SID`, `EXOTEL_API_KEY`, `EXOTEL_API_TOKEN`, and `EXOTEL_EXOPHONE`.
2. Point your Exotel VoiceBot applet to `https://<YOUR_PUBLIC_DOMAIN>/exotel/resolve`.
3. Set `PUBLIC_WS_BASE=wss://<YOUR_PUBLIC_DOMAIN>` in `.env`.
4. Call your ExoPhone from any standard mobile or landline.
5. Say: *"Hello, Hindi mein baat karo."* followed by *"Jaipur mein kal baarish hogi?"*
6. BoloAI answers over the telephone in natural speech.

*Note: In environments without active Exotel telephony credentials, the complete code path and audio streaming framing are fully verified via automated tests and mock doubles (`CODE PATH VERIFIED — LIVE PROVIDER TEST PENDING`).*
