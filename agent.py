import anthropic
from config import ANTHROPIC_API_KEY
from database.contacts import get_or_create_contact
from database.conversations import save_message, get_conversation_history
from prompt import build_system_prompt
from knowledge import search_knowledge
from photos import load_photos, find_best_photo, get_photo_url

client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

TRANSFORMATION_PHOTO_TOOL = {
    "name": "get_transformation_photo",
    "description": (
        "Retrieve a real client transformation photo to share with the lead. "
        "Use this when the lead asks for proof of results, expresses doubt about "
        "whether coaching works, or when showing a real transformation would help "
        "move them toward booking a call. Only call once per response."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": (
                    "Description of the type of transformation you're looking for, "
                    "e.g. 'fat loss busy professional male' or 'muscle building beginner female'."
                )
            }
        },
        "required": ["query"]
    }
}


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

    # Step 7 - load photos and conditionally include the tool
    photos = load_photos(pt['pt_folder']) if pt.get('pt_folder') else []
    print(f"Photos loaded: {len(photos)} from pt_folder={pt.get('pt_folder')}")
    tools = [TRANSFORMATION_PHOTO_TOOL] if photos else []
    print(f"Tools active: {[t['name'] for t in tools]}")

    # Step 8 - call the Anthropic API
    try:
        response = client.messages.create(
            model='claude-sonnet-4-20250514',
            max_tokens=1000,
            system=system_prompt,
            messages=messages,
            tools=tools if tools else anthropic.NOT_GIVEN,
        )
    except Exception as e:
        print(f"Claude API error for sender {sender_id}: {e}")
        return None, None

    photo_url = None

    # Step 9 - handle tool use if Claude called get_transformation_photo
    if response.stop_reason == 'tool_use':
        tool_use_block = next(
            (b for b in response.content if b.type == 'tool_use'),
            None
        )
        if tool_use_block:
            query = tool_use_block.input.get('query', '')
            photo = find_best_photo(photos, query)

            if photo:
                photo_url = get_photo_url(pt['instagram_account_id'], photo['filename'])
                tool_result_content = (
                    f"Photo URL: {photo_url}\n"
                    f"Description: {photo['description']}\n"
                    f"Important: do NOT include the URL in your reply — the photo will be sent automatically as a separate image message."
                )
            else:
                tool_result_content = "No matching transformation photo found."

            # Continue conversation with tool result to get final text reply
            messages = messages + [
                {'role': 'assistant', 'content': response.content},
                {'role': 'user', 'content': [{
                    'type': 'tool_result',
                    'tool_use_id': tool_use_block.id,
                    'content': tool_result_content,
                }]}
            ]

            try:
                response = client.messages.create(
                    model='claude-sonnet-4-20250514',
                    max_tokens=1000,
                    system=system_prompt,
                    messages=messages,
                )
            except Exception as e:
                print(f"Claude API error (tool follow-up) for sender {sender_id}: {e}")
                return None, None

    reply = next(
        (b.text for b in response.content if hasattr(b, 'text')),
        None
    )

    if reply is None:
        print(f"No text content in Claude response for sender {sender_id}")
        return None, None

    # Step 10 - save Claude's reply
    save_message(contact_id, 'assistant', reply)

    return reply, photo_url
