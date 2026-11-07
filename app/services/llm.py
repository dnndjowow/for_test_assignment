import asyncio
import logging
import os

import httpx

from app.config import OPENROUTER_URL, get_model, get_reasoning, get_timeout
from app.services.errors import GenerationError
from app.services.prompts import build_response_format


logger = logging.getLogger(__name__)
RETRY_STATUSES = {408, 429, 500, 502, 503, 504}


async def request_completion(messages: list) -> str:
    api_key = os.getenv('OPENROUTER_API_KEY', '').strip()
    if not api_key:
        raise GenerationError(
            'Генерация не настроена. Укажи ключ OpenRouter в настройках приложения.',
            status_code=503,
            code='missing_api_key',
        )

    try:
        timeout = get_timeout()
        reasoning = get_reasoning()
    except ValueError:
        raise GenerationError(
            'Некорректные параметры модели в настройках приложения.',
            status_code=503,
            code='invalid_configuration',
        ) from None

    payload = {
        'model': get_model(),
        'messages': messages,
        'response_format': build_response_format(),
        'provider': {'require_parameters': True},
        'temperature': 0.2,
        'max_tokens': 2400,
    }
    if reasoning is not None:
        payload['reasoning'] = {'enabled': reasoning}
    headers = {
        'Authorization': f'Bearer {api_key}',
        'Content-Type': 'application/json',
        'X-Title': 'Product Cards',
    }

    async with httpx.AsyncClient(timeout=httpx.Timeout(timeout, connect=10)) as client:
        for attempt in range(2):
            try:
                response = await client.post(OPENROUTER_URL, headers=headers, json=payload)
            except httpx.TimeoutException:
                if attempt == 0:
                    await asyncio.sleep(0.5)
                    continue
                raise GenerationError(
                    'Модель не ответила вовремя. Попробуй повторить запрос позже.',
                    status_code=504,
                    code='provider_timeout',
                ) from None
            except httpx.RequestError:
                if attempt == 0:
                    await asyncio.sleep(0.5)
                    continue
                raise GenerationError(
                    'Не удалось подключиться к OpenRouter. Проверь соединение и повтори запрос.',
                    status_code=503,
                    code='provider_unavailable',
                ) from None

            if response.status_code in RETRY_STATUSES and attempt == 0:
                await asyncio.sleep(0.5)
                continue

            check_provider_status(response.status_code)
            return read_completion(response)

    raise GenerationError('Не удалось получить ответ модели.')


def check_provider_status(status_code: int):
    if status_code in {401, 403}:
        raise GenerationError(
            'OpenRouter отклонил доступ. Проверь ключ и разрешения аккаунта.',
            status_code=503,
            code='provider_authentication',
        )
    if status_code == 402:
        raise GenerationError(
            'На аккаунте OpenRouter недостаточно средств для запроса.',
            status_code=503,
            code='provider_credits',
        )
    if status_code == 429:
        raise GenerationError(
            'Превышен лимит запросов к модели. Повтори попытку позже.',
            status_code=429,
            code='provider_rate_limit',
        )
    if status_code in {400, 404, 422}:
        raise GenerationError(
            'Модель недоступна или не поддерживает нужный формат ответа. Проверь выбранную модель.',
            code='unsupported_model',
        )
    if status_code >= 400:
        logger.warning('OpenRouter returned HTTP %s', status_code)
        raise GenerationError('OpenRouter временно недоступен.', status_code=503, code='provider_error')


def read_completion(response: httpx.Response):
    try:
        data = response.json()
        if not isinstance(data, dict) or data.get('error'):
            raise ValueError()
        choice = data['choices'][0]
        message = choice['message']
        finish_reason = choice.get('finish_reason')
        if message.get('refusal') or finish_reason == 'content_filter':
            raise GenerationError('Модель отказалась обрабатывать эти данные.', code='model_refusal')
        if finish_reason == 'length':
            raise GenerationError('Ответ модели оборвался по лимиту длины. Проверь настройки модели и повтори запрос.', code='truncated_response')
        if finish_reason != 'stop':
            raise GenerationError('Модель не завершила ответ.', code='incomplete_response')
        content = message['content']
    except (ValueError, KeyError, IndexError, TypeError, AttributeError):
        raise GenerationError('OpenRouter вернул ответ неверного формата.', code='invalid_provider_response') from None

    if not isinstance(content, str) or not content.strip():
        raise GenerationError('Модель вернула пустой ответ.', code='empty_model_response')
    if len(content) > 24000:
        raise GenerationError('Ответ модели слишком большой.', code='invalid_model_response')

    return content.strip()
