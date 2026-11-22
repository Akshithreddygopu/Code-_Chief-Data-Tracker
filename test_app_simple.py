"""Test script to verify app creation without problematic imports."""
import sys
import os

# Remove the instance DB if it exists
db_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'instance', 'codechef_tracker.db')
if os.path.exists(db_path):
    os.remove(db_path)

from app import create_app

app = create_app()
print('✓ App created successfully!')

# Test that routes are registered (except reports which has pandas issue)
with app.app_context():
    rules = [rule.rule for rule in app.url_map.iter_rules()]
    print(f'Total routes: {len(rules)}')
    
    # Check key routes exist
    key_routes = ['/', '/auth/login', '/students', '/leaderboard', '/analytics']
    for route in key_routes:
        found = any(route in r for r in rules)
        print(f'  {route}: {"✓" if found else "✗"}')