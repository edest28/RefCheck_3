"""
Vapi phone call integration for reference checks.
"""
import re
import requests
from app.services.reference import generate_reference_questions, build_assistant_prompt


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
