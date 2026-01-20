"""
Job posting API routes.
"""
from flask import Blueprint, request, jsonify
from flask_login import current_user
from refcheck_app.models import db, JobPosting
from refcheck_app.utils.auth import api_login_required, log_audit
from refcheck_app.services.ai.jd_generator import generate_job_description_with_claude
from refcheck_app.config import Config

bp = Blueprint('jobs_api', __name__, url_prefix='/api/jobs')


@bp.route('/ai-generate-jd', methods=['POST'])
@api_login_required
def ai_generate_jd():
    """Generate a job description using Claude."""
    from refcheck_app.models import Company
    
    data = request.json or {}
    title = (data.get('title') or '').strip()
    if not title:
        return jsonify({'error': 'title is required'}), 400

    # Get company info from company_id if provided, otherwise from form data
    company_name = None
    company_website = None
    
    company_id = data.get('company_id')
    if company_id:
        company = Company.query.filter_by(id=company_id, user_id=current_user.id).first()
        if company:
            company_name = company.name
            company_website = company.website
    
    # Fallback to form data or user's company_name
    if not company_name:
        company_name = (data.get('company_name') or current_user.company_name or '').strip() or None
    if not company_website:
        company_website = (data.get('company_website') or '').strip() or None

    result = generate_job_description_with_claude(
        title=title,
        department=(data.get('department') or '').strip() or None,
        seniority=(data.get('seniority') or '').strip() or None,
        location=(data.get('location') or '').strip() or None,
        focus_areas=(data.get('focus_areas') or '').strip() or None,
        company_name=company_name,
        company_website=company_website,
        api_key=Config.ANTHROPIC_API_KEY,
    )

    if not result:
        return jsonify({'error': 'Failed to generate job description'}), 500

    log_audit(current_user.id, 'job_description_generated_ai', details={'title': title})
    return jsonify(result)
