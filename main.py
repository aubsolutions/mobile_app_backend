from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from database import engine
from models import Base
from routes import invoice, auth

# 👇 Кастомный JSON-ответ с поддержкой кириллицы
class UTF8JSONResponse(JSONResponse):
    media_type = "application/json; charset=utf-8"

# 👇 Инициализация приложения
app = FastAPI(default_response_class=UTF8JSONResponse)

# 👇 Создание таблиц в базе (один раз при старте)
Base.metadata.create_all(bind=engine)

# 👇 Подключение CORS (один раз!)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # ⚠️ На проде укажи домен
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 👇 Подключение роутов
app.include_router(invoice.router)
app.include_router(auth.router)

# 👇 Заглушка логина (временно)
class LoginRequest(BaseModel):
    phone: str
    password: str

@app.post("/login")
def login(data: LoginRequest):
    print(f"🔥 Получен запрос на логин: phone={data.phone}, password={data.password}")
    if data.phone == "77001234567" and data.password == "qwerty":
        return {"token": "fake-jwt-token"}
    raise HTTPException(status_code=401, detail="Invalid credentials")

# 👇 Пинг для проверки здоровья
@app.get("/")
def health():
    return {"status": "ok"}
