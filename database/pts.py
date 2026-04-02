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

def update_pt(instagram_account_id, fields):
    allowed = {'name', 'tone_config', 'calendly_link', 'price_mode', 'handoff_number'}
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
