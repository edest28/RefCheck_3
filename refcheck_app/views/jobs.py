"""
Job posting view routes.
"""
from flask import Blueprint, render_template, redirect, url_for, flash, request, jsonify, make_response
from flask_login import login_required, current_user
from refcheck_app.models import db, JobPosting, JobApplication, Candidate, Company, PipelineColumn
from refcheck_app.utils.auth import api_login_required, log_audit
from refcheck_app.services.ai.jd_generator import generate_job_description_with_claude
from refcheck_app.services.ai.application_screener import analyze_application_with_claude
from refcheck_app.config import Config
from datetime import datetime
import secrets

bp = Blueprint('jobs', __name__)


@bp.route('/jobs')
@login_required
def jobs():
    """List job postings for the current user."""
    from sqlalchemy import func

    company_id = request.args.get('company', '').strip() or None
    companies = Company.query.filter_by(user_id=current_user.id).order_by(Company.name).all()

    query = JobPosting.query.filter_by(user_id=current_user.id)
    if company_id:
        query = query.filter_by(company_id=company_id)
    postings = query.order_by(JobPosting.updated_at.desc()).all()

    # Get applicant counts for each job
    job_ids = [p.id for p in postings]
    applicant_counts = {}
    if job_ids:
        counts = db.session.query(
            JobApplication.job_posting_id,
            func.count(JobApplication.id).label('count')
        ).filter(
            JobApplication.job_posting_id.in_(job_ids)
        ).group_by(JobApplication.job_posting_id).all()

        applicant_counts = {str(job_id): count for job_id, count in counts}

    # Add applicant count to each posting
    for posting in postings:
        posting.applicant_count = applicant_counts.get(posting.id, 0)

    return render_template(
        'jobs/list.html',
        jobs=postings,
        companies=companies,
        selected_company_id=company_id,
    )


@bp.route('/companies/<company_id>/jobs/new', methods=['GET'])
@login_required
def new_job(company_id):
    """Create new job posting form under a company."""
    company = Company.query.get_or_404(company_id)
    
    if company.user_id != current_user.id:
        flash('Access denied', 'error')
        return redirect(url_for('companies.list_companies'))
    
    return render_template('jobs/new.html', company=company)


@bp.route('/jobs/new', methods=['GET'])
@login_required
def new_job_legacy():
    """Legacy route - redirect to companies first."""
    # Check if user has any companies
    companies = Company.query.filter_by(user_id=current_user.id).all()
    
    if not companies:
        flash('Please create a company profile first before creating jobs.', 'info')
        return redirect(url_for('companies.new_company'))
    
    # If only one company, redirect to that company's job creation
    if len(companies) == 1:
        return redirect(url_for('jobs.new_job', company_id=companies[0].id))
    
    # Multiple companies - redirect to companies list
    return redirect(url_for('companies.list_companies'))


@bp.route('/companies/<company_id>/jobs', methods=['POST'])
@login_required
def create_job(company_id):
    """Create a new job posting under a company."""
    try:
        company = Company.query.get_or_404(company_id)
        
        if company.user_id != current_user.id:
            flash('Access denied', 'error')
            return redirect(url_for('companies.list_companies'))
        
        data = request.form

        posting = JobPosting(
            user_id=current_user.id,
            company_id=company.id,
            title=(data.get('title') or '').strip(),
            # Keep company_name/company_website for backward compatibility, populate from company
            company_name=company.name,
            company_website=company.website,
            department=(data.get('department') or '').strip() or None,
            location=(data.get('location') or '').strip() or None,
            employment_type=(data.get('employment_type') or '').strip() or None,
            seniority=(data.get('seniority') or '').strip() or None,
            description_raw=(data.get('description_raw') or '').strip() or None,
            description_html=(data.get('description_html') or '').strip() or None,
            status=(data.get('status') or 'draft').strip(),
            salary_range_text=(data.get('salary_range_text') or '').strip() or None,
            public_id=secrets.token_urlsafe(32) if data.get('status') == 'published' else None,
        )

        db.session.add(posting)
        db.session.commit()

        log_audit(current_user.id, 'job_posting_created', 'job_posting', posting.id)
        flash('Job created successfully', 'success')
        return redirect(url_for('jobs.view_job', job_id=posting.id))
    except Exception as e:
        db.session.rollback()
        flash(f'Error creating job: {str(e)}', 'error')
        import traceback
        print(f"Error in create_job: {traceback.format_exc()}")
        return redirect(url_for('companies.list_companies'))


@bp.route('/jobs/<job_id>')
@login_required
def view_job(job_id):
    """View job posting details and applications."""
    posting = JobPosting.query.get_or_404(job_id)

    if posting.user_id != current_user.id:
        flash('Access denied', 'error')
        return redirect(url_for('jobs.jobs'))

    pipeline_columns = (
        PipelineColumn.query.filter_by(user_id=current_user.id)
        .order_by(PipelineColumn.order.asc(), PipelineColumn.slug.asc())
        .all()
    )
    pipeline_slugs = [c.slug for c in pipeline_columns]
    if not pipeline_slugs:
        pipeline_columns = []
        pipeline_slugs = ['applied', 'screened', 'interview', 'offer', 'hired', 'rejected']
        pipeline_column_dicts = [{'slug': s, 'label': s.capitalize()} for s in pipeline_slugs]
    else:
        pipeline_column_dicts = [c.to_dict() for c in pipeline_columns]

    applications_by_stage = {}
    all_applications = []
    for slug in pipeline_slugs:
        stage_apps = [
            app.to_dict() for app in posting.applications.filter_by(stage=slug).all()
        ]
        applications_by_stage[slug] = stage_apps
        all_applications.extend(stage_apps)
    unknown_slug = '_unknown'
    unknown_apps = [
        app.to_dict() for app in posting.applications.filter(
            ~JobApplication.stage.in_(pipeline_slugs)
        ).all()
    ]
    if unknown_apps:
        applications_by_stage[unknown_slug] = unknown_apps
        all_applications.extend(unknown_apps)

    return render_template(
        'jobs/detail.html',
        job=posting,
        applications=all_applications,
        applications_by_stage=applications_by_stage,
        pipeline_columns=pipeline_column_dicts,
        pipeline_slugs=pipeline_slugs,
    )


@bp.route('/jobs/<job_id>/preview')
@login_required
def preview_job(job_id):
    """Internal preview of the job posting (works for drafts too)."""
    posting = JobPosting.query.get_or_404(job_id)

    if posting.user_id != current_user.id:
        flash('Access denied', 'error')
        return redirect(url_for('jobs.jobs'))

    response = make_response(render_template('public/job.html', job=posting, preview_mode=True))
    response.headers['X-Frame-Options'] = 'SAMEORIGIN'
    return response


@bp.route('/jobs/<job_id>/edit', methods=['GET'])
@login_required
def edit_job(job_id):
    """Edit job posting form."""
    posting = JobPosting.query.get_or_404(job_id)

    if posting.user_id != current_user.id:
        flash('Access denied', 'error')
        return redirect(url_for('jobs.jobs'))

    return render_template('jobs/edit.html', job=posting)


def _validate_job_form(data):
    """Validate job form data. Returns dict of field -> error message (empty if valid)."""
    errors = {}
    title = (data.get('title') or '').strip()
    if not title:
        errors['title'] = 'Job title is required.'
    elif len(title) > 255:
        errors['title'] = 'Job title must be 255 characters or less.'
    for field, maxlen in [('department', 100), ('location', 255), ('seniority', 100), ('salary_range_text', 255)]:
        val = (data.get(field) or '').strip()
        if val and len(val) > maxlen:
            errors[field] = f'Must be {maxlen} characters or less.'
    status = (data.get('status') or 'draft').strip()
    if status not in ('draft', 'published'):
        errors['status'] = 'Invalid status.'
    return errors


@bp.route('/jobs/<job_id>/edit', methods=['POST'])
@login_required
def update_job(job_id):
    """Update a job posting."""
    posting = JobPosting.query.get_or_404(job_id)

    if posting.user_id != current_user.id:
        flash('Access denied', 'error')
        return redirect(url_for('jobs.jobs'))

    data = request.form
    errors = _validate_job_form(data)
    if errors:
        return render_template(
            'jobs/edit.html',
            job=posting,
            errors=errors,
            form_data={
                'title': data.get('title', posting.title),
                'department': data.get('department', posting.department or ''),
                'location': data.get('location', posting.location or ''),
                'employment_type': data.get('employment_type', posting.employment_type or ''),
                'seniority': data.get('seniority', posting.seniority or ''),
                'salary_range_text': data.get('salary_range_text', posting.salary_range_text or ''),
                'status': data.get('status', posting.status),
                'description_html': data.get('description_html', posting.description_html or ''),
                'description_raw': data.get('description_raw', posting.description_raw or ''),
            },
        ), 400

    posting.title = (data.get('title') or '').strip()
    if posting.company:
        posting.company_name = posting.company.name
        posting.company_website = posting.company.website
    posting.department = (data.get('department') or '').strip() or None
    posting.location = (data.get('location') or '').strip() or None
    posting.employment_type = (data.get('employment_type') or '').strip() or None
    posting.seniority = (data.get('seniority') or '').strip() or None
    posting.description_raw = (data.get('description_raw') or '').strip() or None
    posting.description_html = (data.get('description_html') or '').strip() or None
    posting.status = (data.get('status') or 'draft').strip()
    posting.salary_range_text = (data.get('salary_range_text') or '').strip() or None

    if posting.status == 'published' and not posting.public_id:
        posting.public_id = secrets.token_urlsafe(32)

    posting.updated_at = datetime.utcnow()
    db.session.commit()

    log_audit(current_user.id, 'job_posting_updated', 'job_posting', posting.id)
    return redirect(url_for('jobs.view_job', job_id=posting.id))


@bp.route('/jobs/<job_id>/publish', methods=['POST'])
@login_required
def publish_job(job_id):
    """Publish a job posting."""
    posting = JobPosting.query.get_or_404(job_id)

    if posting.user_id != current_user.id:
        return jsonify({'error': 'Access denied'}), 403

    posting.status = 'published'
    if not posting.public_id:
        posting.public_id = secrets.token_urlsafe(32)
    
    posting.updated_at = datetime.utcnow()
    db.session.commit()

    log_audit(current_user.id, 'job_posting_published', 'job_posting', posting.id)
    return jsonify({'success': True, 'message': 'Job published successfully'})


@bp.route('/jobs/<job_id>', methods=['DELETE'])
@login_required
def delete_job(job_id):
    """Delete a job posting and all its applications (cascade delete)."""
    posting = JobPosting.query.get_or_404(job_id)

    if posting.user_id != current_user.id:
        return jsonify({'error': 'Access denied'}), 403

    # Applications will be cascade deleted due to foreign key CASCADE
    application_count = posting.applications.count()
    
    db.session.delete(posting)
    db.session.commit()

    log_audit(current_user.id, 'job_posting_deleted', 'job_posting', job_id)
    return jsonify({'success': True, 'message': f'Job and {application_count} application(s) deleted successfully'})


@bp.route('/apply/jobs', methods=['GET'])
def public_jobs():
    """Public list of published job postings."""
    postings = JobPosting.query.filter_by(status='published').order_by(JobPosting.created_at.desc()).all()
    return render_template('public/careers.html', jobs=postings)


@bp.route('/apply/jobs/<public_id>', methods=['GET'])
def public_job(public_id):
    """Public job detail and application form."""
    posting = JobPosting.query.filter_by(public_id=public_id, status='published').first_or_404()
    return render_template('public/job.html', job=posting)


@bp.route('/apply/jobs/<public_id>', methods=['POST'])
def submit_application(public_id):
    """Submit a job application."""
    posting = JobPosting.query.filter_by(public_id=public_id, status='published').first_or_404()

    # Handle file upload
    resume_file = None
    resume_text = None
    resume_filename = None

    if 'resume' in request.files:
        file = request.files['resume']
        if file and file.filename:
            from werkzeug.utils import secure_filename
            from refcheck_app.utils.constants import ALLOWED_EXTENSIONS
            from refcheck_app.services.file_processing import extract_text_from_pdf

            filename = secure_filename(file.filename)
            if '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS:
                resume_filename = filename
                file_data = file.read()
                resume_text = extract_text_from_pdf(file_data) if filename.endswith('.pdf') else file_data.decode('utf-8', errors='ignore')

    application = JobApplication(
        job_posting_id=posting.id,
        full_name=(request.form.get('full_name') or '').strip(),
        email=(request.form.get('email') or '').strip().lower(),
        phone=(request.form.get('phone') or '').strip() or None,
        location=(request.form.get('location') or '').strip() or None,
        linkedin_url=(request.form.get('linkedin_url') or '').strip() or None,
        portfolio_url=(request.form.get('portfolio_url') or '').strip() or None,
        salary_expectations_text=(request.form.get('salary_expectations_text') or '').strip() or None,
        availability_text=(request.form.get('availability_text') or '').strip() or None,
        work_country=(request.form.get('work_country') or '').strip() or None,
        work_authorization_status=(request.form.get('work_authorization_status') or '').strip() or None,
        requires_sponsorship=request.form.get('requires_sponsorship') == 'true',
        resume_filename=resume_filename,
        resume_text=resume_text,
        cover_letter_text=(request.form.get('cover_letter_text') or '').strip() or None,
        stage='applied'
    )

    db.session.add(application)
    db.session.commit()

    return redirect(url_for('jobs.application_submitted'))


@bp.route('/apply/success', methods=['GET'])
def application_submitted():
    """Application submitted success page."""
    return render_template('public/success.html')
