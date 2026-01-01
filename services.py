"""
Business logic services for RefCheck AI.
Handles resume parsing, reference calls, SMS, and transcript analysis.
"""

import os
import re
import json
from datetime import datetime
import requests
from models import db, Candidate, Job, Reference, ResumeFile


# Default SMS template
DEFAULT_SMS_TEMPLATE = """Hi, I'm reaching out to conduct a brief reference call on behalf of {candidate_first_name} {candidate_last_name}, who listed you as a reference. I attempted to call but wasn't able to connect. Would you be available for a 5–10 minute call to discuss your experience working with {candidate_first_name}? Please let me know a time that works for you. Thank you."""


def extract_text_from_pdf(pdf_data):
    """Extract text from PDF binary data."""
    import tempfile

    try:
        # Write to temp file
        with tempfile.NamedTemporaryFile(suffix='.pdf', delete=False) as f:
            f.write(pdf_data)
            temp_path = f.name

        try:
            import pdfplumber
            text = ""
            with pdfplumber.open(temp_path) as pdf:
                for page in pdf.pages:
                    page_text = page.extract_text()
                    if page_text:
                        text += page_text + "\n"
            return text
        except ImportError:
            from pypdf import PdfReader
            reader = PdfReader(temp_path)
            text = ""
            for page in reader.pages:
                page_text = page.extract_text()
                if page_text:
                    text += page_text + "\n"
            return text
    except Exception as e:
        print(f"Error extracting PDF: {e}")
        return None
    finally:
        try:
            os.unlink(temp_path)
        except:
            pass


def parse_resume_with_claude(resume_text, api_key):
    """Use Claude to extract structured information from a resume."""

    if not api_key:
        # Return mock data for testing without API key
        return {
            "candidate_name": "Sample Candidate",
            "email": "sample@example.com",
            "phone": "+1 555 123 4567",
            "summary": "Experienced professional",
            "skills": ["Python", "JavaScript", "Project Management"],
            "jobs": [
                {
                    "company": "Acme Corp",
                    "title": "Senior Engineer",
                    "dates": "2020-2023",
                    "responsibilities": ["Led development teams", "Managed projects"],
                    "achievements": ["Increased efficiency by 40%", "Launched 3 products"]
                }
            ]
        }

    headers = {
        "x-api-key": api_key,
        "content-type": "application/json",
        "anthropic-version": "2023-06-01"
    }

    payload = {
        "model": "claude-haiku-4-20250514",  # Haiku is 3x faster and 20x cheaper than Sonnet
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


def format_phone_e164(phone):
    """Format phone number to E.164 format (+1XXXXXXXXXX for US)."""
    # Remove all non-digit characters
    digits = re.sub(r'\D', '', phone)

    # If it's 10 digits, assume US and add +1
    if len(digits) == 10:
        return f"+1{digits}"
    # If it's 11 digits starting with 1, add +
    elif len(digits) == 11 and digits.startswith('1'):
        return f"+{digits}"
    # If it already has country code (12+ digits), add +
    elif len(digits) >= 11:
        return f"+{digits}"
    # Otherwise return as-is with + prefix
    else:
        return f"+{digits}" if not phone.startswith('+') else phone


def initiate_vapi_call_global(reference, candidate, job, vapi_api_key, vapi_phone_number_id):
    """Initiate a reference check call via Vapi using global credentials."""

    if not vapi_api_key or not vapi_phone_number_id:
        return {"error": "Vapi not configured."}

    # Format phone number to E.164
    formatted_phone = format_phone_e164(reference.phone)

    questions = generate_reference_questions(
        job,
        candidate.name,
        reference.custom_questions,
        target_role_category=candidate.target_role_category,
        target_role_details=candidate.target_role_details
    )
    system_prompt = build_assistant_prompt(
        candidate.name,
        reference.name,
        job,
        questions,
        target_role_category=candidate.target_role_category,
        target_role_details=candidate.target_role_details
    )

    headers = {
        "Authorization": f"Bearer {vapi_api_key}",
        "Content-Type": "application/json"
    }

    call_payload = {
        "phoneNumberId": vapi_phone_number_id,
        "customer": {"number": formatted_phone},
        "assistant": {
            "name": "Reference Checker",
            "firstMessage": f"Hello, this is Sarah from the hiring verification team. I'm calling regarding a reference check for {candidate.name}. Am I speaking with {reference.name}?",
            "model": {
                "provider": "anthropic",
                "model": "claude-sonnet-4-20250514",
                "messages": [{"role": "system", "content": system_prompt}],
                "temperature": 0.7
            },
            "voice": {"provider": "11labs", "voiceId": "21m00Tcm4TlvDq8ikWAM"},
            "maxDurationSeconds": 600,
            "endCallMessage": "Thank you for your time. Have a great day!",
            "transcriber": {"provider": "deepgram", "language": "en"}
        }
    }

    try:
        response = requests.post(
            "https://api.vapi.ai/call",
            headers=headers,
            json=call_payload,
            timeout=30
        )
        if response.status_code != 201 and response.status_code != 200:
            # Get detailed error from Vapi
            try:
                error_detail = response.json()
            except:
                error_detail = response.text
            return {"error": f"Vapi Error ({response.status_code}): {error_detail}"}

        call_data = response.json()
        return {"success": True, "call_id": call_data.get('id')}
    except requests.exceptions.RequestException as e:
        return {"error": str(e)}


def get_vapi_call_status_global(call_id, vapi_api_key):
    """Get call status and results from Vapi using global credentials."""

    if not vapi_api_key:
        return {"error": "Vapi not configured"}

    headers = {"Authorization": f"Bearer {vapi_api_key}"}

    try:
        response = requests.get(
            f"https://api.vapi.ai/call/{call_id}",
            headers=headers,
            timeout=30
        )
        response.raise_for_status()
        return response.json()
    except requests.exceptions.RequestException as e:
        return {"error": str(e)}


def send_sms_global(to_number, message, account_sid, auth_token, from_number):
    """Send SMS via Twilio using global credentials."""

    if not all([account_sid, auth_token, from_number]):
        return {"success": False, "error": "Twilio not configured"}

    # Format phone number to E.164
    formatted_to = format_phone_e164(to_number)

    try:
        auth = (account_sid, auth_token)
        data = {
            "From": from_number,
            "To": formatted_to,
            "Body": message
        }
        response = requests.post(
            f"https://api.twilio.com/2010-04-01/Accounts/{account_sid}/Messages.json",
            auth=auth,
            data=data,
            timeout=30
        )
        if response.status_code == 201:
            return {"success": True, "sid": response.json().get("sid")}
        return {"success": False, "error": response.text}
    except Exception as e:
        return {"success": False, "error": str(e)}


def initiate_vapi_call(reference, candidate, job, user):
    """Initiate a reference check call via Vapi."""

    if not user.vapi_api_key or not user.vapi_phone_number_id:
        return {"error": "Vapi not configured. Please add your API key in Settings."}

    questions = generate_reference_questions(
        job,
        candidate.name,
        reference.custom_questions
    )
    system_prompt = build_assistant_prompt(
        candidate.name,
        reference.name,
        job,
        questions
    )

    headers = {
        "Authorization": f"Bearer {user.vapi_api_key}",
        "Content-Type": "application/json"
    }

    call_payload = {
        "phoneNumberId": user.vapi_phone_number_id,
        "customer": {"number": reference.phone},
        "assistant": {
            "name": "Reference Checker",
            "firstMessage": f"Hello, this is Sarah from the hiring verification team. I'm calling regarding a reference check for {candidate.name}. Am I speaking with {reference.name}?",
            "model": {
                "provider": "anthropic",
                "model": "claude-sonnet-4-20250514",
                "messages": [{"role": "system", "content": system_prompt}],
                "temperature": 0.7
            },
            "voice": {"provider": "11labs", "voiceId": "21m00Tcm4TlvDq8ikWAM"},
            "maxDurationSeconds": 600,
            "endCallMessage": "Thank you for your time. Have a great day!",
            "transcriber": {"provider": "deepgram", "language": "en"}
        }
    }

    try:
        response = requests.post(
            "https://api.vapi.ai/call",
            headers=headers,
            json=call_payload,
            timeout=30
        )
        response.raise_for_status()
        call_data = response.json()

        return {"success": True, "call_id": call_data.get('id')}
    except requests.exceptions.RequestException as e:
        return {"error": str(e)}


def get_vapi_call_status(call_id, user):
    """Get call status and results from Vapi."""

    if not user.vapi_api_key:
        return {"error": "Vapi not configured"}

    headers = {"Authorization": f"Bearer {user.vapi_api_key}"}

    try:
        response = requests.get(
            f"https://api.vapi.ai/call/{call_id}",
            headers=headers,
            timeout=30
        )
        response.raise_for_status()
        return response.json()
    except requests.exceptions.RequestException as e:
        return {"error": str(e)}


def send_sms(to_number, message, user):
    """Send SMS via Twilio."""

    if not all([user.twilio_account_sid, user.twilio_auth_token, user.twilio_phone_number]):
        return {"success": False, "error": "Twilio not configured"}

    try:
        auth = (user.twilio_account_sid, user.twilio_auth_token)
        data = {
            "From": user.twilio_phone_number,
            "To": to_number,
            "Body": message
        }
        response = requests.post(
            f"https://api.twilio.com/2010-04-01/Accounts/{user.twilio_account_sid}/Messages.json",
            auth=auth,
            data=data,
            timeout=30
        )
        if response.status_code == 201:
            return {"success": True, "sid": response.json().get("sid")}
        return {"success": False, "error": response.text}
    except Exception as e:
        return {"success": False, "error": str(e)}


def format_sms_message(template, candidate_name):
    """Format SMS template with candidate info."""
    parts = candidate_name.split(' ', 1)
    first_name = parts[0]
    last_name = parts[1] if len(parts) > 1 else ''

    return template.format(
        candidate_first_name=first_name,
        candidate_last_name=last_name
    )


def create_candidate_from_resume(user_id, parsed_data, resume_text=None, resume_filename=None):
    """Create a candidate and associated jobs from parsed resume data."""

    candidate = Candidate(
        user_id=user_id,
        name=parsed_data.get('candidate_name', 'Unknown'),
        email=parsed_data.get('email', ''),
        phone=parsed_data.get('phone', ''),
        summary=parsed_data.get('summary', ''),
        skills=json.dumps(parsed_data.get('skills', [])),
        resume_text=resume_text,
        resume_filename=resume_filename,
        status='intake'
    )

    db.session.add(candidate)
    db.session.commit()  # Commit to get candidate ID

    # Create jobs
    for idx, job_data in enumerate(parsed_data.get('jobs', [])):
        job = Job(
            candidate_id=candidate.id,
            company=job_data.get('company', 'Unknown'),
            title=job_data.get('title', ''),
            dates=job_data.get('dates', ''),
            order=idx,
            responsibilities=json.dumps(job_data.get('responsibilities', [])),
            achievements=json.dumps(job_data.get('achievements', []))
        )
        db.session.add(job)

    db.session.commit()
    return candidate


def search_candidates(user_id, query, status=None, limit=50):
    """Search candidates by query string."""

    base_query = Candidate.query.filter_by(user_id=user_id)

    if status:
        base_query = base_query.filter_by(status=status)

    if query:
        search_term = f"%{query.lower()}%"
        base_query = base_query.filter(Candidate.search_vector.ilike(search_term))

    return base_query.order_by(Candidate.updated_at.desc()).limit(limit).all()


# ============================================================================
# Email Services (Resend)
# ============================================================================

def send_reference_request_email(candidate, token, base_url, resend_api_key):
    """Send email to candidate requesting they submit references."""

    if not resend_api_key:
        return {'success': False, 'error': 'Resend API key not configured'}

    if not candidate.email:
        return {'success': False, 'error': 'Candidate email not available'}

    # Build the submission URL
    submit_url = f"{base_url}/submit-references/{token}"

    # Get jobs for the email
    jobs = list(candidate.jobs.order_by(Job.order))

    # Build job list HTML
    jobs_html = ""
    for job in jobs:
        jobs_html += f"<li><strong>{job.title}</strong> at {job.company} ({job.dates})</li>"

    # Email content
    subject = "RefCheck AI - Please Submit Your References"

    html_content = f"""
    <div style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto;">
        <h2 style="color: #4f46e5;">Reference Request</h2>

        <p>Hi {candidate.name.split()[0]},</p>

        <p>RefCheck AI is requesting references for your job application. Please provide contact information for references from your previous roles.</p>

        <p><strong>Your work history:</strong></p>
        <ul>
            {jobs_html}
        </ul>

        <p>Please click the button below to submit your references:</p>

        <p style="text-align: center; margin: 30px 0;">
            <a href="{submit_url}" style="background-color: #4f46e5; color: white; padding: 12px 24px; text-decoration: none; border-radius: 6px; font-weight: bold;">Submit References</a>
        </p>

        <p style="color: #666; font-size: 14px;">This link will expire in 7 days.</p>

        <p style="color: #666; font-size: 14px;">If you have any questions, please contact the hiring team directly.</p>

        <hr style="border: none; border-top: 1px solid #eee; margin: 30px 0;">

        <p style="color: #999; font-size: 12px;">This email was sent by RefCheck AI.</p>
    </div>
    """

    try:
        response = requests.post(
            "https://api.resend.com/emails",
            headers={
                "Authorization": f"Bearer {resend_api_key}",
                "Content-Type": "application/json"
            },
            json={
                "from": "RefCheck AI <onboarding@resend.dev>",
                "to": [candidate.email],
                "subject": subject,
                "html": html_content
            },
            timeout=30
        )

        if response.status_code == 200:
            return {'success': True, 'message_id': response.json().get('id')}
        else:
            return {'success': False, 'error': response.text}

    except Exception as e:
        return {'success': False, 'error': str(e)}


def send_reference_confirmation_email(candidate, resend_api_key):
    """Send confirmation email to candidate after they submit references."""

    if not resend_api_key:
        return {'success': False, 'error': 'Resend API key not configured'}

    if not candidate.email:
        return {'success': False, 'error': 'Candidate email not available'}

    subject = "RefCheck AI - References Received"

    html_content = f"""
    <div style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto;">
        <h2 style="color: #4f46e5;">References Received</h2>

        <p>Hi {candidate.name.split()[0]},</p>

        <p>Thank you for submitting your references. We have received your information and will be in touch with your references shortly.</p>

        <p>No further action is needed from you at this time.</p>

        <hr style="border: none; border-top: 1px solid #eee; margin: 30px 0;">

        <p style="color: #999; font-size: 12px;">This email was sent by RefCheck AI.</p>
    </div>
    """

    try:
        response = requests.post(
            "https://api.resend.com/emails",
            headers={
                "Authorization": f"Bearer {resend_api_key}",
                "Content-Type": "application/json"
            },
            json={
                "from": "RefCheck AI <onboarding@resend.dev>",
                "to": [candidate.email],
                "subject": subject,
                "html": html_content
            },
            timeout=30
        )

        if response.status_code == 200:
            return {'success': True}
        else:
            return {'success': False, 'error': response.text}

    except Exception as e:
        return {'success': False, 'error': str(e)}


def send_reference_reminder_email(candidate, token, base_url, resend_api_key):
    """Send reminder email to candidate who hasn't submitted references."""

    if not resend_api_key:
        return {'success': False, 'error': 'Resend API key not configured'}

    if not candidate.email:
        return {'success': False, 'error': 'Candidate email not available'}

    submit_url = f"{base_url}/submit-references/{token}"

    subject = "Reminder: RefCheck AI - Please Submit Your References"

    html_content = f"""
    <div style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto;">
        <h2 style="color: #4f46e5;">Reminder: Reference Request</h2>

        <p>Hi {candidate.name.split()[0]},</p>

        <p>This is a friendly reminder that we're still waiting for your references. Please submit them at your earliest convenience.</p>

        <p style="text-align: center; margin: 30px 0;">
            <a href="{submit_url}" style="background-color: #4f46e5; color: white; padding: 12px 24px; text-decoration: none; border-radius: 6px; font-weight: bold;">Submit References</a>
        </p>

        <p style="color: #666; font-size: 14px;">This link will expire soon.</p>

        <hr style="border: none; border-top: 1px solid #eee; margin: 30px 0;">

        <p style="color: #999; font-size: 12px;">This email was sent by RefCheck AI.</p>
    </div>
    """

    try:
        response = requests.post(
            "https://api.resend.com/emails",
            headers={
                "Authorization": f"Bearer {resend_api_key}",
                "Content-Type": "application/json"
            },
            json={
                "from": "RefCheck AI <onboarding@resend.dev>",
                "to": [candidate.email],
                "subject": subject,
                "html": html_content
            },
            timeout=30
        )

        if response.status_code == 200:
            return {'success': True}
        else:
            return {'success': False, 'error': response.text}

    except Exception as e:
        return {'success': False, 'error': str(e)}


# ============================================================================
# Survey Services
# ============================================================================

# Standardized survey questions
STANDARDIZED_SURVEY_QUESTIONS = [
    {
        'question_text': 'How long did you work with {candidate_name}?',
        'response_type': 'multiple_choice',
        'options': ['Less than 6 months', '6-12 months', '1-2 years', '2+ years'],
        'required': True
    },
    {
        'question_text': 'What was your working relationship with {candidate_name}?',
        'response_type': 'multiple_choice',
        'options': ['Direct manager', 'Indirect manager', 'Peer/colleague', 'Direct report', 'Client', 'Other'],
        'required': True
    },
    {
        'question_text': 'How would you rate their overall job performance?',
        'response_type': 'rating',
        'required': True
    },
    {
        'question_text': 'How would you rate their reliability and dependability?',
        'response_type': 'rating',
        'required': True
    },
    {
        'question_text': 'How would you rate their communication skills?',
        'response_type': 'rating',
        'required': True
    },
    {
        'question_text': 'How would you rate their teamwork and collaboration?',
        'response_type': 'rating',
        'required': True
    },
    {
        'question_text': 'What were {candidate_name}\'s greatest strengths?',
        'response_type': 'free_text',
        'required': True
    },
    {
        'question_text': 'What areas could {candidate_name} improve or develop?',
        'response_type': 'free_text',
        'required': True
    },
    {
        'question_text': 'Would you rehire or recommend {candidate_name}?',
        'response_type': 'multiple_choice',
        'options': ['Yes, without hesitation', 'Yes, with some reservations', 'No', 'Prefer not to say'],
        'required': True
    },
    {
        'question_text': 'Any additional comments about {candidate_name}?',
        'response_type': 'free_text',
        'required': False
    }
]


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


def send_survey_email(reference, candidate, token, base_url, resend_api_key):
    """Send survey email to a reference."""

    if not resend_api_key:
        return {'success': False, 'error': 'Resend API key not configured'}

    if not reference.email:
        return {'success': False, 'error': 'Reference email not available'}

    survey_url = f"{base_url}/submit-survey/{token}"

    subject = f"RefCheck AI - Reference Survey for {candidate.name}"

    html_content = f"""
    <div style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto;">
        <h2 style="color: #4f46e5;">Reference Survey Request</h2>

        <p>Hi {reference.name.split()[0]},</p>

        <p>You've been listed as a reference for <strong>{candidate.name}</strong>. We would appreciate if you could take a few minutes to complete a brief survey about your experience working with them.</p>

        <p>The survey should take approximately 5-10 minutes to complete.</p>

        <p style="text-align: center; margin: 30px 0;">
            <a href="{survey_url}" style="background-color: #4f46e5; color: white; padding: 12px 24px; text-decoration: none; border-radius: 6px; font-weight: bold;">Complete Survey</a>
        </p>

        <p style="color: #666; font-size: 14px;">This link will expire in 7 days.</p>

        <p style="color: #666; font-size: 14px;">Your responses will be kept confidential and used only for employment verification purposes.</p>

        <hr style="border: none; border-top: 1px solid #eee; margin: 30px 0;">

        <p style="color: #999; font-size: 12px;">This email was sent by RefCheck AI.</p>
    </div>
    """

    try:
        response = requests.post(
            "https://api.resend.com/emails",
            headers={
                "Authorization": f"Bearer {resend_api_key}",
                "Content-Type": "application/json"
            },
            json={
                "from": "RefCheck AI <onboarding@resend.dev>",
                "to": [reference.email],
                "subject": subject,
                "html": html_content
            },
            timeout=30
        )

        if response.status_code == 200:
            return {'success': True, 'message_id': response.json().get('id')}
        else:
            return {'success': False, 'error': response.text}

    except Exception as e:
        return {'success': False, 'error': str(e)}


def send_survey_confirmation_email(reference, candidate, resend_api_key):
    """Send confirmation email to reference after completing survey."""

    if not resend_api_key:
        return {'success': False, 'error': 'Resend API key not configured'}

    if not reference.email:
        return {'success': False, 'error': 'Reference email not available'}

    subject = "RefCheck AI - Survey Completed"

    html_content = f"""
    <div style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto;">
        <h2 style="color: #4f46e5;">Thank You!</h2>

        <p>Hi {reference.name.split()[0]},</p>

        <p>Thank you for completing the reference survey for {candidate.name}. Your feedback is greatly appreciated.</p>

        <p>No further action is needed from you.</p>

        <hr style="border: none; border-top: 1px solid #eee; margin: 30px 0;">

        <p style="color: #999; font-size: 12px;">This email was sent by RefCheck AI.</p>
    </div>
    """

    try:
        response = requests.post(
            "https://api.resend.com/emails",
            headers={
                "Authorization": f"Bearer {resend_api_key}",
                "Content-Type": "application/json"
            },
            json={
                "from": "RefCheck AI <onboarding@resend.dev>",
                "to": [reference.email],
                "subject": subject,
                "html": html_content
            },
            timeout=30
        )

        if response.status_code == 200:
            return {'success': True}
        else:
            return {'success': False, 'error': response.text}

    except Exception as e:
        return {'success': False, 'error': str(e)}


# ============================================================================
# SMS Callback Scheduling Services
# ============================================================================

def send_callback_request_sms(reference, candidate, twilio_sid, twilio_token, twilio_phone):
    """Send SMS asking reference for a better time to call."""

    message = f"Hi {reference.name.split()[0]}, we tried to reach you regarding a reference check for {candidate.name}. Is there a better time to call you back? Please reply with a day and time (e.g., 'Tomorrow at 3pm EST')."

    result = send_sms_global(reference.phone, message, twilio_sid, twilio_token, twilio_phone)

    return result


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


def send_callback_confirmation_sms(reference, friendly_time, twilio_sid, twilio_token, twilio_phone):
    """Send SMS confirming the scheduled callback time."""

    message = f"Great! We'll call you on {friendly_time}. Reply YES to confirm or suggest another time."

    result = send_sms_global(reference.phone, message, twilio_sid, twilio_token, twilio_phone)

    return result


def send_callback_final_confirmation_sms(reference, friendly_time, twilio_sid, twilio_token, twilio_phone):
    """Send final confirmation after user confirms."""

    message = f"Confirmed! We'll call you on {friendly_time}. Thank you!"

    result = send_sms_global(reference.phone, message, twilio_sid, twilio_token, twilio_phone)

    return result


def send_timezone_clarification_sms(reference, twilio_sid, twilio_token, twilio_phone):
    """Ask for timezone clarification."""

    message = "Thanks! What timezone are you in? (e.g., EST, PST, CST)"

    result = send_sms_global(reference.phone, message, twilio_sid, twilio_token, twilio_phone)

    return result


def add_to_sms_conversation(reference, direction, message):
    """Add a message to the SMS conversation log."""
    from datetime import datetime

    conversation = []
    if reference.sms_conversation:
        try:
            conversation = json.loads(reference.sms_conversation)
        except:
            conversation = []

    conversation.append({
        'direction': direction,  # 'inbound' or 'outbound'
        'message': message,
        'timestamp': datetime.utcnow().isoformat()
    })

    reference.sms_conversation = json.dumps(conversation)


# Role categories for target role dropdown
ROLE_CATEGORIES = [
    'Engineering / Technical',
    'Product / Design', 
    'Sales / Business Development',
    'Marketing / Communications',
    'Operations / Logistics',
    'Finance / Accounting',
    'HR / People Operations',
    'Customer Support / Success',
    'Executive / Leadership',
    'Legal / Compliance',
    'Other'
]
