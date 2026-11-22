"""Test script to verify app creation and database initialization."""
import sys
import os

# Remove the instance DB if it exists
db_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'instance', 'codechef_tracker.db')
if os.path.exists(db_path):
    os.remove(db_path)

from app import create_app

app = create_app()
print('✓ App created successfully!')

with app.app_context():
    from app.extensions import db
    db.create_all()
    print('✓ Database tables created!')
    
    # Verify tables
    from sqlalchemy import inspect
    inspector = inspect(db.engine)
    tables = inspector.get_table_names()
    print(f'Created tables: {tables}')
    
    # Test user creation
    from app.models import User
    from app.services.security import hash_password, check_password_hash
    
    # Check if admin user exists
    admin = User.query.filter_by(role='admin').first()
    if admin:
        print(f'✓ Admin user exists: {admin.name} ({admin.email})')
    else:
        print('! No admin user found - creating admin account')
        admin = User()
        admin.name = 'Admin'
        admin.email = 'admin@codecheftracker.local'
        admin.set_password('admin123')
        admin.role = 'admin'
        db.session.add(admin)
        db.session.commit()
        print('✓ Admin user created successfully')
        
        # Test login
        from flask_login import login_user
        login_user(admin)
        print('✓ Login test passed')