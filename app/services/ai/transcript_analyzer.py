"""
AI-powered transcript analysis for reference calls.
"""
import re
import json
import requests


def analyze_transcript_with_claude(transcript, job_info, candidate_name, api_key):
    """Use Claude to analyze transcript and detect discrepancies."""

    if not api_key or not transcript:
        return None

    # Build claims from resume
    claims = []
    claims.append(f"Company: {job_info.get('company', 'Unknown')}")
    claims.append(f"Title: {job_info.get('title', 'Unknown')}")
    claims.append(f"Dates: {job_info.get('dates', 'Unknown')}")

    responsibilities = job_info.get('responsibilities', [])
    if isinstance(responsibilities, str):
        responsibilities = json.loads(responsibilities) if responsibilities else []
    for resp in responsibilities:
        claims.append(f"Responsibility: {resp}")

    achievements = job_info.get('achievements', [])
    if isinstance(achievements, str):
        achievements = json.loads(achievements) if achievements else []
    for ach in achievements:
        claims.append(f"Achievement: {ach}")

    claims_text = "\n".join(claims)

    headers = {
        "x-api-key": api_key,
        "content-type": "application/json",
        "anthropic-version": "2023-06-01"
    }

    prompt = f"""Analyze this reference check call transcript and compare it against the candidate's resume claims.

CANDIDATE: {candidate_name}

RESUME CLAIMS:
{claims_text}

CALL TRANSCRIPT:
{transcript}

Analyze carefully for ANY discrepancies, contradictions, or concerns. Be STRICT - if the reference contradicts, denies, or cannot confirm something from the resume, flag it.

Return ONLY valid JSON:
{{
    "employment_confirmed": true/false/null,
    "dates_accurate": true/false/null,
    "title_confirmed": true/false/null,
    "would_rehire": true/false/null,
    "achievements_verified": ["list of achievements CONFIRMED by reference"],
    "achievements_not_verified": ["list of achievements DENIED or not confirmed"],
    "responsibilities_confirmed": ["confirmed responsibilities"],
    "responsibilities_denied": ["denied or unconfirmed responsibilities"],
    "discrepancies": ["List EVERY discrepancy between resume and reference"],
    "red_flags": ["Concerning statements, hesitations, negative feedback"],
    "positive_signals": ["Strong endorsements, positive feedback"],
    "overall_sentiment": "very_positive/positive/neutral/negative/very_negative",
    "confidence_level": "high/medium/low",
    "summary": "Brief summary of key findings, especially concerns"
}}

Be thorough - contradictions MUST appear in discrepancies and red_flags."""

    try:
        response = requests.post(
            "https://api.anthropic.com/v1/messages",
            headers=headers,
            json={
                "model": "claude-sonnet-4-20250514",
                "max_tokens": 2000,
                "messages": [{"role": "user", "content": prompt}]
            },
            timeout=60
        )
        response.raise_for_status()
        result = response.json()
        content = result['content'][0]['text']

        json_match = re.search(r'\{[\s\S]*\}', content)
        if json_match:
            return json.loads(json_match.group())
        return json.loads(content)
    except Exception as e:
        print(f"Error analyzing transcript: {e}")
        return None


def calculate_verification_score(structured_data):
    """Calculate verification score from call analysis."""
    score = 50  # Start neutral

    # Employment confirmation is critical
    if structured_data.get('employment_confirmed') == True:
        score += 15
    elif structured_data.get('employment_confirmed') == False:
        score -= 30

    # Date accuracy
    if structured_data.get('dates_accurate') == True:
        score += 10
    elif structured_data.get('dates_accurate') == False:
        score -= 20

    # Title confirmation
    if structured_data.get('title_confirmed') == True:
        score += 10
    elif structured_data.get('title_confirmed') == False:
        score -= 15

    # Would rehire is very important
    if structured_data.get('would_rehire') == True:
        score += 15
    elif structured_data.get('would_rehire') == False:
        score -= 25

    # Achievements
    verified = len(structured_data.get('achievements_verified', []))
    not_verified = len(structured_data.get('achievements_not_verified', []))
    score += min(verified * 5, 15)
    score -= not_verified * 8

    # Discrepancies are critical
    discrepancies = structured_data.get('discrepancies', [])
    score -= len(discrepancies) * 10

    # Red flags
    red_flags = structured_data.get('red_flags', [])
    score -= len(red_flags) * 7

    # Positive signals
    positive = structured_data.get('positive_signals', [])
    score += min(len(positive) * 3, 10)

    # Sentiment
    sentiment_scores = {
        'very_positive': 10, 'positive': 5, 'neutral': 0,
        'negative': -15, 'very_negative': -25
    }
    score += sentiment_scores.get(structured_data.get('overall_sentiment', 'neutral'), 0)

    return max(0, min(100, int(score)))
