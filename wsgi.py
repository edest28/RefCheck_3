"""
Production WSGI entry point.
"""
import os
from refcheck_app import create_app

# Create the Flask application
app = create_app(os.environ.get('FLASK_ENV', 'production'))

if __name__ == '__main__':
    app.run()
