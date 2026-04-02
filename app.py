from flask import Flask, request, jsonify
from agent import run_agent
from database.db import init_db
from database.pts import get_pt_by_instagram_id, get_all_pts
from database.contacts import get_all_contacts
from database.conversations import get_messages_for_contact
from channels.instagram import verify_webhook, verify_signature, parse_message, send_reply
from config import INSTAGRAM_VERIFY_TOKEN, ADMIN_SECRET
from swap_demo_pt import swap

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
    if not verify_signature(request):
        return 'Forbidden', 403

    payload = request.get_json()
    if not payload:
        return 'OK', 200

    parsed = parse_message(payload)
    if parsed:
        print(f"sender_id: {parsed['sender_id']}, recipient_id: {parsed['recipient_id']}")
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

@app.route('/admin/message', methods=['POST'])
def admin_message():
    if request.headers.get('Authorization') != f'Bearer {ADMIN_SECRET}':
        return 'Forbidden', 403
    body = request.get_json()
    if not body or not all(k in body for k in ('instagram_account_id', 'sender_id', 'message')):
        return jsonify({'error': 'instagram_account_id, sender_id, and message are required'}), 400
    pt = get_pt_by_instagram_id(body['instagram_account_id'])
    if not pt:
        return jsonify({'error': 'PT not found'}), 404
    reply = run_agent(
        pt=dict(pt),
        sender_id=body['sender_id'],
        message_text=body['message']
    )
    return jsonify({'reply': reply}), 200

@app.route('/admin/db/pts', methods=['GET'])
def admin_db_pts():
    if request.headers.get('Authorization') != f'Bearer {ADMIN_SECRET}':
        return 'Forbidden', 403
    return jsonify(get_all_pts()), 200

@app.route('/admin/db/contacts', methods=['GET'])
def admin_db_contacts():
    if request.headers.get('Authorization') != f'Bearer {ADMIN_SECRET}':
        return 'Forbidden', 403
    return jsonify(get_all_contacts()), 200

@app.route('/admin/db/messages', methods=['GET'])
def admin_db_messages():
    if request.headers.get('Authorization') != f'Bearer {ADMIN_SECRET}':
        return 'Forbidden', 403
    contact_id = request.args.get('contact_id')
    if not contact_id:
        return jsonify({'error': 'contact_id query param required'}), 400
    return jsonify(get_messages_for_contact(contact_id)), 200

@app.route('/admin/swap', methods=['POST'])
def admin_swap():
    if request.headers.get('Authorization') != f'Bearer {ADMIN_SECRET}':
        return 'Forbidden', 403
    body = request.get_json()
    if not body or 'pt_folder' not in body:
        return jsonify({'error': 'pt_folder required'}), 400
    try:
        swap(body['pt_folder'])
        return jsonify({'ok': True}), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/auth/callback', methods=['GET'])
def auth_callback():
    return 'Connected successfully!', 200

if __name__ == '__main__':
    app.run(debug=True)