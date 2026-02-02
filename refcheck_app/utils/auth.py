"""
Authentication and authorization utilities for RefCheck AI.
Implements secure session management, password validation, and access control.
"""
import re
import json
from functools import wraps
from flask import request, jsonify
from flask_login import current_user
from refcheck_app.models import db, AuditLog


def validate_email(email):
    """Validate email format."""
    pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
    return bool(re.match(pattern, email))


def validate_password(password):
    """
    Validate password strength.
    Returns (is_valid, error_message)
    """
    if len(password) < 8:
        return False, "Password must be at least 8 characters long"
    if not re.search(r'[A-Z]', password):
        return False, "Password must contain at least one uppercase letter"
    if not re.search(r'[a-z]', password):
        return False, "Password must contain at least one lowercase letter"
    if not re.search(r'\d', password):
        return False, "Password must contain at least one number"
    return True, None


def log_audit(user_id, action, resource_type=None, resource_id=None, details=None):
    """Create an audit log entry."""
    try:
        from flask import has_request_context
        ip_address = None
        user_agent = None
        if has_request_context():
            try:
                ip_address = request.remote_addr if request else None
                user_agent = request.user_agent.string[:255] if request and request.user_agent else None
            except:
                pass
        
        log = AuditLog(
            user_id=user_id,
            action=action,
            resource_type=resource_type,
            resource_id=resource_id,
            details=json.dumps(details) if details else None,
            ip_address=ip_address,
            user_agent=user_agent
        )
        db.session.add(log)
        db.session.commit()
    except Exception as e:
        import traceback
        print(f"Audit log error: {e}")
        print(traceback.format_exc())


def api_login_required(f):
    """Decorator for API endpoints that require authentication."""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        # Debug: Check session and user state
        from flask import session
        import logging
        logger = logging.getLogger(__name__)
        
        # Log session info for debugging
        logger.info(f"API auth check - session keys: {list(session.keys())}, user_id in session: {session.get('_user_id', 'NOT FOUND')}")
        logger.info(f"current_user: {current_user}, is_authenticated: {current_user.is_authenticated}")
        
        if not current_user.is_authenticated:
            logger.warning(f"Unauthenticated API request to {request.path} - session: {dict(session)}")
            return jsonify({'error': 'Authentication required'}), 401
        return f(*args, **kwargs)
    return decorated_function


def get_current_user_id():
    """Get the current authenticated user's ID."""
    if current_user.is_authenticated:
        return current_user.id
    return None


def verify_resource_ownership(resource, user_id=None):
    """
    Verify that the current user owns the resource.
    Returns True if authorized, False otherwise.
    """
    if user_id is None:
        user_id = get_current_user_id()
    
    if user_id is None:
        return False
    
    # Check based on resource type
    if hasattr(resource, 'user_id'):
        return resource.user_id == user_id
    elif hasattr(resource, 'candidate'):
        return resource.candidate.user_id == user_id
    elif hasattr(resource, 'owner'):
        return resource.owner.id == user_id
    
    return False


def ownership_required(model_class, id_param='id'):
    """
    Decorator that verifies ownership of a resource.
    Use for API endpoints that access specific resources.
    """
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            if not current_user.is_authenticated:
                return jsonify({'error': 'Authentication required'}), 401
            
            resource_id = kwargs.get(id_param)
            if not resource_id:
                return jsonify({'error': 'Resource ID required'}), 400
            
            resource = model_class.query.get(resource_id)
            if not resource:
                return jsonify({'error': 'Resource not found'}), 404
            
            if not verify_resource_ownership(resource):
                log_audit(
                    current_user.id,
                    'unauthorized_access_attempt',
                    model_class.__tablename__,
                    resource_id
                )
                return jsonify({'error': 'Access denied'}), 403
            
            return f(*args, **kwargs)
        return decorated_function
    return decorator


class TenantFilter:
    """
    Mixin for automatically filtering queries by current user.
    Usage: Model.query.filter_by_tenant()
    """
    
    @classmethod
    def for_user(cls, user_id=None):
        """Get query filtered by user."""
        if user_id is None:
            user_id = get_current_user_id()
        
        if hasattr(cls, 'user_id'):
            return cls.query.filter_by(user_id=user_id)
        else:
            raise AttributeError(f"{cls.__name__} does not support tenant filtering")


def get_user_candidates():
    """Get all candidates for the current user."""
    from refcheck_app.models import Candidate
    if not current_user.is_authenticated:
        return []
    return Candidate.query.filter_by(user_id=current_user.id)


def get_user_settings():
    """Get current user's settings."""
    if not current_user.is_authenticated:
        return {}
    return {
        'sms_template': current_user.sms_template,
        'timezone': current_user.timezone,
        'send_rejection_email': bool(current_user.send_rejection_email),
        'rejection_email_template': current_user.rejection_email_template or '',
        'has_vapi': bool(current_user.vapi_api_key and current_user.vapi_phone_number_id),
        'has_twilio': bool(current_user.twilio_account_sid and current_user.twilio_auth_token),
        'first_name': current_user.first_name,
        'last_name': current_user.last_name,
        'email': current_user.email,
        'company_name': current_user.company_name,
    }
