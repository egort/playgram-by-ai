from __future__ import annotations

import uvicorn

from playgram.settings import get_settings


def main() -> None:
    settings = get_settings()
    uvicorn.run(
        "playgram.app:app",
        host=settings.host,
        port=settings.port,
        reload=settings.reload,
        log_level="info",
    )


if __name__ == "__main__":
    main()
