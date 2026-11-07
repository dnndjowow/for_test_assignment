import asyncio

from pydantic import ValidationError

from app.config import MAX_GENERATION_ATTEMPTS
from app.schemas.product import CardChecks, CardDraft, GenerationResponse, ProductCard, ProductInput
from app.services import llm
from app.services.checks import build_characteristics, check_conflicts, check_draft, find_missing_fields, find_source_conflicts
from app.services.errors import GenerationError
from app.services.prompts import add_repair_message, build_messages


async def generate_card(product: ProductInput):
    try:
        async with asyncio.timeout(120):
            return await _generate_card(product)
    except TimeoutError:
        raise GenerationError('Время подготовки карточки истекло. Повтори запрос позже.', 504, 'generation_timeout') from None


async def _generate_card(product: ProductInput):
    missing_fields = find_missing_fields(product)
    source_conflicts = find_source_conflicts(product)
    if source_conflicts:
        return GenerationResponse(status='needs_clarification', missing_fields=missing_fields, warnings=source_conflicts)
    has_specs = any(value is not None for value in product.specs.values())
    if not has_specs and not product.description:
        return GenerationResponse(
            status='insufficient_data',
            missing_fields=missing_fields,
            warnings=['Для черновика нужны характеристики или описание назначения прибора.'],
        )

    messages = build_messages(product)

    for attempt in range(MAX_GENERATION_ATTEMPTS):
        content = await llm.request_completion(messages)
        try:
            draft = CardDraft.model_validate_json(content)
        except ValidationError:
            errors = ['Ответ не соответствует JSON-схеме. Проверь поля и типы данных.']
        else:
            errors = check_conflicts(draft, product)
            if draft.conflicts and not errors:
                return GenerationResponse(
                    status='needs_clarification',
                    missing_fields=missing_fields,
                    warnings=[
                        f'{conflict.field}: {conflict.explanation} Цитата: «{conflict.quote}»'
                        for conflict in draft.conflicts
                    ],
                )
            if not errors:
                errors = check_draft(draft, product)
            if not errors:
                card = ProductCard(
                    seo_title=draft.seo_title,
                    seo_description=draft.seo_description,
                    characteristics=build_characteristics(product),
                    search_queries=draft.search_queries,
                    commercial_block=draft.commercial_block,
                )
                warnings = []
                if missing_fields:
                    warnings.append('Черновик подготовлен по неполным данным. Уточни указанные поля.')
                return GenerationResponse(
                    status='needs_review' if missing_fields else 'ready',
                    card=card,
                    checks=CardChecks(
                        title_length=len(card.seo_title),
                        description_length=len(card.seo_description),
                        query_count=len(card.search_queries),
                        passed=True,
                    ),
                    missing_fields=missing_fields,
                    warnings=warnings,
                )

        if attempt + 1 < MAX_GENERATION_ATTEMPTS:
            messages = add_repair_message(messages, content, errors)

    raise GenerationError(
        'Карточка не прошла проверку после повторной генерации: ' + ' '.join(errors[:4]),
        code='card_validation_failed',
    )
