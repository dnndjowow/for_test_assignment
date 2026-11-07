import argparse
import asyncio
import sys
from pathlib import Path

from pydantic import ValidationError

from app.config import MAX_BODY_SIZE
from app.schemas.product import ExportRequest, ProductInput
from app.services.errors import GenerationError
from app.services.export import render_markdown
from app.services.generation import generate_card


def main(argv=None):
    parser = argparse.ArgumentParser(description='Подготовить черновик карточки по JSON с данными прибора.')
    parser.add_argument('input', type=Path, help='Путь к JSON-файлу')
    parser.add_argument('--format', choices=['json', 'markdown'], default='json')
    parser.add_argument('--output', type=Path, help='Сохранить результат в файл')
    args = parser.parse_args(argv)

    try:
        with args.input.open('rb') as source:
            content = source.read(MAX_BODY_SIZE + 1)
        if len(content) > MAX_BODY_SIZE:
            raise ValueError('Входной файл должен быть не больше 64 КБ.')
        product = ProductInput.model_validate_json(content)
        result = asyncio.run(generate_card(product))
        if args.format == 'markdown' and result.card:
            text = render_markdown(ExportRequest(card=result.card, missing_fields=result.missing_fields, warnings=result.warnings))
        else:
            text = result.model_dump_json(indent=2)
        if args.output:
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(text + '\n', encoding='utf-8')
        else:
            print(text)
        return 0 if result.card else 1
    except ValidationError as error:
        fields = ', '.join('.'.join(map(str, item['loc'])) or 'JSON' for item in error.errors())
        print('Проверь входные данные: ' + fields, file=sys.stderr)
    except (OSError, ValueError, GenerationError) as error:
        print(str(error), file=sys.stderr)
    return 2


if __name__ == '__main__':
    raise SystemExit(main())
