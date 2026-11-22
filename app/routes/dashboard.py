from flask import Blueprint, render_template
from flask_login import current_user, login_required

from ..models import Student, StudentStatistics, SyncLog
from ..services.stats_service import (improvement_entries, latest_rating_map,
                                      rating_distribution)


dashboard_bp = Blueprint('dashboard', __name__)


@dashboard_bp.route('/')
@login_required
def dashboard():
    total_students = Student.query.count()
    linked_students = Student.query.filter(
        Student.codechef_username.isnot(None)).count()

    latest = latest_rating_map()
    ratings = [snap.rating for snap in latest.values() if snap.rating is not None]

    avg_rating = round(sum(ratings) / len(ratings), 1) if ratings else 0
    highest_rating = max(
        (snap.highest_rating for snap in latest.values()
         if snap.highest_rating is not None), default=0)

    total_problems = sum(
        stats.problems_solved or 0
        for stats in StudentStatistics.query.all()
    )

    # Top performers from the latest snapshot of each student
    ordered = sorted(latest.values(),
                     key=lambda snap: snap.rating or 0,
                     reverse=True)
    top_students = ordered[:5]

    # Biggest improvement since first snapshot
    movers = [entry for entry in improvement_entries()
              if entry['delta'] != 0][:5]

    last_sync = SyncLog.query.order_by(SyncLog.started_at.desc()).first()
    recent_syncs = (SyncLog.query.order_by(SyncLog.started_at.desc())
                    .limit(5).all())
    recent_students = (Student.query.order_by(Student.created_at.desc())
                       .limit(6).all())

    distribution = rating_distribution(ratings)
    distribution_max = max((bucket['count'] for bucket in distribution),
                           default=0)

    unlinked_students = (Student.query
                         .filter(Student.codechef_username.is_(None))
                         .order_by(Student.name.asc()).all())
    failed_students = (Student.query
                       .filter(Student.last_sync_status == 'failed')
                       .order_by(Student.name.asc()).all())

    return render_template(
        'dashboard/index.html',
        total_students=total_students,
        linked_students=linked_students,
        unlinked_students=unlinked_students,
        failed_students=failed_students,
        active_profiles=Student.query.filter(
            Student.codechef_username.isnot(None),
            Student.status == 'active').count(),
        avg_rating=avg_rating,
        highest_rating=highest_rating,
        total_problems=total_problems,
        top_students=top_students,
        movers=movers,
        last_sync=last_sync,
        recent_syncs=recent_syncs,
        recent_students=recent_students,
        distribution=distribution,
        distribution_max=distribution_max,
    )
