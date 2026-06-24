from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any
from datetime import datetime


class PersonalDetails(BaseModel):
    full_name: str = Field(..., min_length=1)
    age: int = Field(..., ge=13, le=100)
    gender: str
    education: str
    social_media_hours: float = Field(..., ge=0, le=24)
    platforms_used: List[str]


class QuestionnaireSubmission(BaseModel):
    personal_details: PersonalDetails
    responses: Dict[str, int] = Field(
        ...,
        description="Q1–Q25 Likert responses (1–5)"
    )


class ScoreResult(BaseModel):
    total_score: int
    max_score: int
    percentage: float
    risk_level: str
    key_factors: List[str]
    scored_questions: Dict[str, int]


class ExplainRequest(BaseModel):
    score: int
    risk_level: str
    key_factors: List[str]


class ExplainResponse(BaseModel):
    explanation: str
    disclaimer: str


class ChatStartResponse(BaseModel):
    session_id: str
    opening_message: str


class ChatMessageRequest(BaseModel):
    session_id: str
    message: str
    history: List[Dict[str, str]]


class ChatMessageResponse(BaseModel):
    reply: str
    turn_count: int
    should_end: bool


class ChatAnalyzeRequest(BaseModel):
    session_id: str
    transcript: List[Dict[str, str]]


class ConversationAnalysis(BaseModel):
    sentiment: str
    emotional_tone: str
    self_reference_level: str
    social_withdrawal_indicators: bool
    uncertainty_language: bool
    stress_indicators: bool
    summary: str
    pattern_explanation: str


class CompleteSubmissionRequest(BaseModel):
    submission_id: Optional[str] = None
    personal_details: PersonalDetails
    responses: Dict[str, int]
    score_result: ScoreResult
    ai_explanation: str
    transcript: Optional[List[Dict[str, str]]] = []
    conversation_analysis: Optional[Dict[str, Any]] = None


class CompleteSubmissionResponse(BaseModel):
    success: bool
    row_id: Optional[str] = None
    message: str
