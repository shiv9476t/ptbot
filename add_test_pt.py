from database.db import get_db, init_db

init_db()

conn = get_db()
cursor = conn.cursor()

cursor.execute('''
    INSERT INTO pts (
        name,
        instagram_account_id,
        instagram_token,
        handoff_number,
        tone_config,
        calendly_link,
        price_mode,
        channels
    )
    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
''', (
    'James Hartley Fitness',
    'james_hartley_ig_account_id',       # Replace with real IG account ID
    'james_hartley_ig_token',            # Replace with real token
    '+447700900999',
    'Direct and no-nonsense. Casual language. Occasional dry humour. Short sentences. No corporate tone. Never say "absolutely" or "certainly".',
    'https://calendly.com/jameshartley/discovery',
    'deflect',
    '["instagram"]'
))

conn.commit()
print("Test PT added.")
conn.close()
