from sqlalchemy.ext.asyncio import AsyncAttrs, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase
import os
from dotenv import load_dotenv

load_dotenv()

# We will use asyncpg for PostgreSQL
DATABASE_URL = os.getenv("DATABASE_URL", "postgresql+asyncpg://analyst:analyst_secret@localhost:5433/vendor_analyst")

engine = create_async_engine(DATABASE_URL, echo=True)
AsyncSessionLocal = async_sessionmaker(engine, expire_on_commit=False)

class Base(AsyncAttrs, DeclarativeBase):
    pass
