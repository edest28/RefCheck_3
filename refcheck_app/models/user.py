"""
User model for authentication and tenant isolation.
"""
import uuid
from datetime import datetime
from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash
from refcheck_app.models.base import db


class User(UserMixin, db.Model):
    """User model for authentication and tenant isolation."""
    __tablename__ = 'users'

    id = db.Column(db.String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
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
