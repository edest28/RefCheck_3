"""
AI-powered resume parsing using Claude.
"""
import re
import json
import requests


def parse_resume_with_claude(resume_text, api_key):
    """Use Claude to extract structured information from a resume."""

    if not api_key:
        # Don't return mock data - raise an error instead
        raise ValueError("ANTHROPIC_API_KEY is not configured. Please set it in your environment variables.")

    headers = {
        "x-api-key": api_key,
        "content-type": "application/json",
        "anthropic-version": "2023-06-01"
    }

    payload = {
        "model": "claude-3-5-haiku-20241022",  # Haiku 3.5 is faster and cheaper than Sonnet
        "max_tokens": 4000,
        "messages": [{
            "role": "user",
            "content": f"""Analyze this resume and extract structured information. Return ONLY valid JSON.

{{
    "candidate_name": "Full name",
    "email": "Email if found",
    "phone": "Phone if found",
    "summary": "Brief professional summary (2-3 sentences)",
    "skills": ["skill1", "skill2", "skill3"],
    "jobs": [
        {{
            "company": "Company name",
            "title": "Job title",
            "dates": "Employment dates",
            "responsibilities": ["Day-to-day duty 1", "Duty 2"],
            "achievements": ["Quantifiable achievement 1", "Achievement 2"]
        }}
    ]
}}

IMPORTANT: Separate responsibilities (routine duties) from achievements (specific accomplishments with metrics/impact).

Resume:
{resume_text}

Return ONLY the JSON object, no other text."""
        }]
    }

    try:
        response = requests.post(
            "https://api.anthropic.com/v1/messages",
            headers=headers,
            json=payload,
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
        print(f"Error parsing resume: {e}")
        return None
