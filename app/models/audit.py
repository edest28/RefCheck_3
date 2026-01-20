"""
AuditLog model for security and compliance.
"""
from datetime import datetime
from sqlalchemy import Index
from app.models.base import db, generate_uuid


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
