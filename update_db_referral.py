
import sqlite3
import os

db_path = "instance/luxoya_dev.db"
if os.path.exists(db_path):
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    try:
        print("Adding 'referred_by_id' to 'users' table...")
        cursor.execute("ALTER TABLE users ADD COLUMN referred_by_id TEXT")
        conn.commit()
        print("SUCCESS: Added 'referred_by_id' to 'users'")
    except sqlite3.OperationalError as e:
        if "duplicate column name" in str(e).lower():
            print("'referred_by_id' already exists in 'users'")
        else:
            print(f"Error: {e}")
    finally:
        conn.close()
else:
    print(f"Database not found at {db_path}")
