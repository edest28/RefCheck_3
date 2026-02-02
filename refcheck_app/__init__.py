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
    
    # Get database URL from environment
    database_url = os.environ.get('DATABASE_URL')
    
    # Set template and static folders to project root (same level as refcheck_app/)
    root = os.path.dirname(os.path.dirname(__file__))
    template_folder = os.path.join(root, 'templates')
    static_folder = os.path.join(root, 'static')
    app = Flask(__name__, template_folder=template_folder, static_folder=static_folder)
    
    # Load configuration
    app.config.from_object(config[config_name])
    
    # IMPORTANT: Override database URL from environment at runtime
    # This is necessary because class attributes are evaluated at import time,
    # before Railway injects environment variables
    if database_url:
        app.config['SQLALCHEMY_DATABASE_URI'] = database_url
    
    # Handle PostgreSQL URL format from Heroku/Railway
    if app.config['SQLALCHEMY_DATABASE_URI'].startswith('postgres://'):
        app.config['SQLALCHEMY_DATABASE_URI'] = app.config['SQLALCHEMY_DATABASE_URI'].replace(
            'postgres://', 'postgresql://', 1
        )
    
    # Initialize extensions
    db.init_app(app)
    migrate.init_app(app, db)
    login_manager.init_app(app)
    
    # Configure login manager
    login_manager.login_view = 'auth.login'
    login_manager.login_message = 'Please log in to access this page.'
    login_manager.login_message_category = 'info'
    login_manager.session_protection = None  # Disable session protection to avoid logout issues
    
    @login_manager.user_loader
    def load_user(user_id):
        """Load user from database for Flask-Login."""
        try:
            return User.query.get(user_id)
        except Exception as e:
            import logging
            logging.error(f"Error loading user {user_id}: {e}")
            return None
    
    # Register blueprints
    from refcheck_app.views import auth, dashboard, candidates, jobs, settings, public, companies
    from refcheck_app.api import candidates_api, references_api, calls_api, jobs_api, applications_api, settings_api, search_api, pipeline_api
    
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
    app.register_blueprint(pipeline_api.bp)
    
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
