"""
OpenAI integration.
AI is ONLY used for:
  1. Explaining survey results in human-readable form
  2. Conversational follow-up (optional research enrichment)
  3. Linguistic analysis of conversation text

AI does NOT compute risk scores or make diagnostic decisions.
"""
import json
import httpx
import logging
from typing import List, Dict, Any
from backend.config.settings import settings

logger = logging.getLogger(__name__)

OPENAI_RESPONSES_URL = "https://api.openai.com/v1/responses"


def _extract_openai_text(data: Dict[str, Any]) -> str:
    """Extract text from the Responses API shape."""
    if data.get("output_text"):
        return data["output_text"]

    text_parts = []
    for item in data.get("output", []):
        for content in item.get("content", []):
            if content.get("type") in {"output_text", "text"} and content.get("text"):
                text_parts.append(content["text"])

    if text_parts:
        return "\n".join(text_parts)

    raise ValueError(f"No text response from OpenAI. Raw data keys={list(data.keys())}")


def _contains_any(text: str, terms) -> bool:
    return any(term in text for term in terms)


def _fallback_chat_reply(history: List[Dict[str, str]], user_message: str, turn_count: int) -> str:
    lower_message = user_message.lower()
    crisis_terms = ("self-harm", "suicide", "kill myself", "end my life", "hurt myself")
    if _contains_any(lower_message, crisis_terms):
        return (
            "I can hear you're going through something difficult. Please consider speaking with a mental health "
            "professional or contacting a crisis helpline; they can offer the right support. "
            "Would you like to continue sharing for the research?"
        )

    if _contains_any(lower_message, ("safe", "save", "secure", "private", "anonymous", "confidential")):
        return (
            "Your question about safety is understandable. This conversation is for academic research only, "
            "and you can stop at any time; please avoid sharing details you are not comfortable recording. "
            "What would help you feel more comfortable continuing?"
        )

    if _contains_any(lower_message, ("sleep", "tired", "night", "insomnia", "wake")):
        return (
            "Sleep can be closely affected by social media habits. When you use social media at night, "
            "does it usually help you relax, keep you awake, or change your mood the next day?"
        )

    if _contains_any(lower_message, ("sad", "depressed", "down", "lonely", "alone", "empty")):
        return (
            "Thank you for sharing that. When those feelings come up around social media, "
            "are they more connected to comparing yourself with others, feeling ignored, or something else?"
        )

    if _contains_any(lower_message, ("anxious", "stress", "worried", "pressure", "overwhelmed")):
        return (
            "That sounds like it may feel stressful. What parts of social media create the most pressure for you: "
            "notifications, comments, comparison, news, or expectations to respond?"
        )

    if _contains_any(lower_message, ("friends", "family", "relationship", "people", "followers")):
        return (
            "Relationships online can shape how people feel offline too. Has social media mostly helped you feel "
            "connected to people, or has it sometimes made you feel distant from them?"
        )

    # Stop asking questions after the 10th exchange.
    # Our turn_count passed here is (server_turn_count + 1), so:
    # - turn_count 1..10 => allow up to 10 exchanges
    # - turn_count >= 10 => wrap up instead of asking another question
    if turn_count >= 10:
        return (
            "Thank you—your responses are really helpful for the research. "
            "Before we wrap up, is there anything else you’d like to add that we haven’t covered?"
        )

    if turn_count >= 8:
        return (
            "Thank you; that gives useful context for the research. Before we wrap up, is there one social media "
            "experience you think best explains how it affects your emotional well-being?"
        )


    prompts = [
        "Thank you for sharing that. Could you describe one recent moment when social media noticeably affected your mood?",
        "That is useful context. How often does this happen, and does it feel stronger on any particular platform?",
        "I appreciate the detail. What do you usually do after social media affects you that way?",
        "Could you say a little more about whether this affects your sleep, focus, relationships, or self-esteem?",
    ]
    return prompts[max(0, (turn_count - 1) % len(prompts))]


def _fallback_analysis(transcript: List[Dict[str, str]]) -> Dict[str, Any]:
    user_texts = [
        t.get("content", "")
        for t in transcript
        if t.get("role") == "user"
    ]
    joined = " ".join(user_texts).lower()

    stress = _contains_any(joined, ("stress", "stressed", "anxious", "worried", "pressure", "overwhelmed"))
    withdrawal = _contains_any(joined, ("alone", "lonely", "isolated", "avoid", "withdraw", "ignored"))
    uncertainty = _contains_any(joined, ("maybe", "not sure", "i think", "i guess", "confused", "don't know", "dont know"))
    negative = _contains_any(joined, ("sad", "depressed", "down", "bad", "tired", "angry", "empty", "hurt"))
    positive = _contains_any(joined, ("happy", "good", "better", "connected", "supported", "relaxed"))
    self_refs = sum(joined.count(term) for term in (" i ", " me ", " my ", " myself "))

    if positive and negative:
        sentiment = "mixed"
    elif negative:
        sentiment = "negative"
    elif positive:
        sentiment = "positive"
    else:
        sentiment = "neutral"

    if stress:
        tone = "stress or worry"
    elif withdrawal:
        tone = "loneliness or social distance"
    elif negative:
        tone = "low mood"
    elif positive:
        tone = "positive or supported"
    else:
        tone = "neutral or unclear"

    if self_refs >= 10:
        self_reference = "high"
    elif self_refs >= 4:
        self_reference = "medium"
    else:
        self_reference = "low"

    detected = []
    if stress:
        detected.append("stress-related language")
    if withdrawal:
        detected.append("social withdrawal language")
    if uncertainty:
        detected.append("uncertainty language")
    if negative:
        detected.append("negative emotion words")

    summary = (
        "Local fallback analysis found " + ", ".join(detected) + "."
        if detected else
        "Local fallback analysis did not find strong linguistic indicators in the conversation."
    )

    return {
        "sentiment": sentiment,
        "emotional_tone": tone,
        "self_reference_level": self_reference,
        "social_withdrawal_indicators": withdrawal,
        "uncertainty_language": uncertainty,
        "stress_indicators": stress,
        "summary": summary,
        "pattern_explanation": (
            "This analysis was generated locally because the AI provider was unavailable. "
            "It uses simple keyword patterns from the participant's messages and is less nuanced than AI analysis."
        ),
    }


async def _call_openai(prompt: str, system_instruction: str = "") -> str:
    """Low-level OpenAI Responses API call."""
    if not settings.OPENAI_API_KEY:
        raise ValueError("OPENAI_API_KEY is not configured.")

    payload: Dict[str, Any] = {
        "model": settings.OPENAI_MODEL,
        "input": prompt,
        "max_output_tokens": 800,
    }
    if system_instruction:
        payload["instructions"] = system_instruction

    async with httpx.AsyncClient(timeout=30.0) as client:
        try:
            response = await client.post(
                OPENAI_RESPONSES_URL,
                json=payload,
                headers={
                    "Authorization": f"Bearer {settings.OPENAI_API_KEY}",
                    "Content-Type": "application/json",
                },
            )
            response.raise_for_status()
        except httpx.HTTPStatusError as e:
            body_text = ""
            try:
                body_text = e.response.text
            except Exception:
                body_text = "<could not read response body>"

            logger.error(
                "OpenAI HTTP error. status=%s url=%s model=%s body=%s",
                e.response.status_code,
                OPENAI_RESPONSES_URL,
                settings.OPENAI_MODEL,
                body_text,
            )
            raise
        except Exception as e:
            logger.exception("OpenAI request failed: %s", e)
            raise

    data = response.json()
    return _extract_openai_text(data)



async def explain_results(score: int, risk_level: str, key_factors: List[str]) -> Dict[str, str]:
    """
    AI generates a human-readable explanation of rule-based results.
    AI does NOT determine the risk level — it only explains it.
    """
    system = (
        "You are a compassionate research assistant helping participants understand their "
        "survey results. You do not make diagnoses. You speak in plain, warm, non-clinical language. "
        "Always remind the user this is academic research, not medical advice."
    )

    factors_text = "\n".join(f"- {f}" for f in key_factors) if key_factors else "- No strongly indicated factors"

    prompt = f"""
The rule-based scoring system (not AI) has calculated the following result from a participant's survey:

Score: {score} out of 60
Risk Classification: {risk_level}
Key contributing factors identified:
{factors_text}

Please write a 3–4 paragraph explanation for the participant that:
1. Summarises what their score means in simple terms
2. Gently addresses the key factors without alarming language
3. Emphasises this is for academic research only
4. Encourages them to seek professional support if they're struggling

Do NOT recompute or change the risk level. Only explain what has already been calculated.
Write directly to the participant (use "you").
"""

    disclaimer = (
        "⚠️ This explanation is provided for research purposes only. "
        "It is NOT a medical diagnosis and should NOT replace professional mental health advice. "
        "If you are in distress, please contact a qualified mental health professional or crisis helpline."
    )

    try:
        explanation = await _call_openai(prompt, system)
        return {"explanation": explanation, "disclaimer": disclaimer}
    except Exception:
        # Deterministic fallback to ensure the UI always shows an explanation.
        if key_factors:
            factors_bullets = "\n".join(f"- {f}" for f in key_factors)
        else:
            factors_bullets = "- No strongly indicated factors"

        explanation = (
            f"Your survey responses were scored using a rule-based system (not AI). "
            f"Your overall result is: {risk_level} (score {score} out of 60).\n\n"
            f"This classification is based on patterns in your answers, including these key contributing factors:\n"
            f"{factors_bullets}\n\n"
            f"It can be helpful to reflect on what these experiences might mean for you, "
            f"while remembering this tool is designed for academic research, not diagnosis. "
            f"If you feel you are struggling or in distress, consider speaking with a qualified mental health professional "
            f"or contacting a crisis helpline in your country."
        )
        return {"explanation": explanation, "disclaimer": disclaimer}



async def chat_opening() -> str:
    """Generate opening message for optional AI conversation."""
    system = (
        "You are a supportive research companion for an academic study on social media and mental health. "
        "Your role is to listen, ask thoughtful follow-up questions, and help enrich the research data. "
        "You are NOT a therapist and must not offer diagnoses. "
        "If a participant expresses distress or mentions self-harm, respond empathetically, "
        "encourage them to seek professional help, and do not engage further on harmful topics."
    )

    prompt = (
        "Generate a warm, brief opening message (2-3 sentences) inviting the participant to share more "
        "about their social media experiences and emotional well-being. Make it feel safe and voluntary."
    )
    try:
        return await _call_openai(prompt, system)
    except Exception:
        return (
            "Welcome. Feel free to share anything about your social media experiences and emotional well-being. "
            "This is a safe, voluntary space for research."
        )


async def chat_reply(history: List[Dict[str, str]], user_message: str, turn_count: int) -> str:
    """Generate AI reply in optional conversation."""

    system = (
        "You are a supportive research companion for an academic study on social media and mental wellbeing. "
        "Ask thoughtful, open-ended follow-up questions about social media use, emotional experiences, and online behaviour. "
        "Keep responses concise (2–4 sentences). Be warm but professional. "
        "Do NOT diagnose, prescribe, or offer clinical advice. "
        "If the user mentions self-harm or crisis, respond with: "
        "'I can hear you're going through something difficult. Please consider speaking with a mental health professional "
        "or contacting a crisis helpline — they can offer the right support. Would you like to continue sharing for the research?'"
        f"\nThis is turn {turn_count} of the conversation. If turn >= 8, gently begin wrapping up."
    )

    history_text = "\n".join(
        f"{'Participant' if h['role'] == 'user' else 'Researcher AI'}: {h['content']}"
        for h in history[-10:]  # Last 10 turns for context window
    )

    prompt = f"""Conversation so far:
{history_text}

Participant: {user_message}

Respond as the Researcher AI:"""

    try:
        return await _call_openai(prompt, system)
    except Exception:
        # Ensure we also stop asking questions when the fallback is used.
        # turn_count is (server_turn_count + 1).
        return _fallback_chat_reply(history, user_message, turn_count)



async def analyze_conversation(transcript: List[Dict[str, str]]) -> Dict[str, Any]:
    """
    Linguistic analysis of full conversation.
    Returns structured JSON insight — AI does NOT update risk level.
    """
    system = (
        "You are a linguistic analysis system for academic mental health research. "
        "Analyse conversation transcripts for linguistic and behavioural patterns. "
        "Return ONLY valid JSON with no markdown formatting. "
        "Be objective. Do not make clinical diagnoses."
    )

    transcript_text = "\n".join(
        f"{'Participant' if t['role'] == 'user' else 'Researcher AI'}: {t['content']}"
        for t in transcript
    )

    prompt = f"""Analyse this research conversation transcript for linguistic patterns:

{transcript_text}

Return ONLY a valid JSON object with exactly these fields:
{{
  "sentiment": "positive|negative|neutral|mixed",
  "emotional_tone": "string describing dominant emotion",
  "self_reference_level": "low|medium|high",
  "social_withdrawal_indicators": true|false,
  "uncertainty_language": true|false,
  "stress_indicators": true|false,
  "summary": "1-2 sentence summary of key patterns observed",
  "pattern_explanation": "2-3 sentences explaining why these patterns were detected based on the text"
}}"""

    try:
        raw = await _call_openai(prompt, system)
    except Exception:
        return _fallback_analysis(transcript)

    # Strip markdown fences if present
    clean = raw.strip()
    if clean.startswith("```"):
        clean = clean.split("```")[1]
        if clean.startswith("json"):
            clean = clean[4:]
    clean = clean.strip()

    try:
        return json.loads(clean)
    except json.JSONDecodeError:
        # Fallback structure if AI returns malformed JSON
        return {
            "sentiment": "undetermined",
            "emotional_tone": "undetermined",
            "self_reference_level": "undetermined",
            "social_withdrawal_indicators": False,
            "uncertainty_language": False,
            "stress_indicators": False,
            "summary": "Analysis could not be structured automatically.",
            "pattern_explanation": raw[:500]
        }
