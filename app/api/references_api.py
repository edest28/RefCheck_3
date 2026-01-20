"""
Reference API routes.
"""
from flask import Blueprint, request, jsonify
from flask_login import current_user
from app.models import db, Candidate, Reference, SurveyRequest, SurveyQuestion
from app.utils.auth import api_login_required, log_audit, verify_resource_ownership
from app.services.reference import get_survey_questions_for_reference
from app.config import Config
from datetime import datetime, timedelta
import secrets
import json

bp = Blueprint('references_api', __name__, url_prefix='/api/candidates/<candidate_id>/references')


@bp.route('', methods=['POST'])
@api_login_required
def create_reference(candidate_id):
    """Create a new reference for a candidate."""
    candidate = Candidate.query.get_or_404(candidate_id)

    if not verify_resource_ownership(candidate):
        return jsonify({'error': 'Access denied'}), 403

    data = request.json or {}
    job_id = data.get('job_id')

    reference = Reference(
        candidate_id=candidate.id,
        job_id=job_id,
        name=(data.get('name') or '').strip(),
        phone=(data.get('phone') or '').strip(),
        email=(data.get('email') or '').strip() or None,
        relationship=(data.get('relationship') or '').strip() or None,
        contact_method=data.get('contact_method', 'call_only')
    )

    db.session.add(reference)
    db.session.commit()

    log_audit(current_user.id, 'reference_created', 'reference', reference.id, {'candidate_id': candidate.id})
    return jsonify({'success': True, 'reference': reference.to_dict()}), 201


@bp.route('/<reference_id>', methods=['PATCH'])
@api_login_required
def update_reference(candidate_id, reference_id):
    """Update a reference."""
    candidate = Candidate.query.get_or_404(candidate_id)
    reference = Reference.query.get_or_404(reference_id)

    if not verify_resource_ownership(candidate) or reference.candidate_id != candidate.id:
        return jsonify({'error': 'Access denied'}), 403

    data = request.json or {}
    if 'name' in data:
        reference.name = (data.get('name') or '').strip()
    if 'phone' in data:
        reference.phone = (data.get('phone') or '').strip()
    if 'email' in data:
        reference.email = (data.get('email') or '').strip() or None
    if 'relationship' in data:
        reference.relationship = (data.get('relationship') or '').strip() or None
    if 'contact_method' in data:
        reference.contact_method = data.get('contact_method', 'call_only')

    db.session.commit()
    log_audit(current_user.id, 'reference_updated', 'reference', reference.id)
    return jsonify({'success': True, 'reference': reference.to_dict()})


@bp.route('/<reference_id>', methods=['DELETE'])
@api_login_required
def delete_reference(candidate_id, reference_id):
    """Delete a reference."""
    candidate = Candidate.query.get_or_404(candidate_id)
    reference = Reference.query.get_or_404(reference_id)

    if not verify_resource_ownership(candidate) or reference.candidate_id != candidate.id:
        return jsonify({'error': 'Access denied'}), 403

    db.session.delete(reference)
    db.session.commit()
    log_audit(current_user.id, 'reference_deleted', 'reference', reference_id)
    return jsonify({'success': True})
