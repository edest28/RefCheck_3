"""
Dashboard view routes.
"""
from flask import Blueprint, render_template, redirect, url_for
from flask_login import login_required, current_user

bp = Blueprint('dashboard', __name__)


@bp.route('/')
def index():
    """Landing page or dashboard."""
    if current_user.is_authenticated:
        return redirect(url_for('dashboard.dashboard'))
    return redirect(url_for('auth.login'))


@bp.route('/dashboard')
@login_required
def dashboard():
    """Main dashboard."""
    return render_template('candidates/dashboard.html')
