import os
from dotenv import load_dotenv
load_dotenv()  # Load .env file if present
basedir = os.path.abspath(os.path.dirname(__file__))

class Config:
    # Flask configuration
    SECRET_KEY = os.environ.get('SECRET_KEY') or 'your-secret-key-here'
    DEBUG = False
    
    # SQLAlchemy configuration
    # Use SQLite for development by default, MySQL via DATABASE_URL env var for production
    SQLALCHEMY_DATABASE_URI = os.environ.get('DATABASE_URL') or \
        'sqlite:///' + os.path.join(basedir, 'instance', 'codechef_tracker.db')
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    
    # APScheduler configuration
    SCHEDULER_API_ENABLED = True
    SCHEDULER_TIMEZONE = 'Asia/Kolkata'
    
    # CodeChef API configuration
    CODECHEF_BASE_URL = 'https://www.codechef.com'
    
    # Gemini AI configuration
    GEMINI_API_KEY = os.environ.get('GEMINI_API_KEY')
    
    # File upload configuration
    MAX_CONTENT_LENGTH = 16 * 1024 * 1024  # 16MB max file size
    
    # Bootstrap configuration
    BOOTSTRAP_SERVE = True


class DevelopmentConfig(Config):
    DEBUG = True


class ProductionConfig(Config):
    DEBUG = False


config = {
    'development': DevelopmentConfig,
    'production': ProductionConfig,
    'default': DevelopmentConfig
}