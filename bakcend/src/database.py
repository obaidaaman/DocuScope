import os
from dotenv import load_dotenv
from sqlalchemy.ext.asyncio import AsyncAttrs, async_sessionmaker, create_async_engine, AsyncSession
from sqlalchemy.orm import DeclarativeBase

# Load .env from root or current dir
load_dotenv()

raw_url = os.getenv("DATABASE_URL") or os.getenv("DATABASE_URI") or "postgresql+asyncpg://analyst:analyst_secret@localhost:5433/vendor_analyst"

# Ensure asyncpg dialect prefix
if raw_url.startswith("postgresql://"):
    DATABASE_URL = raw_url.replace("postgresql://", "postgresql+asyncpg://", 1)
elif raw_url.startswith("postgres://"):
    DATABASE_URL = raw_url.replace("postgres://", "postgresql+asyncpg://", 1)
else:
    DATABASE_URL = raw_url

# Support PgBouncer / Supabase transaction pooler if detected
is_pgbouncer = "pooler.supabase.com" in DATABASE_URL or ":6543" in DATABASE_URL

engine_kwargs = {"echo": False}
if is_pgbouncer:
    import uuid
    from sqlalchemy.pool import NullPool
    engine_kwargs.update({
        "poolclass": NullPool,
        "connect_args": {
            "statement_cache_size": 0,
            "prepared_statement_name_func": lambda: f"__asyncpg_{uuid.uuid4()}__",
        }
    })

engine = create_async_engine(DATABASE_URL, **engine_kwargs)
AsyncSessionLocal = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)

class Base(AsyncAttrs, DeclarativeBase):
    pass

async def get_db():
    async with AsyncSessionLocal() as session:
        try:
            yield session
        finally:
            await session.close()

