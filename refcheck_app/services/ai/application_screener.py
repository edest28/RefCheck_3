"""
AI-powered application screening.
"""
import re
import json
import requests


def analyze_application_with_claude(job_posting, application, api_key):
    """Score an application against a job posting.

    Returns dict:
      {
        "score": int,
        "score_label": "strong|mixed|weak",
        "summary": str,
        "strengths": [str],
        "risks": [str],
        "missing_requirements": [str]
      }
    """
    if not api_key:
        # Deterministic-ish fallback for local dev.
        score = 70 if (application.resume_text or "") else 40
        return {
            "score": score,
            "score_label": "strong" if score >= 75 else "mixed" if score >= 55 else "weak",
            "summary": "Mock screening result (no AI key configured).",
            "strengths": [],
            "risks": [],
            "missing_requirements": [],
        }

    jd_text = (job_posting.description_raw or "") + "\n" + (job_posting.description_html or "")
    resume_text = application.resume_text or ""
    answers = {
        "location": application.location,
        "linkedin_url": application.linkedin_url,
        "portfolio_url": application.portfolio_url,
        "salary_expectations_text": application.salary_expectations_text,
        "availability_text": application.availability_text,
        "work_country": application.work_country,
        "work_authorization_status": application.work_authorization_status,
        "requires_sponsorship": application.requires_sponsorship,
    }

    prompt = f"""You are an applicant screening assistant.
Score the applicant from 0-100 based on fit for the job description.

Return ONLY valid JSON with this exact shape:
{{
  "score": 0,
  "score_label": "strong|mixed|weak",
  "summary": "2-3 sentences",
  "strengths": ["..."],
  "risks": ["..."],
  "missing_requirements": ["..."]
}}

Job title: {job_posting.title}
Job description:
{jd_text}

Applicant:
Name: {application.full_name}
Email: {application.email}
Answers (JSON):
{json.dumps(answers)}

Resume text:
{resume_text[:15000]}
"""
    try:
        response = requests.post(
            "https://api.anthropic.com/v1/messages",
            headers={
                "x-api-key": api_key,
                "anthropic-version": "2023-06-01",
                "content-type": "application/json",
            },
            json={
                "model": "claude-sonnet-4-20250514",
                "max_tokens": 1500,
                "messages": [{"role": "user", "content": prompt}],
            },
            timeout=60,
        )
        response.raise_for_status()
        result = response.json()
        content = result.get("content", [{}])[0].get("text", "{}")
        json_match = re.search(r"\{[\s\S]*\}", content)
        return json.loads(json_match.group() if json_match else content)
    except Exception as e:
        print(f"Error screening application: {e}")
        return None
