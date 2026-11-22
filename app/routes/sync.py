"""Synchronization blueprint: history, coverage, and manual runs."""

from flask import (Blueprint, flash, redirect, render_template, request,
                   send_file, url_for)
from flask_login import current_user, login_required

from ..extensions import scheduler
from ..models import Student, SyncLog
from ..services import excel_service
from ..services.sync_service import (sync_all_students, sync_overview,
                                     sync_student)

sync_bp = Blueprint('sync', __name__)

JOB_ID = 'daily_student_sync'


def next_scheduled_run():
    """Return the next run datetime, or ``None`` when no job is active."""
    try:
        job = scheduler.get_job(JOB_ID)
        return job.next_run_time if job else None
    except Exception:
        return None


@sync_bp.route('/')
@login_required
def history():
    logs = (SyncLog.query
            .order_by(SyncLog.started_at.desc())
            .limit(50)
            .all())

    overview = sync_overview()

    return render_template(
        'sync/history.html',
        logs=logs,
        overview=overview,
        linked_students=overview['linked'],
        total_students=overview['total'],
        last_sync=logs[0] if logs else None,
        next_run=next_scheduled_run(),
    )


@sync_bp.route('/run', methods=['POST'])
@login_required
def run_all():
    if not current_user.is_admin():
        flash('Access denied. Administrator privileges required.', 'danger')
        return redirect(url_for('sync.history'))

    only_failed = request.form.get('scope') == 'failed'
    result = sync_all_students(only_failed=only_failed)

    if result['total'] == 0:
        message = ('No failed students to retry.' if only_failed
                   else 'No students with a CodeChef profile to synchronize.')
        flash(message, 'info')
    elif result['failed'] and not result['successful']:
        flash('Synchronization failed for every student. '
              'Check the run details below.', 'danger')
    elif result['failed']:
        flash(f"Synchronized {result['successful']} of "
              f"{result['total']} student(s); {result['failed']} failed.",
              'warning')
    else:
        flash(f"All {result['successful']} student(s) synchronized "
              f"({result['snapshots']} new snapshot(s)).", 'success')

    return redirect(url_for('sync.history'))


@sync_bp.route('/run/student/<int:student_id>', methods=['POST'])
@login_required
def run_student(student_id):
    if not current_user.is_admin():
        flash('Access denied. Administrator privileges required.', 'danger')
        return redirect(url_for('students.profile', student_id=student_id))

    student = Student.query.get_or_404(student_id)
    result = sync_student(student)

    category = 'success' if result['status'] == 'success' else (
        'info' if result['status'] == 'skipped' else 'danger')
    flash(result['message'], category)

    next_page = request.form.get('next') or request.referrer
    if next_page:
        return redirect(next_page)
    return redirect(url_for('students.profile', student_id=student_id))


@sync_bp.route('/unlinked/export')
@login_required
def export_unlinked():
    """Download the list of students who still need a CodeChef profile."""
    if not current_user.is_admin():
        flash('Access denied. Administrator privileges required.', 'danger')
        return redirect(url_for('sync.history'))

    students = (Student.query
                .filter(Student.codechef_username.is_(None))
                .order_by(Student.name.asc())
                .all())
    filepath = excel_service.export_unlinked_workbook(students)
    return send_file(
        filepath,
        as_attachment=True,
        download_name='students_not_linked_to_codechef.xlsx',
        mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
    )
