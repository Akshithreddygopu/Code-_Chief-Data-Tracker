from flask import Blueprint, render_template
from flask_login import login_required

from ..models import RatingHistory, Student, SyncLog
from ..services.stats_service import (class_average_trend,
                                      improvement_entries, latest_rating_map,
                                      rating_distribution)


analytics_bp = Blueprint('analytics', __name__)


@analytics_bp.route('/')
@login_required
def index():
    """Class analytics computed from the latest snapshot per student."""
    latest = latest_rating_map()
    ratings = [snap.rating for snap in latest.values() if snap.rating is not None]

    avg_rating = round(sum(ratings) / len(ratings), 1) if ratings else 0
    max_rating = max(ratings) if ratings else 0
    min_rating = min(ratings) if ratings else 0

    ordered = sorted(latest.values(),
                     key=lambda snap: snap.rating or 0,
                     reverse=True)
    top_performers = ordered[:10]

    improvements = [entry for entry in improvement_entries()
                    if entry['delta'] != 0][:10]
    decliners = [entry for entry in improvement_entries()
                 if entry['delta'] < 0][-5:]

    distribution = rating_distribution(ratings)
    distribution_max = max((bucket['count'] for bucket in distribution),
                           default=0)

    trend_labels, trend_values = class_average_trend()

    ranked_snapshots = [snap for snap in latest.values() if snap.global_rank]
    country_snapshots = [snap for snap in latest.values() if snap.country_rank]
    best_global = min(ranked_snapshots,
                      key=lambda snap: snap.global_rank) if ranked_snapshots else None
    best_country = min(country_snapshots,
                       key=lambda snap: snap.country_rank) if country_snapshots else None

    students_unavailable = Student.query.filter(
        Student.codechef_username.is_(None)).count()

    recent_syncs = (SyncLog.query.order_by(SyncLog.started_at.desc())
                    .limit(5).all())

    total_snapshots = RatingHistory.query.count()

    return render_template(
        'analytics/index.html',
        avg_rating=avg_rating,
        max_rating=max_rating,
        min_rating=min_rating,
        top_performers=top_performers,
        improvements=improvements,
        decliners=decliners,
        distribution=distribution,
        distribution_max=distribution_max,
        trend_labels=trend_labels,
        trend_values=trend_values,
        students_unavailable=students_unavailable,
        recent_syncs=recent_syncs,
        total_snapshots=total_snapshots,
        ranked_count=len(ranked_snapshots),
        country_ranked_count=len(country_snapshots),
        best_global=best_global,
        best_country=best_country,
    )
