from flask import Flask, request, jsonify
from agent import run_agent
from database.db import init_db
from database.pts import get_pt_by_instagram_id
from channels.instagram import verify_webhook, parse_message, send_reply
from config import INSTAGRAM_VERIFY_TOKEN

app = Flask(__name__)

init_db()

@app.route('/health', methods=['GET'])
def health():
    return 'OK', 200

@app.route('/instagram', methods=['GET'])
def instagram_verify():
    mode, token, challenge = verify_webhook(request)
    if mode == 'subscribe' and token == INSTAGRAM_VERIFY_TOKEN:
        return challenge, 200
    return 'Forbidden', 403

@app.route('/instagram', methods=['POST'])
def instagram_webhook():
    payload = request.get_json()
    if not payload:
        return 'OK', 200

    parsed = parse_message(payload)
    if not parsed:
        return 'OK', 200

    # Identify which PT this message belongs to
    pt = get_pt_by_instagram_id(parsed['recipient_id'])
    if not pt:
        return 'OK', 200

    pt = dict(pt)

    reply = run_agent(
        pt=pt,
        sender_id=parsed['sender_id'],
        message_text=parsed['message_text']
    )

    send_reply(
        sender_id=parsed['sender_id'],
        reply_text=reply,
        instagram_token=pt['instagram_token']
    )

    return 'OK', 200

if __name__ == '__main__':
    app.run(debug=True)