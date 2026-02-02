"""
Pipeline column model for account-wide Kanban stages.
"""
from refcheck_app.models.base import db, generate_uuid


class PipelineColumn(db.Model):
    """Kanban pipeline column per user (account-wide)."""
    __tablename__ = 'pipeline_columns'

    id = db.Column(db.String(36), primary_key=True, default=generate_uuid)
    user_id = db.Column(
        db.String(36),
        db.ForeignKey('users.id', ondelete='CASCADE'),
        nullable=False,
        index=True,
    )
    slug = db.Column(db.String(64), nullable=False, index=True)
    label = db.Column(db.String(128), nullable=False)
    order = db.Column(db.Integer, nullable=False, default=0)
    is_action_triggering = db.Column(db.Boolean, nullable=False, default=False)

    __table_args__ = (
        db.UniqueConstraint('user_id', 'slug', name='uq_pipeline_columns_user_slug'),
    )

    def to_dict(self):
        return {
            'id': self.id,
            'slug': self.slug,
            'label': self.label,
            'order': self.order,
            'is_action_triggering': self.is_action_triggering,
        }
