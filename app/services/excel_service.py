"""Excel / CSV import and report generation.

Pure openpyxl + csv implementation (no pandas dependency) so it works
on locked-down Windows hosts where pandas native DLLs are blocked.
"""

import csv
import os
import re
from datetime import datetime

from openpyxl import Workbook, load_workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter
from werkzeug.utils import secure_filename

from .codechef_provider import CodeChefProvider

REQUIRED_COLUMNS = [
    "Roll Number",
    "Student Name",
    "Department",
    "Year",
    "Section",
]

# Optional columns: the import works with or without a CodeChef profile.
OPTIONAL_COLUMNS = ["CodeChef URL"]

# Full header row written into the downloadable template.
TEMPLATE_COLUMNS = REQUIRED_COLUMNS + OPTIONAL_COLUMNS

# Normalised header -> canonical name
HEADER_ALIASES = {
    "roll number": "Roll Number",
    "roll no": "Roll Number",
    "rollno": "Roll Number",
    "roll": "Roll Number",
    "student name": "Student Name",
    "name": "Student Name",
    "student": "Student Name",
    "department": "Department",
    "dept": "Department",
    "year": "Year",
    "academic year": "Year",
    "section": "Section",
    "sec": "Section",
    "codechef url": "CodeChef URL",
    "codechef url username": "CodeChef URL",
    "codechef profile": "CodeChef URL",
    "codechef profile url": "CodeChef URL",
    "profile url": "CodeChef URL",
    "codechef username": "CodeChef URL",
    "codechef handle": "CodeChef URL",
    "username": "CodeChef URL",
    "handle": "CodeChef URL",
    "url": "CodeChef URL",
}

ALLOWED_EXTENSIONS = {"xlsx", "xlsm", "csv"}

_HEADER_FILL = PatternFill("solid", start_color="1E3A5F", end_color="1E3A5F")
_HEADER_FONT_COLOR = "FFFFFF"
_THIN = Side(style="thin", color="D9E2EF")
_BORDER = Border(left=_THIN, right=_THIN, top=_THIN, bottom=_THIN)


def _bold(color=None, size=None):
    kwargs = {"bold": True}
    if color:
        kwargs["color"] = color
    if size:
        kwargs["size"] = size
    return Font(**kwargs)


# --------------------------------------------------------------------------
# Helpers
# --------------------------------------------------------------------------

def allowed_file(filename: str) -> bool:
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS


def _norm_header(value) -> str:
    if value is None:
        return ""
    # Strip punctuation and collapse whitespace so "Roll No." matches
    # "roll no" and "Dept." matches "dept".
    text = re.sub(r"[^a-z0-9]+", " ", str(value).lower())
    return re.sub(r"\s+", " ", text).strip()


def _cell_text(value) -> str:
    if value is None:
        return ""
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value).strip()


def _instance_dir() -> str:
    path = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(
        os.path.abspath(__file__)))), "instance")
    os.makedirs(path, exist_ok=True)
    return path


# --------------------------------------------------------------------------
# Import parsing
# --------------------------------------------------------------------------

def _read_table(file_storage):
    """Return (headers, rows) from an uploaded xlsx/xlsm/csv file."""
    filename = secure_filename(file_storage.filename or "")
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    tmp_dir = os.path.join(_instance_dir(), "uploads")
    os.makedirs(tmp_dir, exist_ok=True)
    tmp_path = os.path.join(tmp_dir, f"{datetime.now().strftime('%Y%m%d%H%M%S%f')}_{filename}")
    file_storage.save(tmp_path)

    try:
        if ext == "csv":
            with open(tmp_path, "r", encoding="utf-8-sig", errors="replace", newline="") as fh:
                sample = fh.read(4096)
                fh.seek(0)
                try:
                    dialect = csv.Sniffer().sniff(sample, delimiters=",;\t")
                except csv.Error:
                    dialect = csv.excel
                reader = csv.reader(fh, dialect)
                table = [row for row in reader if any(_cell_text(c) for c in row)]
            if not table:
                return [], []
            headers = table[0]
            return headers, table[1:]

        wb = load_workbook(tmp_path, read_only=True, data_only=True)
        ws = wb.active
        rows_iter = ws.iter_rows(values_only=True)
        try:
            headers = list(next(rows_iter))
        except StopIteration:
            wb.close()
            return [], []
        rows = [list(r) for r in rows_iter if any(_cell_text(c) for c in r)]
        wb.close()
        return headers, rows
    finally:
        try:
            os.remove(tmp_path)
        except OSError:
            pass


def parse_students_file(file_storage, existing_rolls=None, existing_usernames=None):
    """Parse and validate an uploaded roster file.

    Returns a dict describing every row so the UI can show a preview
    before the admin confirms the import.
    """
    existing_rolls = {str(r).strip().lower() for r in (existing_rolls or [])}
    existing_usernames = {str(u).strip().lower() for u in (existing_usernames or [])}

    result = {
        "success": False,
        "error": None,
        "headers": [],
        "missing_columns": [],
        "rows": [],
        "summary": {"total": 0, "valid": 0, "invalid": 0, "duplicate": 0},
    }

    if not file_storage or not file_storage.filename:
        result["error"] = "Please choose a file to upload."
        return result
    if not allowed_file(file_storage.filename):
        result["error"] = "Unsupported file type. Upload a .xlsx, .xlsm or .csv file."
        return result

    try:
        raw_headers, raw_rows = _read_table(file_storage)
    except Exception as exc:  # noqa: BLE001 - surfaced to the admin
        result["error"] = f"Could not read the file: {exc}"
        return result

    if not raw_headers:
        result["error"] = "The file appears to be empty."
        return result

    # Map each header column index to a canonical column name
    index_map = {}
    display_headers = []
    for idx, header in enumerate(raw_headers):
        canonical = HEADER_ALIASES.get(_norm_header(header))
        display_headers.append(_cell_text(header))
        if canonical and canonical not in index_map:
            index_map[canonical] = idx

    result["headers"] = display_headers
    result["missing_columns"] = [c for c in REQUIRED_COLUMNS if c not in index_map]
    if result["missing_columns"]:
        result["error"] = (
            "Missing required column(s): " + ", ".join(result["missing_columns"])
        )
        return result

    seen_rolls = set()
    seen_usernames = set()

    for offset, raw in enumerate(raw_rows, start=2):
        def val(col):
            idx = index_map.get(col)
            if idx is None or idx >= len(raw):
                return ""
            return _cell_text(raw[idx])

        data = {
            "roll_number": val("Roll Number"),
            "name": val("Student Name"),
            "department": val("Department"),
            "academic_year": val("Year"),
            "section": val("Section"),
            "codechef_url": val("CodeChef URL"),
            "codechef_username": "",
        }
        errors = []

        # "N/A", "none", "-" and similar placeholders mean "not linked".
        if data["codechef_url"].strip().lower() in {
                "", "na", "n/a", "none", "nil", "-", "--", "not applicable"}:
            data["codechef_url"] = ""

        for field, label in (
            ("roll_number", "Roll number"),
            ("name", "Student name"),
            ("department", "Department"),
            ("academic_year", "Year"),
            ("section", "Section"),
        ):
            if not data[field]:
                errors.append(f"{label} is required")

        status = "valid"

        if data["roll_number"]:
            key = data["roll_number"].lower()
            if key in existing_rolls:
                status = "duplicate"
                errors.append("Roll number already exists in the database")
            elif key in seen_rolls:
                status = "duplicate"
                errors.append("Duplicate roll number inside the file")
            else:
                seen_rolls.add(key)

        if data["codechef_url"]:
            ok, extracted = CodeChefProvider.extract_username(data["codechef_url"])
            if not ok:
                status = "invalid" if status != "duplicate" else status
                errors.append(f"Invalid CodeChef URL ({extracted})")
            else:
                data["codechef_username"] = extracted
                data["codechef_url"] = f"https://www.codechef.com/users/{extracted}"
                ukey = extracted.lower()
                if ukey in existing_usernames:
                    status = "duplicate"
                    errors.append("CodeChef username already linked to another student")
                elif ukey in seen_usernames:
                    status = "duplicate"
                    errors.append("Duplicate CodeChef username inside the file")
                else:
                    seen_usernames.add(ukey)

        if errors and status == "valid":
            status = "invalid"

        result["rows"].append({
            "row_number": offset,
            "data": data,
            "status": status,
            "errors": errors,
        })
        result["summary"][status] += 1

    result["summary"]["total"] = len(result["rows"])
    result["success"] = True
    return result


# --------------------------------------------------------------------------
# Template
# --------------------------------------------------------------------------

def build_import_template() -> str:
    """Create the downloadable sample roster workbook."""
    wb = Workbook()
    ws = wb.active
    ws.title = "Students"

    for col, header in enumerate(TEMPLATE_COLUMNS, start=1):
        cell = ws.cell(row=1, column=col, value=header)
        cell.font = _bold(color=_HEADER_FONT_COLOR)
        cell.fill = _HEADER_FILL
        cell.alignment = Alignment(horizontal="center", vertical="center")
        cell.border = _BORDER

    sample = [
        "21CS001", "Aarav Sharma", "Computer Science", "3rd Year", "A",
        "https://www.codechef.com/users/aarav_sharma",
    ]
    for col, value in enumerate(sample, start=1):
        cell = ws.cell(row=2, column=col, value=value)
        cell.border = _BORDER

    widths = {"A": 14, "B": 26, "C": 24, "D": 12, "E": 10, "F": 46}
    for col, width in widths.items():
        ws.column_dimensions[col].width = width
    ws.freeze_panes = "A2"

    notes = wb.create_sheet("Instructions")
    guidance = [
        ("How to use this template", ""),
        ("", ""),
        ("1.", "Keep the header row exactly as shown on the 'Students' sheet."),
        ("2.", "One student per row. Do not merge cells or leave blank rows."),
        ("3.", "Roll Number must be unique across the class."),
        ("4.", "CodeChef URL is optional. Paste either a profile URL "
                "(https://www.codechef.com/users/<username>) or just the username."),
        ("5.", "Rows without a CodeChef profile are imported as 'Not linked' "
                "and can be linked later from Synchronization."),
        ("6.", "Save as .xlsx or .csv, then upload it from Students → Import."),
    ]
    for r, (a, b) in enumerate(guidance, start=1):
        title_cell = notes.cell(row=r, column=1, value=a)
        if r == 1:
            title_cell.font = _bold(size=13)
        notes.cell(row=r, column=2, value=b)
    notes.column_dimensions["A"].width = 28
    notes.column_dimensions["B"].width = 80

    path = os.path.join(_instance_dir(), "student_import_template.xlsx")
    wb.save(path)
    return path


# --------------------------------------------------------------------------
# Report helpers
# --------------------------------------------------------------------------

def _new_sheet(wb, title, heading, subtitle, columns, widths):
    ws = wb.active
    ws.title = title

    ws.cell(row=1, column=1, value=heading).font = _bold(size=15, color="1E3A5F")
    ws.cell(row=2, column=1, value=subtitle)
    ws.cell(row=3, column=1, value=f"Generated: {datetime.now():%d %b %Y, %H:%M}")
    ws.merge_cells(start_row=1, start_column=1, end_row=1, end_column=max(len(columns), 1))
    ws.merge_cells(start_row=2, start_column=1, end_row=2, end_column=max(len(columns), 1))
    ws.merge_cells(start_row=3, start_column=1, end_row=3, end_column=max(len(columns), 1))

    header_row = 5
    for idx, header in enumerate(columns, start=1):
        cell = ws.cell(row=header_row, column=idx, value=header)
        cell.font = _bold(color=_HEADER_FONT_COLOR)
        cell.fill = _HEADER_FILL
        cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
        cell.border = _BORDER

    for col, width in widths.items():
        ws.column_dimensions[col].width = width
    ws.freeze_panes = ws.cell(row=header_row + 1, column=1)

    return ws, header_row + 1


def _write_rows(ws, start_row, rows):
    for r, row in enumerate(rows, start=start_row):
        for c, value in enumerate(row, start=1):
            cell = ws.cell(row=r, column=c, value=value)
            cell.border = _BORDER
            if c > 1:
                cell.alignment = Alignment(horizontal="center", vertical="center")
    return start_row + len(rows)


def _save(wb, filename):
    path = os.path.join(_instance_dir(), filename)
    wb.save(path)
    return path


def export_students_workbook(students, filename="class_performance.xlsx"):
    """Full class roster with latest statistics."""
    from ..models import RatingHistory, StudentStatistics

    columns = [
        "Rank", "Roll Number", "Student Name", "Department", "Year", "Section",
        "CodeChef Username", "CodeChef Name", "Link Status", "Last Sync",
        "Current Rating", "Highest Rating", "Stars", "Global Rank",
        "Country Rank", "Problems Solved", "Contests", "Profile URL",
        "Last Synced",
    ]
    widths = {"A": 8, "B": 14, "C": 26, "D": 22, "E": 11, "F": 9, "G": 20,
              "H": 20, "I": 12, "J": 15, "K": 14, "L": 14, "M": 8, "N": 12,
              "O": 13, "P": 15, "Q": 10, "R": 44, "S": 18}

    wb = Workbook()
    ws, start = _new_sheet(
        wb, "Class Performance", "CodeChef Class Performance Report",
        f"{len(students)} student(s) included in this report", columns, widths,
    )

    status_labels = {
        "success": "Synchronized", "failed": "Failed",
        "unlinked": "Not linked",
    }

    rows = []
    for index, student in enumerate(students, start=1):
        latest = (RatingHistory.query.filter_by(student_id=student.id)
                  .order_by(RatingHistory.recorded_at.desc()).first())
        stats = StudentStatistics.query.filter_by(student_id=student.id).first()
        last_synced = (stats.last_synced_at if stats and stats.last_synced_at
                       else student.last_sync_at)
        rows.append([
            index,
            student.roll_number,
            student.name,
            student.department,
            student.academic_year,
            student.section,
            student.codechef_username or "—",
            student.codechef_display_name or "—",
            "Linked" if student.codechef_username else "Not linked",
            status_labels.get(student.last_sync_status or "", "Never"),
            latest.rating if latest else "N/A",
            latest.highest_rating if latest else "N/A",
            latest.stars if latest else "N/A",
            latest.global_rank if latest and latest.global_rank else "N/A",
            latest.country_rank if latest and latest.country_rank else "N/A",
            stats.problems_solved if stats and stats.problems_solved is not None else "N/A",
            stats.contests_participated if stats and stats.contests_participated is not None else "N/A",
            student.codechef_url or "—",
            last_synced.strftime("%d %b %Y %H:%M") if last_synced else "Never",
        ])

    _write_rows(ws, start, rows)
    ws.auto_filter.ref = f"A5:S{start + max(len(rows) - 1, 0)}"
    return _save(wb, filename)


def export_student_detail(student, filename=None):
    """Single student report with summary and rating history."""
    from ..models import RatingHistory, StudentStatistics

    latest = (RatingHistory.query.filter_by(student_id=student.id)
              .order_by(RatingHistory.recorded_at.desc()).first())
    stats = StudentStatistics.query.filter_by(student_id=student.id).first()
    history = (RatingHistory.query.filter_by(student_id=student.id)
               .order_by(RatingHistory.recorded_at.asc()).all())

    filename = filename or f"student_{student.roll_number}.xlsx"
    wb = Workbook()
    ws = wb.active
    ws.title = "Student Report"

    ws.cell(row=1, column=1, value="Individual Student Report").font = \
        _bold(size=15, color="1E3A5F")
    ws.cell(row=2, column=1, value=f"Generated: {datetime.now():%d %b %Y, %H:%M}")

    summary = [
        ("Roll Number", student.roll_number),
        ("Student Name", student.name),
        ("Department", student.department),
        ("Academic Year", student.academic_year),
        ("Section", student.section),
        ("CodeChef Username", student.codechef_username or "Not provided"),
        ("Profile URL", student.codechef_url or "Not provided"),
        ("Current Rating", latest.rating if latest else "N/A"),
        ("Highest Rating", latest.highest_rating if latest else "N/A"),
        ("Stars", latest.stars if latest else "N/A"),
        ("Global Rank", latest.global_rank if latest and latest.global_rank else "N/A"),
        ("Country Rank", latest.country_rank if latest and latest.country_rank else "N/A"),
        ("Problems Solved", stats.problems_solved if stats and stats.problems_solved is not None else "N/A"),
        ("Contests Participated", stats.contests_participated if stats and stats.contests_participated is not None else "N/A"),
        ("Last Synchronized", stats.last_synced_at.strftime("%d %b %Y %H:%M") if stats and stats.last_synced_at else "Never"),
    ]

    row = 4
    for label, value in summary:
        ws.cell(row=row, column=1, value=label).font = _bold()
        ws.cell(row=row, column=2, value=value)
        row += 1

    row += 1
    ws.cell(row=row, column=1, value="Rating History").font = \
        _bold(size=12, color="1E3A5F")
    row += 1

    header_row = row
    for col, header in enumerate(
            ["Recorded At", "Rating", "Highest", "Stars", "Global Rank", "Country Rank"], start=1):
        cell = ws.cell(row=header_row, column=col, value=header)
        cell.font = _bold(color=_HEADER_FONT_COLOR)
        cell.fill = _HEADER_FILL
        cell.border = _BORDER

    data_rows = [[
        entry.recorded_at.strftime("%d %b %Y %H:%M") if entry.recorded_at else "",
        entry.rating, entry.highest_rating, entry.stars,
        entry.global_rank or "N/A", entry.country_rank or "N/A",
    ] for entry in history]

    if data_rows:
        _write_rows(ws, header_row + 1, data_rows)
    else:
        ws.cell(row=header_row + 1, column=1,
                value="No rating history recorded yet.")

    for col, width in {"A": 26, "B": 24, "C": 12, "D": 10, "E": 14, "F": 14}.items():
        ws.column_dimensions[col].width = width

    return _save(wb, filename)


def export_improvement_workbook(entries, filename="rating_improvement.xlsx"):
    """entries: list of dicts with student, first, latest, delta, snapshots."""
    columns = ["Rank", "Roll Number", "Student Name", "Section", "Username",
               "First Rating", "Latest Rating", "Change", "Snapshots"]
    widths = {"A": 8, "B": 14, "C": 26, "D": 9, "E": 20, "F": 14, "G": 14, "H": 12, "I": 11}

    wb = Workbook()
    ws, start = _new_sheet(
        wb, "Rating Improvement", "Rating Improvement Report",
        "Students ordered by rating change between their first and latest recorded snapshot",
        columns, widths,
    )
    rows = [[
        i,
        e["student"].roll_number,
        e["student"].name,
        e["student"].section,
        e["student"].codechef_username or "—",
        e["first"],
        e["latest"],
        e["delta"],
        e["snapshots"],
    ] for i, e in enumerate(entries, start=1)]

    _write_rows(ws, start, rows)
    return _save(wb, filename)


def export_rank_workbook(students, filename="codechef_rank_analysis.xlsx"):
    """Rank-focused workbook with global/country rank for every student."""
    from ..models import RatingHistory

    columns = ["Position", "Roll Number", "Student Name", "Section",
               "Username", "CodeChef Name", "Current Rating", "Global Rank",
               "Country Rank", "Highest Rating", "Stars", "Last Synced"]
    widths = {"A": 9, "B": 14, "C": 26, "D": 9, "E": 20, "F": 24, "G": 14,
              "H": 13, "I": 13, "J": 14, "K": 8, "L": 18}

    wb = Workbook()
    ws, start = _new_sheet(
        wb, "Global & Country Ranks", "CodeChef Rank Analysis",
        f"{len(students)} linked student(s) included · best global rank first",
        columns, widths,
    )

    rows = []
    for student in students:
        latest = (RatingHistory.query.filter_by(student_id=student.id)
                  .order_by(RatingHistory.recorded_at.desc()).first())
        rows.append([
            0,
            student.roll_number,
            student.name,
            student.section,
            student.codechef_username or "—",
            student.codechef_display_name or "—",
            latest.rating if latest else "N/A",
            latest.global_rank if latest and latest.global_rank else "—",
            latest.country_rank if latest and latest.country_rank else "—",
            latest.highest_rating if latest else "N/A",
            latest.stars if latest else "N/A",
            latest.recorded_at.strftime("%d %b %Y %H:%M")
            if latest and latest.recorded_at else "Never",
        ])

    # Best (lowest) global rank first, then country rank, then rating.
    rows.sort(key=lambda row: (
        not isinstance(row[7], int),
        row[7] if isinstance(row[7], int) else 0,
        not isinstance(row[8], int),
        row[8] if isinstance(row[8], int) else 0,
    ))
    for position, row in enumerate(rows, start=1):
        row[0] = position

    _write_rows(ws, start, rows)
    ws.auto_filter.ref = f"A5:L{start + max(len(rows) - 1, 0)}"

    global_ranks = [r[7] for r in rows if isinstance(r[7], int)]
    country_ranks = [r[8] for r in rows if isinstance(r[8], int)]
    summary = wb.create_sheet("Rank summary")
    summary.cell(row=1, column=1, value="Rank analysis summary").font = \
        _bold(size=15, color="1E3A5F")
    facts = [
        ("Students in report", len(students)),
        ("Students with a global rank", len(global_ranks)),
        ("Students with a country rank", len(country_ranks)),
        ("Best global rank", min(global_ranks) if global_ranks else "N/A"),
        ("Best country rank", min(country_ranks) if country_ranks else "N/A"),
        ("Generated", datetime.now().strftime("%d %b %Y, %H:%M")),
    ]
    for r, (label, value) in enumerate(facts, start=3):
        summary.cell(row=r, column=1, value=label).font = _bold()
        summary.cell(row=r, column=2, value=value)
    summary.column_dimensions["A"].width = 34
    summary.column_dimensions["B"].width = 24

    return _save(wb, filename)


def export_unlinked_workbook(students, filename="unlinked_students.xlsx"):
    """Students without a CodeChef profile, ready to be linked offline."""
    columns = ["Roll Number", "Student Name", "Department", "Year", "Section",
               "CodeChef Username", "CodeChef Name", "Added On"]
    widths = {"A": 14, "B": 26, "C": 24, "D": 12, "E": 10, "F": 20, "G": 20,
              "H": 16}

    wb = Workbook()
    ws, start = _new_sheet(
        wb, "Not Linked", "Students Not Linked to CodeChef",
        f"{len(students)} student(s) still need a CodeChef profile",
        columns, widths,
    )

    rows = [[
        student.roll_number,
        student.name,
        student.department,
        student.academic_year,
        student.section,
        student.codechef_username or "—",
        student.codechef_display_name or "—",
        student.created_at.strftime("%d %b %Y") if student.created_at else "",
    ] for student in students]

    _write_rows(ws, start, rows)
    return _save(wb, filename)


def export_sync_errors_workbook(logs, filename="sync_errors.xlsx"):
    columns = ["Log ID", "Started", "Completed", "Status", "Processed",
               "Successful", "Failed", "Error Details"]
    widths = {"A": 9, "B": 20, "C": 20, "D": 12, "E": 11, "F": 12, "G": 9, "H": 90}

    wb = Workbook()
    ws, start = _new_sheet(
        wb, "Sync Errors", "Synchronization Error Report",
        "Failed and partially failed synchronization runs",
        columns, widths,
    )
    rows = [[
        log.id,
        log.started_at.strftime("%d %b %Y %H:%M") if log.started_at else "",
        log.completed_at.strftime("%d %b %Y %H:%M") if log.completed_at else "",
        (log.status or "").title(),
        log.total_processed,
        log.successful_count,
        log.failed_count,
        (log.error_details or "")[:3000],
    ] for log in logs]

    _write_rows(ws, start, rows)
    return _save(wb, filename)


# Backwards-compatible alias used by reports.py
def export_to_excel(students=None, filename=None):
    from ..models import Student
    if students is None:
        students = Student.query.filter_by(status="active").all()
    return export_students_workbook(
        students, filename or f"class_performance_{datetime.now():%Y%m%d_%H%M%S}.xlsx")
