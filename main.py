from fastapi import FastAPI, HTTPException, Depends, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.responses import JSONResponse as StarletteJSONResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session
from passlib.context import CryptContext

from database import engine, get_db
from models import Base, User
from routes import invoice, auth

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

# 👇 Хэширование паролей
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# 👇 Модель логина
class LoginRequest(BaseModel):
    phone: str
    password: str

# 👇 Реальный логин
@app.post("/login")
def login(data: LoginRequest, db: Session = Depends(get_db)):
    print(f"🔥 Получен запрос на логин: phone={data.phone}, password={data.password}")

    user = db.query(User).filter(User.phone == data.phone).first()
    if not user:
        raise HTTPException(status_code=401, detail="Пользователь не найден")

    if not pwd_context.verify(data.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Неверный пароль")

    # ✅ Пока возвращаем заглушку токена
    return {"token": "fake-jwt-token"}

# 👇 Проверка, что всё живо
@app.get("/")
def health():
    return {"status": "ok"}
