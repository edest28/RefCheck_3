"""
Job application API routes.
"""
from flask import Blueprint, request, jsonify
from flask_login import current_user
from datetime import datetime
import json
from app.models import db, JobPosting, JobApplication, Candidate
from app.utils.auth import api_login_required, log_audit
from app.services.ai.application_screener import analyze_application_with_claude
from app.services.ai.resume_parser import parse_resume_with_claude
from app.services.candidate import create_candidate_from_resume
from app.config import Config

bp = Blueprint('applications_api', __name__, url_prefix='/api/jobs/<job_id>/applications')


@bp.route('/<app_id>/ai-screen', methods=['POST'])
@api_login_required
def ai_screen_application(job_id, app_id):
    posting = JobPosting.query.get_or_404(job_id)
    if posting.user_id != current_user.id:
        return jsonify({'error': 'Access denied'}), 403

    application = JobApplication.query.get_or_404(app_id)
    if application.job_posting_id != posting.id:
        return jsonify({'error': 'Application not found'}), 404

    analysis = analyze_application_with_claude(posting, application, Config.ANTHROPIC_API_KEY)
    if not analysis:
        return jsonify({'error': 'Failed to screen application'}), 500

    application.ai_score = analysis.get('score')
    application.ai_score_label = analysis.get('score_label')
    application.ai_summary = analysis.get('summary')
    reasons = (
        analysis.get('strengths', [])
        + [f"Risk: {x}" for x in (analysis.get('risks', []) or [])]
        + [f"Missing: {x}" for x in (analysis.get('missing_requirements', []) or [])]
    )
    application.ai_reasons = json.dumps(reasons)
    application.updated_at = datetime.utcnow()
    db.session.commit()

    log_audit(current_user.id, 'job_application_screened_ai', 'job_application', application.id, {
        'job_posting_id': posting.id,
        'score': application.ai_score,
    })

    return jsonify({'success': True, 'application': application.to_dict()})


@bp.route('/ai-screen-all', methods=['POST'])
@api_login_required
def ai_screen_all_applications(job_id):
    posting = JobPosting.query.get_or_404(job_id)
    if posting.user_id != current_user.id:
        return jsonify({'error': 'Access denied'}), 403

    apps = JobApplication.query.filter_by(job_posting_id=posting.id, stage='applied').all()
    results = []
    for application in apps:
        analysis = analyze_application_with_claude(posting, application, Config.ANTHROPIC_API_KEY)
        if not analysis:
            results.append({'id': application.id, 'error': 'screen_failed'})
            continue
        application.ai_score = analysis.get('score')
        application.ai_score_label = analysis.get('score_label')
        application.ai_summary = analysis.get('summary')
        reasons = (
            analysis.get('strengths', [])
            + [f"Risk: {x}" for x in (analysis.get('risks', []) or [])]
            + [f"Missing: {x}" for x in (analysis.get('missing_requirements', []) or [])]
        )
        application.ai_reasons = json.dumps(reasons)
        application.updated_at = datetime.utcnow()
        results.append({'id': application.id, 'score': application.ai_score})

    db.session.commit()
    log_audit(current_user.id, 'job_applications_screened_ai_bulk', details={'job_posting_id': posting.id, 'count': len(apps)})
    return jsonify({'success': True, 'results': results})


@bp.route('', methods=['GET'])
@api_login_required
def list_job_applications(job_id):
    posting = JobPosting.query.get_or_404(job_id)
    if posting.user_id != current_user.id:
        return jsonify({'error': 'Access denied'}), 403

    stage = (request.args.get('stage') or '').strip() or None
    q = JobApplication.query.filter_by(job_posting_id=posting.id)
    if stage:
        q = q.filter_by(stage=stage)
    applications = q.order_by(JobApplication.ai_score.desc().nullslast(), JobApplication.created_at.desc()).all()
    return jsonify([a.to_dict() for a in applications])


@bp.route('/<app_id>', methods=['PATCH'])
@api_login_required
def update_job_application(job_id, app_id):
    posting = JobPosting.query.get_or_404(job_id)
    if posting.user_id != current_user.id:
        return jsonify({'error': 'Access denied'}), 403

    application = JobApplication.query.get_or_404(app_id)
    if application.job_posting_id != posting.id:
        return jsonify({'error': 'Application not found'}), 404

    data = request.json or {}
    if 'stage' in data:
        new_stage = (data.get('stage') or '').strip()
        allowed = {'applied', 'screened', 'interview', 'offer', 'hired', 'rejected'}
        if new_stage not in allowed:
            return jsonify({'error': 'Invalid stage'}), 400
        application.stage = new_stage

        # When hired, create/link a Candidate for downstream reference checks
        if new_stage == 'hired' and not application.candidate_id:
            # Best-effort parse resume into Candidate/Jobs
            parsed = None
            if application.resume_text:
                parsed = parse_resume_with_claude(application.resume_text, Config.ANTHROPIC_API_KEY) or {}
            else:
                parsed = {}

            if not parsed.get('candidate_name'):
                parsed['candidate_name'] = application.full_name
            if not parsed.get('email'):
                parsed['email'] = application.email
            if not parsed.get('phone') and application.phone:
                parsed['phone'] = application.phone

            candidate = create_candidate_from_resume(
                current_user.id,
                parsed,
                resume_text=application.resume_text or '',
                resume_filename=application.resume_filename or '',
            )
            # Attach core metadata
            candidate.position = posting.title
            candidate.email = candidate.email or application.email
            candidate.phone = candidate.phone or application.phone
            db.session.commit()

            application.candidate_id = candidate.id
            db.session.commit()

            log_audit(current_user.id, 'application_converted_to_candidate', 'candidate', candidate.id, {
                'job_posting_id': posting.id,
                'job_application_id': application.id,
            })

    if 'manual_status' in data:
        application.manual_status = (data.get('manual_status') or '').strip() or None
    if 'decision_notes' in data:
        application.decision_notes = (data.get('decision_notes') or '').strip() or None

    application.updated_at = datetime.utcnow()
    db.session.commit()

    log_audit(current_user.id, 'job_application_updated', 'job_application', application.id, {
        'job_posting_id': posting.id,
        'stage': application.stage,
    })

    return jsonify({'success': True, 'application': application.to_dict()})
