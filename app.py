"""
RefCheck AI - Production-ready multi-tenant reference verification system.
"""

import os
import json
import secrets
from datetime import datetime, timedelta
from flask import Flask, request, jsonify, render_template, redirect, url_for, flash, session
from flask_login import login_user, logout_user, login_required, current_user
from flask_migrate import Migrate
from werkzeug.utils import secure_filename
from dotenv import load_dotenv

from models import db, User, Candidate, Job, Reference, ResumeFile, AuditLog, ReferenceRequest, SurveyRequest, SurveyQuestion, SurveyResponse
from auth import (
    login_manager, validate_email, validate_password, log_audit,
    api_login_required, verify_resource_ownership, get_user_settings
)
from services import (
    extract_text_from_pdf, parse_resume_with_claude, analyze_transcript_with_claude,
    calculate_verification_score, generate_reference_questions, build_assistant_prompt,
    initiate_vapi_call, get_vapi_call_status, send_sms, format_sms_message,
    create_candidate_from_resume, search_candidates, DEFAULT_SMS_TEMPLATE,
    send_reference_request_email, send_reference_confirmation_email, send_reference_reminder_email,
    get_survey_questions_for_reference, analyze_survey_responses, send_survey_email, send_survey_confirmation_email,
    send_callback_request_sms, parse_callback_time_with_claude, send_callback_confirmation_sms,
    send_callback_final_confirmation_sms, send_timezone_clarification_sms, add_to_sms_conversation,
    ROLE_CATEGORIES, STANDARDIZED_SURVEY_QUESTIONS, generate_ai_survey_questions
)

load_dotenv()

# Initialize Flask app
app = Flask(__name__)
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', os.urandom(32).hex())
app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get(
    'DATABASE_URL', 
    'sqlite:///refcheck.db'
)
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['SQLALCHEMY_ENGINE_OPTIONS'] = {
    'pool_pre_ping': True,
    'pool_recycle': 300,
}
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16MB

# Handle PostgreSQL URL format from Heroku/Railway
if app.config['SQLALCHEMY_DATABASE_URI'].startswith('postgres://'):
    app.config['SQLALCHEMY_DATABASE_URI'] = app.config['SQLALCHEMY_DATABASE_URI'].replace(
        'postgres://', 'postgresql://', 1
    )

# Initialize extensions
db.init_app(app)
migrate = Migrate(app, db)
login_manager.init_app(app)

# Global API keys (shared across all users)
ANTHROPIC_API_KEY = os.environ.get('ANTHROPIC_API_KEY')
VAPI_API_KEY = os.environ.get('VAPI_API_KEY')
VAPI_PHONE_NUMBER_ID = os.environ.get('VAPI_PHONE_NUMBER_ID')
TWILIO_ACCOUNT_SID = os.environ.get('TWILIO_ACCOUNT_SID')
TWILIO_AUTH_TOKEN = os.environ.get('TWILIO_AUTH_TOKEN')
TWILIO_PHONE_NUMBER = os.environ.get('TWILIO_PHONE_NUMBER')
RESEND_API_KEY = os.environ.get('RESEND_API_KEY')

ALLOWED_EXTENSIONS = {'pdf', 'txt', 'doc', 'docx'}

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS


# Custom Jinja filter for JSON parsing
@app.template_filter('from_json')
def from_json_filter(value):
    if not value:
        return []
    try:
        return json.loads(value)
    except:
        return []


# ============================================================================
# Database initialization
# ============================================================================

@app.before_request
def ensure_tables():
    """Ensure database tables exist."""
    if not hasattr(app, '_db_initialized'):
        with app.app_context():
            db.create_all()
        app._db_initialized = True


# ============================================================================
# Authentication Routes
# ============================================================================

@app.route('/register', methods=['GET', 'POST'])
def register():
    """User registration."""
    if current_user.is_authenticated:
        return redirect(url_for('dashboard'))

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
            return render_template('register.html')

        # Create user
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

        log_audit(user.id, 'user_registered')

        login_user(user)
        flash('Welcome to RefCheck AI!', 'success')
        return redirect(url_for('dashboard'))

    return render_template('register.html')


@app.route('/login', methods=['GET', 'POST'])
def login():
    """User login."""
    if current_user.is_authenticated:
        return redirect(url_for('dashboard'))

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
            return redirect(url_for('dashboard'))

        flash('Invalid email or password', 'error')
        log_audit(None, 'failed_login', details={'email': email})

    return render_template('login.html')


@app.route('/logout')
@login_required
def logout():
    """User logout."""
    log_audit(current_user.id, 'user_logout')
    logout_user()
    flash('You have been logged out', 'info')
    return redirect(url_for('login'))


# ============================================================================
# Page Routes
# ============================================================================

@app.route('/')
def index():
    """Landing page or dashboard."""
    if current_user.is_authenticated:
        return redirect(url_for('dashboard'))
    return render_template('login.html')


@app.route('/health')
def health():
    """Health check endpoint for deployment."""
    return jsonify({'status': 'healthy'}), 200


@app.route('/dashboard')
@login_required
def dashboard():
    """Main dashboard."""
    return render_template('dashboard.html')


@app.route('/candidate/new')
@login_required
def new_candidate():
    """New candidate intake page."""
    sms_template = current_user.sms_template or DEFAULT_SMS_TEMPLATE
    return render_template('new_candidate.html', sms_template=sms_template)


@app.route('/candidate/<candidate_id>')
@login_required
def view_candidate(candidate_id):
    """View candidate details."""
    candidate = Candidate.query.get_or_404(candidate_id)

    if candidate.user_id != current_user.id:
        flash('Access denied', 'error')
        return redirect(url_for('dashboard'))

    return render_template('candidate_detail.html', candidate_id=candidate_id)


@app.route('/settings')
@login_required
def settings():
    """User settings page."""
    return render_template('settings.html')


# ============================================================================
# API Routes - Candidates
# ============================================================================

@app.route('/api/candidates', methods=['GET'])
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
    from sqlalchemy import func
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


@app.route('/api/candidates', methods=['POST'])
@api_login_required
def create_candidate():
    """Create a new candidate from uploaded resume."""

    if 'file' not in request.files:
        return jsonify({'error': 'No file provided'}), 400

    file = request.files['file']
    position = request.form.get('position', '').strip()
    candidate_name = request.form.get('candidate_name', '').strip()
    sms_template = request.form.get('sms_template', current_user.sms_template or DEFAULT_SMS_TEMPLATE)

    if file.filename == '':
        return jsonify({'error': 'No file selected'}), 400

    if not allowed_file(file.filename):
        return jsonify({'error': 'Invalid file type. Allowed: PDF, DOC, DOCX, TXT'}), 400

    try:
        # Read file
        file_data = file.read()
        filename = secure_filename(file.filename)

        # Extract text
        if filename.lower().endswith('.pdf'):
            resume_text = extract_text_from_pdf(file_data)
            if not resume_text:
                return jsonify({'error': 'Could not extract text from PDF'}), 400
        else:
            resume_text = file_data.decode('utf-8', errors='ignore')

        # Parse with Claude
        api_key = ANTHROPIC_API_KEY
        parsed = parse_resume_with_claude(resume_text, api_key)

        if not parsed:
            return jsonify({'error': 'Failed to parse resume'}), 500

        if candidate_name:
            parsed['candidate_name'] = candidate_name

        # Create candidate
        candidate = create_candidate_from_resume(
            current_user.id,
            parsed,
            resume_text=resume_text,
            resume_filename=filename
        )

        # Set position and SMS template
        candidate.position = position
        candidate.sms_template = sms_template

        # Store resume file
        resume_file = ResumeFile(
            candidate_id=candidate.id,
            filename=filename,
            original_filename=file.filename,
            content_type=file.content_type,
            file_size=len(file_data),
            file_data=file_data
        )
        db.session.add(resume_file)
        db.session.commit()

        log_audit(current_user.id, 'candidate_created', 'candidate', candidate.id)

        return jsonify({
            'candidate_id': candidate.id,
            'candidate': candidate.to_dict(include_jobs=True, include_references=True)
        })

    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500


@app.route('/api/candidates/<candidate_id>', methods=['GET'])
@api_login_required
def get_candidate(candidate_id):
    """Get full candidate details."""
    candidate = Candidate.query.get_or_404(candidate_id)

    if candidate.user_id != current_user.id:
        return jsonify({'error': 'Access denied'}), 403

    result = candidate.to_dict(include_jobs=True, include_references=True)
    result['signal'] = candidate.get_signal()
    result['reference_progress'] = candidate.get_reference_progress()

    return jsonify(result)


@app.route('/api/candidates/<candidate_id>/resume', methods=['GET'])
@api_login_required
def get_candidate_resume(candidate_id):
    """Download candidate's resume file."""
    candidate = Candidate.query.get_or_404(candidate_id)

    if candidate.user_id != current_user.id:
        return jsonify({'error': 'Access denied'}), 403

    # Get the resume file
    resume_file = ResumeFile.query.filter_by(candidate_id=candidate_id).first()

    if not resume_file or not resume_file.file_data:
        return jsonify({'error': 'Resume file not found'}), 404

    from flask import Response

    return Response(
        resume_file.file_data,
        mimetype=resume_file.content_type or 'application/pdf',
        headers={
            'Content-Disposition': f'inline; filename="{resume_file.original_filename or resume_file.filename}"'
        }
    )


@app.route('/api/candidates/<candidate_id>', methods=['PATCH'])
@api_login_required
def update_candidate(candidate_id):
    """Update candidate details."""
    candidate = Candidate.query.get_or_404(candidate_id)

    if candidate.user_id != current_user.id:
        return jsonify({'error': 'Access denied'}), 403

    data = request.json

    # Update allowed fields
    allowed_fields = ['position', 'status', 'sms_template', 'notes', 'name', 'email', 'phone',
                      'target_role_category', 'target_role_details']
    for field in allowed_fields:
        if field in data:
            setattr(candidate, field, data[field])

    candidate.updated_at = datetime.utcnow()
    db.session.commit()

    log_audit(current_user.id, 'candidate_updated', 'candidate', candidate.id)

    return jsonify(candidate.to_dict(include_jobs=True, include_references=True))


@app.route('/api/candidates/<candidate_id>', methods=['DELETE'])
@api_login_required
def delete_candidate(candidate_id):
    """Delete a candidate and all related records."""
    candidate = Candidate.query.get_or_404(candidate_id)

    if candidate.user_id != current_user.id:
        return jsonify({'error': 'Access denied'}), 403

    try:
        log_audit(current_user.id, 'candidate_deleted', 'candidate', candidate.id,
                  {'name': candidate.name})

        # Delete reference requests first (they reference candidate_id)
        db.session.execute(
            db.text('DELETE FROM reference_requests WHERE candidate_id = :cid'),
            {'cid': candidate.id}
        )

        # Delete survey-related records
        for ref in candidate.references:
            # Delete survey requests and their questions/responses
            db.session.execute(
                db.text('''
                    DELETE FROM survey_responses WHERE survey_question_id IN (
                        SELECT sq.id FROM survey_questions sq
                        JOIN survey_requests sr ON sq.survey_request_id = sr.id
                        WHERE sr.reference_id = :rid
                    )
                '''),
                {'rid': ref.id}
            )
            db.session.execute(
                db.text('''
                    DELETE FROM survey_questions WHERE survey_request_id IN (
                        SELECT id FROM survey_requests WHERE reference_id = :rid
                    )
                '''),
                {'rid': ref.id}
            )
            db.session.execute(
                db.text('DELETE FROM survey_requests WHERE reference_id = :rid'),
                {'rid': ref.id}
            )

        # Now delete the candidate (cascades to references, jobs, resume)
        db.session.delete(candidate)
        db.session.commit()

        return jsonify({'success': True})
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': f'Failed to delete: {str(e)}'}), 500


# ============================================================================
# API Routes - References
# ============================================================================

@app.route('/api/candidates/<candidate_id>/references', methods=['POST'])
@api_login_required
def add_reference(candidate_id):
    """Add a reference to a candidate."""
    candidate = Candidate.query.get_or_404(candidate_id)

    if candidate.user_id != current_user.id:
        return jsonify({'error': 'Access denied'}), 403

    data = request.json

    # Get job if specified
    job_id = None
    job_index = data.get('job_index')
    if job_index is not None:
        jobs = list(candidate.jobs.order_by(Job.order))
        if 0 <= job_index < len(jobs):
            job_id = jobs[job_index].id

    reference = Reference(
        candidate_id=candidate.id,
        job_id=job_id,
        name=data.get('reference_name', ''),
        phone=data.get('reference_phone', ''),
        email=data.get('reference_email', ''),
        relationship=data.get('relationship', ''),
        contact_method=data.get('contact_method', 'survey_only'),
        custom_questions=json.dumps(data.get('custom_questions', [])),
        timezone=data.get('timezone', current_user.timezone or 'America/New_York'),
        status='pending'
    )

    db.session.add(reference)
    candidate.updated_at = datetime.utcnow()
    db.session.commit()

    log_audit(current_user.id, 'reference_added', 'reference', reference.id)

    return jsonify({'reference': reference.to_dict()})


@app.route('/api/candidates/<candidate_id>/references/<reference_id>', methods=['PATCH'])
@api_login_required
def update_reference(candidate_id, reference_id):
    """Update a reference."""
    candidate = Candidate.query.get_or_404(candidate_id)

    if candidate.user_id != current_user.id:
        return jsonify({'error': 'Access denied'}), 403

    reference = Reference.query.get_or_404(reference_id)

    if reference.candidate_id != candidate.id:
        return jsonify({'error': 'Reference not found'}), 404

    data = request.json

    allowed_fields = ['name', 'phone', 'email', 'relationship', 'scheduled_time', 
                      'timezone', 'status', 'custom_questions', 'notes', 'contact_method']

    for field in allowed_fields:
        if field in data:
            if field == 'custom_questions':
                reference.custom_questions = json.dumps(data[field])
            elif field == 'scheduled_time' and data[field]:
                reference.scheduled_time = datetime.fromisoformat(data[field].replace('Z', '+00:00'))
            else:
                setattr(reference, field, data[field])

    reference.updated_at = datetime.utcnow()
    db.session.commit()

    return jsonify({'reference': reference.to_dict()})


@app.route('/api/candidates/<candidate_id>/references/<reference_id>', methods=['DELETE'])
@api_login_required
def delete_reference(candidate_id, reference_id):
    """Delete a reference."""
    candidate = Candidate.query.get_or_404(candidate_id)

    if candidate.user_id != current_user.id:
        return jsonify({'error': 'Access denied'}), 403

    reference = Reference.query.get_or_404(reference_id)

    if reference.candidate_id != candidate.id:
        return jsonify({'error': 'Reference not found'}), 404

    db.session.delete(reference)
    db.session.commit()

    return jsonify({'success': True})


@app.route('/api/candidates/<candidate_id>/references/<reference_id>/schedule', methods=['POST'])
@api_login_required
def schedule_reference_call(candidate_id, reference_id):
    """Schedule a follow-up call."""
    candidate = Candidate.query.get_or_404(candidate_id)

    if candidate.user_id != current_user.id:
        return jsonify({'error': 'Access denied'}), 403

    reference = Reference.query.get_or_404(reference_id)

    if reference.candidate_id != candidate.id:
        return jsonify({'error': 'Reference not found'}), 404

    data = request.json

    reference.scheduled_time = datetime.fromisoformat(data['scheduled_time'].replace('Z', '+00:00'))
    reference.timezone = data.get('timezone', 'America/New_York')
    reference.status = 'scheduled'
    reference.updated_at = datetime.utcnow()

    db.session.commit()

    log_audit(current_user.id, 'call_scheduled', 'reference', reference.id)

    return jsonify({'success': True, 'reference': reference.to_dict()})


@app.route('/api/candidates/<candidate_id>/references/<reference_id>/send-sms', methods=['POST'])
@api_login_required
def send_reference_sms(candidate_id, reference_id):
    """Send SMS to a reference."""
    if not TWILIO_ACCOUNT_SID:
        return jsonify({'error': 'SMS not configured. Please contact administrator.'}), 500

    candidate = Candidate.query.get_or_404(candidate_id)

    if candidate.user_id != current_user.id:
        return jsonify({'error': 'Access denied'}), 403

    reference = Reference.query.get_or_404(reference_id)

    if reference.candidate_id != candidate.id:
        return jsonify({'error': 'Reference not found'}), 404

    data = request.json or {}

    if data.get('message'):
        message = data['message']
    else:
        template = candidate.sms_template or current_user.sms_template or DEFAULT_SMS_TEMPLATE
        message = format_sms_message(template, candidate.name)

    from services import send_sms_global
    result = send_sms_global(reference.phone, message, TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN, TWILIO_PHONE_NUMBER)

    if result.get('success'):
        reference.sms_sent = True
        reference.sms_sent_at = datetime.utcnow()
        db.session.commit()
        log_audit(current_user.id, 'sms_sent', 'reference', reference.id)

    return jsonify(result)


# ============================================================================
# API Routes - Calls
# ============================================================================

@app.route('/api/start-reference-check', methods=['POST'])
@api_login_required
def start_reference_check():
    """Start a single reference check call."""
    if not VAPI_API_KEY or not VAPI_PHONE_NUMBER_ID:
        return jsonify({'error': 'Vapi not configured. Please contact administrator.'}), 500

    data = request.json
    candidate_id = data.get('candidate_id')
    reference_id = data.get('reference_id')

    candidate = Candidate.query.get_or_404(candidate_id)

    if candidate.user_id != current_user.id:
        return jsonify({'error': 'Access denied'}), 403

    reference = Reference.query.get_or_404(reference_id)

    if reference.candidate_id != candidate.id:
        return jsonify({'error': 'Reference not found'}), 404

    # Get the job for this reference
    job = reference.job
    if not job:
        jobs = list(candidate.jobs.order_by(Job.order))
        job = jobs[0] if jobs else None

    if not job:
        return jsonify({'error': 'No job information available'}), 400

    # Update status
    reference.status = 'calling'
    db.session.commit()

    # Initiate call with global credentials
    from services import initiate_vapi_call_global
    result = initiate_vapi_call_global(reference, candidate, job, VAPI_API_KEY, VAPI_PHONE_NUMBER_ID)

    if result.get('error'):
        reference.status = 'failed'
        db.session.commit()
        return jsonify(result), 500

    reference.call_id = result.get('call_id')
    db.session.commit()

    log_audit(current_user.id, 'call_initiated', 'reference', reference.id)

    return jsonify({'success': True, 'check_id': reference.call_id})


@app.route('/api/candidates/<candidate_id>/start-outreach', methods=['POST'])
@api_login_required
def start_outreach(candidate_id):
    """Begin reference outreach for all pending references."""
    if not VAPI_API_KEY or not VAPI_PHONE_NUMBER_ID:
        return jsonify({'error': 'Vapi not configured. Please contact administrator.'}), 500

    candidate = Candidate.query.get_or_404(candidate_id)

    if candidate.user_id != current_user.id:
        return jsonify({'error': 'Access denied'}), 403

    candidate.status = 'in_progress'
    candidate.updated_at = datetime.utcnow()
    db.session.commit()

    from services import initiate_vapi_call_global
    results = []
    pending_refs = [r for r in candidate.references if r.status == 'pending']

    for reference in pending_refs:
        job = reference.job
        if not job:
            jobs = list(candidate.jobs.order_by(Job.order))
            job = jobs[0] if jobs else None

        if not job:
            results.append({
                'reference_id': reference.id,
                'reference_name': reference.name,
                'result': {'error': 'No job information'}
            })
            continue

        reference.status = 'calling'
        db.session.commit()

        call_result = initiate_vapi_call_global(reference, candidate, job, VAPI_API_KEY, VAPI_PHONE_NUMBER_ID)

        if call_result.get('error'):
            reference.status = 'failed'
        else:
            reference.call_id = call_result.get('call_id')

        db.session.commit()

        results.append({
            'reference_id': reference.id,
            'reference_name': reference.name,
            'result': call_result
        })

    log_audit(current_user.id, 'outreach_started', 'candidate', candidate.id)

    return jsonify({'success': True, 'results': results})


@app.route('/api/check-status/<check_id>', methods=['GET'])
@api_login_required
def check_call_status(check_id):
    """Get call status and results."""

    # Find the reference with this call_id
    reference = Reference.query.filter_by(call_id=check_id).first()

    if not reference:
        return jsonify({'error': 'Call not found'}), 404

    candidate = reference.candidate

    if candidate.user_id != current_user.id:
        return jsonify({'error': 'Access denied'}), 403

    # Get call status from Vapi using global credentials
    from services import get_vapi_call_status_global
    call_data = get_vapi_call_status_global(check_id, VAPI_API_KEY)

    if call_data.get('error'):
        return jsonify(call_data), 500

    status = call_data.get('status', 'unknown')
    ended_reason = call_data.get('endedReason', '')

    result = {
        'check_id': check_id,
        'status': status,
        'ended_reason': ended_reason
    }

    # Handle call completion
    if status == 'ended':
        ended_reason_lower = ended_reason.lower()

        # Check for unsuccessful call outcomes
        unsuccessful_reasons = [
            'voicemail', 'no-answer', 'busy', 'failed', 'rejected', 
            'declined', 'machine', 'answering-machine', 'no_answer',
            'customer-busy', 'customer-did-not-answer', 'no-human',
            'assistant-error', 'phone-call-provider-closed-websocket',
            'customer-did-not-give-microphone-permission'
        ]

        is_unsuccessful = any(reason in ended_reason_lower for reason in unsuccessful_reasons)

        # Also check if there's no meaningful transcript (very short or empty)
        artifact = call_data.get('artifact', {})
        transcript = artifact.get('transcript', '')
        transcript_too_short = len(transcript.strip()) < 100  # Less than 100 chars likely means no real conversation

        if is_unsuccessful or (transcript_too_short and 'hangup' not in ended_reason_lower):
            reference.status = 'no_answer'

            # Store the reason for the hiring manager
            reference.notes = f"Call unsuccessful: {ended_reason}"

            # Auto-send callback request SMS if configured
            if not reference.sms_sent and TWILIO_ACCOUNT_SID:
                from services import send_sms_global
                sms_result = send_callback_request_sms(
                    reference, candidate,
                    TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN, TWILIO_PHONE_NUMBER
                )
                if sms_result.get('success'):
                    reference.sms_sent = True
                    reference.sms_sent_at = datetime.utcnow()
                    reference.callback_status = 'awaiting_reply'
                    reference.callback_expires_at = datetime.utcnow() + timedelta(hours=24)
                    add_to_sms_conversation(reference, 'outbound', 
                        f"Hi {reference.name.split()[0]}, we tried to reach you regarding a reference check for {candidate.name}. Is there a better time to call you back? Please reply with a day and time.")

            result['message'] = f'Call did not connect: {ended_reason}. SMS sent asking for callback time.'
        else:
            # Successful call - analyze transcript
            reference.status = 'completed'
            reference.completed_at = datetime.utcnow()

            reference.transcript = transcript
            result['transcript'] = transcript
            result['recording_url'] = artifact.get('recordingUrl')

            # Get job info for analysis
            job = reference.job
            if not job:
                jobs = list(candidate.jobs.order_by(Job.order))
                job = jobs[0] if jobs else None

            # Analyze with Claude
            if job and transcript:
                job_dict = job.to_dict()
                analysis = analyze_transcript_with_claude(
                    transcript, job_dict, candidate.name, ANTHROPIC_API_KEY
                )

                if analysis:
                    # Store analysis results
                    reference.score = calculate_verification_score(analysis)
                    reference.summary = analysis.get('summary', '')
                    reference.sentiment = analysis.get('overall_sentiment', 'neutral')
                    reference.red_flags = json.dumps(analysis.get('red_flags', []))
                    reference.discrepancies = json.dumps(analysis.get('discrepancies', []))
                    reference.achievements_verified = json.dumps(analysis.get('achievements_verified', []))
                    reference.achievements_not_verified = json.dumps(analysis.get('achievements_not_verified', []))
                    reference.positive_signals = json.dumps(analysis.get('positive_signals', []))
                    reference.structured_data = json.dumps(analysis)

                    # Build result
                    red_flags = list(analysis.get('red_flags', []))
                    discrepancies = analysis.get('discrepancies', [])

                    for disc in discrepancies:
                        if disc not in red_flags:
                            red_flags.append(f"DISCREPANCY: {disc}")

                    if analysis.get('employment_confirmed') == False:
                        red_flags.append("Employment not confirmed by reference")
                    if analysis.get('dates_accurate') == False:
                        red_flags.append("Employment dates disputed by reference")
                    if analysis.get('title_confirmed') == False:
                        red_flags.append("Job title not confirmed by reference")
                    if analysis.get('would_rehire') == False:
                        red_flags.append("Reference would NOT rehire candidate")

                    result.update({
                        'verification_score': reference.score,
                        'summary': reference.summary,
                        'red_flags': red_flags,
                        'discrepancies': discrepancies,
                        'achievements_verified': analysis.get('achievements_verified', []),
                        'achievements_not_verified': analysis.get('achievements_not_verified', []),
                        'positive_signals': analysis.get('positive_signals', []),
                        'structured_data': analysis
                    })

        db.session.commit()

        # Check if all references are done
        all_done = all(r.status in ['completed', 'failed', 'no_answer'] for r in candidate.references)
        if all_done:
            candidate.status = 'completed'
            db.session.commit()

    elif status == 'failed' or 'error' in status.lower():
        reference.status = 'failed'
        db.session.commit()

    return jsonify(result)


# ============================================================================
# API Routes - Settings
# ============================================================================

@app.route('/api/settings', methods=['GET'])
@api_login_required
def get_settings():
    """Get current user settings."""
    return jsonify({
        'email': current_user.email,
        'first_name': current_user.first_name,
        'last_name': current_user.last_name,
        'company_name': current_user.company_name,
        'timezone': current_user.timezone,
        'sms_template': current_user.sms_template or DEFAULT_SMS_TEMPLATE,
        'has_vapi': bool(current_user.vapi_api_key),
        'has_twilio': bool(current_user.twilio_account_sid),
        'vapi_phone_number_id': current_user.vapi_phone_number_id or ''
    })


@app.route('/api/settings', methods=['PATCH'])
@api_login_required
def update_settings():
    """Update user settings."""
    data = request.json

    # Profile fields
    if 'first_name' in data:
        current_user.first_name = data['first_name']
    if 'last_name' in data:
        current_user.last_name = data['last_name']
    if 'company_name' in data:
        current_user.company_name = data['company_name']
    if 'timezone' in data:
        current_user.timezone = data['timezone']
    if 'sms_template' in data:
        current_user.sms_template = data['sms_template']

    # API keys
    if 'vapi_api_key' in data:
        current_user.vapi_api_key = data['vapi_api_key'] or None
    if 'vapi_phone_number_id' in data:
        current_user.vapi_phone_number_id = data['vapi_phone_number_id'] or None
    if 'twilio_account_sid' in data:
        current_user.twilio_account_sid = data['twilio_account_sid'] or None
    if 'twilio_auth_token' in data:
        current_user.twilio_auth_token = data['twilio_auth_token'] or None
    if 'twilio_phone_number' in data:
        current_user.twilio_phone_number = data['twilio_phone_number'] or None

    current_user.updated_at = datetime.utcnow()
    db.session.commit()

    log_audit(current_user.id, 'settings_updated')

    return jsonify({'success': True})


@app.route('/api/role-categories', methods=['GET'])
def get_role_categories():
    """Get available role categories for target role dropdown."""
    return jsonify(ROLE_CATEGORIES)


@app.route('/api/settings/password', methods=['POST'])
@api_login_required
def change_password():
    """Change user password."""
    data = request.json

    current_password = data.get('current_password', '')
    new_password = data.get('new_password', '')
    confirm_password = data.get('confirm_password', '')

    if not current_user.check_password(current_password):
        return jsonify({'error': 'Current password is incorrect'}), 400

    is_valid, error = validate_password(new_password)
    if not is_valid:
        return jsonify({'error': error}), 400

    if new_password != confirm_password:
        return jsonify({'error': 'New passwords do not match'}), 400

    current_user.set_password(new_password)
    db.session.commit()

    log_audit(current_user.id, 'password_changed')

    return jsonify({'success': True})


# ============================================================================
# API Routes - Search
# ============================================================================

@app.route('/api/search', methods=['GET'])
@api_login_required
def search():
    """Search candidates."""
    query = request.args.get('q', '').strip()
    status = request.args.get('status', '').strip() or None

    candidates = search_candidates(current_user.id, query, status)

    result = []
    for c in candidates:
        result.append({
            'id': c.id,
            'name': c.name,
            'position': c.position,
            'status': c.status,
            'reference_progress': c.get_reference_progress(),
            'signal': c.get_signal()
        })

    return jsonify(result)


# ============================================================================
# Webhooks
# ============================================================================

# ============================================================================
# Reference Request Routes (Candidate Self-Service)
# ============================================================================

@app.route('/api/candidates/<candidate_id>/send-reference-request', methods=['POST'])
@api_login_required
def send_reference_request(candidate_id):
    """Send email to candidate requesting they submit references."""
    if not RESEND_API_KEY:
        return jsonify({'error': 'Email service not configured. Please add RESEND_API_KEY.'}), 500

    candidate = Candidate.query.get_or_404(candidate_id)

    if candidate.user_id != current_user.id:
        return jsonify({'error': 'Access denied'}), 403

    if not candidate.email:
        return jsonify({'error': 'Candidate email is required. Please add their email first.'}), 400

    # Invalidate any existing pending requests
    existing_requests = ReferenceRequest.query.filter_by(
        candidate_id=candidate.id,
        status='pending'
    ).all()
    for req in existing_requests:
        req.status = 'expired'

    # Create new request
    token = secrets.token_urlsafe(32)
    ref_request = ReferenceRequest(
        candidate_id=candidate.id,
        token=token,
        status='pending',
        expires_at=datetime.utcnow() + timedelta(days=7)
    )
    db.session.add(ref_request)
    db.session.commit()

    # Send email
    base_url = request.url_root.rstrip('/')
    result = send_reference_request_email(candidate, token, base_url, RESEND_API_KEY)

    if result.get('success'):
        ref_request.email_sent_at = datetime.utcnow()
        db.session.commit()
        log_audit(current_user.id, 'reference_request_sent', 'candidate', candidate.id)
        return jsonify({'success': True, 'message': 'Reference request sent to candidate'})
    else:
        # Rollback the request if email failed
        ref_request.status = 'expired'
        db.session.commit()
        return jsonify({'error': f"Failed to send email: {result.get('error')}"}), 500


@app.route('/api/candidates/<candidate_id>/resend-reference-request', methods=['POST'])
@api_login_required
def resend_reference_request(candidate_id):
    """Resend/remind candidate to submit references."""
    if not RESEND_API_KEY:
        return jsonify({'error': 'Email service not configured.'}), 500

    candidate = Candidate.query.get_or_404(candidate_id)

    if candidate.user_id != current_user.id:
        return jsonify({'error': 'Access denied'}), 403

    # Find existing pending request
    ref_request = ReferenceRequest.query.filter_by(
        candidate_id=candidate.id,
        status='pending'
    ).order_by(ReferenceRequest.created_at.desc()).first()

    if not ref_request or not ref_request.is_valid():
        # No valid request, send a new one
        return send_reference_request(candidate_id)

    # Send reminder
    base_url = request.url_root.rstrip('/')
    result = send_reference_reminder_email(candidate, ref_request.token, base_url, RESEND_API_KEY)

    if result.get('success'):
        ref_request.reminder_sent_at = datetime.utcnow()
        db.session.commit()
        log_audit(current_user.id, 'reference_reminder_sent', 'candidate', candidate.id)
        return jsonify({'success': True, 'message': 'Reminder sent to candidate'})
    else:
        return jsonify({'error': f"Failed to send reminder: {result.get('error')}"}), 500


@app.route('/api/candidates/<candidate_id>/reference-request-status', methods=['GET'])
@api_login_required
def get_reference_request_status(candidate_id):
    """Get the status of reference request for a candidate."""
    candidate = Candidate.query.get_or_404(candidate_id)

    if candidate.user_id != current_user.id:
        return jsonify({'error': 'Access denied'}), 403

    status = candidate.get_reference_request_status()

    # Get latest request details
    latest_request = ReferenceRequest.query.filter_by(
        candidate_id=candidate.id
    ).order_by(ReferenceRequest.created_at.desc()).first()

    if latest_request:
        status['request'] = latest_request.to_dict()

    return jsonify(status)


@app.route('/submit-references/<token>', methods=['GET'])
def submit_references_form(token):
    """Public page for candidate to submit references."""
    ref_request = ReferenceRequest.query.filter_by(token=token).first()

    if not ref_request:
        return render_template('submit_references.html', error='Invalid link'), 404

    if not ref_request.is_valid():
        db.session.commit()  # Save expired status
        return render_template('submit_references.html', error='This link has expired. Please contact the hiring team for a new link.'), 410

    candidate = ref_request.candidate
    jobs = list(candidate.jobs.order_by(Job.order))

    return render_template('submit_references.html', 
                          candidate=candidate, 
                          jobs=jobs, 
                          token=token,
                          error=None)


@app.route('/submit-references/<token>', methods=['POST'])
def submit_references(token):
    """Handle candidate's reference submission."""
    ref_request = ReferenceRequest.query.filter_by(token=token).first()

    if not ref_request:
        return render_template('submit_references.html', error='Invalid link'), 404

    if not ref_request.is_valid():
        db.session.commit()
        return render_template('submit_references.html', error='This link has expired.'), 410

    candidate = ref_request.candidate
    jobs = list(candidate.jobs.order_by(Job.order))

    # Parse form data
    references_added = 0

    for i, job in enumerate(jobs):
        # Reference 1 (required if any data provided)
        ref1_name = request.form.get(f'job_{i}_ref1_name', '').strip()
        ref1_phone = request.form.get(f'job_{i}_ref1_phone', '').strip()
        ref1_email = request.form.get(f'job_{i}_ref1_email', '').strip()
        ref1_relationship = request.form.get(f'job_{i}_ref1_relationship', '').strip()

        if ref1_name and ref1_phone:
            reference = Reference(
                candidate_id=candidate.id,
                job_id=job.id,
                name=ref1_name,
                phone=ref1_phone,
                email=ref1_email,
                relationship=ref1_relationship,
                status='pending'
            )
            db.session.add(reference)
            references_added += 1

        # Reference 2 (optional)
        ref2_name = request.form.get(f'job_{i}_ref2_name', '').strip()
        ref2_phone = request.form.get(f'job_{i}_ref2_phone', '').strip()
        ref2_email = request.form.get(f'job_{i}_ref2_email', '').strip()
        ref2_relationship = request.form.get(f'job_{i}_ref2_relationship', '').strip()

        if ref2_name and ref2_phone:
            reference = Reference(
                candidate_id=candidate.id,
                job_id=job.id,
                name=ref2_name,
                phone=ref2_phone,
                email=ref2_email,
                relationship=ref2_relationship,
                status='pending'
            )
            db.session.add(reference)
            references_added += 1

    # Validate at least 1 reference
    if references_added < 1:
        return render_template('submit_references.html',
                              candidate=candidate,
                              jobs=jobs,
                              token=token,
                              error='Please provide at least one reference.')

    # Mark request as completed
    ref_request.status = 'completed'
    ref_request.completed_at = datetime.utcnow()
    candidate.updated_at = datetime.utcnow()

    db.session.commit()

    # Send confirmation email
    if RESEND_API_KEY:
        send_reference_confirmation_email(candidate, RESEND_API_KEY)

    return render_template('submit_references.html', 
                          success=True, 
                          references_added=references_added)


# ============================================================================
# Survey Routes
# ============================================================================

@app.route('/api/generate-survey-questions', methods=['POST'])
@api_login_required
def generate_survey_questions_preview():
    """Generate survey questions for preview before creating reference."""
    data = request.json

    candidate_name = data.get('candidate_name', '')
    job_title = data.get('job_title', '')
    job_company = data.get('job_company', '')
    job_dates = data.get('job_dates', '')
    responsibilities = data.get('responsibilities', [])
    achievements = data.get('achievements', [])

    # Get standardized questions (10 questions)
    standardized = []
    for idx, q in enumerate(STANDARDIZED_SURVEY_QUESTIONS):
        standardized.append({
            'index': idx,
            'type': 'standardized',
            'question': q['question'].replace('{candidate_name}', candidate_name),
            'answer_type': q.get('type', 'text')
        })

    # Generate AI questions (up to 5 questions)
    ai_questions = []
    try:
        ai_qs = generate_ai_survey_questions(
            candidate_name=candidate_name,
            prior_job_title=job_title,
            prior_company=job_company,
            prior_dates=job_dates,
            prior_responsibilities=responsibilities[:5] if responsibilities else [],
            prior_achievements=achievements[:3] if achievements else [],
            target_role=None,  # Not using target role
            api_key=ANTHROPIC_API_KEY
        )

        for idx, q in enumerate(ai_qs):
            ai_questions.append({
                'index': len(standardized) + idx,
                'type': 'ai_generated',
                'question': q,
                'answer_type': 'text'
            })
    except Exception as e:
        print(f"Error generating AI questions: {e}")
        # Continue without AI questions if there's an error

    # Combine all questions
    all_questions = standardized + ai_questions

    return jsonify({'questions': all_questions})


@app.route('/api/candidates/<candidate_id>/references/<reference_id>/survey/preview', methods=['GET'])
@api_login_required
def preview_survey_questions(candidate_id, reference_id):
    """Generate and return survey questions for review before sending."""
    candidate = Candidate.query.get_or_404(candidate_id)

    if candidate.user_id != current_user.id:
        return jsonify({'error': 'Access denied'}), 403

    reference = Reference.query.get_or_404(reference_id)

    if reference.candidate_id != candidate.id:
        return jsonify({'error': 'Reference not found'}), 404

    job = reference.job or candidate.jobs.first()

    if not job:
        return jsonify({'error': 'No job associated with this reference'}), 400

    # Generate questions
    questions = get_survey_questions_for_reference(reference, candidate, job, ANTHROPIC_API_KEY)

    return jsonify({
        'questions': questions,
        'reference': reference.to_dict(),
        'candidate_name': candidate.name,
        'job': job.to_dict()
    })


@app.route('/api/candidates/<candidate_id>/references/<reference_id>/survey/send', methods=['POST'])
@api_login_required
def send_survey(candidate_id, reference_id):
    """Send survey email to reference with provided questions."""
    if not RESEND_API_KEY:
        return jsonify({'error': 'Email service not configured'}), 500

    candidate = Candidate.query.get_or_404(candidate_id)

    if candidate.user_id != current_user.id:
        return jsonify({'error': 'Access denied'}), 403

    reference = Reference.query.get_or_404(reference_id)

    if reference.candidate_id != candidate.id:
        return jsonify({'error': 'Reference not found'}), 404

    if not reference.email:
        return jsonify({'error': 'Reference email is required to send survey'}), 400

    data = request.json
    questions = data.get('questions', [])

    if not questions:
        return jsonify({'error': 'No questions provided'}), 400

    # Invalidate any existing pending survey requests
    existing_requests = SurveyRequest.query.filter_by(
        reference_id=reference.id,
        status='pending'
    ).all()
    for req in existing_requests:
        req.status = 'expired'

    # Create new survey request
    token = secrets.token_urlsafe(32)
    survey_request = SurveyRequest(
        reference_id=reference.id,
        token=token,
        status='pending',
        expires_at=datetime.utcnow() + timedelta(days=7)
    )
    db.session.add(survey_request)
    db.session.flush()  # Get ID for questions

    # Create survey questions
    for i, q in enumerate(questions):
        question = SurveyQuestion(
            survey_request_id=survey_request.id,
            question_text=q['question_text'],
            question_type=q.get('question_type', 'standardized'),
            response_type=q.get('response_type', 'free_text'),
            options=json.dumps(q.get('options')) if q.get('options') else None,
            order=i,
            required=q.get('required', True)
        )
        db.session.add(question)

    db.session.commit()

    # Send email
    base_url = request.url_root.rstrip('/')
    result = send_survey_email(reference, candidate, token, base_url, RESEND_API_KEY)

    if result.get('success'):
        survey_request.email_sent_at = datetime.utcnow()
        reference.survey_status = 'pending'
        db.session.commit()
        log_audit(current_user.id, 'survey_sent', 'reference', reference.id)
        return jsonify({'success': True, 'message': 'Survey sent to reference'})
    else:
        # Rollback on failure
        survey_request.status = 'expired'
        db.session.commit()
        return jsonify({'error': f"Failed to send survey: {result.get('error')}"}), 500


@app.route('/api/candidates/<candidate_id>/references/<reference_id>/survey/results', methods=['GET'])
@api_login_required
def get_survey_results(candidate_id, reference_id):
    """Get survey results for a reference."""
    candidate = Candidate.query.get_or_404(candidate_id)

    if candidate.user_id != current_user.id:
        return jsonify({'error': 'Access denied'}), 403

    reference = Reference.query.get_or_404(reference_id)

    if reference.candidate_id != candidate.id:
        return jsonify({'error': 'Reference not found'}), 404

    # Get completed survey request
    survey_request = SurveyRequest.query.filter_by(
        reference_id=reference.id,
        status='completed'
    ).order_by(SurveyRequest.completed_at.desc()).first()

    if not survey_request:
        return jsonify({'error': 'No completed survey found'}), 404

    return jsonify(survey_request.to_dict(include_questions=True, include_responses=True))


@app.route('/submit-survey/<token>', methods=['GET'])
def survey_form(token):
    """Public survey form for reference to complete."""
    survey_request = SurveyRequest.query.filter_by(token=token).first()

    if not survey_request:
        return render_template('survey_form.html', error='Invalid link'), 404

    if not survey_request.is_valid():
        db.session.commit()
        return render_template('survey_form.html', error='This survey link has expired.'), 410

    reference = survey_request.reference
    candidate = reference.candidate
    questions = survey_request.questions

    return render_template('survey_form.html',
                          survey_request=survey_request,
                          reference=reference,
                          candidate=candidate,
                          questions=questions,
                          error=None)


@app.route('/submit-survey/<token>', methods=['POST'])
def submit_survey(token):
    """Handle survey submission from reference."""
    survey_request = SurveyRequest.query.filter_by(token=token).first()

    if not survey_request:
        return render_template('survey_form.html', error='Invalid link'), 404

    if not survey_request.is_valid():
        db.session.commit()
        return render_template('survey_form.html', error='This survey link has expired.'), 410

    reference = survey_request.reference
    candidate = reference.candidate
    questions = survey_request.questions

    # Process responses
    for question in questions:
        response_data = {}

        if question.response_type == 'rating':
            rating = request.form.get(f'q_{question.id}_rating')
            if rating:
                response_data['rating'] = int(rating)
        elif question.response_type == 'multiple_choice':
            response_data['selected_option'] = request.form.get(f'q_{question.id}_option')
        elif question.response_type == 'free_text':
            response_data['text_response'] = request.form.get(f'q_{question.id}_text', '').strip()

        # Check required fields
        if question.required:
            has_response = (
                response_data.get('rating') or 
                response_data.get('selected_option') or 
                response_data.get('text_response')
            )
            if not has_response:
                return render_template('survey_form.html',
                                      survey_request=survey_request,
                                      reference=reference,
                                      candidate=candidate,
                                      questions=questions,
                                      error=f'Please answer all required questions.')

        # Save response
        if any(response_data.values()):
            response = SurveyResponse(
                survey_question_id=question.id,
                rating=response_data.get('rating'),
                text_response=response_data.get('text_response'),
                selected_option=response_data.get('selected_option')
            )
            db.session.add(response)

    # Mark survey as completed
    survey_request.status = 'completed'
    survey_request.completed_at = datetime.utcnow()
    reference.survey_status = 'completed'

    db.session.commit()

    # Analyze responses
    job = reference.job or candidate.jobs.first()
    analysis = analyze_survey_responses(survey_request, candidate.name, job, ANTHROPIC_API_KEY)

    if analysis:
        survey_request.survey_score = analysis.get('score')
        survey_request.survey_summary = analysis.get('summary')
        survey_request.survey_red_flags = json.dumps(analysis.get('red_flags', []))
        survey_request.survey_analysis = json.dumps(analysis)
        db.session.commit()

    # Send confirmation email
    if RESEND_API_KEY:
        send_survey_confirmation_email(reference, candidate, RESEND_API_KEY)

    return render_template('survey_form.html', success=True)


# ============================================================================
# Webhooks
# ============================================================================

@app.route('/api/webhook/vapi', methods=['POST'])
def vapi_webhook():
    """Handle Vapi call webhooks."""
    data = request.json or {}
    message_type = data.get('message', {}).get('type')
    call_id = data.get('message', {}).get('call', {}).get('id')

    if call_id:
        reference = Reference.query.filter_by(call_id=call_id).first()
        if reference and message_type == 'end-of-call-report':
            # Process will happen on next status check
            pass

    return jsonify({'success': True})


@app.route('/api/webhook/sms', methods=['POST'])
def sms_webhook():
    """Handle incoming SMS responses including callback scheduling."""
    from_number = request.form.get('From', '')
    body = request.form.get('Body', '').strip()

    # Find reference by phone (normalize phone comparison)
    normalized = from_number[-10:] if len(from_number) >= 10 else from_number

    references = Reference.query.filter(
        Reference.phone.endswith(normalized)
    ).all()

    for reference in references:
        if not reference.candidate.user_id:
            continue

        candidate = reference.candidate

        # Log the incoming message
        add_to_sms_conversation(reference, 'inbound', body)
        reference.sms_response = body
        reference.updated_at = datetime.utcnow()

        # Handle callback scheduling flow
        if reference.callback_status == 'awaiting_reply':
            # Parse the time with Claude
            parsed = parse_callback_time_with_claude(body, ANTHROPIC_API_KEY)

            if parsed.get('error'):
                # Parsing failed, ask them to try again
                from services import send_sms_global
                send_sms_global(reference.phone, 
                    "Sorry, I didn't understand. Please reply with a day and time like 'Tomorrow at 3pm EST'.",
                    TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN, TWILIO_PHONE_NUMBER)
                add_to_sms_conversation(reference, 'outbound', "Sorry, I didn't understand. Please reply with a day and time like 'Tomorrow at 3pm EST'.")

            elif not parsed.get('parsed_successfully'):
                # Message wasn't about scheduling
                reference.callback_status = 'none'
                reference.notes = f"Reference declined or sent unclear response: {body}"

            elif parsed.get('needs_clarification'):
                # Need more info
                question = parsed.get('clarification_question', "What timezone are you in? (e.g., EST, PST)")
                from services import send_sms_global
                send_sms_global(reference.phone, question, TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN, TWILIO_PHONE_NUMBER)
                add_to_sms_conversation(reference, 'outbound', question)

            elif not parsed.get('timezone') or parsed.get('timezone_assumed'):
                # No timezone, propose with EST default
                friendly_time = parsed.get('friendly_time', 'the suggested time')
                if not 'EST' in friendly_time and not 'PST' in friendly_time:
                    friendly_time = f"{friendly_time} EST"

                reference.callback_timezone = parsed.get('timezone') or 'EST'
                reference.callback_scheduled_time = datetime.fromisoformat(parsed.get('datetime_iso')) if parsed.get('datetime_iso') else None
                reference.callback_status = 'time_proposed'

                send_callback_confirmation_sms(reference, friendly_time, TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN, TWILIO_PHONE_NUMBER)
                add_to_sms_conversation(reference, 'outbound', f"Great! We'll call you on {friendly_time}. Reply YES to confirm or suggest another time.")

            else:
                # Got timezone, propose the time
                friendly_time = parsed.get('friendly_time', 'the suggested time')
                reference.callback_timezone = parsed.get('timezone')
                reference.callback_scheduled_time = datetime.fromisoformat(parsed.get('datetime_iso')) if parsed.get('datetime_iso') else None
                reference.callback_status = 'time_proposed'

                send_callback_confirmation_sms(reference, friendly_time, TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN, TWILIO_PHONE_NUMBER)
                add_to_sms_conversation(reference, 'outbound', f"Great! We'll call you on {friendly_time}. Reply YES to confirm or suggest another time.")

        elif reference.callback_status == 'time_proposed':
            # Check if they confirmed
            body_lower = body.lower().strip()
            if body_lower in ['yes', 'y', 'yep', 'yeah', 'sure', 'ok', 'okay', 'confirm', 'confirmed']:
                reference.callback_status = 'confirmed'

                # Send final confirmation
                friendly_time = f"{reference.callback_scheduled_time.strftime('%A, %B %d at %I:%M %p')} {reference.callback_timezone}" if reference.callback_scheduled_time else "the scheduled time"
                send_callback_final_confirmation_sms(reference, friendly_time, TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN, TWILIO_PHONE_NUMBER)
                add_to_sms_conversation(reference, 'outbound', f"Confirmed! We'll call you on {friendly_time}. Thank you!")
            else:
                # They suggested a different time, parse again
                reference.callback_status = 'awaiting_reply'
                # Re-process as a new time suggestion
                parsed = parse_callback_time_with_claude(body, ANTHROPIC_API_KEY)
                if parsed.get('parsed_successfully') and parsed.get('datetime_iso'):
                    friendly_time = parsed.get('friendly_time', 'the suggested time')
                    reference.callback_timezone = parsed.get('timezone') or 'EST'
                    reference.callback_scheduled_time = datetime.fromisoformat(parsed.get('datetime_iso'))
                    reference.callback_status = 'time_proposed'

                    send_callback_confirmation_sms(reference, friendly_time, TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN, TWILIO_PHONE_NUMBER)
                    add_to_sms_conversation(reference, 'outbound', f"Great! We'll call you on {friendly_time}. Reply YES to confirm or suggest another time.")

        db.session.commit()
        break

    return '', 200


@app.route('/api/process-callbacks', methods=['POST'])
def process_scheduled_callbacks():
    """Process due callbacks - call this endpoint every minute via cron/scheduler."""
    # Find references with confirmed callbacks that are due
    now = datetime.utcnow()

    due_callbacks = Reference.query.filter(
        Reference.callback_status == 'confirmed',
        Reference.callback_scheduled_time <= now
    ).all()

    results = []
    for reference in due_callbacks:
        candidate = reference.candidate
        job = reference.job or candidate.jobs.first()

        if not job:
            reference.callback_status = 'completed'
            reference.notes = (reference.notes or '') + ' | Callback skipped: no job info'
            db.session.commit()
            continue

        # Initiate the call
        reference.callback_status = 'callback_due'
        reference.status = 'calling'
        db.session.commit()

        from services import initiate_vapi_call_global
        call_result = initiate_vapi_call_global(reference, candidate, job, VAPI_API_KEY, VAPI_PHONE_NUMBER_ID)

        if call_result.get('error'):
            reference.status = 'failed'
            reference.callback_status = 'completed'
            reference.notes = (reference.notes or '') + f' | Callback failed: {call_result.get("error")}'
        else:
            reference.call_id = call_result.get('call_id')
            reference.callback_status = 'completed'

        db.session.commit()
        results.append({
            'reference_id': reference.id,
            'reference_name': reference.name,
            'result': call_result
        })

    # Also check for expired callbacks (24 hours without confirmation)
    expired = Reference.query.filter(
        Reference.callback_status.in_(['awaiting_reply', 'time_proposed']),
        Reference.callback_expires_at <= now
    ).all()

    for reference in expired:
        reference.callback_status = 'expired'
        reference.notes = (reference.notes or '') + ' | Callback expired: no confirmation within 24 hours'
        db.session.commit()

    return jsonify({
        'processed': len(results),
        'expired': len(expired),
        'results': results
    })


# ============================================================================
# Error Handlers
# ============================================================================

@app.errorhandler(404)
def not_found(e):
    if request.path.startswith('/api/'):
        return jsonify({'error': 'Not found'}), 404
    return render_template('404.html'), 404


@app.errorhandler(500)
def server_error(e):
    db.session.rollback()
    if request.path.startswith('/api/'):
        return jsonify({'error': 'Internal server error'}), 500
    return render_template('500.html'), 500


# ============================================================================
# CLI Commands
# ============================================================================

@app.cli.command('init-db')
def init_db():
    """Initialize the database."""
    db.create_all()
    print('Database initialized.')


@app.cli.command('create-admin')
def create_admin():
    """Create an admin user."""
    import getpass

    email = input('Email: ')
    password = getpass.getpass('Password: ')
    first_name = input('First name: ')
    last_name = input('Last name: ')

    user = User(
        email=email,
        first_name=first_name,
        last_name=last_name,
        sms_template=DEFAULT_SMS_TEMPLATE
    )
    user.set_password(password)

    db.session.add(user)
    db.session.commit()

    print(f'User {email} created.')


if __name__ == '__main__':
    with app.app_context():
        db.create_all()

    port = int(os.environ.get('PORT', 5000))
    debug = os.environ.get('FLASK_DEBUG', 'false').lower() == 'true'
    app.run(host='0.0.0.0', port=port, debug=debug)
