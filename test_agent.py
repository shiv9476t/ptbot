from database.db import init_db
from database.pts import get_pt_by_instagram_id
from agent import run_agent

pt = dict(get_pt_by_instagram_id('arjhanrai.fitgains'))
sender_id = 'test_prospect_001'

print("PTBot test conversation (type 'quit' to exit)\n")

while True:
    user_input = input("Prospect: ").strip()
    if user_input.lower() == 'quit':
        break
    if not user_input:
        continue

    reply = run_agent(
        pt=pt,
        sender_id=sender_id,
        message_text=user_input
    )

    print(f"\nArjhan: {reply}\n")