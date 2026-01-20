"""
Flask application factory for RefCheck AI.
"""
from flask import Flask
from app.config import config
from app.extensions import login_manager, migrate
from app.models import db, User


def create_app(config_name='default'):
    """Create and configure the Flask application."""
    import os
    # Set template folder to project root templates directory
    template_folder = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'templates')
    app = Flask(__name__, template_folder=template_folder)
    
    # Load configuration
    app.config.from_object(config[config_name])
    
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
    
    @login_manager.user_loader
    def load_user(user_id):
        return User.query.get(user_id)
    
    # Register blueprints
    from app.views import auth, dashboard, candidates, jobs, settings, public, companies
    from app.api import candidates_api, references_api, calls_api, jobs_api, applications_api, settings_api, search_api
    
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
