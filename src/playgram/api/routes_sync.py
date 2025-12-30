from __future__ import annotations

from fastapi import APIRouter, HTTPException

from playgram.telegram.sync import get_sync_status, start_sync_job

router = APIRouter(tags=["sync"])


@router.post("/sync/start")
async def api_sync_start():
    try:
        status = await start_sync_job()
        return {"ok": True, **status}
    except Exception as e:  # noqa: BLE001
        raise HTTPException(status_code=400, detail=f"{type(e).__name__}: {str(e)}")


@router.get("/sync/status")
async def api_sync_status():
    try:
        status = await get_sync_status()
        return {"ok": True, **status}
    except Exception as e:  # noqa: BLE001
        raise HTTPException(status_code=400, detail=f"{type(e).__name__}: {str(e)}")
