import requests
from flask import Flask, request, jsonify
from agent import run_agent
from database.db import init_db, get_db
from database.pts import get_pt_by_instagram_id, get_all_pts, update_pt, get_pt_by_slug, is_sender_blocked, block_sender, unblock_sender
from database.contacts import get_all_contacts
from database.conversations import get_messages_for_contact, get_conversations_for_pt
from channels.instagram import verify_webhook, verify_signature, parse_message, send_reply
from config import INSTAGRAM_VERIFY_TOKEN, ADMIN_SECRET, META_APP_ID, META_INSTAGRAM_APP_SECRET
from swap_demo_pt import swap
from add_demo_pt import add as add_demo_pt, update as update_demo_pt
from setup_pt import setup as setup_pt

app = Flask(__name__)

init_db()

# Railway hits this every few seconds to confirm the server process is alive.
# Returns a plain 200 with no logic — intentionally simple so it never fails
# due to a database or external service issue.
@app.route('/health', methods=['GET'])
def health():
    return 'OK', 200

# Step 1 of Meta's webhook setup. When you register a webhook URL in the Meta
# developer dashboard, Meta sends a one-time GET with a challenge value to prove
# you own the server. We confirm by echoing the challenge back.
@app.route('/instagram', methods=['GET'])
def instagram_verify():
    mode, token, challenge = verify_webhook(request)
    if mode == 'subscribe' and token == INSTAGRAM_VERIFY_TOKEN:
        return challenge, 200
    return 'Forbidden', 403

# The live webhook — every Instagram DM sent to any connected PT account arrives
# here as a POST. We verify the payload is genuinely from Meta, parse out the
# sender and message, look up which PT owns the receiving account, run the agent
# to generate a reply, then send it back via the Instagram Graph API.
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

    if is_sender_blocked(pt['instagram_account_id'], parsed['sender_id']):
        return 'OK', 200

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

# Admin utility for testing the agent directly without going through Instagram.
# Useful for simulating a conversation as a specific sender, or for debugging
# a PT's prompt and knowledge base. Protected by ADMIN_SECRET.
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

# Lets you inspect the raw chunks stored in a PT's ChromaDB collection — useful
# for verifying embeddings were created correctly after onboarding a PT.
# Pass ?instagram_account_id=<id> as a query parameter.
@app.route('/admin/db/chromadb', methods=['GET'])
def admin_db_chromadb():
    if request.headers.get('Authorization') != f'Bearer {ADMIN_SECRET}':
        return 'Forbidden', 403
    instagram_account_id = request.args.get('instagram_account_id')
    if not instagram_account_id:
        return jsonify({'error': 'instagram_account_id query param required'}), 400
    import chromadb as _chromadb
    import os as _os
    chroma = _chromadb.PersistentClient(path=_os.path.join(_os.getenv('DATA_DIR', '.'), 'chromadb_store'))
    try:
        collection = chroma.get_collection(name=instagram_account_id)
    except Exception:
        return jsonify({'error': f'No collection found for {instagram_account_id}'}), 404
    results = collection.get()
    chunks = [
        {'id': doc_id, 'text': text}
        for doc_id, text in zip(results['ids'], results['documents'])
    ]
    return jsonify({'instagram_account_id': instagram_account_id, 'count': len(chunks), 'chunks': chunks}), 200

# Returns all PT records from the database. Useful for checking which PTs are
# onboarded and inspecting their config (token, tone, price mode, etc.).
@app.route('/admin/db/pts', methods=['GET'])
def admin_db_pts():
    if request.headers.get('Authorization') != f'Bearer {ADMIN_SECRET}':
        return 'Forbidden', 403
    return jsonify(get_all_pts()), 200

# Returns all contacts (leads) across all PTs. Each contact represents a unique
# Instagram user who has DMed a PT at least once.
@app.route('/admin/db/contacts', methods=['GET'])
def admin_db_contacts():
    if request.headers.get('Authorization') != f'Bearer {ADMIN_SECRET}':
        return 'Forbidden', 403
    return jsonify(get_all_contacts()), 200

# Returns all contacts and their full message history for a single PT.
# Pass ?instagram_account_id=<id>. Works for both real and demo PTs.
@app.route('/admin/db/conversations', methods=['GET'])
def admin_db_conversations():
    if request.headers.get('Authorization') != f'Bearer {ADMIN_SECRET}':
        return 'Forbidden', 403
    instagram_account_id = request.args.get('instagram_account_id')
    if not instagram_account_id:
        return jsonify({'error': 'instagram_account_id query param required'}), 400
    return jsonify(get_conversations_for_pt(instagram_account_id)), 200

# Returns the full message history for a single contact. Pass ?contact_id=<id>.
# Useful for reading an entire conversation thread for a specific lead.
@app.route('/admin/db/messages', methods=['GET'])
def admin_db_messages():
    if request.headers.get('Authorization') != f'Bearer {ADMIN_SECRET}':
        return 'Forbidden', 403
    contact_id = request.args.get('contact_id')
    if not contact_id:
        return jsonify({'error': 'contact_id query param required'}), 400
    return jsonify(get_messages_for_contact(contact_id)), 200

# Completes onboarding for a real PT after OAuth. Takes the bare record created
# by /auth/callback, updates it with fields from config.json, and embeds their
# docs into ChromaDB so the bot can start handling their DMs.
@app.route('/admin/pt/setup', methods=['POST'])
def admin_pt_setup():
    if request.headers.get('Authorization') != f'Bearer {ADMIN_SECRET}':
        return 'Forbidden', 403
    body = request.get_json()
    if not body or not body.get('pt_folder') or not body.get('instagram_account_id'):
        return jsonify({'error': 'pt_folder and instagram_account_id required'}), 400
    try:
        setup_pt(body['pt_folder'], body['instagram_account_id'])
        return jsonify({'ok': True}), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500

# Updates fields on a PT record (e.g. tone_config, calendly_link, price_mode).
# The instagram_account_id in the request body identifies which PT to update;
# all other fields in the body are treated as the values to change.
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

# Adds a sender_id to a PT's blocked list. The agent will silently ignore
# any future messages from that sender.
@app.route('/admin/pt/block', methods=['POST'])
def admin_pt_block():
    if request.headers.get('Authorization') != f'Bearer {ADMIN_SECRET}':
        return 'Forbidden', 403
    body = request.get_json()
    if not body or not body.get('instagram_account_id') or not body.get('sender_id'):
        return jsonify({'error': 'instagram_account_id and sender_id required'}), 400
    found = block_sender(body['instagram_account_id'], body['sender_id'])
    if not found:
        return jsonify({'error': 'PT not found'}), 404
    return jsonify({'ok': True}), 200

# Removes a sender_id from a PT's blocked list.
@app.route('/admin/pt/unblock', methods=['POST'])
def admin_pt_unblock():
    if request.headers.get('Authorization') != f'Bearer {ADMIN_SECRET}':
        return 'Forbidden', 403
    body = request.get_json()
    if not body or not body.get('instagram_account_id') or not body.get('sender_id'):
        return jsonify({'error': 'instagram_account_id and sender_id required'}), 400
    found = unblock_sender(body['instagram_account_id'], body['sender_id'])
    if not found:
        return jsonify({'error': 'PT not found'}), 404
    return jsonify({'ok': True}), 200

# Replaces the demo PT on the shared shiv.trains Instagram account. Deletes the
# existing PT record and ChromaDB collection for that account, then inserts the
# new PT from the given folder. Used to switch which PT is being demoed live.
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

# Updates an existing demo PT's config and knowledge base. Reads config.json
# for updated fields, wipes and re-embeds the ChromaDB collection with the
# current docs, and leaves conversation history untouched.
@app.route('/admin/demo/update', methods=['POST'])
def admin_demo_update():
    if request.headers.get('Authorization') != f'Bearer {ADMIN_SECRET}':
        return 'Forbidden', 403
    body = request.get_json()
    if not body or 'pt_folder' not in body:
        return jsonify({'error': 'pt_folder required'}), 400
    try:
        update_demo_pt(body['pt_folder'])
        return jsonify({'ok': True}), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500

# Adds a new demo PT without touching any existing records. Inserts a PT row
# with a fake instagram_account_id (demo_<slug>) and embeds their docs into
# ChromaDB so the demo chat page at /demo/<slug> works.
@app.route('/admin/demo/add', methods=['POST'])
def admin_demo_add():
    if request.headers.get('Authorization') != f'Bearer {ADMIN_SECRET}':
        return 'Forbidden', 403
    body = request.get_json()
    if not body or 'pt_folder' not in body:
        return jsonify({'error': 'pt_folder required'}), 400
    try:
        add_demo_pt(body['pt_folder'])
        return jsonify({'ok': True}), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500

OAUTH_REDIRECT_URI = 'https://web-production-21bb5.up.railway.app/auth/callback'

# OAuth callback for PT onboarding. After a PT authorises PTBot via the Meta
# OAuth flow, Instagram redirects them here with a short-lived code. We exchange
# that code for a long-lived access token, fetch their Instagram account ID, and
# create a new PT record in the database so the bot can start handling their DMs.
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

# Serves the public-facing demo chat UI for a PT identified by their slug.
# Renders a self-contained Instagram-style dark-theme page — no login required.
# The page stores a random sender_id in localStorage so each browser session
# looks like a distinct lead to the agent.
@app.route('/demo/<slug>', methods=['GET'])
def demo_page(slug):
    import json as _json
    pt = get_pt_by_slug(slug)
    if not pt:
        return 'Demo not found', 404
    pt = dict(pt)
    pt_name = pt['name']
    instagram_account_id = pt['instagram_account_id']
    json_name = _json.dumps(pt_name)
    json_id = _json.dumps(instagram_account_id)
    json_slug = _json.dumps(slug)
    html = f'''<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Chat with {pt_name}</title>
<style>
  * {{ box-sizing: border-box; margin: 0; padding: 0; }}
  body {{
    background: #000;
    color: #fff;
    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
    display: flex;
    flex-direction: column;
    height: 100dvh;
    max-width: 480px;
    margin: 0 auto;
  }}
  .header {{
    display: flex;
    align-items: center;
    gap: 12px;
    padding: 14px 16px;
    border-bottom: 1px solid #262626;
    background: #000;
    position: sticky;
    top: 0;
    z-index: 10;
  }}
  .avatar {{
    width: 42px;
    height: 42px;
    border-radius: 50%;
    background: linear-gradient(135deg, #f09433, #e6683c, #dc2743, #cc2366, #bc1888);
    display: flex;
    align-items: center;
    justify-content: center;
    font-size: 18px;
    font-weight: 700;
    color: #fff;
    flex-shrink: 0;
  }}
  .header-info {{ flex: 1; }}
  .header-name {{ font-weight: 600; font-size: 15px; }}
  .header-sub {{ font-size: 12px; color: #737373; margin-top: 1px; }}
  .reset-btn {{
    background: none;
    border: 1px solid #363636;
    color: #a8a8a8;
    font-size: 12px;
    padding: 6px 10px;
    border-radius: 8px;
    cursor: pointer;
    white-space: nowrap;
  }}
  .reset-btn:hover {{ color: #fff; border-color: #737373; }}
  .messages {{
    flex: 1;
    overflow-y: auto;
    padding: 16px 12px;
    display: flex;
    flex-direction: column;
    gap: 8px;
  }}
  .messages::-webkit-scrollbar {{ width: 0; }}
  .bubble-row {{
    display: flex;
    align-items: flex-end;
    gap: 8px;
  }}
  .bubble-row.user {{ justify-content: flex-end; }}
  .bubble-row.pt {{ justify-content: flex-start; }}
  .bubble-avatar {{
    width: 28px;
    height: 28px;
    border-radius: 50%;
    background: linear-gradient(135deg, #f09433, #e6683c, #dc2743, #cc2366, #bc1888);
    display: flex;
    align-items: center;
    justify-content: center;
    font-size: 11px;
    font-weight: 700;
    color: #fff;
    flex-shrink: 0;
  }}
  .bubble {{
    max-width: 72%;
    padding: 10px 14px;
    border-radius: 22px;
    font-size: 14px;
    line-height: 1.45;
    word-break: break-word;
    white-space: pre-wrap;
  }}
  .bubble.user {{
    background: #3797f0;
    color: #fff;
    border-bottom-right-radius: 6px;
  }}
  .bubble.pt {{
    background: #262626;
    color: #fff;
    border-bottom-left-radius: 6px;
  }}
  .typing {{
    display: flex;
    align-items: center;
    gap: 4px;
    padding: 10px 14px;
    background: #262626;
    border-radius: 22px;
    border-bottom-left-radius: 6px;
    width: fit-content;
  }}
  .typing span {{
    width: 7px;
    height: 7px;
    background: #737373;
    border-radius: 50%;
    animation: bounce 1.2s infinite;
  }}
  .typing span:nth-child(2) {{ animation-delay: 0.2s; }}
  .typing span:nth-child(3) {{ animation-delay: 0.4s; }}
  @keyframes bounce {{
    0%, 60%, 100% {{ transform: translateY(0); }}
    30% {{ transform: translateY(-5px); }}
  }}
  .input-area {{
    padding: 10px 12px;
    border-top: 1px solid #262626;
    display: flex;
    align-items: center;
    gap: 10px;
    background: #000;
  }}
  .input-wrap {{
    flex: 1;
    background: #1a1a1a;
    border: 1px solid #363636;
    border-radius: 22px;
    display: flex;
    align-items: center;
    padding: 0 16px;
  }}
  #msg-input {{
    flex: 1;
    background: none;
    border: none;
    outline: none;
    color: #fff;
    font-size: 14px;
    padding: 10px 0;
    font-family: inherit;
    resize: none;
    max-height: 100px;
    line-height: 1.4;
  }}
  #msg-input::placeholder {{ color: #737373; }}
  #send-btn {{
    background: none;
    border: none;
    cursor: pointer;
    padding: 0;
    display: flex;
    align-items: center;
    opacity: 0.4;
    transition: opacity 0.15s;
  }}
  #send-btn.active {{ opacity: 1; }}
  #send-btn svg {{ fill: #3797f0; }}
</style>
</head>
<body>
<div class="header">
  <div class="avatar" id="header-avatar"></div>
  <div class="header-info">
    <div class="header-name">{pt_name}</div>
    <div class="header-sub">Personal Trainer &middot; Demo</div>
  </div>
  <button class="reset-btn" onclick="resetConversation()">Reset conversation</button>
</div>
<div class="messages" id="messages"></div>
<div class="input-area">
  <div class="input-wrap">
    <textarea id="msg-input" rows="1" placeholder="Message..."></textarea>
  </div>
  <button id="send-btn" onclick="sendMessage()">
    <svg width="28" height="28" viewBox="0 0 28 28"><circle cx="14" cy="14" r="14"/><path d="M8 14l3.5 3.5L20 9" stroke="#fff" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" fill="none"/></svg>
  </button>
</div>
<script>
const PT_NAME = {json_name};
const INSTAGRAM_ACCOUNT_ID = {json_id};
const SLUG = {json_slug};
const SENDER_KEY = 'ptbot_sender_' + INSTAGRAM_ACCOUNT_ID;

function initials(name) {{
  return name.split(' ').map(w => w[0]).join('').toUpperCase().slice(0, 2);
}}

document.getElementById('header-avatar').textContent = initials(PT_NAME);

function getSenderId() {{
  let id = localStorage.getItem(SENDER_KEY);
  if (!id) {{
    id = 'demo_' + Math.random().toString(36).slice(2, 12);
    localStorage.setItem(SENDER_KEY, id);
  }}
  return id;
}}

function resetConversation() {{
  const newId = 'demo_' + Math.random().toString(36).slice(2, 12);
  localStorage.setItem(SENDER_KEY, newId);
  document.getElementById('messages').innerHTML = '';
}}

function appendBubble(role, text) {{
  const msgs = document.getElementById('messages');
  const row = document.createElement('div');
  row.className = 'bubble-row ' + role;
  if (role === 'pt') {{
    const av = document.createElement('div');
    av.className = 'bubble-avatar';
    av.textContent = initials(PT_NAME);
    row.appendChild(av);
  }}
  const bubble = document.createElement('div');
  bubble.className = 'bubble ' + role;
  bubble.textContent = text;
  row.appendChild(bubble);
  msgs.appendChild(row);
  msgs.scrollTop = msgs.scrollHeight;
}}

function showTyping() {{
  const msgs = document.getElementById('messages');
  const row = document.createElement('div');
  row.className = 'bubble-row pt';
  row.id = 'typing-indicator';
  const av = document.createElement('div');
  av.className = 'bubble-avatar';
  av.textContent = initials(PT_NAME);
  row.appendChild(av);
  const t = document.createElement('div');
  t.className = 'typing';
  t.innerHTML = '<span></span><span></span><span></span>';
  row.appendChild(t);
  msgs.appendChild(row);
  msgs.scrollTop = msgs.scrollHeight;
}}

function hideTyping() {{
  const el = document.getElementById('typing-indicator');
  if (el) el.remove();
}}

async function sendMessage() {{
  const input = document.getElementById('msg-input');
  const text = input.value.trim();
  if (!text) return;
  input.value = '';
  input.style.height = 'auto';
  document.getElementById('send-btn').classList.remove('active');

  appendBubble('user', text);
  showTyping();

  try {{
    const resp = await fetch('/demo/' + encodeURIComponent(SLUG) + '/chat', {{
      method: 'POST',
      headers: {{'Content-Type': 'application/json'}},
      body: JSON.stringify({{
        sender_id: getSenderId(),
        message: text
      }})
    }});
    const data = await resp.json();
    hideTyping();
    if (data.reply) {{
      appendBubble('pt', data.reply);
    }} else {{
      appendBubble('pt', 'Something went wrong. Please try again.');
    }}
  }} catch(e) {{
    hideTyping();
    appendBubble('pt', 'Connection error. Please try again.');
  }}
}}

const input = document.getElementById('msg-input');
const sendBtn = document.getElementById('send-btn');

input.addEventListener('input', function() {{
  this.style.height = 'auto';
  this.style.height = Math.min(this.scrollHeight, 100) + 'px';
  sendBtn.classList.toggle('active', this.value.trim().length > 0);
}});

input.addEventListener('keydown', function(e) {{
  if (e.key === 'Enter' && !e.shiftKey) {{
    e.preventDefault();
    sendMessage();
  }}
}});
</script>
</body>
</html>'''
    return html, 200, {'Content-Type': 'text/html; charset=utf-8'}


# The backend endpoint the demo page calls when a user sends a message.
# No auth required — intentionally public so the demo works without a token.
# Looks up the PT by slug, runs the agent, and returns the reply as JSON.
@app.route('/demo/<slug>/chat', methods=['POST'])
def demo_chat(slug):
    pt = get_pt_by_slug(slug)
    if not pt:
        return jsonify({'error': 'Demo not found'}), 404
    body = request.get_json()
    if not body or not body.get('sender_id') or not body.get('message'):
        return jsonify({'error': 'sender_id and message are required'}), 400
    if is_sender_blocked(pt['instagram_account_id'], body['sender_id']):
        return jsonify({'error': 'Sender is blocked'}), 403
    reply = run_agent(
        pt=dict(pt),
        sender_id=body['sender_id'],
        message_text=body['message']
    )
    return jsonify({'reply': reply}), 200


if __name__ == '__main__':
    app.run(debug=True)