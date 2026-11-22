import os
from flask import Flask
from config import config
from .extensions import db, login_manager, scheduler

SYNC_JOB_ID = 'daily_student_sync'


def _register_scheduled_sync(app):
    """Register the daily synchronization job and start the scheduler once."""
    from .services.sync_service import sync_all_students

    def _run_sync():
        with app.app_context():
            try:
                sync_all_students()
            except Exception:
                # Never let a scheduled failure take the web process down.
                pass

    if app.config.get('TESTING'):
        return

    try:
        if scheduler.get_job(SYNC_JOB_ID) is None:
            scheduler.add_job(
                id=SYNC_JOB_ID,
                func=_run_sync,
                trigger='cron',
                hour=2,
                minute=0,
                max_instances=1,
                replace_existing=True,
            )
    except Exception:
        return

    @app.before_request
    def _start_scheduler_once():
        # Starting lazily means only the process that actually serves
        # requests owns the job (avoids duplicates with the debug reloader).
        if app.config.get('TESTING') or getattr(scheduler, 'running', False):
            return
        try:
            scheduler.start()
        except Exception:
            pass


def _ensure_new_columns():
    """Add columns introduced after the first release to an existing database.

    ``db.create_all()`` never alters existing tables, so old SQLite files need
    a small additive migration. Only ``ADD COLUMN`` statements are issued, so
    this is safe to run on every start and never touches existing rows.
    """
    from sqlalchemy import inspect, text

    try:
        inspector = inspect(db.engine)
        tables = inspector.get_table_names()
        statements = []

        if 'students' in tables:
            columns = {c['name'] for c in inspector.get_columns('students')}
            additions = {
                'codechef_display_name': 'VARCHAR(120)',
                'last_sync_status': 'VARCHAR(20)',
                'last_sync_error': 'VARCHAR(255)',
                'last_sync_at': 'DATETIME',
            }
            for name, ddl in additions.items():
                if name not in columns:
                    statements.append(
                        f'ALTER TABLE students ADD COLUMN {name} {ddl}')

        if 'sync_logs' in tables:
            columns = {c['name'] for c in inspector.get_columns('sync_logs')}
            if 'skipped_count' not in columns:
                statements.append(
                    'ALTER TABLE sync_logs ADD COLUMN skipped_count INTEGER DEFAULT 0')

        for statement in statements:
            db.session.execute(text(statement))
        if statements:
            db.session.commit()
    except Exception:
        # A failed migration must not stop the app from starting.
        db.session.rollback()


def create_app(config_name='default'):
    app = Flask(__name__)

    # Load configuration
    config_name = config_name or os.environ.get('FLASK_ENV', 'default')
    app.config.from_object(config.get(config_name, config['default']))

    # Ensure basedir is available
    basedir = os.path.abspath(os.path.dirname(__file__))
    app.config['BASEDIR'] = basedir

    # Initialize extensions
    db.init_app(app)
    login_manager.init_app(app)
    scheduler.init_app(app)

    # Configure scheduler
    scheduler.api_enabled = app.config.get('SCHEDULER_API_ENABLED', True)

    # Create database tables
    with app.app_context():
        db.create_all()
        _ensure_new_columns()

    @app.context_processor
    def inject_navigation_health():
        """Expose a small "needs attention" count to the sidebar."""
        try:
            from flask_login import current_user
            if not current_user.is_authenticated:
                return {}
            from .models import Student
            return {
                'nav_unlinked_count': Student.query.filter(
                    Student.codechef_username.is_(None)).count(),
            }
        except Exception:
            return {}

    # Register blueprints
    from .routes.auth import auth_bp
    from .routes.dashboard import dashboard_bp
    from .routes.students import students_bp
    from .routes.leaderboard import leaderboard_bp
    from .routes.analytics import analytics_bp
    from .routes.reports import reports_bp
    from .routes.settings import settings_bp
    from .routes.sync import sync_bp
    from .routes.gemini_auth import gemini_bp

    app.register_blueprint(auth_bp, url_prefix='/auth')
    app.register_blueprint(dashboard_bp, url_prefix='/')
    app.register_blueprint(students_bp, url_prefix='/students')
    app.register_blueprint(leaderboard_bp, url_prefix='/leaderboard')
    app.register_blueprint(analytics_bp, url_prefix='/analytics')
    app.register_blueprint(reports_bp, url_prefix='/reports')
    app.register_blueprint(settings_bp, url_prefix='/settings')
    app.register_blueprint(sync_bp, url_prefix='/sync')
    app.register_blueprint(gemini_bp, url_prefix='/gemini')

    # Daily synchronization at 02:00 (Asia/Kolkata)
    _register_scheduled_sync(app)

    return app
