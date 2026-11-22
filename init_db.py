"""Database initialization script for CodeChef Class Performance Tracker.

This script initializes the MySQL database with the required tables.
Run this after MySQL is running.
"""

import sys
import os

# Add the project directory to the path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app import create_app
from app.models import db

def init_database():
    """Initialize the database by creating all tables."""
    app = create_app()
    
    with app.app_context():
        try:
            db.create_all()
            print("✓ Database tables created successfully!")
            
            # Verify tables were created
            from sqlalchemy import inspect
            inspector = inspect(db.engine)
            tables = inspector.get_table_names()
            print(f"Created tables: {tables}")
            
            return True
        except Exception as e:
            print(f"✗ Failed to create database: {e}")
            return False

if __name__ == '__main__':
    success = init_database()
    sys.exit(0 if success else 1)