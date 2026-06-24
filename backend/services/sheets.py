"""
Google Sheets integration for data persistence.
Each submission is stored as a single structured row.
Uses service account authentication. No hardcoded credentials.
"""
import json
import time
import logging
from typing import List, Any, Dict, Optional
from datetime import datetime, timezone

from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

from backend.config.settings import settings

logger = logging.getLogger(__name__)

SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]
SHEET_NAME = "Submissions"

# Column headers — matches the row structure in append_submission()
HEADERS = [
    "Timestamp",
    "Full Name", "Age", "Gender", "Education", "Social Media Hours/Day", "Platforms Used",
    # Q1–Q25 responses
    *[f"Q{i}" for i in range(1, 26)],
    "Total Score", "Max Score", "Score %", "Risk Level",
    "Key Factors",
    "AI Explanation",
    "Conversation Transcript (JSON)",
    "Conversation Analysis (JSON)",
]


def _get_service():
    """Build Google Sheets API service from env-stored credentials."""
    creds_json = settings.GOOGLE_SERVICE_ACCOUNT_JSON
    if not creds_json:
        raise EnvironmentError("GOOGLE_SERVICE_ACCOUNT_JSON environment variable not set.")

    creds_dict = json.loads(creds_json)
    credentials = service_account.Credentials.from_service_account_info(
        creds_dict, scopes=SCOPES
    )
    return build("sheets", "v4", credentials=credentials, cache_discovery=False)


def _ensure_sheet_exists(service, spreadsheet_id: str) -> None:
    """Create the target worksheet tab if it does not already exist."""
    spreadsheet = service.spreadsheets().get(
        spreadsheetId=spreadsheet_id,
        fields="sheets.properties.title",
    ).execute()

    sheet_titles = {
        sheet.get("properties", {}).get("title")
        for sheet in spreadsheet.get("sheets", [])
    }
    if SHEET_NAME in sheet_titles:
        return

    service.spreadsheets().batchUpdate(
        spreadsheetId=spreadsheet_id,
        body={
            "requests": [
                {
                    "addSheet": {
                        "properties": {
                            "title": SHEET_NAME,
                        }
                    }
                }
            ]
        },
    ).execute()
    logger.info("Created Google Sheets tab: %s", SHEET_NAME)


def ensure_headers():
    """Create header row if sheet is empty. Called on startup."""
    try:
        service = _get_service()
        spreadsheet_id = settings.GOOGLE_SHEETS_SPREADSHEET_ID
        _ensure_sheet_exists(service, spreadsheet_id)
        range_ = f"{SHEET_NAME}!A1:AN1"

        result = service.spreadsheets().values().get(
            spreadsheetId=spreadsheet_id, range=range_
        ).execute()

        existing = result.get("values", [])
        if not existing:
            service.spreadsheets().values().update(
                spreadsheetId=spreadsheet_id,
                range=f"{SHEET_NAME}!A1",
                valueInputOption="RAW",
                body={"values": [HEADERS]},
            ).execute()
            logger.info("Header row written to Google Sheets.")
    except Exception as e:
        logger.warning(f"Could not ensure headers: {e}")


def _build_row(data: Dict) -> List[Any]:
    """Map submission data to ordered row values."""
    personal = data["personal_details"]
    responses = data["responses"]
    score = data["score_result"]

    row = [
        datetime.now(timezone.utc).isoformat(),
        personal.get("full_name", ""),
        personal.get("age", ""),
        personal.get("gender", ""),
        personal.get("education", ""),
        personal.get("social_media_hours", ""),
        ", ".join(personal.get("platforms_used", [])),
    ]

    # Q1–Q25 responses in order
    for i in range(1, 26):
        row.append(responses.get(f"Q{i}", ""))

    row += [
        score.get("total_score", ""),
        score.get("max_score", ""),
        score.get("percentage", ""),
        score.get("risk_level", ""),
        "; ".join(score.get("key_factors", [])),
        data.get("ai_explanation", ""),
        json.dumps(data.get("transcript", []), ensure_ascii=False),
        json.dumps(data.get("conversation_analysis", {}), ensure_ascii=False),
    ]

    return row


def append_submission(data: Dict, max_retries: int = 3) -> Optional[str]:
    """
    Appends a single submission row to Google Sheets.
    Retries up to max_retries times on transient failure.
    Returns the updated range string on success.
    """
    row = _build_row(data)
    spreadsheet_id = settings.GOOGLE_SHEETS_SPREADSHEET_ID

    for attempt in range(1, max_retries + 1):
        try:
            service = _get_service()
            _ensure_sheet_exists(service, spreadsheet_id)
            result = service.spreadsheets().values().append(
                spreadsheetId=spreadsheet_id,
                range=f"{SHEET_NAME}!A1",
                valueInputOption="RAW",
                insertDataOption="INSERT_ROWS",
                body={"values": [row]},
            ).execute()
            updated_range = result.get("updates", {}).get("updatedRange", "")
            logger.info(f"Submission written to Sheets: {updated_range}")
            return updated_range

        except HttpError as e:
            logger.error(f"Sheets API error (attempt {attempt}): {e}")
            if attempt < max_retries:
                time.sleep(2 ** attempt)  # Exponential backoff
            else:
                raise

        except Exception as e:
            logger.error(f"Unexpected error writing to Sheets (attempt {attempt}): {e}")
            if attempt < max_retries:
                time.sleep(2 ** attempt)
            else:
                raise
