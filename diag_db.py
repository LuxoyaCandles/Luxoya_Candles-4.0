from app import create_app
from extensions import db
from sqlalchemy import text
import sys

app = create_app()
with app.app_context():
    try:
        db.session.execute(text('SELECT view_count FROM products LIMIT 1'))
        print('COLUMN_EXISTS')
    except Exception as e:
        print(f'ERROR: {e}')
        # Check if the error is specifically about the missing column
        if 'column "view_count" does not exist' in str(e).lower():
            print('DIAGNOSIS: view_count column is missing from the database.')
        else:
            print('DIAGNOSIS: Other database error detected.')
