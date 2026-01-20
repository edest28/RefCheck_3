"""
JobPosting and JobApplication models for ATS functionality.
"""
import json
from datetime import datetime
from refcheck_app.models.base import db, generate_uuid


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

    # Company relationship
    company_id = db.Column(
        db.String(36),
        db.ForeignKey('companies.id', ondelete='SET NULL'),
        nullable=True,
        index=True,
    )

    # Core metadata
    title = db.Column(db.String(255), nullable=False)
    company_name = db.Column(db.String(255))  # Keep for backward compatibility
    company_website = db.Column(db.String(500))  # Keep for backward compatibility
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
