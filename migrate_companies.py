"""
Migration script to convert existing company_name values to Company records.
Run this after adding the Company model and company_id to JobPosting.
"""
import sys
import os

# Add the parent directory to the path so we can import app
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app import create_app
from app.models import db, Company, JobPosting, User

app = create_app('development')

with app.app_context():
    print("Starting company migration...")
    
    # Get all users
    users = User.query.all()
    
    for user in users:
        print(f"\nProcessing user: {user.email}")
        
        # Get all unique company names for this user's jobs
        jobs = JobPosting.query.filter_by(user_id=user.id).all()
        company_names = {}
        
        for job in jobs:
            if job.company_name and job.company_name.strip():
                name = job.company_name.strip()
                website = job.company_website.strip() if job.company_website else None
                
                # Group by company name
                if name not in company_names:
                    company_names[name] = {
                        'website': website,
                        'jobs': []
                    }
                company_names[name]['jobs'].append(job)
        
        # Create Company records
        for company_name, data in company_names.items():
            # Check if company already exists for this user
            existing = Company.query.filter_by(
                user_id=user.id,
                name=company_name
            ).first()
            
            if existing:
                print(f"  Company '{company_name}' already exists, linking jobs...")
                company = existing
            else:
                print(f"  Creating company: {company_name}")
                company = Company(
                    user_id=user.id,
                    name=company_name,
                    website=data['website']
                )
                db.session.add(company)
                db.session.flush()  # Get the ID
            
            # Link jobs to company
            for job in data['jobs']:
                if not job.company_id:
                    job.company_id = company.id
                    print(f"    Linked job '{job.title}' to company")
        
        db.session.commit()
        print(f"  Completed migration for user {user.email}")
    
    print("\nMigration complete!")
    print("\nSummary:")
    total_companies = Company.query.count()
    jobs_with_companies = JobPosting.query.filter(JobPosting.company_id.isnot(None)).count()
    total_jobs = JobPosting.query.count()
    
    print(f"  Total companies created: {total_companies}")
    print(f"  Jobs linked to companies: {jobs_with_companies} / {total_jobs}")
