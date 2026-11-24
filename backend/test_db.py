import asyncio
import os

from dotenv import load_dotenv
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

load_dotenv()

url = os.environ["DATABASE_URL"]
# SQLAlchemy needs to be told to use the async driver
url = url.replace("postgresql://", "postgresql+asyncpg://", 1)


async def main():
    engine = create_async_engine(url)
    async with engine.connect() as conn:
        result = await conn.execute(text("select postgis_version()"))
        print("PostGIS:", result.scalar())
    await engine.dispose()


asyncio.run(main())
