"""
Database models for RefCheck AI multi-tenant system.
Implements user isolation, candidate management, and reference tracking.
"""

from datetime import datetime
from flask_sqlalchemy import SQLAlchemy
from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash
from sqlalchemy import Index, event
from sqlalchemy.dialects.postgresql import TSVECTOR
import uuid
import json

db = SQLAlchemy()


def generate_uuid():
    return str(uuid.uuid4())


class User(UserMixin, db.Model):
    """User model for authentication and tenant isolation."""
    __tablename__ = 'users'

    id = db.Column(db.String(36), primary_key=True, default=generate_uuid)
    email = db.Column(db.String(255), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(255), nullable=False)
    first_name = db.Column(db.String(100), nullable=False)
    last_name = db.Column(db.String(100), nullable=False)
    company_name = db.Column(db.String(255))

    # Settings
    sms_template = db.Column(db.Text)
    timezone = db.Column(db.String(50), default='America/New_York')

    # API keys (encrypted in production)
    vapi_api_key = db.Column(db.String(255))
    vapi_phone_number_id = db.Column(db.String(255))
    twilio_account_sid = db.Column(db.String(255))
    twilio_auth_token = db.Column(db.String(255))
    twilio_phone_number = db.Column(db.String(50))

    # Timestamps
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    last_login_at = db.Column(db.DateTime)

    # Relationships
    candidates = db.relationship('Candidate', backref='owner', lazy='dynamic',
                                  cascade='all, delete-orphan')

    def set_password(self, password):
        # Use pbkdf2 instead of scrypt for compatibility with LibreSSL
        self.password_hash = generate_password_hash(password, method='pbkdf2:sha256')

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

    @property
    def full_name(self):
        return f"{self.first_name} {self.last_name}"

    def to_dict(self):
        return {
            'id': self.id,
            'email': self.email,
            'first_name': self.first_name,
            'last_name': self.last_name,
            'company_name': self.company_name,
            'timezone': self.timezone,
            'created_at': self.created_at.isoformat() if self.created_at else None
        }


class Candidate(db.Model):
    """Candidate model with full-text search support."""
    __tablename__ = 'candidates'

    id = db.Column(db.String(36), primary_key=True, default=generate_uuid)
    user_id = db.Column(db.String(36), db.ForeignKey('users.id', ondelete='CASCADE'), 
                        nullable=False, index=True)

    # Basic info
    name = db.Column(db.String(255), nullable=False)
    email = db.Column(db.String(255))
    phone = db.Column(db.String(50))
    position = db.Column(db.String(255))

    # Resume data
    resume_text = db.Column(db.Text)
    resume_filename = db.Column(db.String(255))
    summary = db.Column(db.Text)
    skills = db.Column(db.Text)  # JSON array of skills

    # Status
    status = db.Column(db.String(50), default='intake')  # intake, in_progress, completed, archived

    # Target role (for question generation)
    target_role_category = db.Column(db.String(100))  # Engineering, Sales, etc.
    target_role_details = db.Column(db.Text)  # Free-text specifics

    # Settings
    sms_template = db.Column(db.Text)

    # Search optimization
    search_vector = db.Column(db.Text)  # Combined searchable text

    # Notes
    notes = db.Column(db.Text)

    # Timestamps
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    jobs = db.relationship('Job', backref='candidate', lazy='dynamic',
                           cascade='all, delete-orphan', order_by='Job.order')
    references = db.relationship('Reference', backref='candidate', lazy='dynamic',
                                  cascade='all, delete-orphan')

    # Indexes
    __table_args__ = (
        Index('idx_candidate_user_status', 'user_id', 'status'),
    )

    def update_search_vector(self):
        """Update the search vector for full-text search."""
        parts = [
            self.name or '',
            self.email or '',
            self.position or '',
            self.summary or '',
            self.skills or '',
            self.notes or '',
            self.resume_text or ''
        ]
        # Add job info
        for job in self.jobs:
            parts.extend([job.company or '', job.title or ''])

        self.search_vector = ' '.join(parts).lower()

    def to_dict(self, include_jobs=False, include_references=False):
        result = {
            'id': self.id,
            'name': self.name,
            'email': self.email,
            'phone': self.phone,
            'position': self.position,
            'summary': self.summary,
            'skills': self.skills,
            'status': self.status,
            'target_role_category': self.target_role_category,
            'target_role_details': self.target_role_details,
            'notes': self.notes,
            'resume_filename': self.resume_filename,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None
        }

        if include_jobs:
            result['jobs'] = [job.to_dict() for job in self.jobs.order_by(Job.order)]

        if include_references:
            result['references'] = [ref.to_dict() for ref in self.references]

        return result

    def get_reference_progress(self):
        """Get reference check progress."""
        refs = list(self.references)
        total = len(refs)
        completed = len([r for r in refs if r.status == 'completed'])
        return {'completed': completed, 'total': total}

    def get_signal(self):
        """Calculate aggregate signal from completed references."""
        completed_refs = [r for r in self.references if r.status == 'completed' and r.score is not None]

        if not completed_refs:
            return {'score': None, 'label': 'No Data', 'color': 'gray'}

        avg_score = sum(r.score for r in completed_refs) / len(completed_refs)

        if avg_score >= 75:
            return {'score': round(avg_score), 'label': 'Strong', 'color': 'green'}
        elif avg_score >= 55:
            return {'score': round(avg_score), 'label': 'Moderate', 'color': 'yellow'}
        else:
            return {'score': round(avg_score), 'label': 'Concerns', 'color': 'red'}

    def get_reference_request_status(self):
        """Get the status of reference requests for this candidate."""
        requests = list(self.reference_requests)
        if not requests:
            return {'status': 'none', 'label': 'Not Requested'}

        # Get most recent request
        latest = max(requests, key=lambda r: r.created_at)

        if latest.status == 'completed':
            return {'status': 'completed', 'label': 'References Submitted', 'color': 'green'}
        elif latest.status == 'expired':
            return {'status': 'expired', 'label': 'Request Expired', 'color': 'red'}
        elif latest.is_valid():
            return {'status': 'pending', 'label': 'Awaiting Response', 'color': 'yellow'}
        else:
            return {'status': 'expired', 'label': 'Request Expired', 'color': 'red'}


class JobPosting(db.Model):
    """Job postings for the ATS module."""
    __tablename__ = 'job_postings'

    id = db.Column(db.String(36), primary_key=True, default=generate_uuid)
    user_id = db.Column(
        db.String(36),
        db.ForeignKey('users.id', ondelete='CASCADE'),
        nullable=False,
        index=True,
    )

    # Core metadata
    title = db.Column(db.String(255), nullable=False)
    company_name = db.Column(db.String(255))
    company_website = db.Column(db.String(500))  # URL
    department = db.Column(db.String(100))
    location = db.Column(db.String(255))
    employment_type = db.Column(db.String(50))  # Full-time, Part-time, Contract
    seniority = db.Column(db.String(100))  # Junior, Mid, Senior, Lead, etc.

    # Description / JD content
    description_raw = db.Column(db.Text)   # source text / prompt
    description_html = db.Column(db.Text)  # rendered HTML/Markdown

    # Status: draft, published, closed
    status = db.Column(db.String(50), default='draft', index=True)

    application_deadline = db.Column(db.DateTime)
    salary_range_text = db.Column(db.String(255))

    # Public slug/id for application links (UUID string)
    public_id = db.Column(db.String(64), unique=True, index=True)

    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(
        db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )

    applications = db.relationship(
        'JobApplication',
        backref='job_posting',
        lazy='dynamic',
        cascade='all, delete-orphan',
    )

    def to_dict(self, include_description=False):
        return {
            'id': self.id,
            'public_id': self.public_id,
            'title': self.title,
            'company_name': self.company_name,
            'company_website': self.company_website,
            'department': self.department,
            'location': self.location,
            'employment_type': self.employment_type,
            'seniority': self.seniority,
            'status': self.status,
            'application_deadline': self.application_deadline.isoformat()
            if self.application_deadline
            else None,
            'salary_range_text': self.salary_range_text,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None,
            **(
                {
                    'description_raw': self.description_raw,
                    'description_html': self.description_html,
                }
                if include_description
                else {}
            ),
        }


class JobApplication(db.Model):
    """Applications submitted to a job posting."""
    __tablename__ = 'job_applications'

    id = db.Column(db.String(36), primary_key=True, default=generate_uuid)
    job_posting_id = db.Column(
        db.String(36),
        db.ForeignKey('job_postings.id', ondelete='CASCADE'),
        nullable=False,
        index=True,
    )

    # Optional link to internal Candidate once created
    candidate_id = db.Column(
        db.String(36), db.ForeignKey('candidates.id', ondelete='SET NULL')
    )

    # Applicant info
    full_name = db.Column(db.String(255), nullable=False)
    email = db.Column(db.String(255), nullable=False)
    phone = db.Column(db.String(50))
    location = db.Column(db.String(255))
    linkedin_url = db.Column(db.String(255))
    portfolio_url = db.Column(db.String(255))
    salary_expectations_text = db.Column(db.String(255))
    availability_text = db.Column(db.String(255))

    # Work authorization
    work_authorization_status = db.Column(db.String(100))
    requires_sponsorship = db.Column(db.Boolean)
    work_country = db.Column(db.String(100))

    # Resume / cover letter
    resume_filename = db.Column(db.String(255))
    resume_text = db.Column(db.Text)
    resume_file_id = db.Column(
        db.String(36), db.ForeignKey('resume_files.id', ondelete='SET NULL')
    )
    cover_letter_text = db.Column(db.Text)

    # Pipeline stage: applied, screened, interview, offer, hired, rejected
    stage = db.Column(db.String(50), default='applied', index=True)

    # AI screening
    ai_score = db.Column(db.Integer)
    ai_score_label = db.Column(db.String(50))
    ai_summary = db.Column(db.Text)
    ai_reasons = db.Column(db.Text)  # JSON array of bullet reasons

    # Manual review
    manual_status = db.Column(db.String(50))
    decision_notes = db.Column(db.Text)

    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(
        db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )

    # Relationship to candidate for convenience
    candidate = db.relationship('Candidate', backref='job_applications', lazy=True)

    def reasons_list(self):
        try:
            return json.loads(self.ai_reasons) if self.ai_reasons else []
        except Exception:
            return []

    @property
    def reference_progress(self):
        if self.candidate:
            return self.candidate.get_reference_progress()
        return {'completed': 0, 'total': 0}


    def to_dict(self):
        return {
            'id': self.id,
            'job_posting_id': self.job_posting_id,
            'candidate_id': self.candidate_id,
            'full_name': self.full_name,
            'email': self.email,
            'phone': self.phone,
            'location': self.location,
            'linkedin_url': self.linkedin_url,
            'portfolio_url': self.portfolio_url,
            'salary_expectations_text': self.salary_expectations_text,
            'availability_text': self.availability_text,
            'work_authorization_status': self.work_authorization_status,
            'requires_sponsorship': self.requires_sponsorship,
            'work_country': self.work_country,
            'resume_filename': self.resume_filename,
            'stage': self.stage,
            'ai_score': self.ai_score,
            'ai_score_label': self.ai_score_label,
            'ai_summary': self.ai_summary,
            'ai_reasons': self.reasons_list(),
            'manual_status': self.manual_status,
            'decision_notes': self.decision_notes,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None,
        }


class Job(db.Model):
    """Job history from candidate's resume."""
    __tablename__ = 'jobs'

    id = db.Column(db.String(36), primary_key=True, default=generate_uuid)
    candidate_id = db.Column(db.String(36), db.ForeignKey('candidates.id', ondelete='CASCADE'),
                             nullable=False, index=True)

    company = db.Column(db.String(255), nullable=False)
    title = db.Column(db.String(255))
    dates = db.Column(db.String(100))
    order = db.Column(db.Integer, default=0)

    # JSON arrays
    responsibilities = db.Column(db.Text)  # JSON array
    achievements = db.Column(db.Text)  # JSON array

    def to_dict(self):
        import json
        return {
            'id': self.id,
            'company': self.company,
            'title': self.title,
            'dates': self.dates,
            'responsibilities': json.loads(self.responsibilities) if self.responsibilities else [],
            'achievements': json.loads(self.achievements) if self.achievements else []
        }


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
        import json
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
        import json
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
        import json
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
        import json
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


class AuditLog(db.Model):
    """Audit log for security and compliance."""
    __tablename__ = 'audit_logs'

    id = db.Column(db.String(36), primary_key=True, default=generate_uuid)
    user_id = db.Column(db.String(36), db.ForeignKey('users.id', ondelete='SET NULL'), index=True)

    action = db.Column(db.String(100), nullable=False)
    resource_type = db.Column(db.String(50))  # candidate, reference, etc.
    resource_id = db.Column(db.String(36))
    details = db.Column(db.Text)  # JSON
    ip_address = db.Column(db.String(50))
    user_agent = db.Column(db.String(255))

    created_at = db.Column(db.DateTime, default=datetime.utcnow, index=True)

    __table_args__ = (
        Index('idx_audit_user_action', 'user_id', 'action'),
    )


# Event listeners for search vector updates
@event.listens_for(Candidate, 'before_insert')
@event.listens_for(Candidate, 'before_update')
def update_candidate_search_vector(mapper, connection, target):
    # Build search vector without accessing relationships to avoid session issues
    parts = [
        target.name or '',
        target.email or '',
        target.position or '',
        target.summary or '',
        target.skills or '',
        target.notes or '',
        target.resume_text or ''
    ]
    target.search_vector = ' '.join(parts).lower()
