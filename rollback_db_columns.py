
import os
from sqlalchemy import text
from app import create_app
from extensions import db

def rollback_schema():
    app = create_app()
    with app.app_context():
        engine = db.engine
        print(f"CONNECTING TO: {app.config['SQLALCHEMY_DATABASE_URI']}")
        
        drops = [
            # Product Columns added on April 25
            ("products", "recipe_id"),
            ("products", "views"),
            ("products", "short_description"),
            ("products", "video_url"),
            ("products", "occasion_tags"),
            
            # User Columns added on April 25
            ("users", "referral_code"),
            ("users", "loyalty_points")
        ]
        
        with engine.connect() as conn:
            for table, col in drops:
                try:
                    conn.execute(text(f"ALTER TABLE {table} DROP COLUMN {col}"))
                    conn.commit()
                    print(f"SUCCESS: Dropped '{col}' from '{table}'")
                except Exception as e:
                    print(f"SKIPPED: Could not drop '{col}' from '{table}' (might not exist): {type(e).__name__}")
            
            # Note: We are keeping partners, audit_logs, etc. as they existed in the April 20 baseline models.
            print("\nDatabase Schema Rollback to April 20 Baseline Completed.")

if __name__ == '__main__':
    rollback_schema()
