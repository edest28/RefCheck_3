"""
Production WSGI entry point.
"""
import os
import sys

# Add the app directory to path to ensure we import the package, not any app.py file
app_package_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'app')
if os.path.isdir(app_package_path):
    # Force Python to treat 'app' as a package by importing from the directory
    import importlib.util
    spec = importlib.util.spec_from_file_location("app", os.path.join(app_package_path, "__init__.py"))
    app_module = importlib.util.module_from_spec(spec)
    sys.modules["app"] = app_module
    spec.loader.exec_module(app_module)
    create_app = app_module.create_app
else:
    # Fallback to normal import
    from app import create_app

# Create the Flask application
flask_app = create_app(os.environ.get('FLASK_ENV', 'production'))

# For gunicorn - this must be named 'app'
app = flask_app

if __name__ == '__main__':
    app.run()
