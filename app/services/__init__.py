"""
Services package for RefCheck AI.
"""
# Import all service modules for easy access
from app.services.file_processing import extract_text_from_pdf
from app.services.ai.resume_parser import parse_resume_with_claude
from app.services.ai.transcript_analyzer import analyze_transcript_with_claude, calculate_verification_score
from app.services.ai.jd_generator import generate_job_description_with_claude
from app.services.ai.application_screener import analyze_application_with_claude
from app.services.reference import (
    generate_reference_questions,
    build_assistant_prompt,
    generate_ai_survey_questions,
    get_survey_questions_for_reference,
    analyze_survey_responses,
    parse_callback_time_with_claude
)
from app.services.communication.vapi import (
    initiate_vapi_call,
    get_vapi_call_status,
    initiate_vapi_call_global,
    get_vapi_call_status_global,
    format_phone_e164
)
from app.services.communication.twilio import (
    send_sms,
    send_sms_global,
    format_sms_message,
    send_callback_request_sms,
    send_callback_confirmation_sms,
    send_callback_final_confirmation_sms,
    send_timezone_clarification_sms,
    add_to_sms_conversation
)
from app.services.communication.email import (
    send_reference_request_email,
    send_reference_confirmation_email,
    send_reference_reminder_email,
    send_survey_email,
    send_survey_confirmation_email
)
from app.services.candidate import create_candidate_from_resume, search_candidates

__all__ = [
    # File processing
    'extract_text_from_pdf',
    # AI services
    'parse_resume_with_claude',
    'analyze_transcript_with_claude',
    'calculate_verification_score',
    'generate_job_description_with_claude',
    'analyze_application_with_claude',
    # Reference services
    'generate_reference_questions',
    'build_assistant_prompt',
    'generate_ai_survey_questions',
    'get_survey_questions_for_reference',
    'analyze_survey_responses',
    'parse_callback_time_with_claude',
    # Communication services
    'initiate_vapi_call',
    'get_vapi_call_status',
    'initiate_vapi_call_global',
    'get_vapi_call_status_global',
    'format_phone_e164',
    'send_sms',
    'send_sms_global',
    'format_sms_message',
    'send_callback_request_sms',
    'send_callback_confirmation_sms',
    'send_callback_final_confirmation_sms',
    'send_timezone_clarification_sms',
    'add_to_sms_conversation',
    'send_reference_request_email',
    'send_reference_confirmation_email',
    'send_reference_reminder_email',
    'send_survey_email',
    'send_survey_confirmation_email',
    # Candidate services
    'create_candidate_from_resume',
    'search_candidates',
]
