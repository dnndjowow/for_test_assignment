import os
from pathlib import Path

from dotenv import load_dotenv


BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / '.env')

OPENROUTER_URL = 'https://openrouter.ai/api/v1/chat/completions'
DEFAULT_MODEL = 'openai/gpt-4.1-mini'
MAX_BODY_SIZE = 64 * 1024
MAX_GENERATION_ATTEMPTS = 2


def get_model():
    return os.getenv('OPENROUTER_MODEL', DEFAULT_MODEL).strip() or DEFAULT_MODEL


def get_timeout():
    try:
        timeout = float(os.getenv('OPENROUTER_TIMEOUT', '45'))
    except ValueError:
        raise ValueError('OPENROUTER_TIMEOUT должен быть числом от 5 до 120.') from None

    if not 5 <= timeout <= 120:
        raise ValueError('OPENROUTER_TIMEOUT должен быть числом от 5 до 120.')

    return timeout


def get_reasoning():
    value = os.getenv('OPENROUTER_REASONING', '').strip().lower()
    if not value:
        return None
    if value not in {'true', 'false'}:
        raise ValueError('OPENROUTER_REASONING должен быть true, false или пустым.')
    return value == 'true'
