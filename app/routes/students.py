import json
import os
import re
import uuid

from flask import (Blueprint, current_app, flash, redirect, render_template,
                   request, send_file, url_for)
from flask_login import current_user, login_required

from ..extensions import db
from ..models import RatingHistory, Student, StudentStatistics
from ..services.codechef_provider import validate_codechef_url
from ..services.excel_service import build_import_template, parse_students_file
from ..services.stats_service import latest_rating_map
from ..services.sync_service import names_differ, sync_student

students_bp = Blueprint('students', __name__)


@students_bp.route('/')
@login_required
def index():
    """Student list with search, filter, and sort"""
    query = request.args.get('query', '', type=str)
    section = request.args.get('section', '', type=str)
    link_status = request.args.get('link_status', '', type=str)
    sort_by = request.args.get('sort_by', 'name', type=str)
    sort_dir = request.args.get('sort_dir', 'asc', type=str)

    students_query = Student.query

    # Search by name, roll number, username or CodeChef display name
    if query:
        students_query = students_query.filter(
            (Student.name.ilike(f'%{query}%')) |
            (Student.roll_number.ilike(f'%{query}%')) |
            (Student.codechef_username.ilike(f'%{query}%')) |
            (Student.codechef_display_name.ilike(f'%{query}%'))
        )

    # Filter by section
    if section:
        students_query = students_query.filter(Student.section == section)

    # Filter by CodeChef link status
    if link_status == 'linked':
        students_query = students_query.filter(
            Student.codechef_username.isnot(None))
    elif link_status == 'unlinked':
        students_query = students_query.filter(
            Student.codechef_username.is_(None))

    # Sorting
    sort_column = getattr(Student, sort_by, Student.name)
    if sort_dir == 'desc':
        students_query = students_query.order_by(sort_column.desc())
    else:
        students_query = students_query.order_by(sort_column.asc())

    students = students_query.all()

    # Get unique sections for filter
    sections = db.session.query(Student.section).distinct().all()
    sections = sorted([s[0] for s in sections if s[0]])

    total_count = Student.query.count()
    linked_count = Student.query.filter(
        Student.codechef_username.isnot(None)).count()
    name_mismatch_ids = {
        student.id for student in Student.query.all()
        if names_differ(student.name, student.codechef_display_name)
    }

    return render_template(
        'students/index.html',
        students=students,
        latest=latest_rating_map(),
        query=query,
        section=section,
        link_status=link_status,
        sections=sections,
        sort_by=sort_by,
        sort_dir=sort_dir,
        total_count=total_count,
        linked_count=linked_count,
        unlinked_count=total_count - linked_count,
        name_mismatch_ids=name_mismatch_ids,
    )


@students_bp.route('/add', methods=['GET', 'POST'])
@login_required
def add():
    """Add individual student"""
    if request.method == 'POST':
        roll_number = (request.form.get('roll_number') or '').strip()
        name = (request.form.get('name') or '').strip()
        department = (request.form.get('department') or '').strip()
        academic_year = (request.form.get('academic_year') or '').strip()
        section = (request.form.get('section') or '').strip()
        codechef_url = (request.form.get('codechef_url') or '').strip()

        # Validate required fields
        if not roll_number or not name or not department or not academic_year or not section:
            flash('All required fields must be filled.', 'danger')
            return redirect(url_for('students.add'))

        # Check for duplicate roll number
        if Student.query.filter_by(roll_number=roll_number).first():
            flash('Duplicate roll number detected.', 'danger')
            return redirect(url_for('students.add'))

        username = None

        # Validate CodeChef URL if provided
        if codechef_url:
            is_valid, extracted_username = validate_codechef_url(codechef_url)
            if not is_valid:
                flash(f'Invalid CodeChef URL: {extracted_username}', 'danger')
                return redirect(url_for('students.add'))

            # Check for duplicate username
            if Student.query.filter_by(codechef_username=extracted_username).first():
                flash('A student with this CodeChef username already exists.', 'danger')
                return redirect(url_for('students.add'))

            username = extracted_username
            codechef_url = f'https://www.codechef.com/users/{username}'

        student = Student(
            roll_number=roll_number,
            name=name,
            department=department,
            academic_year=academic_year,
            section=section,
            codechef_url=codechef_url or None,
            codechef_username=username
        )

        db.session.add(student)
        db.session.commit()
        flash('Student added successfully!', 'success')
        return redirect(url_for('students.index'))

    return render_template('students/add.html')


@students_bp.route('/edit/<int:student_id>', methods=['GET', 'POST'])
@login_required
def edit(student_id):
    """Edit student details"""
    student = Student.query.get_or_404(student_id)

    if request.method == 'POST':
        roll_number = (request.form.get('roll_number') or '').strip()
        name = (request.form.get('name') or '').strip()
        department = (request.form.get('department') or '').strip()
        academic_year = (request.form.get('academic_year') or '').strip()
        section = (request.form.get('section') or '').strip()
        codechef_url = (request.form.get('codechef_url') or '').strip()

        # Validate required fields
        if not roll_number or not name or not department or not academic_year or not section:
            flash('All required fields must be filled.', 'danger')
            return redirect(url_for('students.edit', student_id=student_id))

        # Check for duplicate roll number (excluding current student)
        existing = Student.query.filter_by(roll_number=roll_number).first()
        if existing and existing.id != student_id:
            flash('Duplicate roll number detected.', 'danger')
            return redirect(url_for('students.edit', student_id=student_id))

        # Update student fields
        student.roll_number = roll_number
        student.name = name
        student.department = department
        student.academic_year = academic_year
        student.section = section

        # Handle CodeChef URL validation
        if codechef_url:
            if codechef_url != student.codechef_url:
                is_valid, extracted_username = validate_codechef_url(codechef_url)
                if not is_valid:
                    flash(f'Invalid CodeChef URL: {extracted_username}', 'danger')
                    return redirect(url_for('students.edit', student_id=student_id))

                # Check for duplicate username (excluding current student)
                existing_user = Student.query.filter(
                    Student.codechef_username == extracted_username,
                    Student.id != student_id
                ).first()
                if existing_user:
                    flash('A student with this CodeChef username already exists.', 'danger')
                    return redirect(url_for('students.edit', student_id=student_id))

                student.codechef_url = f'https://www.codechef.com/users/{extracted_username}'
                student.codechef_username = extracted_username
            # If same URL, keep existing data
        else:
            student.codechef_url = None
            student.codechef_username = None
            student.codechef_display_name = None
            student.last_sync_status = None
            student.last_sync_error = None

        db.session.commit()
        flash('Student updated successfully!', 'success')
        return redirect(url_for('students.profile', student_id=student.id))

    return render_template('students/edit.html', student=student)


@students_bp.route('/link/<int:student_id>', methods=['POST'])
@login_required
def link_profile(student_id):
    """Link a CodeChef handle/URL to a student, optionally syncing at once."""
    if not current_user.is_admin():
        flash('Access denied. Administrator privileges required.', 'danger')
        return redirect(url_for('students.index'))

    student = Student.query.get_or_404(student_id)
    value = (request.form.get('codechef') or '').strip()

    if not value:
        flash('Enter a CodeChef username or profile URL.', 'warning')
        return _back_to_sync(student_id)

    is_valid, extracted = validate_codechef_url(value)
    if not is_valid:
        flash(f'Invalid CodeChef profile: {extracted}', 'danger')
        return _back_to_sync(student_id)

    duplicate = Student.query.filter(
        Student.codechef_username == extracted,
        Student.id != student_id,
    ).first()
    if duplicate:
        flash(f'@{extracted} is already linked to {duplicate.name} '
              f'({duplicate.roll_number}).', 'danger')
        return _back_to_sync(student_id)

    student.codechef_username = extracted
    student.codechef_url = f'https://www.codechef.com/users/{extracted}'
    student.codechef_display_name = None
    student.last_sync_status = None
    student.last_sync_error = None
    db.session.commit()

    flash(f'{student.name} linked to @{extracted}.', 'success')

    if request.form.get('sync'):
        result = sync_student(student)
        category = 'success' if result['status'] == 'success' else (
            'info' if result['status'] == 'skipped' else 'danger')
        flash(result['message'], category)

    return _back_to_sync(student_id)


@students_bp.route('/unlink/<int:student_id>', methods=['POST'])
@login_required
def unlink_profile(student_id):
    """Remove the CodeChef link while keeping all recorded history."""
    if not current_user.is_admin():
        flash('Access denied. Administrator privileges required.', 'danger')
        return redirect(url_for('students.index'))

    student = Student.query.get_or_404(student_id)
    student.codechef_username = None
    student.codechef_url = None
    student.codechef_display_name = None
    student.last_sync_status = None
    student.last_sync_error = None
    db.session.commit()
    flash(f'CodeChef profile unlinked from {student.name}.', 'info')
    return _back_to_sync(student_id)


def _back_to_sync(student_id):
    """Return to the page the link action was triggered from."""
    target = request.form.get('next') or request.referrer
    if target:
        return redirect(target)
    return redirect(url_for('students.profile', student_id=student_id))


@students_bp.route('/delete/<int:student_id>', methods=['POST'])
@login_required
def delete(student_id):
    """Delete student with confirmation"""
    if not current_user.is_admin():
        flash('Access denied. Administrator privileges required.', 'danger')
        return redirect(url_for('students.index'))

    student = Student.query.get_or_404(student_id)
    db.session.delete(student)
    db.session.commit()
    flash('Student deleted successfully!', 'success')
    return redirect(url_for('students.index'))


@students_bp.route('/profile/<int:student_id>')
@login_required
def profile(student_id):
    """Individual student profile"""
    student = Student.query.get_or_404(student_id)

    history = (RatingHistory.query
               .filter_by(student_id=student.id)
               .order_by(RatingHistory.recorded_at.asc())
               .all())
    latest = history[-1] if history else None
    first = history[0] if history else None
    stats = StudentStatistics.query.filter_by(student_id=student.id).first()

    improvement = None
    if latest and first:
        improvement = latest.rating - first.rating

    chart_labels = [entry.recorded_at.strftime('%d %b %y')
                    if entry.recorded_at else '' for entry in history]
    chart_values = [entry.rating for entry in history]

    return render_template(
        'students/profile.html',
        student=student,
        history=list(reversed(history)),
        latest=latest,
        stats=stats,
        improvement=improvement,
        chart_labels=chart_labels,
        chart_values=chart_values,
        name_mismatch=names_differ(student.name,
                                   student.codechef_display_name),
    )


@students_bp.route('/open-profile/<int:student_id>')
@login_required
def open_profile(student_id):
    """Open the student's CodeChef profile"""
    student = Student.query.get_or_404(student_id)
    if student.codechef_url:
        return redirect(student.codechef_url)
    flash('No CodeChef profile URL available for this student.', 'info')
    return redirect(url_for('students.profile', student_id=student_id))


# ---------------------------------------------------------------------------
# Bulk import
# ---------------------------------------------------------------------------

def _preview_dir():
    path = os.path.join(current_app.instance_path, 'import_previews')
    os.makedirs(path, exist_ok=True)
    return path


def _preview_path(token):
    if not re.fullmatch(r'[0-9a-f]{32}', token or ''):
        return None
    return os.path.join(_preview_dir(), f'{token}.json')


@students_bp.route('/import', methods=['GET', 'POST'])
@login_required
def import_students():
    """Upload a roster file and show a validation preview."""
    if not current_user.is_admin():
        flash('Access denied. Administrator privileges required.', 'danger')
        return redirect(url_for('students.index'))

    if request.method == 'GET':
        return render_template('students/import.html')

    upload = request.files.get('file')
    existing_rolls = [s.roll_number for s in Student.query.all()]
    existing_usernames = [s.codechef_username for s in Student.query.all()
                          if s.codechef_username]

    result = parse_students_file(upload, existing_rolls, existing_usernames)

    if result['error'] and not result['rows']:
        flash(result['error'], 'danger')
        return render_template('students/import.html'), 400

    token = uuid.uuid4().hex
    try:
        with open(_preview_path(token), 'w', encoding='utf-8') as fh:
            json.dump(result, fh)
    except OSError as exc:
        flash(f'Could not store the import preview: {exc}', 'danger')
        return redirect(url_for('students.import_students'))

    return render_template(
        'students/import_preview.html',
        token=token,
        result=result,
        filename=getattr(upload, 'filename', 'upload'),
    )


@students_bp.route('/import/confirm', methods=['POST'])
@login_required
def import_confirm():
    """Insert the valid rows of a stored preview."""
    if not current_user.is_admin():
        flash('Access denied. Administrator privileges required.', 'danger')
        return redirect(url_for('students.index'))

    token = request.form.get('token', '')
    path = _preview_path(token)
    if not path or not os.path.exists(path):
        flash('This import preview has expired. Please upload the file again.',
              'warning')
        return redirect(url_for('students.import_students'))

    try:
        with open(path, 'r', encoding='utf-8') as fh:
            result = json.load(fh)
    except (OSError, ValueError):
        flash('This import preview could not be read. Please try again.',
              'danger')
        return redirect(url_for('students.import_students'))

    existing_rolls = {s.roll_number.strip().lower() for s in Student.query.all()}
    existing_usernames = {
        s.codechef_username.strip().lower()
        for s in Student.query.all() if s.codechef_username
    }

    created = 0
    skipped = 0

    for row in result.get('rows', []):
        if row.get('status') != 'valid':
            skipped += 1
            continue

        data = row.get('data', {})
        roll = (data.get('roll_number') or '').strip()
        username = (data.get('codechef_username') or '').strip()

        if not roll or roll.lower() in existing_rolls:
            skipped += 1
            continue
        if username and username.lower() in existing_usernames:
            skipped += 1
            continue

        db.session.add(Student(
            roll_number=roll,
            name=(data.get('name') or '').strip(),
            department=(data.get('department') or '').strip(),
            academic_year=(data.get('academic_year') or '').strip(),
            section=(data.get('section') or '').strip(),
            codechef_url=(data.get('codechef_url') or '').strip() or None,
            codechef_username=username or None,
        ))
        existing_rolls.add(roll.lower())
        if username:
            existing_usernames.add(username.lower())
        created += 1

    db.session.commit()

    try:
        os.remove(path)
    except OSError:
        pass

    if created:
        flash(f'Imported {created} student(s) successfully'
              + (f'; {skipped} row(s) skipped.' if skipped else '.'), 'success')
    else:
        flash('No students were imported. Every row was invalid or a duplicate.',
              'warning')

    return redirect(url_for('students.index'))


@students_bp.route('/import/template')
@login_required
def import_template():
    """Download the sample roster workbook."""
    path = build_import_template()
    return send_file(
        path,
        as_attachment=True,
        download_name='student_import_template.xlsx',
        mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
    )
