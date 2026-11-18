from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base
import os

# Use PostgreSQL on Railway if DATABASE_URL is set, otherwise SQLite locally
DATABASE_URL = os.getenv("DATABASE_URL")

if DATABASE_URL:
    # Railway / production
    # Fix for SQLAlchemy if the URL starts with postgres://
    if DATABASE_URL.startswith("postgres://"):
        DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

    engine = create_engine(DATABASE_URL)
else:
    # Local development
    os.makedirs("data", exist_ok=True)
    SQLALCHEMY_DATABASE_URL = "sqlite:///./data/school_register.db"
    engine = create_engine(
        SQLALCHEMY_DATABASE_URL, connect_args={"check_same_thread": False}
    )

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
