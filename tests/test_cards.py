import pytest

from app.schemas.product import SourceConflict
from app.services import llm


def set_model_answer(monkeypatch, draft):
    calls = []

    async def completion(messages):
        calls.append(messages)
        return draft.model_dump_json()

    monkeypatch.setattr(llm, 'request_completion', completion)
    return calls


def test_create_card_preserves_characteristics(client, product, draft, monkeypatch):
    calls = set_model_answer(monkeypatch, draft)
    response = client.post('/api/cards', json=product.model_dump())
    assert response.status_code == 200
    result = response.json()
    assert result['status'] == 'ready'
    assert result['card']['characteristics'] == [
        {'name': name, 'value': value} for name, value in product.specs.items()
    ]
    assert result['checks'] == {'title_length': 42, 'description_length': 1040, 'query_count': 4, 'passed': True}
    assert len(calls) == 1


def test_missing_fields_are_not_guessed(client, product, draft, monkeypatch):
    product.manufacturer = None
    product.specs['Интерфейс'] = None
    draft.seo_description = draft.seo_description.replace(' производителя ДемоПрибор', '')
    set_model_answer(monkeypatch, draft)
    response = client.post('/api/cards', json=product.model_dump())
    assert response.status_code == 200
    result = response.json()
    assert result['status'] == 'needs_review'
    assert result['missing_fields'] == ['Производитель', 'Интерфейс']
    assert result['card']['characteristics'][-1] == {'name': 'Интерфейс', 'value': 'данных нет'}


def test_insufficient_data_does_not_call_api(client, monkeypatch):
    async def unexpected_call(messages):
        pytest.fail('При пустых данных обращаться к модели не нужно')
    monkeypatch.setattr(llm, 'request_completion', unexpected_call)
    response = client.post('/api/cards', json={'name': 'Манометр', 'specs': {'Диапазон': None}})
    assert response.status_code == 200
    assert response.json()['status'] == 'insufficient_data'
    assert response.json()['card'] is None
    assert 'Диапазон' in response.json()['missing_fields']


def test_explicit_source_conflict_stops_generation(client, product, monkeypatch):
    product.description = 'Класс точности: 2,5.'
    async def unexpected_call(messages):
        pytest.fail('Явное противоречие нужно показать до обращения к модели')
    monkeypatch.setattr(llm, 'request_completion', unexpected_call)
    response = client.post('/api/cards', json=product.model_dump())
    result = response.json()
    assert result['status'] == 'needs_clarification'
    assert result['card'] is None
    assert '2,5' in result['warnings'][0] and '1,5' in result['warnings'][0]


def test_model_conflict_requires_exact_source_quote(client, product, draft, monkeypatch):
    product.description = 'В паспорте указан другой класс: 2,5.'
    draft.conflicts = [SourceConflict(field='Класс точности', quote='другой класс: 2,5', explanation='В specs указан класс 1,5, а в паспорте 2,5.')]
    set_model_answer(monkeypatch, draft)
    result = client.post('/api/cards', json=product.model_dump()).json()
    assert result['status'] == 'needs_clarification'
    assert result['card'] is None
    assert 'другой класс: 2,5' in result['warnings'][0]


@pytest.mark.parametrize('bad_answer', ['not json', '{"seo_title":"Текст"}', '{"seo_title":null}'])
def test_invalid_model_json_is_repaired_once(client, product, draft, monkeypatch, bad_answer):
    calls = []
    async def completion(messages):
        calls.append(messages)
        return bad_answer if len(calls) == 1 else draft.model_dump_json()
    monkeypatch.setattr(llm, 'request_completion', completion)
    response = client.post('/api/cards', json=product.model_dump())
    assert response.status_code == 200
    assert len(calls) == 2
    assert calls[1][-2]['content'] == bad_answer
    assert 'Ошибки проверки' in calls[1][-1]['content']


def test_length_error_is_repaired_with_specific_feedback(client, product, draft, monkeypatch):
    bad = draft.model_copy(update={'seo_description': 'Слишком коротко.'})
    calls = []
    async def completion(messages):
        calls.append(messages)
        return bad.model_dump_json() if len(calls) == 1 else draft.model_dump_json()
    monkeypatch.setattr(llm, 'request_completion', completion)
    response = client.post('/api/cards', json=product.model_dump())
    assert response.status_code == 200
    assert '16 символов' in calls[1][-1]['content']


def test_persistent_invented_characteristic_is_not_returned(client, product, draft, monkeypatch):
    draft.commercial_block = 'Корпус IP65, гарантия 3 года.'
    calls = set_model_answer(monkeypatch, draft)
    response = client.post('/api/cards', json=product.model_dump())
    assert response.status_code == 502
    assert response.json()['code'] == 'card_validation_failed'
    assert 'card' not in response.json()
    assert len(calls) == 2


def test_unverified_conflict_is_not_presented_as_a_fact(client, product, draft, monkeypatch):
    draft.conflicts = [SourceConflict(field='Класс точности', quote='выдуманная цитата', explanation='Не совпадает')]
    calls = set_model_answer(monkeypatch, draft)
    response = client.post('/api/cards', json=product.model_dump())
    assert response.status_code == 502
    assert 'Цитата конфликта' in response.json()['detail']
    assert len(calls) == 2


def test_no_api_key_returns_clear_error(client, product):
    response = client.post('/api/cards', json=product.model_dump())
    assert response.status_code == 503
    assert response.json()['code'] == 'missing_api_key'


@pytest.mark.parametrize('payload', [
    {}, {'name': '   '}, {'name': 100}, {'name': 'Прибор', 'specs': ['100 мм']},
    {'name': 'Прибор', 'specs': {'': '100 мм'}}, {'name': 'Прибор', 'specs': {'Размер': 100}},
    {'name': 'Прибор', 'unknown': True}, {'name': 'Прибор', 'specs': {'Питание': {},}},
    {'name': 'Прибор', 'description': 'а' * 12001},
])
def test_invalid_input_returns_422(client, payload):
    response = client.post('/api/cards', json=payload)
    assert response.status_code == 422
    assert response.json()['errors']


def test_malformed_json_returns_400(client):
    response = client.post('/api/cards', content='{"name":', headers={'Content-Type': 'application/json'})
    assert response.status_code == 400
    assert 'Некорректный JSON' in response.json()['detail']


def test_body_limit_applies_without_content_length(client):
    response = client.post('/api/cards', content=iter([b'x' * 40000, b'x' * 40000]), headers={'Content-Type': 'application/json'})
    assert response.status_code == 413


def test_whitespace_and_null_specs_are_normalized(client, draft, monkeypatch):
    set_model_answer(monkeypatch, draft)
    payload = {'name': ' Манометр МД-100 ', 'manufacturer': ' ', 'specs': {' Интерфейс ': ' '}}
    response = client.post('/api/cards', json=payload)
    assert response.json()['status'] == 'insufficient_data'
    assert response.json()['missing_fields'][-1] == 'Интерфейс'


@pytest.mark.parametrize('example', ['manometer', 'thermometer'])
def test_examples_are_valid_and_match_saved_results(client, example):
    source = client.get(f'/api/examples/{example}').json()
    response = client.get(f'/api/examples/{example}/result')
    assert response.status_code == 200
    card = response.json()['card']
    assert {item['name']: item['value'] for item in card['characteristics']} == {
        name: value or 'данных нет' for name, value in source['specs'].items()
    }
    assert len(card['seo_title']) <= 70
    assert 800 <= len(card['seo_description']) <= 1200


def test_export_contains_missing_values_and_no_raw_html(client):
    result = client.get('/api/examples/thermometer/result').json()
    payload = {key: result[key] for key in ['card', 'missing_fields', 'warnings']}
    payload['card']['seo_title'] = '<script>alert(1)</script>'
    markdown = client.post('/api/export/markdown', json=payload)
    assert markdown.status_code == 200
    assert 'данных нет' in markdown.text
    assert 'Нужно уточнить' in markdown.text
    assert '<script>' not in markdown.text
    response = client.post('/api/export/json', json=payload)
    assert response.json() == payload
    assert 'attachment' in response.headers['Content-Disposition']


def test_unknown_example_returns_404(client):
    assert client.get('/api/examples/unknown').status_code == 404
    assert client.get('/api/examples/unknown/result').status_code == 404


def test_ui_and_health_work_without_key(client):
    assert client.get('/health').json() == {'status': 'ok'}
    assert 'Карточки приборов' in client.get('/').text
    assert client.get('/static/app.js').status_code == 200
    assert client.get('/openapi.json').status_code == 200
