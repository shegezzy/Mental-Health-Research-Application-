"""
Rule-based mental health risk scoring engine.
AI does NOT participate in scoring. This module is purely deterministic.
"""
from typing import Dict, Tuple, List
from backend.config.settings import settings

# Questions used for risk scoring (mental health indicators)
SCORED_QUESTIONS = {
    "Q6", "Q7", "Q8", "Q9",
    "Q12", "Q13", "Q14", "Q15", "Q16",
    "Q18", "Q19", "Q20"
}

MAX_PER_QUESTION = 5
MAX_SCORE = len(SCORED_QUESTIONS) * MAX_PER_QUESTION  # 60

# Key factor mapping: question → what high score indicates
KEY_FACTOR_MAP = {
    "Q6":  "persistent feelings of sadness or hopelessness",
    "Q7":  "loss of interest in previously enjoyed activities",
    "Q8":  "difficulty concentrating or making decisions",
    "Q9":  "social withdrawal or isolation",
    "Q12": "sleep disturbances or insomnia",
    "Q13": "changes in appetite or eating habits",
    "Q14": "low energy or persistent fatigue",
    "Q15": "feelings of worthlessness or excessive guilt",
    "Q16": "recurrent thoughts of death or self-harm",
    "Q18": "reduced social media engagement during low periods",
    "Q19": "use of social media as emotional escape",
    "Q20": "negative comparison with others online",
}

LIKERT_MAP = {1: 1, 2: 2, 3: 3, 4: 4, 5: 5}


def calculate_score(responses: Dict[str, int]) -> Dict:
    """
    Pure rule-based scoring. Returns score, risk level, and contributing factors.
    No AI involved.
    """
    scored = {}
    total = 0

    for q_id in SCORED_QUESTIONS:
        raw = responses.get(q_id, 3)  # default neutral if missing
        value = LIKERT_MAP.get(raw, 3)
        scored[q_id] = value
        total += value

    percentage = round((total / MAX_SCORE) * 100, 1)

    risk_level = _classify_risk(total)
    key_factors = _extract_key_factors(scored)

    return {
        "total_score": total,
        "max_score": MAX_SCORE,
        "percentage": percentage,
        "risk_level": risk_level,
        "key_factors": key_factors,
        "scored_questions": scored,
    }


def _classify_risk(score: int) -> str:
    if score <= settings.LOW_RISK_MAX:
        return "Low Risk"
    elif score <= settings.MODERATE_RISK_MAX:
        return "Moderate Risk"
    elif score <= settings.HIGH_RISK_MAX:
        return "High Risk"
    else:
        return "Very High Risk"


def _extract_key_factors(scored: Dict[str, int]) -> List[str]:
    """Identify factors where user scored 4 or 5 (agree/strongly agree)."""
    factors = []
    for q_id, score in sorted(scored.items()):
        if score >= 4 and q_id in KEY_FACTOR_MAP:
            factors.append(KEY_FACTOR_MAP[q_id])
    # If no high scores, surface mid-range factors
    if not factors:
        for q_id, score in sorted(scored.items()):
            if score == 3 and q_id in KEY_FACTOR_MAP:
                factors.append(KEY_FACTOR_MAP[q_id])
    return factors[:5]  # Cap at 5 for AI prompt clarity
