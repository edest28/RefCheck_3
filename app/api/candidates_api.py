"""
Candidate API routes.
"""
from flask import Blueprint, request, jsonify
from flask_login import current_user
from sqlalchemy import func
from app.models import db, Candidate, Reference, Job, ResumeFile
from app.utils.auth import api_login_required, log_audit, verify_resource_ownership
from app.services.candidate import search_candidates, create_candidate_from_resume
from app.services.file_processing import extract_text_from_pdf
from app.services.ai.resume_parser import parse_resume_with_claude
from app.config import Config
from werkzeug.utils import secure_filename
from app.utils.constants import ALLOWED_EXTENSIONS
import json

bp = Blueprint('candidates_api', __name__, url_prefix='/api/candidates')


@bp.route('', methods=['GET'])
@api_login_required
def list_candidates():
    """List all candidates for the current user."""
    query = request.args.get('q', '').strip()
    status = request.args.get('status', '').strip() or None

    if query:
        candidates = search_candidates(current_user.id, query, status)
        if status == 'active':
            candidates = [c for c in candidates if c.status != 'archived']
    else:
        base_query = Candidate.query.filter_by(user_id=current_user.id)
        if status == 'active':
            base_query = base_query.filter(Candidate.status != 'archived')
        elif status:
            base_query = base_query.filter_by(status=status)
        candidates = base_query.order_by(Candidate.updated_at.desc()).limit(50).all()

    # Get candidate IDs for batch query
    candidate_ids = [c.id for c in candidates]

    # Efficient single query to get reference counts for all candidates
    ref_counts = db.session.query(
        Reference.candidate_id,
        func.count(Reference.id).label('total'),
        func.sum(db.case((Reference.status == 'completed', 1), else_=0)).label('completed'),
        func.avg(db.case((Reference.status == 'completed', Reference.score), else_=None)).label('avg_score')
    ).filter(
        Reference.candidate_id.in_(candidate_ids)
    ).group_by(Reference.candidate_id).all()

    # Build lookup dict
    ref_lookup = {r.candidate_id: {
        'total': r.total,
        'completed': int(r.completed or 0),
        'avg_score': round(r.avg_score) if r.avg_score else None
    } for r in ref_counts}

    # Build response
    result = []
    for c in candidates:
        ref_data = ref_lookup.get(c.id, {'total': 0, 'completed': 0, 'avg_score': None})

        # Calculate signal from avg score
        avg_score = ref_data['avg_score']
        if avg_score is not None:
            if avg_score >= 75:
                signal = {'score': avg_score, 'label': 'Strong', 'color': 'green'}
            elif avg_score >= 55:
                signal = {'score': avg_score, 'label': 'Mixed', 'color': 'yellow'}
            else:
                signal = {'score': avg_score, 'label': 'Concern', 'color': 'red'}
        else:
            signal = {'score': None, 'label': 'View', 'color': 'gray'}

        result.append({
            'id': c.id,
            'name': c.name,
            'position': c.position,
            'status': c.status,
            'reference_progress': {'completed': ref_data['completed'], 'total': ref_data['total']},
            'signal': signal,
            'created_at': c.created_at.isoformat() if c.created_at else None,
            'updated_at': c.updated_at.isoformat() if c.updated_at else None
        })

    return jsonify(result)


@bp.route('', methods=['POST'])
@api_login_required
def create_candidate():
    """Create a new candidate from uploaded resume."""
    if 'file' not in request.files:
        return jsonify({'error': 'No file provided'}), 400

    file = request.files['file']
    if not file or not file.filename:
        return jsonify({'error': 'No file selected'}), 400

    filename = secure_filename(file.filename)
    if '.' not in filename or filename.rsplit('.', 1)[1].lower() not in ALLOWED_EXTENSIONS:
        return jsonify({'error': 'Invalid file type'}), 400

    try:
        file_data = file.read()
        resume_text = extract_text_from_pdf(file_data) if filename.endswith('.pdf') else file_data.decode('utf-8', errors='ignore')

        if not resume_text:
            return jsonify({'error': 'Could not extract text from file'}), 400

        parsed_data = parse_resume_with_claude(resume_text, Config.ANTHROPIC_API_KEY)
        if not parsed_data:
            return jsonify({'error': 'Failed to parse resume'}), 500

        candidate = create_candidate_from_resume(
            current_user.id,
            parsed_data,
            resume_text=resume_text,
            resume_filename=filename
        )

        log_audit(current_user.id, 'candidate_created', 'candidate', candidate.id)
        return jsonify({'success': True, 'candidate': candidate.to_dict()}), 201

    except Exception as e:
        db.session.rollback()
        import traceback
        print(f"Error creating candidate: {e}")
        print(traceback.format_exc())
        return jsonify({'error': str(e)}), 500


@bp.route('/<candidate_id>', methods=['GET'])
@api_login_required
def get_candidate(candidate_id):
    """Get candidate details."""
    candidate = Candidate.query.get_or_404(candidate_id)

    if not verify_resource_ownership(candidate):
        return jsonify({'error': 'Access denied'}), 403

    return jsonify(candidate.to_dict(include_jobs=True, include_references=True))


@bp.route('/<candidate_id>/resume', methods=['GET'])
@api_login_required
def get_candidate_resume(candidate_id):
    """Get candidate resume text."""
    candidate = Candidate.query.get_or_404(candidate_id)

    if not verify_resource_ownership(candidate):
        return jsonify({'error': 'Access denied'}), 403

    return jsonify({
        'resume_text': candidate.resume_text,
        'resume_filename': candidate.resume_filename
    })


@bp.route('/<candidate_id>', methods=['PATCH'])
@api_login_required
def update_candidate(candidate_id):
    """Update candidate information."""
    candidate = Candidate.query.get_or_404(candidate_id)

    if not verify_resource_ownership(candidate):
        return jsonify({'error': 'Access denied'}), 403

    data = request.json or {}
    if 'name' in data:
        candidate.name = (data.get('name') or '').strip()
    if 'email' in data:
        candidate.email = (data.get('email') or '').strip() or None
    if 'phone' in data:
        candidate.phone = (data.get('phone') or '').strip() or None
    if 'position' in data:
        candidate.position = (data.get('position') or '').strip() or None
    if 'status' in data:
        candidate.status = (data.get('status') or '').strip()
    if 'notes' in data:
        candidate.notes = (data.get('notes') or '').strip() or None

    db.session.commit()
    log_audit(current_user.id, 'candidate_updated', 'candidate', candidate.id)
    return jsonify({'success': True, 'candidate': candidate.to_dict()})


@bp.route('/<candidate_id>', methods=['DELETE'])
@api_login_required
def delete_candidate(candidate_id):
    """Delete a candidate."""
    candidate = Candidate.query.get_or_404(candidate_id)

    if not verify_resource_ownership(candidate):
        return jsonify({'error': 'Access denied'}), 403

    db.session.delete(candidate)
    db.session.commit()
    log_audit(current_user.id, 'candidate_deleted', 'candidate', candidate_id)
    return jsonify({'success': True})
