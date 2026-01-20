"""
Reference, Survey, and related models.
"""
import json
from datetime import datetime
from refcheck_app.models.base import db, generate_uuid


class Reference(db.Model):
    """Reference contact and check status."""
    __tablename__ = 'references'

    id = db.Column(db.String(36), primary_key=True, default=generate_uuid)
    candidate_id = db.Column(db.String(36), db.ForeignKey('candidates.id', ondelete='CASCADE'),
                             nullable=False, index=True)
    job_id = db.Column(db.String(36), db.ForeignKey('jobs.id', ondelete='SET NULL'))

    # Contact info
    name = db.Column(db.String(255), nullable=False)
    phone = db.Column(db.String(50), nullable=False)
    email = db.Column(db.String(255))
    relationship = db.Column(db.String(100))  # e.g., "Manager", "Colleague"

    # Contact method: call_only, survey_only, call_and_survey
    contact_method = db.Column(db.String(50), default='call_only')

    # Status for calls
    status = db.Column(db.String(50), default='pending')
    # pending, calling, completed, failed, no_answer, scheduled

    # Survey status: not_sent, pending, completed
    survey_status = db.Column(db.String(50), default='not_sent')

    # Call info
    call_id = db.Column(db.String(255))  # Vapi call ID
    scheduled_time = db.Column(db.DateTime)
    timezone = db.Column(db.String(50))

    # SMS
    sms_sent = db.Column(db.Boolean, default=False)
    sms_sent_at = db.Column(db.DateTime)
    sms_response = db.Column(db.Text)

    # Callback scheduling
    callback_status = db.Column(db.String(50), default='none')
    # none, awaiting_reply, time_proposed, confirmed, callback_due, completed, expired
    callback_scheduled_time = db.Column(db.DateTime)
    callback_timezone = db.Column(db.String(50))
    sms_conversation = db.Column(db.Text)  # JSON array of messages
    callback_expires_at = db.Column(db.DateTime)  # 24 hour timeout

    # Custom questions (JSON array)
    custom_questions = db.Column(db.Text)

    # Notes (for storing failure reasons, etc.)
    notes = db.Column(db.Text)

    # Results
    score = db.Column(db.Integer)
    transcript = db.Column(db.Text)
    summary = db.Column(db.Text)
    sentiment = db.Column(db.String(50))

    # JSON fields for detailed results
    red_flags = db.Column(db.Text)  # JSON array
    discrepancies = db.Column(db.Text)  # JSON array
    achievements_verified = db.Column(db.Text)  # JSON array
    achievements_not_verified = db.Column(db.Text)  # JSON array
    positive_signals = db.Column(db.Text)  # JSON array
    structured_data = db.Column(db.Text)  # Full JSON analysis

    # Timestamps
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    completed_at = db.Column(db.DateTime)

    # Relationship
    job = db.relationship('Job', backref='references')

    def to_dict(self):
        return {
            'id': self.id,
            'candidate_id': self.candidate_id,
            'job_id': self.job_id,
            'name': self.name,
            'phone': self.phone,
            'email': self.email,
            'relationship': self.relationship,
            'contact_method': self.contact_method or 'call_only',
            'status': self.status,
            'survey_status': self.survey_status or 'not_sent',
            'call_id': self.call_id,
            'scheduled_time': self.scheduled_time.isoformat() if self.scheduled_time else None,
            'timezone': self.timezone,
            'sms_sent': self.sms_sent,
            'callback_status': self.callback_status or 'none',
            'callback_scheduled_time': self.callback_scheduled_time.isoformat() if self.callback_scheduled_time else None,
            'callback_timezone': self.callback_timezone,
            'custom_questions': json.loads(self.custom_questions) if self.custom_questions else [],
            'notes': self.notes,
            'score': self.score,
            'summary': self.summary,
            'sentiment': self.sentiment,
            'red_flags': json.loads(self.red_flags) if self.red_flags else [],
            'discrepancies': json.loads(self.discrepancies) if self.discrepancies else [],
            'achievements_verified': json.loads(self.achievements_verified) if self.achievements_verified else [],
            'achievements_not_verified': json.loads(self.achievements_not_verified) if self.achievements_not_verified else [],
            'positive_signals': json.loads(self.positive_signals) if self.positive_signals else [],
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'completed_at': self.completed_at.isoformat() if self.completed_at else None
        }

    def get_result(self):
        """Get result summary for display."""
        if self.status != 'completed':
            return None
        return {
            'score': self.score,
            'red_flags': json.loads(self.red_flags) if self.red_flags else [],
            'discrepancies': json.loads(self.discrepancies) if self.discrepancies else [],
            'summary': self.summary,
            'sentiment': self.sentiment,
            'achievements_verified': json.loads(self.achievements_verified) if self.achievements_verified else [],
            'achievements_not_verified': json.loads(self.achievements_not_verified) if self.achievements_not_verified else []
        }


class ResumeFile(db.Model):
    """Stored resume files."""
    __tablename__ = 'resume_files'

    id = db.Column(db.String(36), primary_key=True, default=generate_uuid)
    candidate_id = db.Column(
        db.String(36),
        db.ForeignKey('candidates.id', ondelete='CASCADE'),
        nullable=True,
        index=True,
    )

    filename = db.Column(db.String(255), nullable=False)
    original_filename = db.Column(db.String(255))
    content_type = db.Column(db.String(100))
    file_size = db.Column(db.Integer)
    file_data = db.Column(db.LargeBinary)  # Store file in DB for simplicity

    created_at = db.Column(db.DateTime, default=datetime.utcnow)


class ReferenceRequest(db.Model):
    """Request for candidate to submit their own references."""
    __tablename__ = 'reference_requests'

    id = db.Column(db.String(36), primary_key=True, default=generate_uuid)
    candidate_id = db.Column(db.String(36), db.ForeignKey('candidates.id', ondelete='CASCADE'),
                             nullable=False, index=True)

    # Secure token for URL
    token = db.Column(db.String(64), unique=True, nullable=False, index=True)

    # Status: pending, completed, expired
    status = db.Column(db.String(20), default='pending')

    # Timestamps
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    expires_at = db.Column(db.DateTime, nullable=False)
    completed_at = db.Column(db.DateTime)

    # Tracking
    email_sent_at = db.Column(db.DateTime)
    reminder_sent_at = db.Column(db.DateTime)

    # Relationship
    candidate = db.relationship('Candidate', backref='reference_requests')

    def is_valid(self):
        """Check if request is still valid (not expired, not completed)."""
        if self.status != 'pending':
            return False
        if datetime.utcnow() > self.expires_at:
            self.status = 'expired'
            return False
        return True

    def to_dict(self):
        return {
            'id': self.id,
            'candidate_id': self.candidate_id,
            'token': self.token,
            'status': self.status,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'expires_at': self.expires_at.isoformat() if self.expires_at else None,
            'completed_at': self.completed_at.isoformat() if self.completed_at else None,
            'email_sent_at': self.email_sent_at.isoformat() if self.email_sent_at else None,
            'reminder_sent_at': self.reminder_sent_at.isoformat() if self.reminder_sent_at else None
        }


class SurveyRequest(db.Model):
    """Survey request sent to a reference."""
    __tablename__ = 'survey_requests'

    id = db.Column(db.String(36), primary_key=True, default=generate_uuid)
    reference_id = db.Column(db.String(36), db.ForeignKey('references.id', ondelete='CASCADE'),
                             nullable=False, index=True)

    # Secure token for URL
    token = db.Column(db.String(64), unique=True, nullable=False, index=True)

    # Status: pending, completed, expired
    status = db.Column(db.String(20), default='pending')

    # Timestamps
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    expires_at = db.Column(db.DateTime, nullable=False)
    completed_at = db.Column(db.DateTime)
    email_sent_at = db.Column(db.DateTime)

    # Analysis results (populated after completion)
    survey_score = db.Column(db.Integer)
    survey_summary = db.Column(db.Text)
    survey_red_flags = db.Column(db.Text)  # JSON array
    survey_analysis = db.Column(db.Text)  # Full JSON analysis

    # Relationships
    reference = db.relationship('Reference', backref='survey_requests')
    questions = db.relationship('SurveyQuestion', backref='survey_request', 
                                cascade='all, delete-orphan', order_by='SurveyQuestion.order')

    def is_valid(self):
        """Check if survey request is still valid."""
        if self.status != 'pending':
            return False
        if datetime.utcnow() > self.expires_at:
            self.status = 'expired'
            return False
        return True

    def to_dict(self, include_questions=False, include_responses=False):
        result = {
            'id': self.id,
            'reference_id': self.reference_id,
            'token': self.token,
            'status': self.status,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'expires_at': self.expires_at.isoformat() if self.expires_at else None,
            'completed_at': self.completed_at.isoformat() if self.completed_at else None,
            'survey_score': self.survey_score,
            'survey_summary': self.survey_summary,
            'survey_red_flags': json.loads(self.survey_red_flags) if self.survey_red_flags else []
        }
        if include_questions:
            result['questions'] = [q.to_dict(include_response=include_responses) for q in self.questions]
        return result


class SurveyQuestion(db.Model):
    """Individual survey question."""
    __tablename__ = 'survey_questions'

    id = db.Column(db.String(36), primary_key=True, default=generate_uuid)
    survey_request_id = db.Column(db.String(36), db.ForeignKey('survey_requests.id', ondelete='CASCADE'),
                                   nullable=False, index=True)

    # Question content
    question_text = db.Column(db.Text, nullable=False)
    question_type = db.Column(db.String(20), nullable=False)  # standardized, ai_generated

    # Response type: rating, multiple_choice, free_text, yes_no_maybe
    response_type = db.Column(db.String(20), nullable=False)

    # Options for multiple choice (JSON array)
    options = db.Column(db.Text)

    # Display order
    order = db.Column(db.Integer, default=0)

    # Whether response is required
    required = db.Column(db.Boolean, default=True)

    # Response (one-to-one)
    response = db.relationship('SurveyResponse', backref='question', uselist=False,
                               cascade='all, delete-orphan')

    def to_dict(self, include_response=False):
        result = {
            'id': self.id,
            'question_text': self.question_text,
            'question_type': self.question_type,
            'response_type': self.response_type,
            'options': json.loads(self.options) if self.options else None,
            'order': self.order,
            'required': self.required
        }
        if include_response and self.response:
            result['response'] = self.response.to_dict()
        return result


class SurveyResponse(db.Model):
    """Response to a survey question."""
    __tablename__ = 'survey_responses'

    id = db.Column(db.String(36), primary_key=True, default=generate_uuid)
    survey_question_id = db.Column(db.String(36), db.ForeignKey('survey_questions.id', ondelete='CASCADE'),
                                    nullable=False, unique=True)

    # Response data (use whichever is appropriate for question type)
    rating = db.Column(db.Integer)  # 1-5 for rating questions
    text_response = db.Column(db.Text)  # For free text
    selected_option = db.Column(db.String(255))  # For multiple choice / yes_no_maybe

    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def to_dict(self):
        return {
            'id': self.id,
            'rating': self.rating,
            'text_response': self.text_response,
            'selected_option': self.selected_option
        }
