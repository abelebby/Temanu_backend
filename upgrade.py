from sqlalchemy import text
from app.database import engine

print("Connecting to Railway database...")

try:
    with engine.connect() as conn:
        conn.execute(text("""
            ALTER TABLE users 
            ADD COLUMN gender VARCHAR(20), 
            ADD COLUMN dob VARCHAR(50), 
            ADD COLUMN blood_type VARCHAR(10);
        """))
        conn.commit()
    print("Success! The new columns have been added.")
except Exception as e:
    print(f"An error occurred: {e}")