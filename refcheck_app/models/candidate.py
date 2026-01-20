"""
Candidate and Job models.
"""
import uuid
import json
from datetime import datetime
from sqlalchemy import Index, event
from refcheck_app.models.base import db, generate_uuid


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
        return {
            'id': self.id,
            'company': self.company,
            'title': self.title,
            'dates': self.dates,
            'responsibilities': json.loads(self.responsibilities) if self.responsibilities else [],
            'achievements': json.loads(self.achievements) if self.achievements else []
        }


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
