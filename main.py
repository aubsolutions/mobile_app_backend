from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from database import engine
from models import Base
from routes import invoice
from fastapi.responses import JSONResponse



app = FastAPI(
    default_response_class=JSONResponse
)
# Подключение роутов
app.include_router(invoice.router)

# CORS middleware (оставляем один раз!)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # ⚠️ на проде указать конкретный домен
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Создание таблиц при старте
Base.metadata.create_all(bind=engine)

# Роут логина
class LoginRequest(BaseModel):
    phone: str
    password: str

@app.post("/login")
def login(data: LoginRequest):
    print(f"🔥 Получен запрос на логин: phone={data.phone}, password={data.password}")
    if data.phone == "77001234567" and data.password == "qwerty":
        return {"token": "fake-jwt-token"}
    raise HTTPException(status_code=401, detail="Invalid credentials")

@app.get("/")
def health():
    return {"status": "ok"}


