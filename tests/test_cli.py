import json

from generate import main


def test_cli_reports_invalid_json(tmp_path, capsys):
    path = tmp_path / 'broken.json'
    path.write_text('{broken', encoding='utf-8')
    assert main([str(path)]) == 2
    assert 'Проверь входные данные' in capsys.readouterr().err


def test_cli_saves_missing_data_result(tmp_path):
    path = tmp_path / 'product.json'
    path.write_text('{"name": "Манометр"}', encoding='utf-8')
    output = tmp_path / 'results' / 'card.json'
    assert main([str(path), '--output', str(output)]) == 1
    assert json.loads(output.read_text())['status'] == 'insufficient_data'


def test_cli_reports_missing_key(monkeypatch, capsys):
    monkeypatch.delenv('OPENROUTER_API_KEY', raising=False)
    assert main(['examples/manometer.json']) == 2
    assert 'OpenRouter' in capsys.readouterr().err
