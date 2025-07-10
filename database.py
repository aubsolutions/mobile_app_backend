from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base
import os
import os
from dotenv import load_dotenv
load_dotenv()



DATABASE_URL = os.getenv("DATABASE_URL")  # переменная окружения Render

if not DATABASE_URL:
    raise RuntimeError("❌ DATABASE_URL не загружен из .env")
engine = create_engine(DATABASE_URL, connect_args={"options": "-c client_encoding=utf8"})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()
