"""Audio file metadata extraction using mutagen."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from mutagen import File as MutagenFile  # type: ignore[attr-defined]
from mutagen.easyid3 import EasyID3
from mutagen.id3 import ID3, POPM  # type: ignore[attr-defined]
from mutagen.mp3 import MP3
from mutagen.mp4 import MP4
from mutagen.flac import FLAC
from mutagen.oggvorbis import OggVorbis


@dataclass
class AudioMeta:
    """Extracted audio metadata."""

    artist: Optional[str] = None
    title: Optional[str] = None
    album: Optional[str] = None
    year: Optional[int] = None
    duration_seconds: Optional[int] = None


def _parse_year(raw: str | None) -> int | None:
    """Extract year as integer from various date formats."""
    if not raw:
        return None
    # Handle formats like "2023", "2023-05-01", "2023/05/01"
    raw = raw.strip()
    if not raw:
        return None
    try:
        # Take first 4 chars if it looks like a year
        year_str = raw[:4]
        year = int(year_str)
        if 1900 <= year <= 2100:
            return year
    except (ValueError, IndexError):
        pass
    return None


def _first(lst: list | tuple | str | None) -> str | None:
    """Get first element from a list-like or return string as-is."""
    if lst is None:
        return None
    if isinstance(lst, str):
        return lst.strip() or None
    if isinstance(lst, (list, tuple)) and lst:
        val = lst[0]
        if isinstance(val, str):
            return val.strip() or None
        return str(val).strip() or None
    return None


def extract_metadata(file_path: Path | str) -> AudioMeta:
    """
    Extract metadata from an audio file.

    Supports MP3 (ID3), MP4/M4A, FLAC, OGG Vorbis.
    Returns AudioMeta with None for fields that couldn't be read.
    """
    path = Path(file_path)
    if not path.exists():
        return AudioMeta()

    result = AudioMeta()

    try:
        audio = MutagenFile(str(path))
        if audio is None:
            return result

        # Get duration from audio info
        if hasattr(audio, "info") and hasattr(audio.info, "length"):
            result.duration_seconds = int(audio.info.length)

        # Extract tags based on file type
        if isinstance(audio, MP3):
            result = _extract_mp3(path, result)
        elif isinstance(audio, MP4):
            result = _extract_mp4(audio, result)
        elif isinstance(audio, FLAC):
            result = _extract_vorbis_comments(audio, result)
        elif isinstance(audio, OggVorbis):
            result = _extract_vorbis_comments(audio, result)
        else:
            # Try EasyID3 for other formats
            result = _extract_easy(audio, result)

    except Exception:  # noqa: BLE001
        # If metadata extraction fails, return what we have
        pass

    return result


def _extract_mp3(path: Path, meta: AudioMeta) -> AudioMeta:
    """Extract metadata from MP3 file using ID3 tags."""
    try:
        tags = ID3(str(path))
    except Exception:  # noqa: BLE001
        return meta

    # Artist: TPE1 (Lead performer)
    if "TPE1" in tags:
        meta.artist = _first(tags["TPE1"].text)

    # Title: TIT2
    if "TIT2" in tags:
        meta.title = _first(tags["TIT2"].text)

    # Album: TALB
    if "TALB" in tags:
        meta.album = _first(tags["TALB"].text)

    # Year: TDRC (recording date) or TYER (legacy)
    year_str = None
    if "TDRC" in tags:
        year_str = str(tags["TDRC"].text[0]) if tags["TDRC"].text else None
    elif "TYER" in tags:
        year_str = _first(tags["TYER"].text)
    meta.year = _parse_year(year_str)

    return meta


def _extract_mp4(audio: MP4, meta: AudioMeta) -> AudioMeta:
    """Extract metadata from MP4/M4A file."""
    tags = audio.tags or {}

    # Artist: ©ART
    if "©ART" in tags:
        meta.artist = _first(tags["©ART"])

    # Title: ©nam
    if "©nam" in tags:
        meta.title = _first(tags["©nam"])

    # Album: ©alb
    if "©alb" in tags:
        meta.album = _first(tags["©alb"])

    # Year: ©day
    if "©day" in tags:
        meta.year = _parse_year(_first(tags["©day"]))

    return meta


def _extract_vorbis_comments(audio, meta: AudioMeta) -> AudioMeta:
    """Extract metadata from FLAC/OGG Vorbis comments."""
    tags = audio.tags or {}

    if "artist" in tags:
        meta.artist = _first(tags["artist"])
    if "title" in tags:
        meta.title = _first(tags["title"])
    if "album" in tags:
        meta.album = _first(tags["album"])
    if "date" in tags:
        meta.year = _parse_year(_first(tags["date"]))

    return meta


def _extract_easy(audio, meta: AudioMeta) -> AudioMeta:
    """Fallback extraction using EasyID3-like interface."""
    tags = getattr(audio, "tags", None) or {}

    for key in ("artist", "ARTIST"):
        if key in tags:
            meta.artist = _first(tags[key])
            break

    for key in ("title", "TITLE"):
        if key in tags:
            meta.title = _first(tags[key])
            break

    for key in ("album", "ALBUM"):
        if key in tags:
            meta.album = _first(tags[key])
            break

    for key in ("date", "DATE", "year", "YEAR"):
        if key in tags:
            meta.year = _parse_year(_first(tags[key]))
            break

    return meta


def _rating_to_popm(rating: int) -> int:
    """Convert 1-3 star rating to POPM rating (0-255)."""
    # POPM uses 0-255, common mapping:
    # 1 star = 1-63, 2 stars = 64-127, 3 stars = 128-191, 4 stars = 192-254, 5 stars = 255
    # We use 1-3, so: 1=64, 2=128, 3=255
    mapping = {1: 64, 2: 128, 3: 255}
    return mapping.get(rating, 0)


def write_rating_to_file(file_path: Path | str, rating: int) -> None:
    """
    Write rating to audio file tags.

    Supports:
    - MP3: POPM (Popularimeter) frame
    - MP4/M4A: Not supported (no standard rating field)
    - FLAC/OGG: RATING tag (0-100 scale)

    Raises exception on failure.
    """
    path = Path(file_path)
    if not path.exists():
        raise FileNotFoundError(f"File not found: {path}")

    if not (1 <= rating <= 3):
        raise ValueError(f"Rating must be 1-3, got {rating}")

    audio = MutagenFile(str(path))
    if audio is None:
        raise ValueError(f"Cannot read audio file: {path}")

    if isinstance(audio, MP3):
        # Use ID3 POPM frame
        try:
            tags = ID3(str(path))
        except Exception:
            # No ID3 tag, create one
            audio.add_tags()
            tags = audio.tags
            if tags is None:
                raise ValueError(f"Cannot create ID3 tags for: {path}")

        # Remove existing POPM frames and add new one
        # POPM frame: email, rating (0-255), count
        tags.delall("POPM")
        tags.add(POPM(email="playgram", rating=_rating_to_popm(rating), count=0))
        tags.save(str(path))

    elif isinstance(audio, MP4):
        # MP4 doesn't have a standard rating field
        # Some players use custom atoms, but it's not reliable
        raise NotImplementedError("MP4/M4A rating not supported")

    elif isinstance(audio, (FLAC, OggVorbis)):
        # Use RATING tag (common convention: 0-100 or 0-5)
        # We use 0-100 scale: 1=33, 2=67, 3=100
        rating_100 = {1: 33, 2: 67, 3: 100}.get(rating, 0)
        audio["RATING"] = [str(rating_100)]
        audio.save()

    else:
        raise NotImplementedError(f"Rating not supported for: {type(audio).__name__}")
