import sqlite3
import os

DATA_DIR = os.getenv('DATA_DIR', '.')
DATABASE = os.path.join(DATA_DIR, 'ptbot.db')

def get_db():
    conn = sqlite3.connect(DATABASE)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db()
    cursor = conn.cursor()

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS pts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            instagram_account_id TEXT,
            instagram_token TEXT,
            handoff_number TEXT,
            tone_config TEXT,
            calendly_link TEXT,
            price_mode TEXT CHECK(price_mode IN ('reveal', 'deflect')) DEFAULT 'deflect',
            channels TEXT DEFAULT '["instagram"]',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS contacts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            pt_id INTEGER NOT NULL,
            sender_id TEXT NOT NULL,
            channel TEXT NOT NULL,
            is_new BOOLEAN DEFAULT TRUE,
            name TEXT,
            handed_off BOOLEAN DEFAULT FALSE,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (pt_id) REFERENCES pts (id)
        )
    ''')

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            contact_id INTEGER NOT NULL,
            role TEXT NOT NULL,
            content TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (contact_id) REFERENCES contacts (id)
        )
    ''')

    # Add demo_slug column if it doesn't exist (safe migration)
    try:
        cursor.execute('ALTER TABLE pts ADD COLUMN demo_slug TEXT')
    except Exception:
        pass  # Column already exists

    # Add blocked_senders column if it doesn't exist (safe migration)
    try:
        cursor.execute("ALTER TABLE pts ADD COLUMN blocked_senders TEXT DEFAULT '[]'")
    except Exception:
        pass  # Column already exists

    conn.commit()
    conn.close()
    print("PTBot database initialised.")

if __name__ == '__main__':
    init_db()
