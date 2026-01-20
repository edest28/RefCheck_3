"""
Search API routes.
"""
from flask import Blueprint, request, jsonify
from flask_login import current_user
from refcheck_app.utils.auth import api_login_required
from refcheck_app.services.candidate import search_candidates

bp = Blueprint('search_api', __name__, url_prefix='/api/search')


@bp.route('', methods=['GET'])
@api_login_required
def search():
    """Search candidates."""
    query = request.args.get('q', '').strip()
    status = request.args.get('status', '').strip() or None

    if not query:
        return jsonify({'error': 'Query parameter required'}), 400

    candidates = search_candidates(current_user.id, query, status)
    return jsonify([c.to_dict() for c in candidates])
