from app import create_app
from app.extensions import db
from sqlalchemy import inspect

app = create_app()
with app.app_context():
    ins = inspect(db.engine)
    for table in ['users', 'students', 'student_statistics', 'rating_history', 'sync_logs']:
        cols = ins.get_columns(table)
        print(f'Table: {table}')
        for c in cols:
            print(f'  {c["name"]}: {c["type"]}')