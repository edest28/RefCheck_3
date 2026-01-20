"""
Constants used throughout the application.
"""
DEFAULT_SMS_TEMPLATE = """Hi {name}, this is {sender_name} from {company_name}. I'm conducting a reference check for {candidate_name} and would love to get your feedback. Could we schedule a brief call? Please reply with your availability."""

STANDARDIZED_SURVEY_QUESTIONS = [
    {
        "question_text": "How would you rate {candidate_name}'s overall performance?",
        "response_type": "rating",
        "question_type": "standardized",
        "required": True
    },
    {
        "question_text": "Would you rehire {candidate_name}?",
        "response_type": "yes_no_maybe",
        "question_type": "standardized",
        "required": True
    },
    {
        "question_text": "What were {candidate_name}'s greatest strengths?",
        "response_type": "free_text",
        "question_type": "standardized",
        "required": True
    },
    {
        "question_text": "What areas could {candidate_name} improve in?",
        "response_type": "free_text",
        "question_type": "standardized",
        "required": False
    },
    {
        "question_text": "Is there anything else you'd like to share about {candidate_name}?",
        "response_type": "free_text",
        "question_type": "standardized",
        "required": False
    }
]

ALLOWED_EXTENSIONS = {'pdf', 'txt', 'doc', 'docx'}
