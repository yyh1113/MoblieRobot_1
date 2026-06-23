import os
import asyncpg
from typing import Optional

# Fetch database credentials from environment variables or use defaults
DB_USER = os.getenv("DB_USER", "postgres")
DB_PASSWORD = os.getenv("DB_PASSWORD", "1234")
DB_HOST = os.getenv("DB_HOST", "127.0.0.1")
DB_PORT = os.getenv("DB_PORT", "5432")
DB_NAME = os.getenv("DB_NAME", "lost_found_db")

db_pool: Optional[asyncpg.Pool] = None

async def init_db_pool() -> asyncpg.Pool:
    """
    Initializes the asyncpg Connection Pool.
    """
    global db_pool
    print(f"[Database] Attempting connection to PostgreSQL at {DB_HOST}:{DB_PORT}/{DB_NAME}...")
    try:
        db_pool = await asyncpg.create_pool(
            user=DB_USER,
            password=DB_PASSWORD,
            host=DB_HOST,
            port=int(DB_PORT),
            database=DB_NAME,
            min_size=2,
            max_size=10,
            command_timeout=10.0
        )
        print("[Database] PostgreSQL Async Connection Pool created successfully!")
        return db_pool
    except Exception as e:
        print("\n" + "=" * 60)
        print(f"[DB Connection Error] Reason: {e}")
        print("Please check if PostgreSQL is running: 'sudo systemctl start postgresql' or 'pg_ctl'")
        print("=" * 60 + "\n")
        raise e

async def get_db_pool() -> asyncpg.Pool:
    """
    Returns the active database pool. Initializes one if it doesn't exist.
    """
    global db_pool
    if db_pool is None:
        return await init_db_pool()
    return db_pool

async def close_db_pool() -> None:
    """
    Closes the active database pool connection.
    """
    global db_pool
    if db_pool:
        await db_pool.close()
        db_pool = None
        print("[Database] Connection pool closed successfully.")
