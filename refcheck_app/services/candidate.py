"""
Candidate management services.
"""
import json
from refcheck_app.models import Candidate, Job, db


def create_candidate_from_resume(user_id, parsed_data, resume_text=None, resume_filename=None):
    """Create a candidate and associated jobs from parsed resume data."""

    candidate = Candidate(
        user_id=user_id,
        name=parsed_data.get('candidate_name', 'Unknown'),
        email=parsed_data.get('email', ''),
        phone=parsed_data.get('phone', ''),
        summary=parsed_data.get('summary', ''),
        skills=json.dumps(parsed_data.get('skills', [])),
        resume_text=resume_text,
        resume_filename=resume_filename,
        status='intake'
    )

    db.session.add(candidate)
    db.session.commit()  # Commit to get candidate ID

    # Create jobs
    for idx, job_data in enumerate(parsed_data.get('jobs', [])):
        job = Job(
            candidate_id=candidate.id,
            company=job_data.get('company', 'Unknown'),
            title=job_data.get('title', ''),
            dates=job_data.get('dates', ''),
            order=idx,
            responsibilities=json.dumps(job_data.get('responsibilities', [])),
            achievements=json.dumps(job_data.get('achievements', []))
        )
        db.session.add(job)

    db.session.commit()
    return candidate


def search_candidates(user_id, query, status=None, limit=50):
    """Search candidates by query string."""

    base_query = Candidate.query.filter_by(user_id=user_id)

    if status:
        base_query = base_query.filter_by(status=status)

    if query:
        search_term = f"%{query.lower()}%"
        base_query = base_query.filter(Candidate.search_vector.ilike(search_term))

    return base_query.order_by(Candidate.updated_at.desc()).limit(limit).all()
