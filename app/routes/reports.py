from flask import (Blueprint, flash, redirect, render_template, request,
                   send_file, url_for)
from flask_login import current_user, login_required

from ..models import Student, SyncLog
from ..services import excel_service
from ..services.stats_service import improvement_entries


reports_bp = Blueprint('reports', __name__)


def _admin_only():
    if not current_user.is_admin():
        flash('Access denied. Administrator privileges required.', 'danger')
        return False
    return True


@reports_bp.route('/')
@login_required
def index():
    students = Student.query.order_by(Student.name.asc()).all()
    sync_failures = SyncLog.query.filter(
        (SyncLog.status == 'failed') | (SyncLog.failed_count > 0)
    ).count()
    return render_template('reports/index.html',
                           students=students,
                           sync_failures=sync_failures)


@reports_bp.route('/class-performance')
@login_required
def class_performance():
    if not _admin_only():
        return redirect(url_for('dashboard.dashboard'))

    students = Student.query.filter_by(status='active').order_by(
        Student.roll_number.asc()).all()
    filepath = excel_service.export_students_workbook(
        students, filename='class_performance_report.xlsx')
    return send_file(
        filepath,
        as_attachment=True,
        download_name='codechef_class_performance_report.xlsx',
        mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
    )


@reports_bp.route('/student-report/<int:student_id>')
@login_required
def student_report(student_id):
    if not _admin_only():
        return redirect(url_for('dashboard.dashboard'))

    student = Student.query.get_or_404(student_id)
    filepath = excel_service.export_student_detail(
        student, filename=f'student_report_{student.roll_number}.xlsx')
    return send_file(
        filepath,
        as_attachment=True,
        download_name=f'student_report_{student.roll_number}.xlsx',
        mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
    )


@reports_bp.route('/rating-improvement')
@login_required
def rating_improvement():
    if not _admin_only():
        return redirect(url_for('dashboard.dashboard'))

    entries = improvement_entries()
    filepath = excel_service.export_improvement_workbook(
        entries, filename='rating_improvement_report.xlsx')
    return send_file(
        filepath,
        as_attachment=True,
        download_name='rating_improvement_report.xlsx',
        mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
    )


@reports_bp.route('/ranks')
@login_required
def ranks():
    if not _admin_only():
        return redirect(url_for('dashboard.dashboard'))

    students = (Student.query
                .filter(Student.codechef_username.isnot(None))
                .order_by(Student.name.asc()).all())
    filepath = excel_service.export_rank_workbook(
        students, filename='codechef_rank_analysis.xlsx')
    return send_file(
        filepath,
        as_attachment=True,
        download_name='codechef_rank_analysis.xlsx',
        mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
    )


@reports_bp.route('/unlinked')
@login_required
def unlinked():
    if not _admin_only():
        return redirect(url_for('dashboard.dashboard'))

    students = (Student.query
                .filter(Student.codechef_username.is_(None))
                .order_by(Student.name.asc()).all())
    filepath = excel_service.export_unlinked_workbook(
        students, filename='students_not_linked.xlsx')
    return send_file(
        filepath,
        as_attachment=True,
        download_name='students_not_linked_to_codechef.xlsx',
        mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
    )


@reports_bp.route('/sync-error')
@login_required
def sync_error():
    if not _admin_only():
        return redirect(url_for('dashboard.dashboard'))

    logs = SyncLog.query.filter(
        (SyncLog.status == 'failed') | (SyncLog.failed_count > 0)
    ).order_by(SyncLog.started_at.desc()).limit(100).all()

    filepath = excel_service.export_sync_errors_workbook(
        logs, filename='sync_error_report.xlsx')
    return send_file(
        filepath,
        as_attachment=True,
        download_name='sync_error_report.xlsx',
        mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
    )
