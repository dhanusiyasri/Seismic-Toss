from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.pool import NullPool
from sqlalchemy.orm import declarative_base, sessionmaker

BASE_DIR = Path(__file__).resolve().parent
DATABASE_PATH = BASE_DIR / "sensor_data.db"
DATABASE_URL = f"sqlite:///{DATABASE_PATH}"

engine = create_engine(
    DATABASE_URL,
    # SQLite is used by the SIH prototype and the React dashboard can call
    # several endpoints concurrently.  NullPool gives each short-lived
    # request its own SQLite connection and avoids exhausting SQLAlchemy
    # QueuePool when multiple AI endpoints run at once.
    poolclass=NullPool,
    connect_args={"check_same_thread": False, "timeout": 30},
)

SessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=engine,
)

Base = declarative_base()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
