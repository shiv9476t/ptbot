from database.db import get_db

def save_message(contact_id, role, content):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('''
        INSERT INTO messages (contact_id, role, content)
        VALUES (?, ?, ?)
    ''', (contact_id, role, content))
    conn.commit()
    conn.close()

def get_conversation_history(contact_id, limit=20):
    """
    Returns the last N messages in chronological order.
    Limit is higher than GymBot (20 vs 10) — PT conversations
    tend to be longer as qualification happens over multiple turns.
    """
    conn = get_db()
    messages = conn.execute('''
        SELECT role, content FROM messages
        WHERE contact_id = ?
        ORDER BY created_at DESC
        LIMIT ?
    ''', (contact_id, limit)).fetchall()
    conn.close()
    return [{'role': row['role'], 'content': row['content']} for row in reversed(messages)]

def get_last_inbound_timestamp(contact_id):
    """
    Returns the timestamp of the most recent user message.
    Used to check whether the Instagram 24-hour messaging window is still open
    before attempting to send a follow-up message.
    """
    conn = get_db()
    row = conn.execute('''
        SELECT created_at FROM messages
        WHERE contact_id = ? AND role = 'user'
        ORDER BY created_at DESC
        LIMIT 1
    ''', (contact_id,)).fetchone()
    conn.close()
    return row['created_at'] if row else None
