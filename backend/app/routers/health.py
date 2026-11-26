from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.session import get_session

router = APIRouter(tags=["health"])


@router.get("/health")
async def health(session: AsyncSession = Depends(get_session)):
    postgis = (await session.execute(text("SELECT postgis_version()"))).scalar()
    return {"status": "ok", "postgis": postgis}