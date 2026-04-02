from database.db import get_db

def get_contact(pt_id, sender_id, channel):
    conn = get_db()
    contact = conn.execute('''
        SELECT * FROM contacts
        WHERE pt_id = ? AND sender_id = ? AND channel = ?
    ''', (pt_id, sender_id, channel)).fetchone()
    conn.close()
    return contact

def create_contact(pt_id, sender_id, channel):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('''
        INSERT INTO contacts (pt_id, sender_id, channel)
        VALUES (?, ?, ?)
    ''', (pt_id, sender_id, channel))
    conn.commit()
    contact_id = cursor.lastrowid
    conn.close()
    return contact_id

def get_or_create_contact(pt_id, sender_id, channel):
    """
    Returns (contact_id, is_new).
    is_new tells the agent whether this is the very first message
    from this person — used in the system prompt to set opening context.
    """
    contact = get_contact(pt_id, sender_id, channel)
    if contact:
        return contact['id'], False
    else:
        contact_id = create_contact(pt_id, sender_id, channel)
        return contact_id, True

def get_all_contacts():
    conn = get_db()
    contacts = conn.execute('SELECT * FROM contacts').fetchall()
    conn.close()
    return [dict(c) for c in contacts]

def mark_handed_off(contact_id):
    conn = get_db()
    conn.execute(
        'UPDATE contacts SET handed_off = TRUE WHERE id = ?',
        (contact_id,)
    )
    conn.commit()
    conn.close()
