"""
Production WSGI entry point.
"""
import os
from app import create_app

# Create the Flask application
# Environment variables should be available at this point when gunicorn loads the module
app = create_app(os.environ.get('FLASK_ENV', 'production'))

if __name__ == '__main__':
    app.run()
