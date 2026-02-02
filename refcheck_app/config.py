"""
Configuration management for RefCheck AI.
"""
import hashlib
import logging
import os
from dotenv import load_dotenv

load_dotenv()


def _get_secret_key():
    """Read SECRET_KEY from env; support common alternate names and treat empty as unset."""
    for name in ("SECRET_KEY", "FLASK_SECRET_KEY"):
        val = os.environ.get(name)
        if val and isinstance(val, str) and val.strip():
            return val.strip()
    return None


def _production_secret_fallback():
    """Deterministic key from DATABASE_URL so all Gunicorn workers share the same key."""
    url = os.environ.get("DATABASE_URL") or ""
    if not url:
        return None
    return hashlib.sha256(url.encode()).hexdigest()


class Config:
    """Base configuration."""
    # SECRET_KEY: prefer env vars; base class does not raise so deployment always succeeds.
    SECRET_KEY = _get_secret_key()
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SQLALCHEMY_ENGINE_OPTIONS = {
        'pool_pre_ping': True,
        'pool_recycle': 300,
    }
    MAX_CONTENT_LENGTH = 16 * 1024 * 1024  # 16MB
    
    # Global API keys (shared across all users)
    ANTHROPIC_API_KEY = os.environ.get('ANTHROPIC_API_KEY')
    VAPI_API_KEY = os.environ.get('VAPI_API_KEY')
    VAPI_PHONE_NUMBER_ID = os.environ.get('VAPI_PHONE_NUMBER_ID')
    TWILIO_ACCOUNT_SID = os.environ.get('TWILIO_ACCOUNT_SID')
    TWILIO_AUTH_TOKEN = os.environ.get('TWILIO_AUTH_TOKEN')
    TWILIO_PHONE_NUMBER = os.environ.get('TWILIO_PHONE_NUMBER')
    RESEND_API_KEY = os.environ.get('RESEND_API_KEY')
    
    ALLOWED_EXTENSIONS = {'pdf', 'txt', 'doc', 'docx'}


class DevelopmentConfig(Config):
    """Development configuration."""
    DEBUG = True
    # Use absolute path for database to avoid working directory issues
    _db_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'instance', 'refcheck.db')
    SQLALCHEMY_DATABASE_URI = os.environ.get(
        'DATABASE_URL',
        f'sqlite:///{_db_path}'
    )
    if not Config.SECRET_KEY:
        SECRET_KEY = "dev-secret-key-change-in-production"


class ProductionConfig(Config):
    """Production configuration."""
    DEBUG = False
    SQLALCHEMY_DATABASE_URI = os.environ.get('DATABASE_URL', 'sqlite:///instance/refcheck.db')
    # Ensure a stable SECRET_KEY so all Gunicorn workers share the same key (sessions work).
    # Prefer explicit SECRET_KEY; if missing, use deterministic fallback from DATABASE_URL.
    if not Config.SECRET_KEY:
        _fallback = _production_secret_fallback()
        if _fallback:
            SECRET_KEY = _fallback
            logging.warning(
                "SECRET_KEY not set; using deterministic key from DATABASE_URL. "
                "Set SECRET_KEY in Railway for stronger security."
            )
        else:
            SECRET_KEY = "production-change-me-set-SECRET_KEY"
    
    # Session cookie security for production
    SESSION_COOKIE_HTTPONLY = True  # Prevent JavaScript access to cookies
    SESSION_COOKIE_SAMESITE = 'Lax'  # CSRF protection
    PERMANENT_SESSION_LIFETIME = 86400  # 24 hours in seconds
    
    # Handle PostgreSQL URL format from Heroku/Railway
    @staticmethod
    def init_app(app):
        import os
        # SESSION_COOKIE_SECURE: Default to False for Railway compatibility
        # Railway proxies HTTPS but the app might not detect it correctly
        # Set SESSION_COOKIE_SECURE=true in env if you're sure HTTPS is working
        app.config['SESSION_COOKIE_SECURE'] = os.environ.get('SESSION_COOKIE_SECURE', 'false').lower() == 'true'
        
        # Ensure session cookie path is root so it works for all routes
        app.config['SESSION_COOKIE_PATH'] = '/'
        
        if app.config['SQLALCHEMY_DATABASE_URI'].startswith('postgres://'):
            app.config['SQLALCHEMY_DATABASE_URI'] = app.config['SQLALCHEMY_DATABASE_URI'].replace(
                'postgres://', 'postgresql://', 1
            )


class TestingConfig(Config):
    """Testing configuration."""
    TESTING = True
    SQLALCHEMY_DATABASE_URI = 'sqlite:///:memory:'
    if not Config.SECRET_KEY:
        SECRET_KEY = "test-secret-key"


# Configuration dictionary
config = {
    'development': DevelopmentConfig,
    'production': ProductionConfig,
    'testing': TestingConfig,
    'default': DevelopmentConfig
}
