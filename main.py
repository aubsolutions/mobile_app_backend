from fastapi import FastAPI, HTTPException, Request
from pydantic import BaseModel

app = FastAPI()


class LoginRequest(BaseModel):
    phone: str
    password: str


@app.post("/login")
def login(data: LoginRequest):
    if data.phone == "77001234567" and data.password == "qwerty":
        return {"token": "fake-jwt-token"}
    raise HTTPException(status_code=401, detail="Invalid credentials")
