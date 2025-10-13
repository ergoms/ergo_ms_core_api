from sqlalchemy import create_engine

def get_pg_engine():
    return create_engine("postgresql+asyncpg://user:password@host/dbname")