"""
Authentication view routes.
"""
from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import login_user, logout_user, login_required, current_user
from datetime import datetime
from app.models import db, User
from app.utils.auth import validate_email, validate_password, log_audit
from app.utils.constants import DEFAULT_SMS_TEMPLATE

bp = Blueprint('auth', __name__)


@bp.route('/register', methods=['GET', 'POST'])
def register():
    """User registration."""
    if current_user.is_authenticated:
        return redirect(url_for('dashboard.dashboard'))

    if request.method == 'POST':
        email = request.form.get('email', '').strip().lower()
        password = request.form.get('password', '')
        confirm_password = request.form.get('confirm_password', '')
        first_name = request.form.get('first_name', '').strip()
        last_name = request.form.get('last_name', '').strip()
        company_name = request.form.get('company_name', '').strip()

        errors = []

        if not email or not validate_email(email):
            errors.append("Please enter a valid email address")
        elif User.query.filter_by(email=email).first():
            errors.append("An account with this email already exists")

        if not first_name:
            errors.append("First name is required")
        if not last_name:
            errors.append("Last name is required")

        is_valid, password_error = validate_password(password)
        if not is_valid:
            errors.append(password_error)
        elif password != confirm_password:
            errors.append("Passwords do not match")

        if errors:
            for error in errors:
                flash(error, 'error')
            return render_template('auth/register.html')

        # Create user
        try:
            user = User(
                email=email,
                first_name=first_name,
                last_name=last_name,
                company_name=company_name,
                sms_template=DEFAULT_SMS_TEMPLATE
            )
            user.set_password(password)

            db.session.add(user)
            db.session.commit()

            # Try to log audit, but don't fail registration if it fails
            try:
                log_audit(user.id, 'user_registered')
            except Exception as audit_error:
                print(f"Audit log error (non-critical): {audit_error}")

            login_user(user)
            flash('Welcome to RefCheck AI!', 'success')
            return redirect(url_for('dashboard.dashboard'))
        except Exception as e:
            db.session.rollback()
            import traceback
            error_msg = str(e)
            print(f"Registration error: {error_msg}")
            print(traceback.format_exc())
            # Show more specific error message if possible
            if 'UNIQUE constraint' in error_msg or 'duplicate' in error_msg.lower():
                flash('An account with this email already exists.', 'error')
            else:
                flash(f'An error occurred while creating your account: {error_msg}', 'error')
            return render_template('auth/register.html')

    return render_template('auth/register.html')


@bp.route('/login', methods=['GET', 'POST'])
def login():
    """User login."""
    if current_user.is_authenticated:
        return redirect(url_for('dashboard.dashboard'))

    if request.method == 'POST':
        email = request.form.get('email', '').strip().lower()
        password = request.form.get('password', '')
        remember = request.form.get('remember') == 'on'

        user = User.query.filter_by(email=email).first()

        if user and user.check_password(password):
            user.last_login_at = datetime.utcnow()
            db.session.commit()

            login_user(user, remember=remember)
            log_audit(user.id, 'user_login')

            next_page = request.args.get('next')
            if next_page and next_page.startswith('/'):
                return redirect(next_page)
            return redirect(url_for('dashboard.dashboard'))

        flash('Invalid email or password', 'error')
        log_audit(None, 'failed_login', details={'email': email})

    return render_template('auth/login.html')


@bp.route('/logout')
@login_required
def logout():
    """User logout."""
    log_audit(current_user.id, 'user_logout')
    logout_user()
    flash('You have been logged out', 'info')
    return redirect(url_for('auth.login'))
