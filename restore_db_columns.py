
import os
from sqlalchemy import text
from app import create_app
from extensions import db

def restore_schema():
    app = create_app()
    with app.app_context():
        engine = db.engine
        print(f"CONNECTING TO: {app.config['SQLALCHEMY_DATABASE_URI']}")
        
        # Format: (table, column, type_definition)
        restores = [
            # Product Columns
            ("products", "recipe_id", "VARCHAR(100)"),
            ("products", "views", "INTEGER DEFAULT 0"),
            ("products", "short_description", "VARCHAR(500)"),
            ("products", "video_url", "VARCHAR(500)"),
            ("products", "occasion_tags", "VARCHAR(255)"),
            
            # User Columns
            ("users", "referral_code", "VARCHAR(50)"),
            ("users", "loyalty_points", "INTEGER DEFAULT 0")
        ]
        
        with engine.connect() as conn:
            for table, col, col_type in restores:
                try:
                    # Check if column exists (simplified check for SQLite/Postgres)
                    # We'll just try to add it and catch the error if it exists
                    conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {col} {col_type}"))
                    conn.commit()
                    print(f"SUCCESS: Added '{col}' to '{table}'")
                except Exception as e:
                    if "already exists" in str(e).lower() or "duplicate column" in str(e).lower():
                        print(f"SKIPPED: Column '{col}' already exists in '{table}'")
                    else:
                        print(f"ERROR adding '{col}' to '{table}': {str(e)}")
            
            print("\nDatabase Schema Restoration Completed.")

if __name__ == '__main__':
    restore_schema()
