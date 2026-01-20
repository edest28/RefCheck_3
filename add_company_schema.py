"""
Migration script to add Company table and company_id column to job_postings.
Run this once to update the database schema.
"""
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app import create_app
from app.models import db, Company, JobPosting
from sqlalchemy import inspect, text
import os

# Set the database path explicitly
os.environ.setdefault('DATABASE_URL', 'sqlite:///instance/refcheck.db')

app = create_app('development')

with app.app_context():
    print("Starting database migration...")
    
    inspector = inspect(db.engine)
    
    # Check if companies table exists
    tables = inspector.get_table_names()
    companies_exists = 'companies' in tables
    
    if not companies_exists:
        print("Creating companies table...")
        Company.__table__.create(db.engine)
        print("✓ Companies table created")
    else:
        print("✓ Companies table already exists")
    
    # Check if company_id column exists in job_postings
    job_postings_columns = [col['name'] for col in inspector.get_columns('job_postings')]
    company_id_exists = 'company_id' in job_postings_columns
    
    if not company_id_exists:
        print("Adding company_id column to job_postings table...")
        try:
            with db.engine.connect() as conn:
                conn.execute(text("ALTER TABLE job_postings ADD COLUMN company_id VARCHAR(36)"))
                conn.commit()
            print("✓ company_id column added")
        except Exception as e:
            print(f"Error adding column: {e}")
            # Try with different SQL syntax
            try:
                with db.engine.connect() as conn:
                    conn.execute(text("ALTER TABLE job_postings ADD COLUMN company_id TEXT"))
                    conn.commit()
                print("✓ company_id column added (using TEXT type)")
            except Exception as e2:
                print(f"Error with alternative syntax: {e2}")
                raise
    else:
        print("✓ company_id column already exists")
    
    # Create foreign key constraint if it doesn't exist
    print("Checking foreign key constraints...")
    try:
        # SQLite doesn't support adding foreign keys via ALTER TABLE easily
        # We'll rely on SQLAlchemy's relationship handling
        print("✓ Foreign key relationship will be handled by SQLAlchemy")
    except Exception as e:
        print(f"Note: {e}")
    
    print("\nMigration complete!")
    print("\nNext steps:")
    print("1. Run migrate_companies.py to convert existing company_name values to Company records")
    print("2. Restart your Flask application")
