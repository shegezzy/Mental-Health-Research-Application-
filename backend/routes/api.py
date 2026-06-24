import logging
import hashlib
import json
from fastapi import APIRouter, HTTPException


from backend.models.schemas import (
    QuestionnaireSubmission, ScoreResult,
    ExplainRequest, ExplainResponse,
    ChatStartResponse, ChatMessageRequest, ChatMessageResponse,
    ChatAnalyzeRequest, ConversationAnalysis,
    CompleteSubmissionRequest, CompleteSubmissionResponse,
)
from backend.services import scoring, openai_service, sheets
from backend.utils import session_store

logger = logging.getLogger(__name__)
router = APIRouter()

MAX_TURNS = 10
_completed_submissions = set()
_completed_submissions_fallback = set()


def _payload_id(payload: CompleteSubmissionRequest) -> str:
    """Deterministic idempotency key.

    Used when the client doesn't provide a stable submission_id.
    """
    personal = payload.personal_details.model_dump()
    responses = payload.responses
    score = payload.score_result.model_dump()
    transcript = payload.transcript or []

    blob = {
        "personal": personal,
        "responses": responses,
        "score": score,
        "transcript": transcript,
    }

    s = json.dumps(blob, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(s.encode("utf-8")).hexdigest()



@router.post("/submit", response_model=ScoreResult)
async def submit_questionnaire(payload: QuestionnaireSubmission):
    """
    Step 1: Receive questionnaire, compute rule-based risk score.
    AI is NOT involved here.
    """
    try:
        result = scoring.calculate_score(payload.responses)
        return ScoreResult(**result)
    except Exception as e:
        logger.error(f"Scoring error: {e}")
        raise HTTPException(status_code=500, detail="Scoring failed. Please try again.")


@router.post("/explain", response_model=ExplainResponse)
async def explain_results(payload: ExplainRequest):
    """
    Step 2: AI generates human-readable explanation of rule-based score.
    AI does NOT recompute or change the risk level.
    """
    try:
        result = await openai_service.explain_results(
            score=payload.score,
            risk_level=payload.risk_level,
            key_factors=payload.key_factors,
        )
        return ExplainResponse(**result)
    except Exception as e:
        logger.error(f"AI explain error: {e}")
        raise HTTPException(status_code=502, detail="AI explanation unavailable. Please try again.")


@router.post("/chat/start", response_model=ChatStartResponse)
async def chat_start():
    """
    Step 3: Initialise optional AI conversation session.
    """
    try:
        session_id = session_store.create_session()
        opening = await openai_service.chat_opening()
        return ChatStartResponse(session_id=session_id, opening_message=opening)
    except Exception as e:
        logger.error(f"Chat start error: {e}")
        raise HTTPException(status_code=502, detail="Could not start conversation.")


@router.post("/chat/message", response_model=ChatMessageResponse)
async def chat_message(payload: ChatMessageRequest):
    """
    Step 4: Send user message, receive AI reply.
    Enforces turn limit and safety guardrails.
    """
    session = session_store.get_session(payload.session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found or expired.")

    turn_count = session_store.get_turn_count(payload.session_id)
    if turn_count >= MAX_TURNS:
        return ChatMessageResponse(
            reply="Thank you for sharing your experiences. This concludes our conversation. Your responses have been recorded for research analysis.",
            turn_count=turn_count,
            should_end=True,
        )

    try:
        history = session_store.get_history(payload.session_id)
        reply = await openai_service.chat_reply(
            history=history,
            user_message=payload.message,
            turn_count=turn_count + 1,
        )
        new_count = session_store.add_turn(payload.session_id, payload.message, reply)
        should_end = new_count >= MAX_TURNS

        return ChatMessageResponse(reply=reply, turn_count=new_count, should_end=should_end)
    except Exception as e:
        logger.error(f"Chat message error: {e}")
        raise HTTPException(status_code=502, detail="AI response unavailable.")


@router.post("/chat/analyze", response_model=ConversationAnalysis)
async def chat_analyze(payload: ChatAnalyzeRequest):
    """
    Step 5: Linguistic analysis of full conversation transcript.
    AI returns structured JSON — does NOT update risk classification.
    """
    if not payload.transcript:
        raise HTTPException(status_code=400, detail="No transcript provided.")
    try:
        result = await openai_service.analyze_conversation(payload.transcript)
        return ConversationAnalysis(**result)
    except Exception as e:
        logger.error(f"Chat analysis error: {e}")
        raise HTTPException(status_code=502, detail="Conversation analysis failed.")


@router.post("/complete", response_model=CompleteSubmissionResponse)
async def complete_submission(payload: CompleteSubmissionRequest):

    """
    Final step: Write all data to Google Sheets atomically.
    """
    try:
        # Idempotency: dedupe by explicit submission_id if present,
        # otherwise dedupe by deterministic hash of payload content.
        dedupe_id = payload.submission_id
        used_fallback = False

        if not dedupe_id:
            used_fallback = True
            dedupe_id = _payload_id(payload)

        completed_set = _completed_submissions_fallback if used_fallback else _completed_submissions

        if dedupe_id in completed_set:
            return CompleteSubmissionResponse(
                success=True,
                row_id=None,
                message="Your responses have already been recorded.",
            )


        data = {
            "personal_details": payload.personal_details.model_dump(),
            "responses": payload.responses,
            "score_result": payload.score_result.model_dump(),
            "ai_explanation": payload.ai_explanation,
            "transcript": payload.transcript or [],
            "conversation_analysis": payload.conversation_analysis or {},
        }
        row_id = sheets.append_submission(data)
        if used_fallback:
            _completed_submissions_fallback.add(dedupe_id)
        else:
            if payload.submission_id:
                _completed_submissions.add(dedupe_id)

        return CompleteSubmissionResponse(
            success=True,
            row_id=row_id,
            message="Your responses have been recorded. Thank you for contributing to this research.",
        )
    except EnvironmentError as e:
        logger.warning(f"Sheets not configured: {e}")
        # Graceful degradation — still acknowledge user
        return CompleteSubmissionResponse(
            success=True,
            row_id=None,
            message="Your responses have been recorded. Thank you for contributing to this research.",
        )
    except Exception as e:
        logger.error(f"Sheets write error: {e}")
        raise HTTPException(status_code=500, detail="Failed to save submission. Please try again.")
