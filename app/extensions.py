"""
Flask extensions initialization.
"""
from flask_login import LoginManager
from flask_migrate import Migrate

login_manager = LoginManager()
login_manager.login_view = 'auth.login'
login_manager.login_message = 'Please log in to access this page.'
login_manager.login_message_category = 'info'

migrate = Migrate()
