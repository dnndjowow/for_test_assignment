import re

from app.schemas.product import ExportRequest


def escape_markdown(value: str):
    value = re.sub(r'([\\`*_{}\[\]<>#!])', r'\\\1', value)
    return value.replace('|', '\\|').replace('\n', ' ')


def render_markdown(data: ExportRequest):
    card = data.card
    lines = [
        '# ' + escape_markdown(card.seo_title),
        '',
        '## SEO-описание',
        '',
        card.seo_description.replace('<', '&lt;').replace('>', '&gt;'),
        '',
        '## Характеристики',
        '',
        '| Характеристика | Значение |',
        '| --- | --- |',
    ]
    lines.extend(
        f'| {escape_markdown(item.name)} | {escape_markdown(item.value)} |'
        for item in card.characteristics
    )
    if not card.characteristics:
        lines.append('| Характеристики | данных нет |')
    lines.extend(['', '## Поисковые запросы', ''])
    lines.extend('- ' + escape_markdown(query) for query in card.search_queries)
    lines.extend(['', '## Для менеджера', '', escape_markdown(card.commercial_block)])
    if data.missing_fields:
        lines.extend(['', '## Нужно уточнить', ''])
        lines.extend('- ' + escape_markdown(field) for field in data.missing_fields)
    if data.warnings:
        lines.extend(['', '## Замечания', ''])
        lines.extend('- ' + escape_markdown(warning) for warning in data.warnings)
    lines.extend(['', 'Черновик карточки. Проверь формулировки перед публикацией.', ''])
    return '\n'.join(lines)
