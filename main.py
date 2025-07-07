from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

app = FastAPI()


class LoginRequest(BaseModel):
    phone: str
    password: str


@app.post("/login")
def login(data: LoginRequest):
    print(f"🔥 Получен запрос на логин: phone={data.phone}, password={data.password}")  # ← Вставь это

    if data.phone == "77001234567" and data.password == "qwerty":
        return {"token": "fake-jwt-token"}

    raise HTTPException(status_code=401, detail="Invalid credentials")

@app.get("/")
def health():
    return {"status": "ok"}

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # ⚠️ временно разрешаем всё
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)