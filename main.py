from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
import uvicorn

from Controller.api_router import router as api_router
from Service.auth_service import auth_service
from db.database import db_manager

app = FastAPI(title='ShuijingTools API')
app.include_router(api_router)


@app.on_event('startup')
def startup_event():
    db_manager.init_db()


@app.middleware('http')
async def api_auth_middleware(request: Request, call_next):
    path = request.url.path
    if path.startswith('/api') and path not in ('/api/health', '/api/auth/verify'):
        auth_header = request.headers.get('Authorization', '').strip()
        token = ''
        if auth_header.lower().startswith('bearer '):
            token = auth_header[7:].strip()
        if not token or not auth_service.verify_session(token):
            return JSONResponse(status_code=401, content={'detail': 'unauthorized'})
    return await call_next(request)


if __name__ == '__main__':
    uvicorn.run('main:app', host='0.0.0.0', port=8081, reload=False)
