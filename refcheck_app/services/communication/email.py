"""
Email sending services using Resend API.
"""
import requests
from refcheck_app.models import Job


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


def send_rejection_email(application, job_posting, template, resend_api_key):
    """Send rejection email to applicant using the user's template.
    Template may use: {{candidate_name}}, {{job_title}}, {{company_name}}
    """
    if not resend_api_key:
        return {'success': False, 'error': 'Resend API key not configured'}
    if not application.email:
        return {'success': False, 'error': 'Applicant email not available'}

    candidate_name = application.full_name or 'Candidate'
    job_title = job_posting.title or 'the position'
    company_name = getattr(job_posting, 'company', None) and job_posting.company.name or job_posting.company_name or 'our company'

    body = (template or '').strip()
    if not body:
        body = f"Hi {candidate_name},\n\nThank you for your interest in {job_title} at {company_name}. After careful consideration, we have decided to move forward with other candidates for this role.\n\nWe wish you the best in your job search.\n\nBest regards,\nThe Hiring Team"
    body = body.replace('{{candidate_name}}', candidate_name)
    body = body.replace('{{job_title}}', job_title)
    body = body.replace('{{company_name}}', company_name)

    subject = f"Update on your application – {job_title}"
    html_content = f"""
    <div style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto; line-height: 1.6;">
        {body.replace(chr(10), '<br>')}
        <p style="color: #666; font-size: 14px; margin-top: 24px;">This email was sent by RefCheck AI.</p>
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
                "to": [application.email],
                "subject": subject,
                "html": html_content
            },
            timeout=30
        )
        if response.status_code == 200:
            return {'success': True, 'message_id': response.json().get('id')}
        return {'success': False, 'error': response.text}
    except Exception as e:
        return {'success': False, 'error': str(e)}
