from datetime import datetime
from . import db, login_manager
from flask_login import UserMixin


# Role choices
class Role:
    ADMIN = 'admin'
    FACULTY = 'faculty'


# Import models here to avoid circular imports
from .services.security import hash_password, check_password_hash


@login_manager.user_loader
def load_user(user_id):
    from .models import User
    return User.query.get(int(user_id))


class User(UserMixin, db.Model):
    __tablename__ = 'users'

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(256), nullable=False)
    role = db.Column(db.String(20), nullable=False, default=Role.FACULTY)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    def set_password(self, password):
        self.password_hash = hash_password(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

    def is_admin(self):
        return self.role == Role.ADMIN

    def is_faculty(self):
        return self.role == Role.FACULTY


class Student(db.Model):
    __tablename__ = 'students'

    id = db.Column(db.Integer, primary_key=True)
    roll_number = db.Column(db.String(20), unique=True, nullable=False)
    name = db.Column(db.String(100), nullable=False)
    department = db.Column(db.String(100), nullable=False)
    academic_year = db.Column(db.String(20), nullable=False)
    section = db.Column(db.String(10), nullable=False)
    codechef_username = db.Column(db.String(50), unique=True, nullable=True)
    codechef_url = db.Column(db.String(255), unique=True, nullable=True)
    # Name shown on the public CodeChef profile (may differ from the roster name).
    codechef_display_name = db.Column(db.String(120), nullable=True)
    # Last synchronization outcome: success / failed / unlinked.
    last_sync_status = db.Column(db.String(20), nullable=True)
    last_sync_error = db.Column(db.String(255), nullable=True)
    last_sync_at = db.Column(db.DateTime, nullable=True)
    status = db.Column(db.String(20), default='active')
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    statistics = db.relationship('StudentStatistics', backref='student', lazy='joined', cascade='all, delete-orphan')
    rating_history = db.relationship('RatingHistory', backref='student', lazy='dynamic', cascade='all, delete-orphan')

    def __repr__(self):
        return f'<Student {self.name} ({self.roll_number})>'

    @property
    def is_active_profile(self):
        return self.codechef_url is not None and self.status == 'active'

    @property
    def is_linked(self):
        return bool(self.codechef_username)


class StudentStatistics(db.Model):
    __tablename__ = 'student_statistics'

    id = db.Column(db.Integer, primary_key=True)
    student_id = db.Column(db.Integer, db.ForeignKey('students.id'), nullable=False)
    problems_solved = db.Column(db.Integer, default=0)
    contests_participated = db.Column(db.Integer, default=0)
    last_synced_at = db.Column(db.DateTime, default=datetime.utcnow)

    __table_args__ = (
        db.UniqueConstraint('student_id', name='uq_student_statistics'),
    )


class RatingHistory(db.Model):
    __tablename__ = 'rating_history'

    id = db.Column(db.Integer, primary_key=True)
    student_id = db.Column(db.Integer, db.ForeignKey('students.id', ondelete='CASCADE'), nullable=False)
    rating = db.Column(db.Integer, nullable=False)
    highest_rating = db.Column(db.Integer, nullable=False)
    stars = db.Column(db.Integer, nullable=False)
    global_rank = db.Column(db.Integer, nullable=True)
    country_rank = db.Column(db.Integer, nullable=True)
    recorded_at = db.Column(db.DateTime, default=datetime.utcnow)

    __table_args__ = (
        db.Index('ix_rating_history_student_id', 'student_id'),
        db.Index('ix_rating_history_recorded_at', 'recorded_at'),
    )

    def __repr__(self):
        return f'<RatingHistory {self.student_id} - Rating {self.rating}>'


class SyncLog(db.Model):
    __tablename__ = 'sync_logs'

    id = db.Column(db.Integer, primary_key=True)
    started_at = db.Column(db.DateTime, default=datetime.utcnow)
    completed_at = db.Column(db.DateTime, nullable=True)
    total_processed = db.Column(db.Integer, default=0)
    successful_count = db.Column(db.Integer, default=0)
    failed_count = db.Column(db.Integer, default=0)
    skipped_count = db.Column(db.Integer, default=0)
    status = db.Column(db.String(20), default='pending')  # pending, running, completed, failed
    error_details = db.Column(db.Text, nullable=True)

    def __repr__(self):
        return f'<SyncLog {self.id} - {self.status}>'