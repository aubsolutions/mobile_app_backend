from fastapi import FastAPI, HTTPException, Depends, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.responses import JSONResponse as StarletteJSONResponse
from routes import feedback
from database import engine
from models import Base
from routes import invoice, auth
from routes import employees
from routes.employees import router as employees_router

# 👇 Кастомный JSON-ответ с поддержкой кириллицы
class UTF8JSONResponse(StarletteJSONResponse):
    media_type = "application/json; charset=utf-8"

# 👇 Инициализация FastAPI
app = FastAPI(default_response_class=UTF8JSONResponse)

# 👇 Глобальный обработчик ошибок — чтобы не было кракозябр в ответах
@app.exception_handler(HTTPException)
async def custom_http_exception_handler(request: Request, exc: HTTPException):
    return JSONResponse(
        status_code=exc.status_code,
        content={"detail": str(exc.detail)},
        media_type="application/json; charset=utf-8",
    )

# 👇 Создание таблиц
Base.metadata.create_all(bind=engine)

# 👇 CORS (разрешить доступ отовсюду)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # ⚠️ Укажи домен на проде
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 👇 Подключение роутов
app.include_router(invoice.router)
app.include_router(auth.router)
app.include_router(feedback.router)
app.include_router(employees.router)

# 👇 Проверка, что всё живо
@app.get("/")
def health():
    return {"status": "ok"}

