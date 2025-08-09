from fastapi import FastAPI, HTTPException, Depends, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.responses import JSONResponse as StarletteJSONResponse
from routes import feedback
from database import engine
from models import Base
from routes import invoice, auth
from routes import employees
from routes import products  # один корректный импорт

# 👇 Кастомный JSON-ответ с поддержкой кириллицы
class UTF8JSONResponse(StarletteJSONResponse):
    media_type = "application/json; charset=utf-8"

app = FastAPI(default_response_class=UTF8JSONResponse)

@app.exception_handler(HTTPException)
async def custom_http_exception_handler(request: Request, exc: HTTPException):
    return JSONResponse(
        status_code=exc.status_code,
        content={"detail": str(exc.detail)},
        media_type="application/json; charset=utf-8",
    )

Base.metadata.create_all(bind=engine)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(invoice.router)
app.include_router(auth.router)
app.include_router(feedback.router)
app.include_router(employees.router)
app.include_router(products.router)

@app.get("/")
def health():
    return {"status": "ok"}