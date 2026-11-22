from flask import Blueprint, render_template, redirect, url_for, flash, request
from flask_login import login_required, current_user
from ..models import Role, User
from ..extensions import db


settings_bp = Blueprint('settings', __name__)


@settings_bp.route('/')
@login_required
def index():
    """Application settings page"""
    if not current_user.is_admin():
        flash('Access denied. Administrator privileges required.', 'danger')
        return redirect(url_for('dashboard.dashboard'))

    users = User.query.order_by(User.name.asc()).all()
    return render_template('settings/index.html', users=users)


@settings_bp.route('/add-admin', methods=['POST'])
@login_required
def add_admin():
    """Add a new user"""
    if not current_user.is_admin():
        flash('Access denied.', 'danger')
        return redirect(url_for('settings.index'))

    name = (request.form.get('name') or '').strip()
    email = (request.form.get('email') or '').strip().lower()
    password = request.form.get('password') or ''
    role = request.form.get('role', Role.FACULTY)

    if not name or not email or not password:
        flash('Name, email and password are required.', 'danger')
        return redirect(url_for('settings.index'))

    if role not in (Role.ADMIN, Role.FACULTY):
        role = Role.FACULTY

    if User.query.filter_by(email=email).first():
        flash('Email already registered.', 'danger')
    else:
        user = User(name=name, email=email, role=role)
        user.set_password(password)
        db.session.add(user)
        db.session.commit()
        flash(f'{user.name} added as {user.role.capitalize()}.', 'success')

    return redirect(url_for('settings.index'))


@settings_bp.route('/toggle-role/<int:user_id>', methods=['POST'])
@login_required
def toggle_role(user_id):
    """Toggle user role between admin and faculty"""
    if not current_user.is_admin():
        flash('Access denied.', 'danger')
        return redirect(url_for('settings.index'))

    user = User.query.get_or_404(user_id)

    # Prevent self-demotion
    if user.id == current_user.id:
        flash('Cannot change your own role.', 'danger')
        return redirect(url_for('settings.index'))

    if user.role == 'admin':
        user.role = 'faculty'
        flash(f'{user.name}\'s role changed to Faculty.', 'info')
    else:
        user.role = 'admin'
        flash(f'{user.name}\'s role changed to Admin.', 'info')

    db.session.commit()
    return redirect(url_for('settings.index'))


@settings_bp.route('/delete-user/<int:user_id>', methods=['POST'])
@login_required
def delete_user(user_id):
    """Delete a user account (never your own, never the last admin)."""
    if not current_user.is_admin():
        flash('Access denied.', 'danger')
        return redirect(url_for('settings.index'))

    user = User.query.get_or_404(user_id)

    if user.id == current_user.id:
        flash('You cannot delete your own account.', 'danger')
        return redirect(url_for('settings.index'))

    if user.role == 'admin' and User.query.filter_by(role='admin').count() <= 1:
        flash('At least one administrator account must remain.', 'danger')
        return redirect(url_for('settings.index'))

    db.session.delete(user)
    db.session.commit()
    flash(f'{user.name} has been deleted.', 'success')
    return redirect(url_for('settings.index'))
