"""Run the Flask development server.

Set ``PORT`` to override the default port, for example::

    set PORT=5001 && python run_server.py
"""
import os

from app import create_app

app = create_app()

port = int(os.environ.get('PORT', '5000'))
print('Starting Flask development server...')
print(f'Visit http://127.0.0.1:{port} to access the application')
print(f'Visit http://127.0.0.1:{port}/auth/login to log in')

app.run(host='127.0.0.1', port=port, debug=True)
