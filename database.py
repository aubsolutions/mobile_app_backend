from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base, Session
import os
from dotenv import load_dotenv

# 📥 Загрузка переменных окружения
load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")

if not DATABASE_URL:
    raise RuntimeError("❌ DATABASE_URL не загружен из .env")

# ⚙️ Создание движка
engine = create_engine(DATABASE_URL, connect_args={"options": "-c client_encoding=utf8"})

# 📦 Локальная сессия для каждого запроса
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# 📐 Базовый класс для моделей
Base = declarative_base()

# ✅ Dependency — обязательно для FastAPI
def get_db() -> Session:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
