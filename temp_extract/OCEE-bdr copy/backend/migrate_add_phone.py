#!/usr/bin/env python3
"""
Simple migration script to add phone_number column to prospects table
"""
import sqlite3
import os

def migrate():
    db_path = "bdr.db"
    if not os.path.exists(db_path):
        print(f"Database file {db_path} not found!")
        return
    
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    try:
        # Check if phone_number column already exists
        cursor.execute("PRAGMA table_info(prospects)")
        columns = [column[1] for column in cursor.fetchall()]
        
        if 'phone_number' not in columns:
            print("Adding phone_number column to prospects table...")
            cursor.execute("ALTER TABLE prospects ADD COLUMN phone_number TEXT")
            conn.commit()
            print("✅ Successfully added phone_number column!")
        else:
            print("✅ phone_number column already exists!")
            
    except Exception as e:
        print(f"❌ Error during migration: {e}")
        conn.rollback()
    finally:
        conn.close()

if __name__ == "__main__":
    migrate()
