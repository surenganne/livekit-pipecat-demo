# LiveKit + Pipecat Demo Configuration

# LiveKit Configuration
# Option A: LiveKit Cloud (Recommended)
# LIVEKIT_URL = "wss://your-project.livekit.cloud"
# LIVEKIT_API_KEY = "your-api-key"
# LIVEKIT_API_SECRET = "your-api-secret"

# Option B: Local LiveKit Server (using docker-compose)
LIVEKIT_URL = "ws://localhost:7880"
LIVEKIT_API_KEY = "devkey"
LIVEKIT_API_SECRET = "secret"

# Load environment variables from .env file
import os
from dotenv import load_dotenv

# Load .env file from parent directory
load_dotenv(os.path.join(os.path.dirname(os.path.dirname(__file__)), '.env'))

# AI Service Configuration
OPENAI_API_KEY = os.getenv('OPENAI_API_KEY', 'your-openai-api-key')  # Set via environment variable

# Cartesia TTS Configuration
CARTESIA_API_KEY = os.getenv('CARTESIA_API_KEY', 'your-cartesia-api-key')  # Set via environment variable
CARTESIA_VOICE_ID = "79a125e8-cd45-4c13-8a67-188112f4dd22"  # British Lady voice (default)


# Room Configuration
ROOM_NAME = "pipecat-demo"
import random
import string
import time
AGENT_NAME = f"PipecatAgent-{int(time.time())}-{''.join(random.choices(string.ascii_lowercase + string.digits, k=4))}"

# Audio Configuration
SAMPLE_RATE = 16000
CHANNELS = 1

# Agent Behavior
ECHO_SUFFIX = "...got it"
RESPONSE_TIMEOUT = 5.0  # seconds
BARGE_IN_ENABLED = True

# Logging
LOG_LEVEL = "INFO"  # DEBUG, INFO, WARNING, ERROR
