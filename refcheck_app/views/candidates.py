"""
Candidate view routes.
"""
from flask import Blueprint, render_template, redirect, url_for, flash
from flask_login import login_required, current_user
from refcheck_app.models import Candidate
from refcheck_app.utils.constants import DEFAULT_SMS_TEMPLATE

bp = Blueprint('candidates', __name__)


@bp.route('/candidate/new')
@login_required
def new_candidate():
    """New candidate intake page."""
    sms_template = current_user.sms_template or DEFAULT_SMS_TEMPLATE
    return render_template('candidates/new_candidate.html', sms_template=sms_template)


@bp.route('/candidate/<candidate_id>')
@login_required
def view_candidate(candidate_id):
    """View candidate details."""
    candidate = Candidate.query.get_or_404(candidate_id)

    if candidate.user_id != current_user.id:
        flash('Access denied', 'error')
        return redirect(url_for('dashboard.dashboard'))

    return render_template('candidates/detail.html', candidate_id=candidate_id)
