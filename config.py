import os
from dotenv import load_dotenv

load_dotenv()

# Authenticates calls to Claude
ANTHROPIC_API_KEY = os.getenv('ANTHROPIC_API_KEY')

# One-time webhook verification with Meta
INSTAGRAM_VERIFY_TOKEN = os.getenv('INSTAGRAM_VERIFY_TOKEN')

# Used to verify X-Hub-Signature-256 on incoming webhook payloads
META_APP_SECRET = os.getenv('META_APP_SECRET')
# Instagram product may have a separate app secret (check Meta developer dashboard → Instagram product)
META_INSTAGRAM_APP_SECRET = os.getenv('META_INSTAGRAM_APP_SECRET')
