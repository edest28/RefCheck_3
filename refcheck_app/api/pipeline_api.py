"""
Pipeline (Kanban columns) API - account-wide config.
"""
import uuid as uuid_mod
from flask import Blueprint, request, jsonify
from flask_login import current_user
from refcheck_app.models import db, PipelineColumn, JobPosting, JobApplication
from refcheck_app.utils.auth import api_login_required, log_audit

bp = Blueprint('pipeline_api', __name__, url_prefix='/api/pipeline')


@bp.route('', methods=['GET'])
@api_login_required
def get_pipeline():
    """Get current user's pipeline columns (ordered)."""
    columns = (
        PipelineColumn.query.filter_by(user_id=current_user.id)
        .order_by(PipelineColumn.order.asc(), PipelineColumn.slug.asc())
        .all()
    )
    return jsonify({'columns': [c.to_dict() for c in columns]})


@bp.route('', methods=['PATCH', 'PUT'])
@api_login_required
def update_pipeline():
    """Update pipeline columns. Payload: { columns: [ { id?, slug, label, order, is_action_triggering } ] }."""
    data = request.json or {}
    columns_payload = data.get('columns')
    if not isinstance(columns_payload, list):
        return jsonify({'error': 'columns array required'}), 400

    existing = {
        c.id: c
        for c in PipelineColumn.query.filter_by(user_id=current_user.id).all()
    }
    existing_by_slug = {c.slug: c for c in existing.values()}
    new_slugs = set()
    to_keep_ids = set()
    first_slug = None

    for i, item in enumerate(columns_payload):
        if not isinstance(item, dict):
            continue
        slug = (item.get('slug') or '').strip() or f"column_{uuid_mod.uuid4().hex[:12]}"
        label = (item.get('label') or slug).strip() or slug
        order = int(item.get('order', i))
        is_action = bool(item.get('is_action_triggering', False))
        if first_slug is None:
            first_slug = slug
        col_id = item.get('id')
        if col_id and col_id in existing:
            col = existing[col_id]
            col.label = label
            col.order = order
            col.is_action_triggering = is_action
            to_keep_ids.add(col_id)
            new_slugs.add(col.slug)
        else:
            new_col = PipelineColumn(
                user_id=current_user.id,
                slug=slug,
                label=label,
                order=order,
                is_action_triggering=is_action,
            )
            db.session.add(new_col)
            db.session.flush()
            to_keep_ids.add(new_col.id)
            new_slugs.add(slug)

    deleted = [c for c in existing.values() if c.id not in to_keep_ids]
    deleted_slugs = [c.slug for c in deleted]
    if deleted_slugs and first_slug:
        job_ids = [p.id for p in JobPosting.query.filter_by(user_id=current_user.id).all()]
        if job_ids:
            JobApplication.query.filter(
                JobApplication.job_posting_id.in_(job_ids),
                JobApplication.stage.in_(deleted_slugs),
            ).update({JobApplication.stage: first_slug}, synchronize_session=False)
    for c in deleted:
        db.session.delete(c)

    db.session.commit()
    log_audit(current_user.id, 'pipeline_updated', details={'columns_count': len(columns_payload)})

    columns = (
        PipelineColumn.query.filter_by(user_id=current_user.id)
        .order_by(PipelineColumn.order.asc(), PipelineColumn.slug.asc())
        .all()
    )
    return jsonify({'success': True, 'columns': [c.to_dict() for c in columns]})
