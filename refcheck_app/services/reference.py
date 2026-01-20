"""
Reference check question generation and survey management.
"""
import json
import re
import requests
from refcheck_app.utils.constants import STANDARDIZED_SURVEY_QUESTIONS


def generate_reference_questions(job, candidate_name, custom_questions=None, target_role_category=None, target_role_details=None):
    """Generate questions for reference check call."""
    job_dict = job.to_dict() if hasattr(job, 'to_dict') else job

    company = job_dict.get('company', 'the company')
    title = job_dict.get('title', 'their role')

    questions = [
        f"Can you confirm that {candidate_name} worked at {company} as a {title}?",
        f"What was your working relationship with {candidate_name}?",
        f"Can you confirm the dates {candidate_name} was employed there?",
    ]

    responsibilities = job_dict.get('responsibilities', [])
    if responsibilities and len(responsibilities) > 0:
        questions.append(f"The candidate mentioned responsibilities including: {responsibilities[0]}. Can you confirm?")

    achievements = job_dict.get('achievements', [])
    for achievement in achievements[:3]:
        questions.append(f"The candidate claims: '{achievement}'. Can you verify this?")

    questions.extend([
        f"How would you describe {candidate_name}'s work quality and reliability?",
        f"What were {candidate_name}'s greatest strengths?",
        "Were there any areas for improvement?",
        f"Would you rehire {candidate_name}?",
    ])

    # Add target role specific questions
    if target_role_category or target_role_details:
        if target_role_category == 'Executive / Leadership':
            questions.append(f"Did {candidate_name} demonstrate leadership or strategic thinking abilities?")
        elif target_role_category == 'Engineering / Technical':
            questions.append(f"How would you rate {candidate_name}'s technical problem-solving skills?")
        elif target_role_category == 'Sales / Business Development':
            questions.append(f"Can you speak to {candidate_name}'s ability to build relationships and close deals?")
        elif target_role_category == 'Customer Support / Success':
            questions.append(f"How did {candidate_name} handle difficult customer situations?")
        elif target_role_category == 'Product / Design':
            questions.append(f"How did {candidate_name} approach product decisions and user feedback?")

        if target_role_details:
            questions.append(f"Based on your experience, would {candidate_name} be well-suited for a role involving {target_role_details[:100]}?")

    questions.append("Is there anything else we should know?")

    if custom_questions:
        if isinstance(custom_questions, str):
            custom_questions = json.loads(custom_questions) if custom_questions else []
        for q in custom_questions:
            if q and q.strip():
                questions.append(q.strip())

    return questions


def build_assistant_prompt(candidate_name, reference_name, job, questions, target_role_category=None, target_role_details=None):
    """Build the system prompt for Vapi assistant."""
    job_dict = job.to_dict() if hasattr(job, 'to_dict') else job

    company = job_dict.get('company', 'the company')
    title = job_dict.get('title', 'their role')
    questions_text = "\n".join([f"- {q}" for q in questions])

    # Build target role context
    target_context = ""
    if target_role_category or target_role_details:
        target_context = f"""

Note: {candidate_name} is being considered for a {target_role_category or 'new'} position{f' involving {target_role_details}' if target_role_details else ''}. 
Pay special attention to skills and experiences that would be relevant to this target role."""

    return f"""You are a professional reference checker calling on behalf of a company conducting background verification. You are speaking with {reference_name}.

IMPORTANT: Do NOT mention you are an AI. Present yourself as Sarah from the hiring verification team.

Goal: Verify information about {candidate_name} who worked at {company} as {title}.{target_context}

Call Flow:
1. "Hello, this is Sarah from the hiring verification team. I'm calling regarding a reference check for {candidate_name}. Is this {reference_name}?"
2. If confirmed: "Thank you. {candidate_name} listed you as a reference. Do you have 5-10 minutes to answer a few questions about their time at {company}?"
3. Ask these questions naturally:
{questions_text}
4. Thank them and end professionally.

Guidelines:
- Be conversational, not robotic
- Ask follow-up questions when appropriate
- Note any hesitation or red flags
- Keep under 10 minutes
- Be respectful of their time"""


def generate_ai_survey_questions(job, candidate_name, api_key, num_questions=5, target_role_category=None, target_role_details=None):
    """Generate role-specific survey questions using Claude."""

    if not api_key:
        return []

    job_dict = job.to_dict() if hasattr(job, 'to_dict') else job

    # Build target role context
    target_role_context = ""
    if target_role_category or target_role_details:
        target_role_context = f"""

TARGET ROLE (what {candidate_name} is being hired for):
Category: {target_role_category or 'Not specified'}
Details: {target_role_details or 'Not specified'}

Generate questions that help assess whether their past performance indicates they would succeed in this target role.
Consider what skills/behaviors from their past role would transfer to the target role."""

    prompt = f"""Generate {num_questions} specific survey questions to ask a reference about a candidate's performance in this role.

Candidate: {candidate_name}

PRIOR ROLE (the role they held when working with this reference):
Company: {job_dict.get('company', 'Unknown')}
Job Title: {job_dict.get('title', 'Unknown')}
Dates: {job_dict.get('dates', 'Unknown')}

Responsibilities:
{json.dumps(job_dict.get('responsibilities', []), indent=2)}

Achievements claimed:
{json.dumps(job_dict.get('achievements', []), indent=2)}
{target_role_context}

Generate questions that:
1. Verify specific achievements or responsibilities listed
2. Assess skills relevant to both their prior role AND the target role (if specified)
3. Probe for concrete examples and metrics
4. Bridge their past experience to future success potential
5. Are NOT generic questions about teamwork, communication, or overall performance (those are covered elsewhere)

Return a JSON array of questions. Each question should have:
- "question_text": The question to ask
- "response_type": Either "free_text" for open-ended, or "rating" for 1-5 scale questions

Example format:
[
  {{"question_text": "Can you describe a specific project where [candidate] demonstrated [skill from resume]?", "response_type": "free_text"}},
  {{"question_text": "How would you rate [candidate]'s proficiency in [technology from resume]?", "response_type": "rating"}}
]

Return ONLY the JSON array, no other text."""

    try:
        response = requests.post(
            "https://api.anthropic.com/v1/messages",
            headers={
                "x-api-key": api_key,
                "anthropic-version": "2023-06-01",
                "content-type": "application/json"
            },
            json={
                "model": "claude-sonnet-4-20250514",
                "max_tokens": 1500,
                "messages": [{"role": "user", "content": prompt}]
            },
            timeout=60
        )

        if response.status_code != 200:
            print(f"AI question generation failed: {response.text}")
            return []

        result = response.json()
        content = result.get('content', [{}])[0].get('text', '[]')

        # Parse JSON response
        # Handle potential markdown code blocks
        if '```json' in content:
            content = content.split('```json')[1].split('```')[0]
        elif '```' in content:
            content = content.split('```')[1].split('```')[0]

        questions = json.loads(content.strip())

        # Validate and format questions
        formatted_questions = []
        for q in questions:
            if 'question_text' in q:
                formatted_questions.append({
                    'question_text': q['question_text'],
                    'response_type': q.get('response_type', 'free_text'),
                    'required': True
                })

        return formatted_questions[:num_questions]

    except Exception as e:
        print(f"Error generating AI questions: {e}")
        return []


def get_survey_questions_for_reference(reference, candidate, job, api_key):
    """Get all survey questions (standardized + AI-generated) for a reference."""

    candidate_name = candidate.name

    # Format standardized questions with candidate name
    standardized = []
    for i, q in enumerate(STANDARDIZED_SURVEY_QUESTIONS):
        standardized.append({
            'question_text': q['question_text'].format(candidate_name=candidate_name),
            'question_type': 'standardized',
            'response_type': q['response_type'],
            'options': q.get('options'),
            'order': i,
            'required': q.get('required', True)
        })

    # Generate AI questions with target role context
    ai_questions = generate_ai_survey_questions(
        job, 
        candidate_name, 
        api_key,
        target_role_category=candidate.target_role_category,
        target_role_details=candidate.target_role_details
    )

    for i, q in enumerate(ai_questions):
        q['question_type'] = 'ai_generated'
        q['order'] = len(standardized) + i
        q['options'] = None

    return standardized + ai_questions


def analyze_survey_responses(survey_request, candidate_name, job, api_key):
    """Analyze survey responses using Claude and generate summary."""

    if not api_key:
        return None

    # Build response summary
    responses_text = []
    for question in survey_request.questions:
        if question.response:
            response_value = ""
            if question.response.rating:
                response_value = f"{question.response.rating}/5"
            elif question.response.selected_option:
                response_value = question.response.selected_option
            elif question.response.text_response:
                response_value = question.response.text_response

            responses_text.append(f"Q: {question.question_text}\nA: {response_value}")

    job_dict = job.to_dict() if hasattr(job, 'to_dict') else job

    prompt = f"""Analyze this reference survey for a job candidate and provide a structured assessment.

Candidate: {candidate_name}
Role being verified: {job_dict.get('title', 'Unknown')} at {job_dict.get('company', 'Unknown')}

Survey Responses:
{chr(10).join(responses_text)}

Provide your analysis as a JSON object with:
1. "score": Overall verification score from 0-100
2. "summary": 2-3 sentence summary of the reference's feedback
3. "red_flags": Array of any concerning responses or red flags (empty array if none)
4. "strengths": Array of positive attributes mentioned
5. "areas_for_development": Array of weaknesses or improvement areas mentioned
6. "recommendation_strength": "strong", "moderate", "weak", or "negative" based on rehire question and overall tone
7. "key_insights": Array of notable specific insights from the responses

Return ONLY the JSON object, no other text."""

    try:
        response = requests.post(
            "https://api.anthropic.com/v1/messages",
            headers={
                "x-api-key": api_key,
                "anthropic-version": "2023-06-01",
                "content-type": "application/json"
            },
            json={
                "model": "claude-sonnet-4-20250514",
                "max_tokens": 1500,
                "messages": [{"role": "user", "content": prompt}]
            },
            timeout=60
        )

        if response.status_code != 200:
            print(f"Survey analysis failed: {response.text}")
            return None

        result = response.json()
        content = result.get('content', [{}])[0].get('text', '{}')

        # Parse JSON response
        if '```json' in content:
            content = content.split('```json')[1].split('```')[0]
        elif '```' in content:
            content = content.split('```')[1].split('```')[0]

        analysis = json.loads(content.strip())
        return analysis

    except Exception as e:
        print(f"Error analyzing survey: {e}")
        return None


def parse_callback_time_with_claude(message_text, api_key):
    """Use Claude to parse a natural language time into structured format."""

    if not api_key:
        return {'error': 'API key not configured'}

    from datetime import datetime
    current_time = datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')

    prompt = f"""Parse this message into a scheduled callback time.

Current time: {current_time}

User message: "{message_text}"

Analyze the message and return a JSON object with:
- "parsed_successfully": true/false - whether you could extract a time
- "datetime_iso": ISO format datetime string (e.g., "2024-12-26T15:00:00") or null
- "timezone": extracted timezone (e.g., "EST", "PST", "UTC") or null if not specified
- "timezone_assumed": true if you had to assume a timezone, false if explicitly stated
- "needs_clarification": true if the time is ambiguous and needs clarification
- "clarification_question": if needs_clarification is true, what question to ask
- "friendly_time": human-readable version like "Thursday, December 26 at 3:00 PM EST"
- "confidence": "high", "medium", or "low"

Handle cases like:
- "tomorrow at 3pm" 
- "next Tuesday morning"
- "in 2 hours"
- "anytime after 5"
- "3pm EST"
- "Monday"

If the message doesn't seem to be about scheduling (e.g., "stop" or "wrong number"), set parsed_successfully to false.

Return ONLY the JSON object, no other text."""

    try:
        response = requests.post(
            "https://api.anthropic.com/v1/messages",
            headers={
                "x-api-key": api_key,
                "anthropic-version": "2023-06-01",
                "content-type": "application/json"
            },
            json={
                "model": "claude-sonnet-4-20250514",
                "max_tokens": 500,
                "messages": [{"role": "user", "content": prompt}]
            },
            timeout=30
        )

        if response.status_code != 200:
            return {'error': f'API error: {response.text}'}

        result = response.json()
        content = result.get('content', [{}])[0].get('text', '{}')

        # Parse JSON response
        if '```json' in content:
            content = content.split('```json')[1].split('```')[0]
        elif '```' in content:
            content = content.split('```')[1].split('```')[0]

        parsed = json.loads(content.strip())
        return parsed

    except Exception as e:
        return {'error': str(e)}
