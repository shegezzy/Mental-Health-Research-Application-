# Mental Health Research Application

**Exploring Social Media Behaviour & AI-Based Detection of Depression and Suicidal Ideation**

> Academic research tool only. NOT a diagnostic platform. NOT medical advice.

---

## Architecture Overview

```
mental-health-research/
├── backend/
│   ├── main.py                   # FastAPI app entrypoint
│   ├── config/
│   │   └── settings.py           # Environment-based config
│   ├── models/
│   │   └── schemas.py            # Pydantic request/response models
│   ├── routes/
│   │   └── api.py                # All REST endpoints
│   ├── services/
│   │   ├── scoring.py            # ⚡ Rule-based risk scoring (NO AI)
│   │   ├── openai_service.py     # 🤖 AI: explanation & analysis ONLY
│   │   └── sheets.py             # 📊 Google Sheets persistence
│   └── utils/
│       └── session_store.py      # In-memory chat session store
├── frontend/
│   └── index.html                # Complete SPA (HTML + CSS + JS)
├── requirements.txt
├── .env.example
└── README.md
```

### Strict Separation of Roles

| Component | Role | Uses AI? |
|-----------|------|----------|
| `scoring.py` | Computes risk score & classification | ❌ Never |
| `openai_service.py` | Explains results, converses, analyses text | ✅ Only |
| `sheets.py` | Persists all data | ❌ Never |
| `api.py` | Orchestrates the flow | ❌ Never |

---

## Setup Instructions

### 1. Clone & Install

```bash
git clone <repo>
cd mental-health-research
python -m venv venv
source venv/bin/activate   # Windows: venv\Scripts\activate
pip install -r requirements.txt
```

### 2. Configure Environment

```bash
cp .env.example .env
```

Edit `.env` with your credentials (see sections below).

### 3. Google Cloud Setup

**a) Create a Service Account:**
1. Go to [Google Cloud Console](https://console.cloud.google.com)
2. Create a new project or select existing
3. Enable **Google Sheets API**: APIs & Services → Library → search "Sheets"
4. Go to IAM & Admin → Service Accounts → Create Service Account
5. Grant role: **Editor** (or custom with Sheets write access)
6. Create a JSON key → download it

**b) Prepare the credentials for `.env`:**
```bash
# Convert JSON to single line for .env
cat your-creds.json | python3 -c "import sys,json; print(json.dumps(json.load(sys.stdin)))"
```
Paste the output as `GOOGLE_SERVICE_ACCOUNT_JSON=...` in `.env`

**c) Create the Google Sheet:**
1. Create a new Google Sheet
2. Rename "Sheet1" tab to **Submissions**
3. Copy the Spreadsheet ID from the URL: `https://docs.google.com/spreadsheets/d/<ID>/edit`
4. Share the sheet with your service account email (Editor permission)
5. Set `GOOGLE_SHEETS_SPREADSHEET_ID=<ID>` in `.env`

### 4. OpenAI API Setup

1. Go to [OpenAI Platform](https://platform.openai.com)
2. Create an API key
3. Set `OPENAI_API_KEY=your_key` in `.env`
4. Keep `OPENAI_MODEL=gpt-5.4-nano` for the lowest-cost text model currently configured for this app

### 5. Run the Application

```bash
uvicorn backend.main:app --reload --port 8000
```

Visit: [http://localhost:8000](http://localhost:8000)

API Docs: [http://localhost:8000/docs](http://localhost:8000/docs)

---

## API Reference

### POST `/api/submit`
Receives questionnaire, computes rule-based score. **No AI.**

**Request:**
```json
{
  "personal_details": {
    "age": 24,
    "gender": "Female",
    "education": "Bachelor's Degree",
    "social_media_hours": 4.5,
    "platforms_used": ["Instagram", "TikTok"]
  },
  "responses": {
    "Q1": 4, "Q2": 3, "Q3": 5, "Q4": 2,
    "Q5": 4, "Q6": 5, "Q7": 4, "Q8": 3,
    "Q9": 4, "Q10": 2, "Q11": 2, "Q12": 5,
    "Q13": 3, "Q14": 4, "Q15": 3, "Q16": 2,
    "Q17": 3, "Q18": 4, "Q19": 3, "Q20": 5,
    "Q21": 3, "Q22": 2, "Q23": 4, "Q24": 2, "Q25": 3
  }
}
```

**Response:**
```json
{
  "total_score": 44,
  "max_score": 60,
  "percentage": 73.3,
  "risk_level": "High Risk",
  "key_factors": ["persistent feelings of sadness", "loss of interest"],
  "scored_questions": { "Q6": 5, "Q7": 4, ... }
}
```

---

### POST `/api/explain`
AI generates human-readable explanation. **Does NOT change risk level.**

**Request:**
```json
{
  "score": 44,
  "risk_level": "High Risk",
  "key_factors": ["persistent feelings of sadness", "loss of interest"]
}
```

---

### POST `/api/chat/start`
Initialises optional AI conversation session.

**Response:**
```json
{
  "session_id": "uuid-here",
  "opening_message": "Hello! I'd love to hear more about..."
}
```

---

### POST `/api/chat/message`
Send user message, receive AI reply (max 10 turns).

**Request:**
```json
{
  "session_id": "uuid-here",
  "message": "I feel more anxious when I use Instagram.",
  "history": [...]
}
```

---

### POST `/api/chat/analyze`
AI linguistic analysis of conversation. **Does NOT update risk level.**

**Request:**
```json
{
  "session_id": "uuid-here",
  "transcript": [
    { "role": "user", "content": "..." },
    { "role": "assistant", "content": "..." }
  ]
}
```

**Response:**
```json
{
  "sentiment": "negative",
  "emotional_tone": "sadness",
  "self_reference_level": "high",
  "social_withdrawal_indicators": true,
  "uncertainty_language": true,
  "stress_indicators": true,
  "summary": "User frequently used self-referential language...",
  "pattern_explanation": "The repeated use of 'I feel alone' indicates..."
}
```

---

### POST `/api/complete`
Writes all data to Google Sheets atomically.

---

## Google Sheets Schema

| Column | Description |
|--------|-------------|
| A | Timestamp (ISO 8601 UTC) |
| B | Age |
| C | Gender |
| D | Education |
| E | Social Media Hours/Day |
| F | Platforms Used (comma-separated) |
| G–AE | Q1–Q25 Likert responses (1–5) |
| AF | Total Score |
| AG | Max Score (60) |
| AH | Score % |
| AI | Risk Level |
| AJ | Key Factors (semicolon-separated) |
| AK | AI Explanation |
| AL | Conversation Transcript (JSON) |
| AM | Conversation Analysis (JSON) |

---

## Scoring Logic

**Scored questions:** Q6, Q7, Q8, Q9, Q12, Q13, Q14, Q15, Q16, Q18, Q19, Q20 (12 questions)

**Scale:** Strongly Disagree=1, Disagree=2, Undecided=3, Agree=4, Strongly Agree=5

**Maximum score:** 60

| Score Range | Classification |
|-------------|----------------|
| 0–26 (≤43%) | Low Risk |
| 27–39 (44–65%) | Moderate Risk |
| 40–52 (66–86%) | High Risk |
| 53–60 (>86%) | Very High Risk |

Thresholds are configurable via `.env` without code changes.

---

## Safety & Ethics

- AI **never** determines risk level or makes diagnoses
- AI includes ethical disclaimers in all explanations
- If participant expresses self-harm intent, AI responds empathetically and recommends professional support
- All data is stored securely; no PII linking is performed
- Participants may withdraw at any time
- Results page includes clear "not a diagnostic tool" disclaimer

---

## Production Deployment Notes

- Replace `session_store.py` in-memory store with Redis for multi-worker deployments
- Set `CORS_ORIGINS` to your actual domain in production
- Use `uvicorn backend.main:app --workers 4` for production load
- Consider rate limiting on `/api/chat/message` to prevent abuse
- Regularly rotate the OpenAI API key
