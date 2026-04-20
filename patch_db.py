from app import create_app
from extensions import db
from sqlalchemy import text
import traceback

app = create_app()
with app.app_context():
    try:
        print("Checking for missing columns...")
        # Step 1: Add view_count to products
        db.session.execute(text("ALTER TABLE products ADD COLUMN IF NOT EXISTS view_count INTEGER DEFAULT 0"))
        
        # Step 2: Ensure other new columns exist if any (future proofing)
        db.session.commit()
        print("DATABASE PATCH SUCCESSFUL: 'view_count' column added to 'products' table.")
    except Exception as e:
        db.session.rollback()
        print(f"DATABASE PATCH FAILED: {e}")
        traceback.print_exc()
