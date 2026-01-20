"""
Company model for organizing jobs under company profiles.
"""
from datetime import datetime
from refcheck_app.models.base import db, generate_uuid


class Company(db.Model):
    """Company profile model."""
    __tablename__ = 'companies'

    id = db.Column(db.String(36), primary_key=True, default=generate_uuid)
    user_id = db.Column(
        db.String(36),
        db.ForeignKey('users.id', ondelete='CASCADE'),
        nullable=False,
        index=True,
    )

    # Company information
    name = db.Column(db.String(255), nullable=False)
    website = db.Column(db.String(500))  # URL
    description = db.Column(db.Text)
    logo_url = db.Column(db.String(500))  # Optional logo URL

    # Timestamps
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(
        db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )

    # Relationships
    jobs = db.relationship(
        'JobPosting',
        backref='company',
        lazy='dynamic',
        cascade='all, delete-orphan',
    )

    def to_dict(self, include_jobs=False):
        result = {
            'id': self.id,
            'name': self.name,
            'website': self.website,
            'description': self.description,
            'logo_url': self.logo_url,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None,
        }
        if include_jobs:
            result['jobs'] = [job.to_dict() for job in self.jobs.order_by('created_at desc')]
        return result
