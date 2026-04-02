import os
from dotenv import load_dotenv

load_dotenv()

# Authenticates calls to Claude
ANTHROPIC_API_KEY = os.getenv('ANTHROPIC_API_KEY')

# One-time webhook verification with Meta
INSTAGRAM_VERIFY_TOKEN = os.getenv('INSTAGRAM_VERIFY_TOKEN')

# Used to verify X-Hub-Signature-256 on incoming webhook payloads (Instagram app secret)
META_INSTAGRAM_APP_SECRET = os.getenv('META_INSTAGRAM_APP_SECRET')

# Protects the /admin/* endpoints
ADMIN_SECRET = os.getenv('ADMIN_SECRET')

# Instagram OAuth app credentials
META_APP_ID = os.getenv('META_APP_ID')
