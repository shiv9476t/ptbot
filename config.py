import os
from dotenv import load_dotenv

load_dotenv()

# Authenticates calls to Claude
ANTHROPIC_API_KEY = os.getenv('ANTHROPIC_API_KEY')

# One-time webhook verification with Meta
INSTAGRAM_VERIFY_TOKEN = os.getenv('INSTAGRAM_VERIFY_TOKEN')
