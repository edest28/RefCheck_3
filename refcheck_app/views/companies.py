"""
Company management view routes.
"""
from flask import Blueprint, render_template, redirect, url_for, flash, request, jsonify
from flask_login import login_required, current_user
from refcheck_app.models import db, Company, JobPosting
from refcheck_app.utils.auth import log_audit
from datetime import datetime

bp = Blueprint('companies', __name__)


@bp.route('/companies')
@login_required
def list_companies():
    """List all companies for the current user."""
    companies = (
        Company.query.filter_by(user_id=current_user.id)
        .order_by(Company.updated_at.desc())
        .all()
    )
    
    # Get job counts for each company
    company_ids = [c.id for c in companies]
    job_counts = {}
    if company_ids:
        from sqlalchemy import func
        counts = db.session.query(
            JobPosting.company_id,
            func.count(JobPosting.id).label('count')
        ).filter(
            JobPosting.company_id.in_(company_ids)
        ).group_by(JobPosting.company_id).all()
        
        job_counts = {str(company_id): count for company_id, count in counts}
    
    for company in companies:
        company.job_count = job_counts.get(company.id, 0)
    
    return render_template('companies/list.html', companies=companies)


@bp.route('/companies/new', methods=['GET'])
@login_required
def new_company():
    """Create new company form."""
    return render_template('companies/new.html')


@bp.route('/companies', methods=['POST'])
@login_required
def create_company():
    """Create a new company."""
    data = request.form

    company = Company(
        user_id=current_user.id,
        name=(data.get('name') or '').strip(),
        website=(data.get('website') or '').strip() or None,
        description=(data.get('description') or '').strip() or None,
    )

    if not company.name:
        flash('Company name is required', 'error')
        return render_template('companies/new.html')

    db.session.add(company)
    db.session.commit()

    log_audit(current_user.id, 'company_created', 'company', company.id)
    flash('Company created successfully', 'success')
    return redirect(url_for('companies.view_company', company_id=company.id))


@bp.route('/companies/<company_id>')
@login_required
def view_company(company_id):
    """View company details and jobs."""
    company = Company.query.get_or_404(company_id)

    if company.user_id != current_user.id:
        flash('Access denied', 'error')
        return redirect(url_for('companies.list_companies'))

    jobs = company.jobs.order_by(JobPosting.updated_at.desc()).all()
    
    # Get applicant counts for jobs
    job_ids = [j.id for j in jobs]
    applicant_counts = {}
    if job_ids:
        from sqlalchemy import func
        from refcheck_app.models import JobApplication
        counts = db.session.query(
            JobApplication.job_posting_id,
            func.count(JobApplication.id).label('count')
        ).filter(
            JobApplication.job_posting_id.in_(job_ids)
        ).group_by(JobApplication.job_posting_id).all()
        
        applicant_counts = {str(job_id): count for job_id, count in counts}
    
    for job in jobs:
        job.applicant_count = applicant_counts.get(job.id, 0)

    return render_template('companies/detail.html', company=company, jobs=jobs)


@bp.route('/companies/<company_id>/edit', methods=['GET'])
@login_required
def edit_company(company_id):
    """Edit company form."""
    company = Company.query.get_or_404(company_id)

    if company.user_id != current_user.id:
        flash('Access denied', 'error')
        return redirect(url_for('companies.list_companies'))

    return render_template('companies/edit.html', company=company)


@bp.route('/companies/<company_id>/edit', methods=['POST'])
@login_required
def update_company(company_id):
    """Update a company."""
    company = Company.query.get_or_404(company_id)

    if company.user_id != current_user.id:
        return jsonify({'error': 'Access denied'}), 403

    data = request.form

    company.name = (data.get('name') or '').strip()
    company.website = (data.get('website') or '').strip() or None
    company.description = (data.get('description') or '').strip() or None

    if not company.name:
        flash('Company name is required', 'error')
        return render_template('companies/edit.html', company=company)

    company.updated_at = datetime.utcnow()
    db.session.commit()

    log_audit(current_user.id, 'company_updated', 'company', company.id)
    flash('Company updated successfully', 'success')
    return redirect(url_for('companies.view_company', company_id=company.id))


@bp.route('/companies/<company_id>', methods=['DELETE'])
@login_required
def delete_company(company_id):
    """Delete a company and all its jobs (cascade delete)."""
    company = Company.query.get_or_404(company_id)

    if company.user_id != current_user.id:
        return jsonify({'error': 'Access denied'}), 403

    # Jobs will be cascade deleted due to relationship configuration
    job_count = company.jobs.count()
    
    db.session.delete(company)
    db.session.commit()

    log_audit(current_user.id, 'company_deleted', 'company', company_id)
    return jsonify({'success': True, 'message': f'Company and {job_count} job(s) deleted successfully'})
