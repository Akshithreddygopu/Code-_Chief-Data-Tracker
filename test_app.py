from app import create_app

app = create_app()
print('App created successfully!')

# Test that routes are registered
with app.app_context():
    rules = [rule.rule for rule in app.url_map.iter_rules()]
    print(f'Total routes: {len(rules)}')
    print('Registered routes:')
    for rule in sorted(rules):
        print(f'  {rule}')