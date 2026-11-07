import asyncio
import json

import httpx
import pytest

from app.services import llm
from app.services.errors import GenerationError


def configure_transport(monkeypatch, handler):
    monkeypatch.setenv('OPENROUTER_API_KEY', 'test-key-not-a-secret')
    client_class = httpx.AsyncClient
    monkeypatch.setattr(llm.httpx, 'AsyncClient', lambda **kwargs: client_class(transport=httpx.MockTransport(handler), **kwargs))
    async def no_wait(delay):
        return None
    monkeypatch.setattr(llm.asyncio, 'sleep', no_wait)


def response_body(content='{}', **choice_values):
    return {'choices': [{'finish_reason': 'stop', 'message': {'content': content}, **choice_values}]}


def test_request_uses_configured_model_and_strict_schema(monkeypatch):
    monkeypatch.setenv('OPENROUTER_MODEL', 'openai/gpt-4.1-mini')
    seen = []
    def handler(request):
        seen.append(request)
        return httpx.Response(200, json=response_body('{"ok":true}'))
    configure_transport(monkeypatch, handler)
    assert asyncio.run(llm.request_completion([{'role': 'user', 'content': 'test'}])) == '{"ok":true}'
    payload = json.loads(seen[0].content)
    assert payload['model'] == 'openai/gpt-4.1-mini'
    assert payload['provider'] == {'require_parameters': True}
    assert payload['response_format']['json_schema']['strict'] is True
    assert seen[0].headers['Authorization'] == 'Bearer test-key-not-a-secret'


@pytest.mark.parametrize('setting, expected', [('false', False), ('true', True), ('', None)])
def test_reasoning_setting_is_sent_only_when_requested(monkeypatch, setting, expected):
    monkeypatch.setenv('OPENROUTER_MODEL', 'nvidia/nemotron-3.5-super-vl:free')
    monkeypatch.setenv('OPENROUTER_REASONING', setting)
    payloads = []
    def handler(request):
        payloads.append(json.loads(request.content))
        return httpx.Response(200, json=response_body())
    configure_transport(monkeypatch, handler)
    asyncio.run(llm.request_completion([]))
    assert payloads[0]['model'] == 'nvidia/nemotron-3.5-super-vl:free'
    if expected is None:
        assert 'reasoning' not in payloads[0]
    else:
        assert payloads[0]['reasoning'] == {'enabled': expected}


def test_invalid_reasoning_setting_is_configuration_error(monkeypatch):
    monkeypatch.setenv('OPENROUTER_API_KEY', 'test-key-not-a-secret')
    monkeypatch.setenv('OPENROUTER_REASONING', 'sometimes')
    with pytest.raises(GenerationError) as error:
        asyncio.run(llm.request_completion([]))
    assert error.value.code == 'invalid_configuration'


@pytest.mark.parametrize('status, code, count', [
    (401, 'provider_authentication', 1), (402, 'provider_credits', 1),
    (429, 'provider_rate_limit', 2), (503, 'provider_error', 2),
    (400, 'unsupported_model', 1),
])
def test_provider_errors_are_bounded_and_do_not_leak_body(monkeypatch, status, code, count):
    calls = []
    def handler(request):
        calls.append(request)
        return httpx.Response(status, json={'error': {'message': 'private-provider-text test-key-not-a-secret'}})
    configure_transport(monkeypatch, handler)
    with pytest.raises(GenerationError) as error:
        asyncio.run(llm.request_completion([]))
    assert error.value.code == code
    assert 'test-key' not in str(error.value)
    assert 'private-provider-text' not in str(error.value)
    assert len(calls) == count


def test_temporary_failure_recovers_on_second_request(monkeypatch):
    calls = []
    def handler(request):
        calls.append(request)
        return httpx.Response(503) if len(calls) == 1 else httpx.Response(200, json=response_body())
    configure_transport(monkeypatch, handler)
    assert asyncio.run(llm.request_completion([])) == '{}'
    assert len(calls) == 2


@pytest.mark.parametrize('error_class, code', [(httpx.ReadTimeout, 'provider_timeout'), (httpx.ConnectError, 'provider_unavailable')])
def test_network_errors_are_handled(monkeypatch, error_class, code):
    calls = []
    def handler(request):
        calls.append(request)
        raise error_class('private network error', request=request)
    configure_transport(monkeypatch, handler)
    with pytest.raises(GenerationError) as error:
        asyncio.run(llm.request_completion([]))
    assert error.value.code == code
    assert len(calls) == 2


@pytest.mark.parametrize('body, code', [
    ({}, 'invalid_provider_response'),
    ({'choices': []}, 'invalid_provider_response'),
    ({'choices': [None]}, 'invalid_provider_response'),
    (response_body(content=None), 'empty_model_response'),
    (response_body(content=''), 'empty_model_response'),
    (response_body(finish_reason='length'), 'truncated_response'),
    (response_body(finish_reason='content_filter'), 'model_refusal'),
    (response_body(message={'refusal': 'no'}), 'model_refusal'),
    (response_body(finish_reason=None), 'incomplete_response'),
    ({'error': {'message': 'internal'}}, 'invalid_provider_response'),
])
def test_invalid_or_incomplete_provider_response_is_not_success(monkeypatch, body, code):
    configure_transport(monkeypatch, lambda request: httpx.Response(200, json=body))
    with pytest.raises(GenerationError) as error:
        asyncio.run(llm.request_completion([]))
    assert error.value.code == code


def test_invalid_timeout_is_configuration_error(monkeypatch):
    monkeypatch.setenv('OPENROUTER_API_KEY', 'test-key-not-a-secret')
    monkeypatch.setenv('OPENROUTER_TIMEOUT', 'nan')
    with pytest.raises(GenerationError) as error:
        asyncio.run(llm.request_completion([]))
    assert error.value.code == 'invalid_configuration'
