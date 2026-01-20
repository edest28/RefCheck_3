"""
Flask application factory for RefCheck AI.
"""
import os
from flask import Flask


def create_app(config_name='default'):
    """Create and configure the Flask application."""
    import sys
    
    # Import these inside the function to avoid import-time side effects
    from refcheck_app.config import config
    from refcheck_app.extensions import login_manager, migrate
    from refcheck_app.models import db, User
    
    # Debug: Print all environment variables containing DATABASE or POSTGRES
    print(f"[APP INIT] Environment vars with DATABASE/POSTGRES:", file=sys.stderr)
    for key, value in os.environ.items():
        if 'DATABASE' in key.upper() or 'POSTGRES' in key.upper() or 'PG' in key.upper():
            # Mask password in output
            masked = value[:20] + '...' if len(value) > 20 else value
            print(f"[APP INIT]   {key}={masked}", file=sys.stderr)
    
    # Debug: Print database configuration
    database_url = os.environ.get('DATABASE_URL')
    print(f"[APP INIT] DATABASE_URL from env: {'SET' if database_url else 'NOT SET'}", file=sys.stderr)
    print(f"[APP INIT] Config name: {config_name}", file=sys.stderr)
    
    # Set template folder to project root templates directory
    template_folder = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'templates')
    app = Flask(__name__, template_folder=template_folder)
    
    # Load configuration
    app.config.from_object(config[config_name])
    
    # IMPORTANT: Override database URL from environment at runtime
    # This is necessary because class attributes are evaluated at import time,
    # before Railway injects environment variables
    if database_url:
        app.config['SQLALCHEMY_DATABASE_URI'] = database_url
        print(f"[APP INIT] Using DATABASE_URL from environment", file=sys.stderr)
    
    # Handle PostgreSQL URL format from Heroku/Railway
    if app.config['SQLALCHEMY_DATABASE_URI'].startswith('postgres://'):
        app.config['SQLALCHEMY_DATABASE_URI'] = app.config['SQLALCHEMY_DATABASE_URI'].replace(
            'postgres://', 'postgresql://', 1
        )
    
    # Log final DB type (not the full URL for security)
    db_uri = app.config['SQLALCHEMY_DATABASE_URI']
    db_type = 'postgresql' if 'postgresql' in db_uri else 'sqlite' if 'sqlite' in db_uri else 'unknown'
    print(f"[APP INIT] Final DB type: {db_type}", file=sys.stderr)
    
    # Initialize extensions
    db.init_app(app)
    migrate.init_app(app, db)
    login_manager.init_app(app)
    
    # Configure login manager
    login_manager.login_view = 'auth.login'
    login_manager.login_message = 'Please log in to access this page.'
    login_manager.login_message_category = 'info'
    
    @login_manager.user_loader
    def load_user(user_id):
        return User.query.get(user_id)
    
    # Register blueprints
    from refcheck_app.views import auth, dashboard, candidates, jobs, settings, public, companies
    from refcheck_app.api import candidates_api, references_api, calls_api, jobs_api, applications_api, settings_api, search_api
    
    app.register_blueprint(auth.bp)
    app.register_blueprint(dashboard.bp)
    app.register_blueprint(candidates.bp)
    app.register_blueprint(companies.bp)
    app.register_blueprint(jobs.bp)
    app.register_blueprint(settings.bp)
    app.register_blueprint(public.bp)
    
    app.register_blueprint(candidates_api.bp)
    app.register_blueprint(references_api.bp)
    app.register_blueprint(calls_api.bp)
    app.register_blueprint(jobs_api.bp)
    app.register_blueprint(applications_api.bp)
    app.register_blueprint(settings_api.bp)
    app.register_blueprint(search_api.bp)
    
    # Register error handlers
    from flask import render_template
    
    @app.errorhandler(404)
    def not_found(error):
        return render_template('errors/404.html'), 404
    
    @app.errorhandler(500)
    def internal_error(error):
        db.session.rollback()
        return render_template('errors/500.html'), 500
    
    # Database initialization
    @app.before_request
    def ensure_tables():
        """Ensure database tables exist."""
        if not hasattr(app, '_db_initialized'):
            with app.app_context():
                db.create_all()
            app._db_initialized = True
    
    # Custom Jinja filter for JSON parsing
    @app.template_filter('from_json')
    def from_json_filter(value):
        import json
        if not value:
            return []
        try:
            return json.loads(value)
        except:
            return []
    
    return app


# NOTE: Do NOT create app at module level!
# The app must be created at runtime (not import time) to ensure
# Railway's environment variables are available.
# Use wsgi.py as the entry point for gunicorn.
