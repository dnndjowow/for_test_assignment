import json

from fastapi import APIRouter, HTTPException, Response

from app.config import BASE_DIR
from app.schemas.product import ExportRequest, GenerationResponse, ProductInput
from app.services.export import render_markdown
from app.services.generation import generate_card


router = APIRouter(prefix='/api', tags=['cards'])
EXAMPLES = {'manometer': 'manometer.json', 'thermometer': 'thermometer.json'}


@router.post('/cards', response_model=GenerationResponse)
async def create_card(product: ProductInput):
    return await generate_card(product)


@router.get('/examples/{example_id}', response_model=ProductInput)
def get_example(example_id: str):
    if example_id not in EXAMPLES:
        raise HTTPException(status_code=404, detail='Пример не найден.')
    path = BASE_DIR / 'examples' / EXAMPLES[example_id]
    return ProductInput.model_validate_json(path.read_text(encoding='utf-8'))


@router.get('/examples/{example_id}/result', response_model=GenerationResponse)
def get_example_result(example_id: str):
    if example_id not in EXAMPLES:
        raise HTTPException(status_code=404, detail='Пример не найден.')
    path = BASE_DIR / 'examples' / 'results' / EXAMPLES[example_id]
    return GenerationResponse.model_validate_json(path.read_text(encoding='utf-8'))


@router.post('/export/markdown')
def export_markdown(data: ExportRequest):
    return Response(
        content=render_markdown(data),
        media_type='text/markdown',
        headers={'Content-Disposition': 'attachment; filename="product-card.md"'},
    )


@router.post('/export/json')
def export_json(data: ExportRequest):
    return Response(
        content=json.dumps(data.model_dump(), ensure_ascii=False, indent=2),
        media_type='application/json',
        headers={'Content-Disposition': 'attachment; filename="product-card.json"'},
    )
