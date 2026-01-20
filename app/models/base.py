"""
Base database setup for RefCheck AI.
"""
from flask_sqlalchemy import SQLAlchemy
import uuid

db = SQLAlchemy()


def generate_uuid():
    """Generate a UUID string for primary keys."""
    return str(uuid.uuid4())
