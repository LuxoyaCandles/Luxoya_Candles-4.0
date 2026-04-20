import os
import socket
from urllib.parse import urlparse
from datetime import timedelta

# Detect serverless environment (VERCEL, Google Cloud Functions, etc.)
IS_VERCEL = os.environ.get('VERCEL', '') == '1'
IS_SERVERLESS = IS_VERCEL or os.environ.get('FUNCTION_NAME') or os.environ.get('K_SERVICE')


def _normalize_postgres_url(db_url):
    if db_url.startswith('postgres://'):
        return db_url.replace('postgres://', 'postgresql://', 1)
    return db_url


def _db_host_resolves(db_url):
    """Return True if database host resolves via DNS; False otherwise."""
    try:
        parsed = urlparse(db_url)
        if not parsed.hostname:
            return False
        socket.getaddrinfo(parsed.hostname, parsed.port or 5432)
        return True
    except Exception:
        return False


class Config:
    """Base configuration."""
    SECRET_KEY = os.environ.get('SECRET_KEY', 'luxoya-secret-key-change-in-production')
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    OPENAI_API_KEY = os.environ.get('OPENAI_API_KEY', '')

    # Database engine options – prevent hanging on cold Neon DB
    _db_is_pg = os.environ.get('DATABASE_URL', '').startswith(('postgresql', 'postgres'))

    if IS_VERCEL:
        # Serverless: use NullPool (one connection per invocation, no pooling)
        from sqlalchemy.pool import NullPool
        SQLALCHEMY_ENGINE_OPTIONS = {
            'pool_pre_ping': True,
            'poolclass': NullPool,
        }
        if _db_is_pg:
            SQLALCHEMY_ENGINE_OPTIONS['connect_args'] = {'connect_timeout': 5}
    else:
        SQLALCHEMY_ENGINE_OPTIONS = {
            'pool_pre_ping': True,
            'pool_recycle': 300,
        }
        if _db_is_pg:
            SQLALCHEMY_ENGINE_OPTIONS['connect_args'] = {'connect_timeout': 3}
    
    # JWT Configuration
    JWT_SECRET_KEY = os.environ.get('JWT_SECRET_KEY', 'luxoya-jwt-secret-change-in-production')
    JWT_ACCESS_TOKEN_EXPIRES = timedelta(hours=24)
    JWT_REFRESH_TOKEN_EXPIRES = timedelta(days=30)
    JWT_TOKEN_LOCATION = ['cookies', 'headers']
    JWT_COOKIE_SECURE = False  # Set True in production
    JWT_COOKIE_CSRF_PROTECT = True
    JWT_COOKIE_SAMESITE = 'Lax'
    JWT_ACCESS_COOKIE_NAME = 'access_token'
    JWT_REFRESH_COOKIE_NAME = 'refresh_token'
    
    # Razorpay Configuration
    RAZORPAY_KEY_ID = os.environ.get('RAZORPAY_KEY_ID', '')
    RAZORPAY_KEY_SECRET = os.environ.get('RAZORPAY_KEY_SECRET', '')
    
    # OpenAI Configuration (for AI Chat)

    GEMINI_API_KEY = os.environ.get('GEMINI_API_KEY', '')
    
    # Upload Configuration
    MAX_CONTENT_LENGTH = 100 * 1024 * 1024  # 100MB max upload (increased for videos)
    UPLOAD_FOLDER = '/tmp/uploads' if IS_VERCEL else os.path.join(
        os.path.dirname(os.path.abspath(__file__)), 'static', 'uploads'
    )
    ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'webp', 'pdf', 'mp4', 'webm'}
    
    # Mail Configuration (System & OTP)
    MAIL_SERVER = os.environ.get('MAIL_SERVER', 'smtp.gmail.com')
    MAIL_PORT = int(os.environ.get('MAIL_PORT', 587))
    MAIL_USE_TLS = True
    # Main General Mail Configuration (Invoices, Order Updates)
    # Using STORE_MAIL_USER to strictly avoid conflicts with existing MAIL_USERNAME uses
    STORE_MAIL_USER = os.environ.get('STORE_MAIL_USER', '')
    STORE_MAIL_PASS = os.environ.get('STORE_MAIL_PASS', '')
    MAIL_DEFAULT_SENDER = os.environ.get('MAIL_DEFAULT_SENDER', STORE_MAIL_USER or 'support@luxoyacandles.com')

    # Dedicated Auth/OTP Mail Configuration
    # We strictly do NOT fall back to MAIL_USERNAME. If OTP credentials are not set, OTP will safely fail or log to terminal without causing SMTP account overlap issues.
    OTP_MAIL_USERNAME = os.environ.get('AUTH_MAIL_USER') or os.environ.get('OTP_MAIL_USERNAME', '')
    OTP_MAIL_PASSWORD = os.environ.get('AUTH_MAIL_PASS') or os.environ.get('OTP_MAIL_PASSWORD', '')
    OTP_MAIL_SENDER = os.environ.get('OTP_MAIL_SENDER') or os.environ.get('AUTH_MAIL_USER', 'security@luxoyacandles.com')
    
    # Google OAuth Configuration
    GOOGLE_CLIENT_ID = os.environ.get('GOOGLE_CLIENT_ID', '')
    GOOGLE_CLIENT_SECRET = os.environ.get('GOOGLE_CLIENT_SECRET', '')

    # Initial Account Provisioning (Override via Environment Variables)
    INITIAL_ADMIN_EMAIL = os.environ.get('INITIAL_ADMIN_EMAIL', 'admin@luxoyacandles.com')
    INITIAL_ADMIN_PASS = os.environ.get('INITIAL_ADMIN_PASS')
    INITIAL_SALES_EMAIL = os.environ.get('INITIAL_SALES_EMAIL', 'sales@luxoyacandles.com')
    INITIAL_SALES_PASS = os.environ.get('INITIAL_SALES_PASS')
    ADMIN_MASTER_PIN = os.environ.get('ADMIN_MASTER_PIN')

    # Shiprocket Configuration
    SHIPROCKET_EMAIL = os.environ.get('SHIPROCKET_EMAIL', '')
    SHIPROCKET_PASSWORD = os.environ.get('SHIPROCKET_PASSWORD', '')


class DevelopmentConfig(Config):
    """Development configuration."""
    DEBUG = True
    SQLALCHEMY_DATABASE_URI = os.environ.get(
        'DATABASE_URL',
        'sqlite:///luxoya_dev.db'
    )
    JWT_COOKIE_SECURE = False

    @staticmethod
    def init_app(app):
        # Detect any serverless environment (already handled globally by IS_SERVERLESS)
        is_serverless = IS_SERVERLESS
        
        db_url = _normalize_postgres_url(app.config.get('SQLALCHEMY_DATABASE_URI', ''))
        app.config['SQLALCHEMY_DATABASE_URI'] = db_url

        # In serverless environments, force SQLite to /tmp/ if used
        if is_serverless and db_url.startswith('sqlite:///'):
             app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:////tmp/luxoya_dev.db'
             app.logger.warning('Serverless detected. Forcing SQLite to /tmp/luxoya_dev.db')

        # Local developer resilience: fallback to SQLite when remote DB DNS is unavailable.
        allow_fallback = os.environ.get('ALLOW_SQLITE_FALLBACK', '1') == '1'
        if allow_fallback and db_url.startswith('postgresql://') and not _db_host_resolves(db_url):
            app.logger.warning('Database host is not resolvable. Falling back to local SQLite (development only).')
            app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///luxoya_dev.db'

            # Remove PostgreSQL-specific connect args that are invalid for SQLite.
            engine_opts = dict(app.config.get('SQLALCHEMY_ENGINE_OPTIONS', {}))
            connect_args = dict(engine_opts.get('connect_args', {}))
            connect_args.pop('connect_timeout', None)
            if connect_args:
                engine_opts['connect_args'] = connect_args
            else:
                engine_opts.pop('connect_args', None)
            app.config['SQLALCHEMY_ENGINE_OPTIONS'] = engine_opts


class ProductionConfig(Config):
    """Production configuration."""
    DEBUG = False
    SQLALCHEMY_DATABASE_URI = os.environ.get(
        'DATABASE_URL',
        'sqlite:////tmp/luxoya_prod.db'
    )
    if SQLALCHEMY_DATABASE_URI.startswith('postgres://'):
        SQLALCHEMY_DATABASE_URI = SQLALCHEMY_DATABASE_URI.replace('postgres://', 'postgresql://', 1)
    
    JWT_COOKIE_SECURE = True
    JWT_COOKIE_SAMESITE = 'Lax'
    JWT_ACCESS_TOKEN_EXPIRES = timedelta(days=7) # Longer persistence for better UX
    JWT_REFRESH_TOKEN_EXPIRES = timedelta(days=30)
    
    @staticmethod
    def init_app(app):
        # Safety check for Database URI to prevent NoneType crash
        db_uri = app.config.get('SQLALCHEMY_DATABASE_URI')
        if db_uri and isinstance(db_uri, str):
            app.config['SQLALCHEMY_DATABASE_URI'] = db_uri.replace('postgres://', 'postgresql://', 1)
        else:
            # Fallback for extreme cases (Prevent total crash)
            app.logger.warning("SQLALCHEMY_DATABASE_URI is missing or not a string. API routes may fail.")

        # In serverless environments, force SQLite to /tmp/ if used
        db_url = os.environ.get('DATABASE_URL', '')
        if IS_SERVERLESS and (not db_url or db_url.startswith('sqlite:///')):
             app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:////tmp/luxoya_prod.db'
             app.logger.warning('Serverless detected. Forcing SQLite to /tmp/luxoya_prod.db')
        
        # Ensure JWT Cookie Security in Production
        app.config['JWT_COOKIE_SECURE'] = True
        app.config['JWT_COOKIE_SAMESITE'] = 'Lax'


class TestingConfig(Config):
    """Testing configuration."""
    TESTING = True
    SQLALCHEMY_DATABASE_URI = 'sqlite:///luxoya_test.db'


config = {
    'development': DevelopmentConfig,
    'production': ProductionConfig,
    'testing': TestingConfig,
    'default': DevelopmentConfig
}
