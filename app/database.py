import os
from dotenv import load_dotenv
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base

# This will search for the .env file in the current directory or parents
load_dotenv() 

DATABASE_URL = os.getenv("DATABASE_URL")

if DATABASE_URL is None:
    # This will help us debug if it fails again
    raise ValueError("DATABASE_URL not found in .env file. Check your environment variables!")

engine = create_engine(DATABASE_URL)

SessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=engine
)

Base = declarative_base()

def get_db():
    database = SessionLocal()
    try:
        yield database
    finally:
        database.close()