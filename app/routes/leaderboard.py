from flask import Blueprint, render_template, request
from flask_login import login_required

from ..extensions import db
from ..models import Student
from ..services.stats_service import first_rating_map, latest_rating_map


leaderboard_bp = Blueprint('leaderboard', __name__)


@leaderboard_bp.route('/')
@login_required
def index():
    """Leaderboard built from the latest snapshot of each student."""
    sort_by = request.args.get('sort_by', 'current_rating', type=str)
    sort_dir = request.args.get('sort_dir', 'desc', type=str)
    section_filter = request.args.get('section', '', type=str)
    search_query = request.args.get('search', '', type=str)

    latest = latest_rating_map()
    first = first_rating_map()

    entries = []
    for student_id, snap in latest.items():
        student = snap.student

        if section_filter and student.section != section_filter:
            continue
        if search_query:
            needle = search_query.lower()
            if (needle not in (student.name or '').lower()
                    and needle not in (student.roll_number or '').lower()):
                continue

        start = first.get(student_id)
        delta = snap.rating - start.rating if start else 0

        if sort_by == 'highest_rating':
            sort_value = snap.highest_rating or 0
        elif sort_by == 'rating_improvement':
            sort_value = delta
        elif sort_by == 'country_rank':
            sort_value = snap.country_rank or 10 ** 9
        elif sort_by == 'global_rank':
            sort_value = snap.global_rank or 10 ** 9
        else:
            sort_value = snap.rating or 0

        entries.append({
            'student': student,
            'current_rating': snap.rating,
            'highest_rating': snap.highest_rating,
            'stars': snap.stars,
            'global_rank': snap.global_rank,
            'country_rank': snap.country_rank,
            'rating_improvement': delta,
            'snapshots': _snapshot_count(student_id),
            '_sort': sort_value,
        })

    entries.sort(key=lambda item: item['_sort'],
                 reverse=(sort_dir != 'asc'))

    # Dense ranking: equal values share a rank.
    ranked = []
    previous = object()
    current_rank = 0
    for position, entry in enumerate(entries, start=1):
        if entry['_sort'] != previous:
            current_rank = position
            previous = entry['_sort']
        entry['rank'] = current_rank
        entry.pop('_sort', None)
        ranked.append(entry)

    sections = sorted({
        section for (section,) in db.session.query(Student.section).distinct()
        if section
    })

    return render_template(
        'leaderboard/index.html',
        leaderboard=ranked,
        sort_by=sort_by,
        sort_dir=sort_dir,
        sections=sections,
        search_query=search_query,
        section_filter=section_filter,
    )


def _snapshot_count(student_id):
    from ..models import RatingHistory
    return RatingHistory.query.filter_by(student_id=student_id).count()
