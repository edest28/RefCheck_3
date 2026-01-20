"""
Production WSGI entry point.

Uses lazy initialization to ensure the app is created at runtime,
after Railway has injected environment variables.
"""
import os

# Global to hold the app instance
_app = None


def get_app():
    """Get or create the Flask app instance."""
    global _app
    if _app is None:
        # Import here to ensure environment variables are available at runtime
        from app import create_app
        _app = create_app(os.environ.get('FLASK_ENV', 'production'))
    return _app


# For gunicorn: this callable will be invoked for each request
# The first invocation creates the app, subsequent ones reuse it
def app(environ, start_response):
    """WSGI application entry point."""
    return get_app()(environ, start_response)


if __name__ == '__main__':
    get_app().run()
