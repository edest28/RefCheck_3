"""
Twilio SMS integration for reference checks.
"""
import re
import requests
from app.services.communication.vapi import format_phone_e164


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


def send_callback_request_sms(reference, candidate, twilio_sid, twilio_token, twilio_phone):
    """Send SMS asking reference for a better time to call."""
    message = f"Hi {reference.name.split()[0]}, we tried to reach you regarding a reference check for {candidate.name}. Is there a better time to call you back? Please reply with a day and time (e.g., 'Tomorrow at 3pm EST')."
    result = send_sms_global(reference.phone, message, twilio_sid, twilio_token, twilio_phone)
    return result


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
    import json
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
