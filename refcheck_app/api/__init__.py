"""
API blueprints for RefCheck AI.
"""
from refcheck_app.api import (
    candidates_api,
    references_api,
    calls_api,
    jobs_api,
    applications_api,
    settings_api,
    search_api
)

__all__ = [
    'candidates_api',
    'references_api',
    'calls_api',
    'jobs_api',
    'applications_api',
    'settings_api',
    'search_api'
]
