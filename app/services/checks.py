import re

from app.schemas.product import CardDraft, Characteristic, ProductInput


NUMBER_RE = re.compile(r'(?<!\d)[+−-]?\d+(?:[.,]\d+)?')
QUANTITY_RE = re.compile(
    r'(?<!\w)[+−-]?\d+(?:[.,]\d+)?'
    r'(?:\s*[–—−-]\s*[+−-]?\d+(?:[.,]\d+)?)?\s*'
    r'(?:МПа|кПа|Па|бар|мм|см|мВ|мА|Вт|мг|мл|кг|°\s*[CС]|%|В|м)(?!\w)',
    re.IGNORECASE,
)
CODE_RE = re.compile(r'\b[A-Za-zА-Яа-яЁё]{1,10}[-/]?\d+(?:[/.-]\d+)*(?:\.[A-Za-z0-9]+)?\b')
CLAIM_MARKERS = (
    ('сертифика', 'сертифик'),
    ('сертифицирован', 'сертифиц'),
    ('поверк', 'поверк'),
    ('госреестр', 'госреестр'),
    ('взрывозащи', 'взрывозащи'),
    ('агрессивн', 'агрессивн'),
    ('нержавеющ', 'нержавеющ'),
    ('гаранти', 'гаранти'),
    ('доставк', 'доставк'),
    ('в наличии', 'в наличии'),
    ('ГОСТ', 'гост'),
    ('ISO', 'iso'),
)


def normalize_value(value: str):
    value = value.casefold().replace(',', '.').replace('−', '-').replace('–', '-').replace('—', '-')
    return re.sub(r'\s+', '', value).lstrip('+')


def build_characteristics(product: ProductInput):
    return [
        Characteristic(name=name, value=value if value is not None else 'данных нет')
        for name, value in product.specs.items()
    ]


def find_missing_fields(product: ProductInput):
    missing = []
    if product.manufacturer is None:
        missing.append('Производитель')
    if product.description is None:
        missing.append('Описание или фрагмент технического паспорта')
    if not product.specs:
        missing.append('Структурированные характеристики')
    missing.extend(name for name, value in product.specs.items() if value is None)
    return missing


def find_source_conflicts(product: ProductInput):
    conflicts = []
    if not product.description:
        return conflicts
    for name, value in product.specs.items():
        if value is None or not NUMBER_RE.search(value):
            continue
        pattern = re.compile(re.escape(name) + r'\s*[:=]\s*(.+)', re.IGNORECASE)
        expected = [normalize_value(number) for number in NUMBER_RE.findall(value)]
        expected_quantity = QUANTITY_RE.search(value)
        fragments = re.split(r'(?<!\d)[.;]|[.;](?!\d)|\n', product.description)
        for fragment in fragments:
            match = pattern.search(fragment)
            if match is None:
                continue
            source_value = match.group(1).strip()
            found = [normalize_value(number) for number in NUMBER_RE.findall(source_value)]
            found_quantity = QUANTITY_RE.search(source_value)
            numbers_differ = found and found[:len(expected)] != expected
            units_differ = expected_quantity and found_quantity and (
                normalize_value(expected_quantity.group()) != normalize_value(found_quantity.group())
            )
            if numbers_differ or units_differ:
                conflicts.append(f'{name}: в характеристиках «{value}», в описании «{source_value}». Уточни значение.')
    return conflicts


def build_source_text(product: ProductInput):
    parts = [product.name, product.manufacturer or '', product.description or '']
    parts.extend(name + ': ' + (value or '') for name, value in product.specs.items())
    return '\n'.join(parts)


def check_draft(draft: CardDraft, product: ProductInput):
    errors = []
    if not 1 <= len(draft.seo_title) <= 70:
        errors.append(f'Заголовок: {len(draft.seo_title)} символов, нужно от 1 до 70.')
    if not 800 <= len(draft.seo_description) <= 1200:
        errors.append(f'Описание: {len(draft.seo_description)} символов, нужно от 800 до 1200.')
    if not 3 <= len(draft.search_queries) <= 5:
        errors.append('Нужно от 3 до 5 поисковых запросов.')
    if any(not query.strip() or len(query) > 160 for query in draft.search_queries):
        errors.append('Поисковые запросы должны содержать от 1 до 160 символов.')
    if len({query.casefold().strip() for query in draft.search_queries}) != len(draft.search_queries):
        errors.append('Поисковые запросы не должны повторяться.')
    if not 1 <= len(draft.commercial_block) <= 700:
        errors.append('Коммерческий блок должен содержать от 1 до 700 символов.')

    source = build_source_text(product)
    text = '\n'.join([draft.seo_title, draft.seo_description, draft.commercial_block, *draft.search_queries])
    source_numbers = {normalize_value(value) for value in NUMBER_RE.findall(source)}
    source_quantities = {normalize_value(value) for value in QUANTITY_RE.findall(source)}
    source_codes = {normalize_value(value) for value in CODE_RE.findall(source)}

    for value in dict.fromkeys(NUMBER_RE.findall(text)):
        if normalize_value(value) not in source_numbers:
            errors.append(f'Число «{value}» отсутствует во входных данных.')
    for value in dict.fromkeys(QUANTITY_RE.findall(text)):
        if normalize_value(value) not in source_quantities:
            errors.append(f'Величина «{value}» с этой единицей отсутствует во входных данных.')
    for value in dict.fromkeys(CODE_RE.findall(text)):
        if normalize_value(value) not in source_codes:
            errors.append(f'Обозначение «{value}» отсутствует во входных данных.')

    for label, marker in CLAIM_MARKERS:
        if marker in text.casefold() and marker not in source.casefold():
            errors.append(f'Утверждение «{label}» не подтверждено входными данными.')

    return errors


def check_conflicts(draft: CardDraft, product: ProductInput):
    errors = []
    for conflict in draft.conflicts:
        if conflict.field not in product.specs or product.specs.get(conflict.field) is None:
            errors.append('В conflicts можно ссылаться только на заполненное поле из specs.')
        if not conflict.quote or conflict.quote not in (product.description or ''):
            errors.append('Цитата конфликта должна точно присутствовать в description.')
        if not conflict.explanation:
            errors.append('Для конфликта нужно объяснение.')
    return errors
