import requests
import time
import random
from config import INSTAGRAM_VERIFY_TOKEN

def verify_webhook(request):
    mode = request.args.get('hub.mode')
    token = request.args.get('hub.verify_token')
    challenge = request.args.get('hub.challenge')
    return mode, token, challenge

def parse_message(payload):
    try:
        entry = payload['entry'][0]
        messaging = entry['messaging'][0]

        if 'message' not in messaging:
            return None

        message = messaging['message']

        if 'text' not in message:
            return None

        if messaging.get('message', {}).get('is_echo'):
            return None

        sender_id = messaging['sender']['id']
        recipient_id = messaging['recipient']['id']
        message_text = message['text']

        return {
            'sender_id': sender_id,
            'recipient_id': recipient_id,
            'message_text': message_text,
        }

    except (KeyError, IndexError):
        return None

def send_reply(sender_id, reply_text, instagram_token):
    # Simulate human typing time — scales with reply length
#    words = len(reply_text.split())
#    base_delay = random.uniform(5, 12)
#    typing_delay = min(words * 0.3, 15)
#    time.sleep(base_delay + typing_delay)

    url = "https://graph.facebook.com/v18.0/me/messages"

    headers = {
        'Authorization': f'Bearer {instagram_token}',
        'Content-Type': 'application/json'
    }

    payload = {
        'recipient': {'id': sender_id},
        'message': {'text': reply_text}
    }

    response = requests.post(url, headers=headers, json=payload)
    
    if response.status_code != 200:
        print(f"Instagram send error: {response.status_code} {response.text}")
    else:
        print(f"Instagram reply sent successfully to {sender_id}")
    
    return response.status_code