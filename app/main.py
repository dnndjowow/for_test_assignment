from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from app.config import BASE_DIR, MAX_BODY_SIZE
from app.middleware import BodyLimitMiddleware
from app.routers.cards import router as cards_router
from app.services.errors import GenerationError


app = FastAPI(title='Карточки приборов', version='1.0.0')
app.add_middleware(BodyLimitMiddleware, max_size=MAX_BODY_SIZE)
app.include_router(cards_router)
app.mount('/static', StaticFiles(directory=BASE_DIR / 'app' / 'static'), name='static')


@app.exception_handler(GenerationError)
async def handle_generation_error(request: Request, error: GenerationError):
    return JSONResponse(status_code=error.status_code, content={'detail': error.message, 'code': error.code})


@app.exception_handler(RequestValidationError)
async def handle_validation_error(request: Request, error: RequestValidationError):
    errors = error.errors()
    if any(item['type'] == 'json_invalid' for item in errors):
        return JSONResponse(status_code=400, content={'detail': 'Некорректный JSON. Проверь кавычки, запятые и скобки.'})

    fields = []
    messages = {
        'missing': 'Обязательное поле.',
        'string_type': 'Ожидается строка.',
        'dict_type': 'Ожидается объект JSON с характеристиками.',
        'extra_forbidden': 'Неизвестное поле.',
        'string_too_short': 'Поле слишком короткое или пустое.',
        'string_too_long': 'Превышена допустимая длина поля.',
        'too_long': 'Слишком много элементов.',
    }
    for item in errors:
        field = '.'.join(str(part) for part in item['loc'] if part != 'body') or 'product'
        message = messages.get(item['type'], item['msg'].removeprefix('Value error, '))
        fields.append({'field': field, 'message': message})
    return JSONResponse(status_code=422, content={'detail': 'Проверь входные данные.', 'errors': fields})


@app.get('/', include_in_schema=False)
def index():
    return FileResponse(BASE_DIR / 'app' / 'static' / 'index.html')


@app.get('/health', tags=['health'])
def health():
    return {'status': 'ok'}
