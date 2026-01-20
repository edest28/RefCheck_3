"""
Phone call and SMS API routes.
"""
from flask import Blueprint, request, jsonify
from flask_login import current_user
from refcheck_app.models import db, Candidate, Reference, Job
from refcheck_app.utils.auth import api_login_required, log_audit, verify_resource_ownership
from refcheck_app.services.communication.vapi import initiate_vapi_call, get_vapi_call_status
from refcheck_app.services.communication.twilio import send_sms, format_sms_message
from refcheck_app.utils.constants import DEFAULT_SMS_TEMPLATE
from datetime import datetime

bp = Blueprint('calls_api', __name__, url_prefix='/api')


@bp.route('/start-reference-check', methods=['POST'])
@api_login_required
def start_reference_check():
    """Start a reference check call."""
    data = request.json or {}
    reference_id = data.get('reference_id')
    candidate_id = data.get('candidate_id')
    job_id = data.get('job_id')

    reference = Reference.query.get_or_404(reference_id)
    candidate = Candidate.query.get_or_404(candidate_id)
    job = Job.query.get_or_404(job_id)

    if not verify_resource_ownership(candidate) or reference.candidate_id != candidate.id:
        return jsonify({'error': 'Access denied'}), 403

    result = initiate_vapi_call(reference, candidate, job, current_user)

    if 'error' in result:
        return jsonify(result), 500

    reference.call_id = result.get('call_id')
    reference.status = 'calling'
    db.session.commit()

    log_audit(current_user.id, 'reference_call_initiated', 'reference', reference.id)
    return jsonify({'success': True, 'call_id': reference.call_id})


@bp.route('/check-status/<check_id>', methods=['GET'])
@api_login_required
def check_status(check_id):
    """Check the status of a reference check call."""
    reference = Reference.query.filter_by(call_id=check_id).first_or_404()

    if not verify_resource_ownership(reference.candidate):
        return jsonify({'error': 'Access denied'}), 403

    call_data = get_vapi_call_status(check_id, current_user)

    if 'error' in call_data:
        return jsonify(call_data), 500

    # Update reference status based on call data
    status = call_data.get('status', '')
    if status == 'ended':
        reference.status = 'completed'
        reference.transcript = call_data.get('transcript', '')
        db.session.commit()

    return jsonify({
        'status': reference.status,
        'transcript': reference.transcript,
        'call_data': call_data
    })


@bp.route('/candidates/<candidate_id>/references/<reference_id>/send-sms', methods=['POST'])
@api_login_required
def send_reference_sms(candidate_id, reference_id):
    """Send SMS to a reference."""
    candidate = Candidate.query.get_or_404(candidate_id)
    reference = Reference.query.get_or_404(reference_id)

    if not verify_resource_ownership(candidate) or reference.candidate_id != candidate.id:
        return jsonify({'error': 'Access denied'}), 403

    template = current_user.sms_template or DEFAULT_SMS_TEMPLATE
    message = format_sms_message(template, candidate.name)

    result = send_sms(reference.phone, message, current_user)

    if not result.get('success'):
        return jsonify(result), 500

    reference.sms_sent = True
    reference.sms_sent_at = datetime.utcnow()
    db.session.commit()

    log_audit(current_user.id, 'reference_sms_sent', 'reference', reference.id)
    return jsonify({'success': True})
