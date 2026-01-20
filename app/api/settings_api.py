"""
Settings API routes.
"""
from flask import Blueprint, request, jsonify
from flask_login import current_user
from app.models import db
from app.utils.auth import api_login_required, log_audit, validate_password
from app.utils.auth import get_user_settings

bp = Blueprint('settings_api', __name__, url_prefix='/api/settings')


@bp.route('', methods=['GET'])
@api_login_required
def get_settings():
    """Get current user settings."""
    return jsonify(get_user_settings())


@bp.route('', methods=['PATCH'])
@api_login_required
def update_settings():
    """Update user settings."""
    data = request.json or {}

    if 'sms_template' in data:
        current_user.sms_template = (data.get('sms_template') or '').strip() or None
    if 'timezone' in data:
        current_user.timezone = (data.get('timezone') or '').strip() or 'America/New_York'
    if 'company_name' in data:
        current_user.company_name = (data.get('company_name') or '').strip() or None

    # API keys (for user-specific credentials)
    if 'vapi_api_key' in data:
        current_user.vapi_api_key = (data.get('vapi_api_key') or '').strip() or None
    if 'vapi_phone_number_id' in data:
        current_user.vapi_phone_number_id = (data.get('vapi_phone_number_id') or '').strip() or None
    if 'twilio_account_sid' in data:
        current_user.twilio_account_sid = (data.get('twilio_account_sid') or '').strip() or None
    if 'twilio_auth_token' in data:
        current_user.twilio_auth_token = (data.get('twilio_auth_token') or '').strip() or None
    if 'twilio_phone_number' in data:
        current_user.twilio_phone_number = (data.get('twilio_phone_number') or '').strip() or None

    db.session.commit()
    log_audit(current_user.id, 'settings_updated')
    return jsonify({'success': True, 'settings': get_user_settings()})


@bp.route('/password', methods=['POST'])
@api_login_required
def update_password():
    """Update user password."""
    data = request.json or {}
    current_password = data.get('current_password', '')
    new_password = data.get('new_password', '')

    if not current_user.check_password(current_password):
        return jsonify({'error': 'Current password is incorrect'}), 400

    is_valid, password_error = validate_password(new_password)
    if not is_valid:
        return jsonify({'error': password_error}), 400

    current_user.set_password(new_password)
    db.session.commit()

    log_audit(current_user.id, 'password_changed')
    return jsonify({'success': True})
