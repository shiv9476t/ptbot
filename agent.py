import anthropic
from config import ANTHROPIC_API_KEY
from database.contacts import get_or_create_contact
from database.conversations import save_message, get_conversation_history
from prompt import build_system_prompt
from knowledge import search_knowledge

client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

def run_agent(pt, sender_id, message_text):
    # Step 1 - identify or create the contact
    contact_id, is_new = get_or_create_contact(
        pt_id=pt['id'],
        sender_id=sender_id,
        channel='instagram'
    )

    # Step 2 - load conversation history
    history = get_conversation_history(contact_id)

    # Step 3 - save the incoming message
    save_message(contact_id, 'user', message_text)

    # Step 4 - build messages list for Claude
    messages = history + [{'role': 'user', 'content': message_text}]

    # Step 5 - search knowledge base for relevant chunks
    knowledge_chunks = search_knowledge(pt['instagram_account_id'], message_text)

    # Step 6 - build system prompt
    system_prompt = build_system_prompt(
        pt=pt,
        is_new=is_new,
        knowledge_chunks=knowledge_chunks
    )
    print(f"Tone config: {pt['tone_config'][:100]}")

    # Step 7 - call the Anthropic API
    try:
        response = client.messages.create(
            model='claude-sonnet-4-20250514',
            max_tokens=1000,
            system=system_prompt,
            messages=messages
        )
    except Exception as e:
        print(f"Claude API error for sender {sender_id}: {e}")
        return None

    reply = response.content[0].text

    # Step 8 - save Claude's reply
    save_message(contact_id, 'assistant', reply)

    return reply