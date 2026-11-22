"""Synchronization service.

Fetches the latest public CodeChef statistics for a student and stores
them without ever destroying previously valid data. A new rating
snapshot is only appended when a value actually changed (or when the
student has no snapshot yet).

Every attempt also records a per-student outcome
(``last_sync_status`` / ``last_sync_error`` / ``last_sync_at``) so the
UI can show exactly which students are linked, which are not, and which
failed.
"""

import re
from datetime import datetime

from ..extensions import db
from ..models import RatingHistory, Student, StudentStatistics, SyncLog
from .codechef_provider import CodeChefProvider

STATUS_SUCCESS = "success"
STATUS_FAILED = "failed"
STATUS_UNLINKED = "unlinked"

_STATUS_LABELS = {
    STATUS_SUCCESS: "Synchronized",
    STATUS_FAILED: "Sync failed",
    STATUS_UNLINKED: "Not linked",
}


def status_label(status):
    """Human readable label for a stored synchronization status."""
    return _STATUS_LABELS.get(status or "", "Never synchronized")


def names_differ(roster_name, codechef_name):
    """True when two names share no word at all.

    CodeChef names are often short (``Aryan``) while the roster carries a
    full name (``Aryan Mehta``), so a shared token is treated as a match.
    """
    if not roster_name or not codechef_name:
        return False
    roster_tokens = set(re.findall(r"[a-z0-9]+", roster_name.lower()))
    codechef_tokens = set(re.findall(r"[a-z0-9]+", codechef_name.lower()))
    if not roster_tokens or not codechef_tokens:
        return False
    return not (roster_tokens & codechef_tokens)


def _latest_snapshot(student_id):
    return (RatingHistory.query
            .filter_by(student_id=student_id)
            .order_by(RatingHistory.recorded_at.desc(),
                      RatingHistory.id.desc())
            .first())


def _store_snapshot(student, data, latest):
    """Append a RatingHistory row only when something meaningful changed."""
    rating = data.get("current_rating")
    if rating is None:
        return False

    highest = data.get("highest_rating") or (latest.highest_rating if latest else rating)
    stars = data.get("stars") or (latest.stars if latest else 0)
    global_rank = data.get("global_rank") or (latest.global_rank if latest else None)
    country_rank = data.get("country_rank") or (latest.country_rank if latest else None)

    if latest is not None:
        unchanged = (
            latest.rating == rating
            and latest.highest_rating == highest
            and latest.stars == stars
            and latest.global_rank == global_rank
            and latest.country_rank == country_rank
        )
        if unchanged:
            return False

    db.session.add(RatingHistory(
        student_id=student.id,
        rating=rating,
        highest_rating=max(highest, rating),
        stars=stars,
        global_rank=global_rank,
        country_rank=country_rank,
        recorded_at=datetime.utcnow(),
    ))
    return True


def _record_attempt(student, status, error=None):
    student.last_sync_status = status
    student.last_sync_error = (error or "")[:255] or None
    student.last_sync_at = datetime.utcnow()


def sync_student(student):
    """Synchronize one student.

    Returns a dict with ``status`` (success / failed / skipped), a human
    readable ``message`` and, when relevant, an ``error`` string.
    """
    if student is None:
        return {"status": "failed", "message": "Student not found.",
                "error": "Student not found."}

    username = student.codechef_username
    if not username and student.codechef_url:
        ok, value = CodeChefProvider.extract_username(student.codechef_url)
        if ok:
            username = value
            student.codechef_username = value

    if not username:
        _record_attempt(student, STATUS_UNLINKED)
        db.session.commit()
        return {
            "status": "skipped",
            "message": "No CodeChef profile linked.",
            "error": "No CodeChef username or profile URL on record.",
        }

    data = CodeChefProvider.get_student_stats(username)
    if not data:
        _record_attempt(student, STATUS_FAILED,
                        f"No response from CodeChef for @{username}.")
        db.session.commit()
        return {
            "status": "failed",
            "message": f"No response from CodeChef for @{username}.",
            "error": f"Empty response for @{username}.",
        }

    error = data.get("error")
    if error:
        _record_attempt(student, STATUS_FAILED, f"@{username}: {error}")
        db.session.commit()
        return {
            "status": "failed",
            "message": f"Could not sync @{username}: {error}.",
            "error": f"@{username}: {error}",
        }

    display_name = data.get("display_name")
    # Some profiles show the handle itself in the heading; that is not a
    # separate "real name" and should not be reported as a name mismatch.
    if display_name and username and \
            display_name.strip().lower() == username.strip().lower():
        display_name = None
    student.codechef_display_name = (display_name or "")[:120] or None

    stats = StudentStatistics.query.filter_by(student_id=student.id).first()
    if stats is None:
        stats = StudentStatistics(student_id=student.id,
                                  problems_solved=0,
                                  contests_participated=0)
        db.session.add(stats)

    if data.get("problems_solved") is not None:
        stats.problems_solved = data["problems_solved"]
    if data.get("contests_participated") is not None:
        stats.contests_participated = data["contests_participated"]
    stats.last_synced_at = datetime.utcnow()

    latest = _latest_snapshot(student.id)
    changed = _store_snapshot(student, data, latest)

    _record_attempt(student, STATUS_SUCCESS)
    db.session.commit()

    return {
        "status": "success",
        "message": f"@{username} synchronized{' (new snapshot)' if changed else ''}.",
        "error": None,
        "changed": changed,
        "display_name": student.codechef_display_name,
        "name_mismatch": names_differ(student.name,
                                      student.codechef_display_name),
    }


def sync_all_students(only_failed=False):
    """Synchronize every student with a CodeChef profile.

    ``only_failed`` restricts the run to students whose last attempt failed,
    which is useful for a quick retry. The run is persisted in ``SyncLog``
    so the UI can display progress, counts and failure reasons.
    """
    log = SyncLog(started_at=datetime.utcnow(), status="running")
    db.session.add(log)
    db.session.commit()

    query = Student.query
    if only_failed:
        query = query.filter(Student.last_sync_status == STATUS_FAILED)
    candidates = query.order_by(Student.roll_number.asc()).all()

    students = [s for s in candidates if s.codechef_username]
    skipped = len(candidates) - len(students)

    if not only_failed:
        # Keep the "not linked" marker fresh for every unlinked student.
        for student in candidates:
            if not student.codechef_username and \
                    student.last_sync_status != STATUS_UNLINKED:
                student.last_sync_status = STATUS_UNLINKED

    log.total_processed = len(candidates)
    log.skipped_count = skipped
    db.session.commit()

    errors = []
    successful = 0
    failed = 0
    snapshots = 0

    for student in students:
        try:
            result = sync_student(student)
        except Exception as exc:  # keep the batch alive
            db.session.rollback()
            failed += 1
            errors.append(f"{student.roll_number}: {exc}")
            try:
                Student.query.filter_by(id=student.id).update({
                    Student.last_sync_status: STATUS_FAILED,
                    Student.last_sync_error: str(exc)[:255],
                    Student.last_sync_at: datetime.utcnow(),
                })
                db.session.commit()
            except Exception:
                db.session.rollback()
            continue

        if result["status"] == "success":
            successful += 1
            if result.get("changed"):
                snapshots += 1
        else:
            failed += 1
            if result.get("error"):
                errors.append(f"{student.roll_number}: {result['error']}")

    log.successful_count = successful
    log.failed_count = failed
    log.completed_at = datetime.utcnow()
    if students and successful == 0 and failed:
        log.status = "failed"
    else:
        log.status = "completed"
    if errors:
        log.error_details = "\n".join(errors)[:8000]
    db.session.commit()

    return {
        "log_id": log.id,
        "total": len(candidates),
        "successful": successful,
        "failed": failed,
        "skipped": skipped,
        "snapshots": snapshots,
        "status": log.status,
    }


def sync_overview():
    """Aggregate the data the synchronization screen needs.

    Returns counts plus the actual student records for:
    * profiles that are not linked yet,
    * linked profiles whose last synchronization failed,
    * linked profiles whose CodeChef name differs from the roster name.
    """
    students = Student.query.order_by(Student.name.asc()).all()

    linked = [s for s in students if s.codechef_username]
    unlinked = [s for s in students if not s.codechef_username]
    failed = [s for s in students if s.last_sync_status == STATUS_FAILED]
    mismatched = [s for s in linked
                  if names_differ(s.name, s.codechef_display_name)]
    never_synced = [s for s in linked if not s.last_sync_at]

    last_success = max(
        (s.last_sync_at for s in linked
         if s.last_sync_status == STATUS_SUCCESS and s.last_sync_at),
        default=None,
    )

    return {
        "total": len(students),
        "linked": len(linked),
        "unlinked": len(unlinked),
        "failed": failed,
        "failed_count": len(failed),
        "mismatched": mismatched,
        "mismatched_count": len(mismatched),
        "never_synced": never_synced,
        "never_synced_count": len(never_synced),
        "unlinked_students": unlinked,
        "last_success": last_success,
    }
