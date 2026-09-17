import os
from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker
from database_safety import database_url_for_process

DATABASE_URL = database_url_for_process()

engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
