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

def get_messages_for_contact(contact_id):
    conn = get_db()
    messages = conn.execute('''
        SELECT id, role, content, created_at FROM messages
        WHERE contact_id = ?
        ORDER BY created_at ASC
    ''', (contact_id,)).fetchall()
    conn.close()
    return [dict(m) for m in messages]

def get_conversations_for_pt(instagram_account_id):
    conn = get_db()
    rows = conn.execute('''
        SELECT
            c.id AS contact_id,
            c.sender_id,
            c.name,
            c.is_new,
            c.handed_off,
            c.created_at AS contact_created_at,
            m.id AS message_id,
            m.role,
            m.content,
            m.created_at AS message_created_at
        FROM contacts c
        JOIN pts p ON c.pt_id = p.id
        LEFT JOIN messages m ON m.contact_id = c.id
        WHERE p.instagram_account_id = ?
        ORDER BY c.id ASC, m.created_at ASC
    ''', (instagram_account_id,)).fetchall()
    conn.close()

    contacts = {}
    for row in rows:
        cid = row['contact_id']
        if cid not in contacts:
            contacts[cid] = {
                'contact_id': cid,
                'sender_id': row['sender_id'],
                'name': row['name'],
                'is_new': row['is_new'],
                'handed_off': row['handed_off'],
                'created_at': row['contact_created_at'],
                'messages': [],
            }
        if row['message_id'] is not None:
            contacts[cid]['messages'].append({
                'id': row['message_id'],
                'role': row['role'],
                'content': row['content'],
                'created_at': row['message_created_at'],
            })

    return list(contacts.values())

def is_rate_limited(pt_id, sender_id, limit=3, window_seconds=60):
    """
    Returns True if the sender has sent more than `limit` messages
    within the last `window_seconds`. Prevents Claude API spam from
    leads who send many messages in quick succession.
    """
    conn = get_db()
    row = conn.execute('''
        SELECT COUNT(*) as count FROM messages m
        JOIN contacts c ON m.contact_id = c.id
        WHERE c.pt_id = ? AND c.sender_id = ?
        AND m.role = 'user'
        AND m.created_at >= datetime('now', ? || ' seconds')
    ''', (pt_id, sender_id, f'-{window_seconds}')).fetchone()
    conn.close()
    return row['count'] >= limit

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
