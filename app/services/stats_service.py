"""Read-only helpers for aggregating rating data.

Every function works from the ``rating_history`` table and returns plain
Python structures so routes and templates stay simple.
"""

from ..models import RatingHistory


# CodeChef division buckets by current rating.
RATING_BUCKETS = [
    ("1 star (<1400)", 0, 1399),
    ("2 star (1400-1599)", 1400, 1599),
    ("3 star (1600-1799)", 1600, 1799),
    ("4 star (1800-1999)", 1800, 1999),
    ("5 star (2000-2199)", 2000, 2199),
    ("6 star (2200-2499)", 2200, 2499),
    ("7 star (2500+)", 2500, 10 ** 9),
]


def latest_rating_map():
    """Return ``{student_id: latest RatingHistory}`` in one query."""
    rows = RatingHistory.query.order_by(
        RatingHistory.student_id.asc(),
        RatingHistory.recorded_at.desc(),
        RatingHistory.id.desc(),
    ).all()

    latest = {}
    for row in rows:
        latest.setdefault(row.student_id, row)
    return latest


def first_rating_map():
    """Return ``{student_id: first RatingHistory}`` in one query."""
    rows = RatingHistory.query.order_by(
        RatingHistory.student_id.asc(),
        RatingHistory.recorded_at.asc(),
        RatingHistory.id.asc(),
    ).all()

    first = {}
    for row in rows:
        first.setdefault(row.student_id, row)
    return first


def rating_distribution(ratings):
    """Bucket a list of rating values into CodeChef divisions."""
    buckets = [{"label": label, "count": 0} for label, _, _ in RATING_BUCKETS]
    for rating in ratings:
        if rating is None:
            continue
        for index, (_, low, high) in enumerate(RATING_BUCKETS):
            if low <= rating <= high:
                buckets[index]["count"] += 1
                break
    return buckets


def improvement_entries():
    """Build one improvement row per student that has any rating history.

    ``delta`` is latest rating minus first recorded rating.
    """
    latest = latest_rating_map()
    first = first_rating_map()
    entries = []

    for student_id, snap in latest.items():
        student = snap.student
        start = first.get(student_id)
        delta = snap.rating - start.rating if start else 0
        entries.append({
            "student": student,
            "first": start.rating if start else snap.rating,
            "latest": snap.rating,
            "delta": delta,
            "snapshots": RatingHistory.query.filter_by(
                student_id=student_id).count(),
            "stars": snap.stars,
            "highest_rating": snap.highest_rating,
        })

    entries.sort(key=lambda item: item["delta"], reverse=True)
    return entries


def class_average_trend():
    """Average rating per recorded day, ordered oldest to newest."""
    rows = RatingHistory.query.order_by(
        RatingHistory.recorded_at.asc()).all()
    buckets = {}
    for row in rows:
        if row.rating is None or row.recorded_at is None:
            continue
        key = row.recorded_at.strftime("%d %b")
        bucket = buckets.setdefault(key, {"sum": 0, "count": 0})
        bucket["sum"] += row.rating
        bucket["count"] += 1

    labels = list(buckets.keys())
    values = [round(buckets[label]["sum"] / buckets[label]["count"], 1)
              for label in labels]
    return labels, values
