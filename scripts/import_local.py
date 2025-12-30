#!/usr/bin/env python3
from pathlib import Path
import zlib, mimetypes, datetime
from playgram.db.library import upsert_track, list_tracks

ROOT = Path('/app/data/downloads')
EXT = {'.mp3','.flac','.wav','.m4a','.ogg','.aac'}
added = 0
for p in sorted(ROOT.rglob('*')):
    if not p.is_file():
        continue
    if p.suffix.lower() not in EXT:
        continue
    tg_msg = zlib.adler32(str(p).encode()) & 0x7fffffff
    created_at = datetime.datetime.fromtimestamp(p.stat().st_mtime, tz=datetime.timezone.utc).isoformat()
    local_path = str(p)
    mime_type = mimetypes.guess_type(str(p))[0]
    size_bytes = p.stat().st_size
    try:
        upsert_track(
            tg_chat_id='local',
            tg_message_id=int(tg_msg),
            file_name=p.name,
            local_path=local_path,
            mime_type=mime_type,
            size_bytes=int(size_bytes),
            duration_seconds=None,
            artist=None,
            title=None,
            created_at=created_at,
        )
        added += 1
    except Exception as e:
        print('ERR', p, e)

print('ADDED', added)
tracks = list_tracks()
print('TOTAL_TRACKS_IN_DB', len(tracks))
for t in tracks[:20]:
    print(t['id'], t['file_name'])
