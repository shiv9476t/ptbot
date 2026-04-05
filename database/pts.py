import json
from database.db import get_db

def get_pt_by_instagram_id(instagram_account_id):
    """
    Identifies which PT tenant a message belongs to.
    All inbound Instagram DMs arrive at the same webhook endpoint —
    this routes them to the right PT by their connected account ID.
    """
    conn = get_db()
    pt = conn.execute(
        'SELECT * FROM pts WHERE instagram_account_id = ?',
        (instagram_account_id,)
    ).fetchone()
    conn.close()
    return pt

def get_all_pts():
    conn = get_db()
    pts = conn.execute('SELECT * FROM pts').fetchall()
    conn.close()
    return [dict(pt) for pt in pts]

def get_pt_by_id(pt_id):
    conn = get_db()
    pt = conn.execute(
        'SELECT * FROM pts WHERE id = ?',
        (pt_id,)
    ).fetchone()
    conn.close()
    return pt

def get_pt_by_slug(slug):
    conn = get_db()
    pt = conn.execute(
        'SELECT * FROM pts WHERE demo_slug = ?',
        (slug,)
    ).fetchone()
    conn.close()
    return pt

def is_sender_blocked(instagram_account_id, sender_id):
    conn = get_db()
    row = conn.execute(
        'SELECT blocked_senders FROM pts WHERE instagram_account_id = ?',
        (instagram_account_id,)
    ).fetchone()
    conn.close()
    if not row:
        return False
    blocked = json.loads(row['blocked_senders'] or '[]')
    return sender_id in blocked

def block_sender(instagram_account_id, sender_id):
    conn = get_db()
    row = conn.execute(
        'SELECT blocked_senders FROM pts WHERE instagram_account_id = ?',
        (instagram_account_id,)
    ).fetchone()
    if not row:
        conn.close()
        return False
    blocked = json.loads(row['blocked_senders'] or '[]')
    if sender_id not in blocked:
        blocked.append(sender_id)
        conn.execute(
            'UPDATE pts SET blocked_senders = ? WHERE instagram_account_id = ?',
            (json.dumps(blocked), instagram_account_id)
        )
        conn.commit()
    conn.close()
    return True

def unblock_sender(instagram_account_id, sender_id):
    conn = get_db()
    row = conn.execute(
        'SELECT blocked_senders FROM pts WHERE instagram_account_id = ?',
        (instagram_account_id,)
    ).fetchone()
    if not row:
        conn.close()
        return False
    blocked = json.loads(row['blocked_senders'] or '[]')
    blocked = [s for s in blocked if s != sender_id]
    conn.execute(
        'UPDATE pts SET blocked_senders = ? WHERE instagram_account_id = ?',
        (json.dumps(blocked), instagram_account_id)
    )
    conn.commit()
    conn.close()
    return True

def update_pt(instagram_account_id, fields):
    allowed = {'name', 'tone_config', 'calendly_link', 'price_mode', 'handoff_number', 'demo_slug'}
    updates = {k: v for k, v in fields.items() if k in allowed}
    if not updates:
        return None
    clauses = ', '.join(f'{k} = ?' for k in updates)
    values = list(updates.values()) + [instagram_account_id]
    conn = get_db()
    conn.execute(
        f'UPDATE pts SET {clauses} WHERE instagram_account_id = ?',
        values
    )
    conn.commit()
    pt = conn.execute(
        'SELECT * FROM pts WHERE instagram_account_id = ?',
        (instagram_account_id,)
    ).fetchone()
    conn.close()
    return dict(pt) if pt else None
