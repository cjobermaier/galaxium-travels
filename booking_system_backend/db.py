import os

from sqlalchemy import create_engine, text
from sqlalchemy.exc import OperationalError, ProgrammingError
from sqlalchemy.orm import sessionmaker

from models import Base

# Get database URL from environment, fallback to SQLite for local dev
SQLALCHEMY_DATABASE_URL = os.getenv(
    'DATABASE_URL',
    'sqlite:///./booking.db'
)

# PostgreSQL doesn't need check_same_thread
connect_args = {}
if SQLALCHEMY_DATABASE_URL.startswith('sqlite'):
    connect_args = {"check_same_thread": False}

engine = create_engine(
    SQLALCHEMY_DATABASE_URL,
    connect_args=connect_args
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

def init_db():
    """Create all tables and add `bookings.itinerary_id` to pre-existing databases."""
    Base.metadata.create_all(bind=engine)
    # create_all does not alter existing tables, so add the column manually.
    # A duplicate-column error means the column already exists and is ignored.
    try:
        with engine.begin() as conn:
            conn.execute(text(
                "ALTER TABLE bookings ADD COLUMN itinerary_id INTEGER "
                "REFERENCES itineraries(itinerary_id)"
            ))
    except (OperationalError, ProgrammingError):
        pass

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()