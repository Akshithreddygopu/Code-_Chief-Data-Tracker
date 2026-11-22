from flask import Blueprint, render_template, redirect, url_for, flash, request
from flask_login import login_user, logout_user, login_required, current_user
from ..models import User
from ..extensions import db
from ..services.gemini_auth import configure_gemini, verify_gemini_credentials, gemini_login
import google.generativeai as genai

gemini_bp = Blueprint('gemini_auth', __name__)


@gemini_bp.route('/gemini-login', methods=['GET', 'POST'])
def login():
    """Gemini AI-powered login page."""
    from ..services.gemini_auth import configure_gemini
    
    # Configure Gemini with API key
    configure_gemini()
    
    if current_user.is_authenticated:
        return redirect(url_for('dashboard.dashboard'))

    if request.method == 'POST':
        email = request.form.get('email')
        password = request.form.get('password')

        # First try traditional password verification
        user = User.query.filter_by(email=email).first()

        if user and user.check_password(password):
            gemini_login(email)
            flash('Login successful!', 'success')
            return redirect(url_for('dashboard.dashboard'))
        else:
            # Try Gemini AI verification as fallback or alternative
            if verify_gemini_credentials(email, password):
                gemini_login(email)
                flash('Login verified via Gemini AI!', 'success')
                return redirect(url_for('dashboard.dashboard'))
            else:
                flash('Invalid email or password.', 'danger')

    return render_template('gemini/login.html')


@gemini_bp.route('/gemini-logout')
@login_required
def logout():
    """Log out the current user."""
    logout_user()
    flash('You have been logged out.', 'info')
    return redirect(url_for('auth.login'))


@gemini_bp.route('/gemini-setup', methods=['GET', 'POST'])
def setup():
    """Create initial admin account with Gemini auth support."""
    from ..models import User

    if request.method == 'POST':
        name = request.form.get('name')
        email = request.form.get('email')
        password = request.form.get('password')
        role = request.form.get('role', 'admin')

        if User.query.filter_by(email=email).first():
            flash('Email already registered.', 'danger')
        else:
            user = User()
            user.name = name
            user.email = email
            user.set_password(password)
            user.role = role
            db.session.add(user)
            db.session.commit()
            flash('Admin account created successfully with Gemini auth support!', 'success')
            return redirect(url_for('auth.login'))

    return render_template('gemini/setup.html')