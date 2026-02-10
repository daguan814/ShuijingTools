from fastapi import FastAPI
import uvicorn

from Controller.api_router import router as api_router
from db.database import db_manager

app = FastAPI(title='ShuijingTools API')
app.include_router(api_router)


@app.on_event('startup')
def startup_event():
    db_manager.init_db()


if __name__ == '__main__':
    uvicorn.run('main:app', host='0.0.0.0', port=8081, reload=False)
