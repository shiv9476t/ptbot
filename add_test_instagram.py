from database.db import get_db, init_db

init_db()

conn = get_db()
cursor = conn.cursor()

cursor.execute("DELETE FROM pts WHERE instagram_account_id = '17841470877982771'")

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
    'Arjhan Rai',
    '17841470877982771',
    'YOUR_TOKEN_HERE',
    '',
    'Warm, direct and a bit cheeky. Casual and conversational, sounds like a mate who happens to be a coach. Short sentences. Never preachy. Never corporate. Big on the message that you can eat your favourite foods and still lose fat. Occasionally uses Punjabi/Hindi words naturally when it genuinely fits — never forces them in.',
    'https://calendly.com/arjhanrai-fitgains/30min',
    'deflect',
    '["instagram"]'
))

conn.commit()
print("Test Instagram account added.")
conn.close()