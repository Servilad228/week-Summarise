import os
import sys
from dotenv import load_dotenv
import pytz

# Load environment variables from .env file if it exists
load_dotenv()

def parse_chat_id(chat_val: str):
    """
    Parses a chat identifier. If it is numeric (e.g. -100123456789), returns an int.
    Otherwise, returns it as a string (username/group username).
    """
    chat_val = chat_val.strip()
    if not chat_val:
        return None
    # Check if it starts with minus and is digit, or is purely digit
    if chat_val.startswith('-') and chat_val[1:].isdigit():
        return int(chat_val)
    if chat_val.isdigit():
        return int(chat_val)
    return chat_val

# --- CONFIGURATION VARIABLES ---

# Telegram API credentials
try:
    TELEGRAM_API_ID = int(os.environ.get("TELEGRAM_API_ID", "0"))
except ValueError:
    print("Error: TELEGRAM_API_ID must be an integer.", file=sys.stderr)
    sys.exit(1)

TELEGRAM_API_HASH = os.environ.get("TELEGRAM_API_HASH", "").strip()

# Source Telegram chat to scrape
_raw_chat_id = os.environ.get("TELEGRAM_CHAT_ID", "").strip()
TELEGRAM_CHAT_ID = parse_chat_id(_raw_chat_id)

# Target Telegram chats to send the summary
_raw_targets = os.environ.get("TELEGRAM_TARGET_CHATS", "me").strip()
TELEGRAM_TARGET_CHATS = []
for t in _raw_targets.split(','):
    t_parsed = parse_chat_id(t)
    if t_parsed:
        TELEGRAM_TARGET_CHATS.append(t_parsed)

# Session file path
SESSION_NAME = os.environ.get("SESSION_NAME", "data/session").strip()

# OpenRouter credentials and model
OPENROUTER_API_KEY = os.environ.get("OPENROUTER_API_KEY", "").strip()
OPENROUTER_MODEL = os.environ.get("OPENROUTER_MODEL", "google/gemini-2.5-flash").strip()

# Run Mode settings
RUN_MODE = os.environ.get("RUN_MODE", "interval").strip().lower()
if RUN_MODE not in ("interval", "scheduled"):
    print(f"Error: RUN_MODE must be 'interval' or 'scheduled', got '{RUN_MODE}'", file=sys.stderr)
    sys.exit(1)

# Interval settings
try:
    INTERVAL_DAYS = int(os.environ.get("INTERVAL_DAYS", "7"))
except ValueError:
    print("Error: INTERVAL_DAYS must be an integer.", file=sys.stderr)
    sys.exit(1)

# Scheduled settings
SCHEDULE_WEEKDAY = os.environ.get("SCHEDULE_WEEKDAY", "sunday").strip().lower()
valid_weekdays = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]
if SCHEDULE_WEEKDAY not in valid_weekdays:
    print(f"Error: SCHEDULE_WEEKDAY must be one of {valid_weekdays}, got '{SCHEDULE_WEEKDAY}'", file=sys.stderr)
    sys.exit(1)

SCHEDULE_TIME = os.environ.get("SCHEDULE_TIME", "20:00").strip()
try:
    _time_parts = SCHEDULE_TIME.split(':')
    if len(_time_parts) != 2:
        raise ValueError()
    SCHEDULE_HOUR = int(_time_parts[0])
    SCHEDULE_MINUTE = int(_time_parts[1])
    if not (0 <= SCHEDULE_HOUR < 24 and 0 <= SCHEDULE_MINUTE < 60):
        raise ValueError()
except ValueError:
    print(f"Error: SCHEDULE_TIME must be in HH:MM format, got '{SCHEDULE_TIME}'", file=sys.stderr)
    sys.exit(1)

# Timezone validation
TIMEZONE_STR = os.environ.get("TIMEZONE", "Europe/Moscow").strip()
try:
    TIMEZONE = pytz.timezone(TIMEZONE_STR)
except pytz.UnknownTimeZoneError:
    print(f"Warning: Unknown Timezone '{TIMEZONE_STR}'. Defaulting to 'UTC'.", file=sys.stderr)
    TIMEZONE = pytz.UTC
    TIMEZONE_STR = "UTC"

# Limits and State
try:
    MAX_MESSAGES_LIMIT = int(os.environ.get("MAX_MESSAGES_LIMIT", "5000"))
except ValueError:
    MAX_MESSAGES_LIMIT = 5000

STATE_FILE_PATH = os.environ.get("STATE_FILE_PATH", "data/state.json").strip()


def validate_config(is_login_only: bool = False):
    """
    Validates that necessary configuration is set.
    If is_login_only is True, does not check chat IDs and LLM keys.
    """
    errors = []
    if not TELEGRAM_API_ID:
        errors.append("TELEGRAM_API_ID is required.")
    if not TELEGRAM_API_HASH:
        errors.append("TELEGRAM_API_HASH is required.")
        
    if not is_login_only:
        if not TELEGRAM_CHAT_ID:
            errors.append("TELEGRAM_CHAT_ID is required to identify which chat to summarize.")
        if not OPENROUTER_API_KEY:
            errors.append("OPENROUTER_API_KEY is required to generate summaries.")
            
    if errors:
        print("Configuration errors found:", file=sys.stderr)
        for err in errors:
            print(f" - {err}", file=sys.stderr)
        print("Please check your .env file or environment variables.", file=sys.stderr)
        sys.exit(1)


# Ensure directories for session and state files exist
def ensure_directories():
    for path in (SESSION_NAME, STATE_FILE_PATH):
        dir_name = os.path.dirname(path)
        if dir_name and not os.path.exists(dir_name):
            os.makedirs(dir_name, exist_ok=True)

ensure_directories()
