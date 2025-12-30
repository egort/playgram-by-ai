from __future__ import annotations

from fastapi import APIRouter

from playgram.api.routes_library import router as library_router
from playgram.api.routes_sync import router as sync_router
from playgram.settings import get_settings

router = APIRouter(prefix="/api")
router.include_router(library_router)
router.include_router(sync_router)


@router.get("/status", tags=["status"])
def api_status():
	s = get_settings()
	telegram_configured = bool(s.telegram_api_id and s.telegram_api_hash and s.telegram_chat)
	return {
		"telegram_configured": telegram_configured,
		"telegram_chat": s.telegram_chat,
		"downloads_dir": str(s.downloads_dir),
		"db_path": str(s.db_path),
	}
