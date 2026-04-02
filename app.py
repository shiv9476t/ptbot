import requests
from flask import Flask, request, jsonify
from agent import run_agent
from database.db import init_db, get_db
from database.pts import get_pt_by_instagram_id, get_all_pts, update_pt
from database.contacts import get_all_contacts
from database.conversations import get_messages_for_contact
from channels.instagram import verify_webhook, verify_signature, parse_message, send_reply
from config import INSTAGRAM_VERIFY_TOKEN, ADMIN_SECRET, META_APP_ID, META_INSTAGRAM_APP_SECRET
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

@app.route('/admin/pt/update', methods=['POST'])
def admin_pt_update():
    if request.headers.get('Authorization') != f'Bearer {ADMIN_SECRET}':
        return 'Forbidden', 403
    body = request.get_json()
    if not body or 'instagram_account_id' not in body:
        return jsonify({'error': 'instagram_account_id required'}), 400
    instagram_account_id = body.pop('instagram_account_id')
    updated = update_pt(instagram_account_id, body)
    if updated is None:
        return jsonify({'error': 'PT not found or no valid fields provided'}), 404
    return jsonify(updated), 200

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

OAUTH_REDIRECT_URI = 'https://web-production-21bb5.up.railway.app/auth/callback'

@app.route('/auth/callback', methods=['GET'])
def auth_callback():
    code = request.args.get('code')
    if not code:
        return 'Missing code parameter', 400

    # Exchange code for access token
    token_resp = requests.post('https://api.instagram.com/oauth/access_token', data={
        'client_id': META_APP_ID,
        'client_secret': META_INSTAGRAM_APP_SECRET,
        'grant_type': 'authorization_code',
        'redirect_uri': OAUTH_REDIRECT_URI,
        'code': code,
    })
    if not token_resp.ok:
        return f'Failed to exchange code: {token_resp.text}', 502

    token_data = token_resp.json()
    access_token = token_data.get('access_token')
    if not access_token:
        return 'No access token in response', 502

    # Fetch the Instagram account ID
    me_resp = requests.get('https://graph.instagram.com/me', params={
        'fields': 'id',
        'access_token': access_token,
    })
    if not me_resp.ok:
        return f'Failed to fetch user info: {me_resp.text}', 502

    instagram_account_id = me_resp.json().get('id')
    if not instagram_account_id:
        return 'No user ID in response', 502

    # Insert new PT record
    conn = get_db()
    conn.execute(
        '''INSERT INTO pts (name, instagram_account_id, instagram_token, price_mode, channels)
           VALUES (?, ?, ?, ?, ?)''',
        ('New PT', instagram_account_id, access_token, 'deflect', '["instagram"]'),
    )
    conn.commit()
    conn.close()

    return '''<!DOCTYPE html>
<html><body>
<h2>Account connected!</h2>
<p>Your Instagram account has been successfully connected to PTBot.</p>
</body></html>''', 200

if __name__ == '__main__':
    app.run(debug=True)