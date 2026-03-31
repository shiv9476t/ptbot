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
    'IGAASdLpoNZAQNBZAGEzT3p0c2UxV3JTTnhvVWliczNaOUt3V2s3eHdVcVBLTC1UXzhhNlNqT3hrVUlyaGpILUJMV0VzSGplRXEzTmJmN3Q1OWhMcGlyRWM2TkdUMmJFMlhvcEtOdlVXM1I1R29WRF82d3hfN1RNU1htS1IzYWtMVQZDZD',
    '',
    'Warm, direct and a bit cheeky. Occasionally uses Punjabi/Hindi words naturally when it genuinely fits — never forces them in. Emojis are used but not overdone — 💪🏽 and 😋 are on brand, rows of emojis are not. Casual and conversational, sounds like a mate who happens to be a coach. Short sentences. Never preachy. Never corporate. Big on the message that you can eat your favourite foods — roti, curry, Indian food — and still lose fat. Genuinely frustrated by coaches who tell clients to cut out cultural foods. Talks about real life — family, enjoying food, not being too restrictive. Believes fitness should fit around your life, not the other way around. Never uses phrases like "amazing", "fantastic", "certainly" or "absolutely". Calls out bad fitness advice directly and confidently.',
    'https://calendly.com/arjhanrai-fitgains/30min',
    'deflect',
    '["instagram"]'
))

conn.commit()
print("Test Instagram account added.")
conn.close()