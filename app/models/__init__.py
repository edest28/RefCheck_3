"""
Database models for RefCheck AI.
"""
from app.models.base import db, generate_uuid
from app.models.user import User
from app.models.candidate import Candidate, Job
from app.models.reference import (
    Reference, ResumeFile, ReferenceRequest,
    SurveyRequest, SurveyQuestion, SurveyResponse
)
from app.models.company import Company
from app.models.job_posting import JobPosting, JobApplication
from app.models.audit import AuditLog

__all__ = [
    'db',
    'generate_uuid',
    'User',
    'Candidate',
    'Job',
    'Reference',
    'ResumeFile',
    'ReferenceRequest',
    'SurveyRequest',
    'SurveyQuestion',
    'SurveyResponse',
    'Company',
    'JobPosting',
    'JobApplication',
    'AuditLog',
]
