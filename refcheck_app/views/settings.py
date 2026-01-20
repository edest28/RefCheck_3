"""
Settings view routes.
"""
from flask import Blueprint, render_template
from flask_login import login_required

bp = Blueprint('settings', __name__)


@bp.route('/settings')
@login_required
def settings():
    """User settings page."""
    return render_template('settings.html')
