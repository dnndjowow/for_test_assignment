from starlette.responses import JSONResponse


class BodyLimitMiddleware:
    def __init__(self, app, max_size: int):
        self.app = app
        self.max_size = max_size

    async def __call__(self, scope, receive, send):
        if scope['type'] != 'http' or scope['method'] != 'POST':
            return await self.app(scope, receive, send)

        body = bytearray()
        while True:
            message = await receive()
            if message['type'] == 'http.disconnect':
                return
            body.extend(message.get('body', b''))
            if len(body) > self.max_size:
                response = JSONResponse(status_code=413, content={'detail': 'Слишком большой запрос. Максимум — 64 КБ.'})
                return await response(scope, receive, send)
            if not message.get('more_body', False):
                break

        delivered = False

        async def read_body():
            nonlocal delivered
            if not delivered:
                delivered = True
                return {'type': 'http.request', 'body': bytes(body), 'more_body': False}
            return await receive()

        await self.app(scope, read_body, send)
