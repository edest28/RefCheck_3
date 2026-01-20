"""
Public-facing view routes (reference submission, surveys).
"""
from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify
from app.models import db, ReferenceRequest, SurveyRequest, Candidate, Reference, SurveyQuestion, SurveyResponse
from app.utils.constants import STANDARDIZED_SURVEY_QUESTIONS
from app.services.reference import get_survey_questions_for_reference, analyze_survey_responses
from app.services.communication.email import send_survey_confirmation_email
from app.config import Config
from datetime import datetime, timedelta
import json

bp = Blueprint('public', __name__)


@bp.route('/submit-references/<token>', methods=['GET'])
def submit_references_form(token):
    """Reference submission form."""
    request_obj = ReferenceRequest.query.filter_by(token=token).first_or_404()

    if not request_obj.is_valid():
        flash('This reference request has expired or is no longer valid.', 'error')
        return render_template('public/reference_expired.html')

    candidate = request_obj.candidate
    return render_template('shared/submit_references.html', candidate=candidate, token=token)


@bp.route('/submit-references/<token>', methods=['POST'])
def submit_references(token):
    """Process reference submission."""
    request_obj = ReferenceRequest.query.filter_by(token=token).first_or_404()

    if not request_obj.is_valid():
        return jsonify({'error': 'Request expired'}), 400

    candidate = request_obj.candidate
    data = request.json or {}

    # Create references
    references_data = data.get('references', [])
    for ref_data in references_data:
        job_id = ref_data.get('job_id')
        reference = Reference(
            candidate_id=candidate.id,
            job_id=job_id,
            name=ref_data.get('name', '').strip(),
            phone=ref_data.get('phone', '').strip(),
            email=ref_data.get('email', '').strip() or None,
            relationship=ref_data.get('relationship', '').strip() or None,
            contact_method=ref_data.get('contact_method', 'call_only')
        )
        db.session.add(reference)

    request_obj.status = 'completed'
    request_obj.completed_at = datetime.utcnow()
    db.session.commit()

    return jsonify({'success': True})


@bp.route('/submit-survey/<token>', methods=['GET'])
def submit_survey_form(token):
    """Survey submission form."""
    survey_request = SurveyRequest.query.filter_by(token=token).first_or_404()

    if not survey_request.is_valid():
        flash('This survey has expired or is no longer valid.', 'error')
        return render_template('public/survey_expired.html')

    questions = survey_request.questions.order_by(SurveyQuestion.order).all()
    return render_template('shared/survey_form.html', survey_request=survey_request, questions=questions)


@bp.route('/submit-survey/<token>', methods=['POST'])
def submit_survey(token):
    """Process survey submission."""
    survey_request = SurveyRequest.query.filter_by(token=token).first_or_404()

    if not survey_request.is_valid():
        return jsonify({'error': 'Survey expired'}), 400

    data = request.json or {}
    responses = data.get('responses', {})

    # Save responses
    for question_id, response_data in responses.items():
        question = SurveyQuestion.query.get(question_id)
        if not question or question.survey_request_id != survey_request.id:
            continue

        # Check if response already exists
        existing_response = question.response
        if existing_response:
            response = existing_response
        else:
            response = SurveyResponse(survey_question_id=question.id)
            db.session.add(response)

        # Set response based on type
        if question.response_type == 'rating':
            response.rating = int(response_data) if response_data else None
        elif question.response_type in ['multiple_choice', 'yes_no_maybe']:
            response.selected_option = str(response_data) if response_data else None
        else:  # free_text
            response.text_response = str(response_data) if response_data else None

    survey_request.status = 'completed'
    survey_request.completed_at = datetime.utcnow()
    db.session.commit()

    # Analyze responses
    if Config.ANTHROPIC_API_KEY:
        analysis = analyze_survey_responses(
            survey_request,
            survey_request.reference.candidate.name,
            survey_request.reference.job,
            Config.ANTHROPIC_API_KEY
        )
        if analysis:
            survey_request.survey_score = analysis.get('score')
            survey_request.survey_summary = analysis.get('summary')
            survey_request.survey_red_flags = json.dumps(analysis.get('red_flags', []))
            survey_request.survey_analysis = json.dumps(analysis)
            db.session.commit()

    # Send confirmation email
    if Config.RESEND_API_KEY:
        send_survey_confirmation_email(survey_request.reference, survey_request.reference.candidate, Config.RESEND_API_KEY)

    return jsonify({'success': True})
