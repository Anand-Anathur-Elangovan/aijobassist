"""
Per-domain ATS field answer cache backed by SQLite via ``aiosqlite``.

Stores previously successful fill values keyed by
``"{ats_platform}__{canonical_key}"`` so repeated runs can bypass the
Claude API for well-known fields.  An answer is considered "trusted" once
it has been successfully filled at least ``_TRUST_THRESHOLD`` times.

Install requirement:  pip install aiosqlite
"""

import json
from datetime import datetime, timezone
from typing import Optional

import aiosqlite
from loguru import logger

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
_DB_PATH:         str = "ats_cache.db"
_TRUST_THRESHOLD: int = 3   # minimum successes before an answer is returned


def set_db_path(path: str) -> None:
    """Override the default SQLite database file path (call before first use)."""
    global _DB_PATH
    _DB_PATH = path


# ---------------------------------------------------------------------------
# In-process counters for hit-rate reporting (reset on process restart)
# ---------------------------------------------------------------------------
_lookup_counts: dict[str, int] = {}
_hit_counts:    dict[str, int] = {}

# ---------------------------------------------------------------------------
# DDL
# ---------------------------------------------------------------------------
_CREATE_TABLE = """
CREATE TABLE IF NOT EXISTS ats_field_cache (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    cache_key     TEXT    UNIQUE NOT NULL,
    canonical_key TEXT    NOT NULL,
    ats_platform  TEXT    NOT NULL,
    raw_labels    TEXT    NOT NULL DEFAULT '[]',
    fill_strategy TEXT    NOT NULL DEFAULT 'text',
    last_answer   TEXT,
    success_count INTEGER NOT NULL DEFAULT 0,
    updated_at    TEXT    NOT NULL
)
"""


async def _ensure_schema(db: aiosqlite.Connection) -> None:
    await db.execute(_CREATE_TABLE)
    await db.commit()


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

async def get_cached_answer(
    ats_platform: str,
    canonical_key: str,
) -> Optional[str]:
    """Return ``last_answer`` if ``success_count >= _TRUST_THRESHOLD``.

    Increments the per-platform lookup counter for hit-rate tracking.
    Returns ``None`` when the entry does not exist or is below threshold.
    """
    cache_key = f"{ats_platform}__{canonical_key}"
    _lookup_counts[ats_platform] = _lookup_counts.get(ats_platform, 0) + 1
    try:
        async with aiosqlite.connect(_DB_PATH) as db:
            await _ensure_schema(db)
            async with db.execute(
                "SELECT last_answer, success_count "
                "FROM ats_field_cache WHERE cache_key = ?",
                (cache_key,),
            ) as cur:
                row = await cur.fetchone()
                if (
                    row
                    and row[1] >= _TRUST_THRESHOLD
                    and row[0] is not None
                ):
                    _hit_counts[ats_platform] = (
                        _hit_counts.get(ats_platform, 0) + 1
                    )
                    logger.debug(
                        f"Cache HIT: {cache_key!r} → {row[0]!r} "
                        f"(success_count={row[1]})"
                    )
                    return row[0]
    except Exception as exc:
        logger.warning(f"field_cache get error for {cache_key!r}: {exc}")
    return None


async def record_success(
    ats_platform: str,
    canonical_key: str,
    raw_label: str,
    fill_strategy: str,
    answer: str,
) -> None:
    """Upsert a successful fill record.

    Increments ``success_count``, updates ``last_answer``, and appends
    ``raw_label`` to the ``raw_labels`` JSON array if not already present.
    """
    cache_key = f"{ats_platform}__{canonical_key}"
    now = datetime.now(timezone.utc).isoformat()
    try:
        async with aiosqlite.connect(_DB_PATH) as db:
            await _ensure_schema(db)
            async with db.execute(
                "SELECT raw_labels, success_count "
                "FROM ats_field_cache WHERE cache_key = ?",
                (cache_key,),
            ) as cur:
                row = await cur.fetchone()

            if row:
                labels: list[str] = json.loads(row[0] or "[]")
                if raw_label and raw_label not in labels:
                    labels.append(raw_label)
                await db.execute(
                    """UPDATE ats_field_cache
                       SET raw_labels=?, fill_strategy=?, last_answer=?,
                           success_count=success_count+1, updated_at=?
                       WHERE cache_key=?""",
                    (
                        json.dumps(labels), fill_strategy,
                        answer, now, cache_key,
                    ),
                )
            else:
                labels = [raw_label] if raw_label else []
                await db.execute(
                    """INSERT INTO ats_field_cache
                           (cache_key, canonical_key, ats_platform,
                            raw_labels, fill_strategy, last_answer,
                            success_count, updated_at)
                       VALUES (?,?,?,?,?,?,1,?)""",
                    (
                        cache_key, canonical_key, ats_platform,
                        json.dumps(labels), fill_strategy, answer, now,
                    ),
                )
            await db.commit()
            logger.debug(f"Cache record_success: {cache_key!r} → {answer!r}")
    except Exception as exc:
        logger.warning(
            f"field_cache record_success error for {cache_key!r}: {exc}"
        )


async def invalidate(ats_platform: str, canonical_key: str) -> None:
    """Reset ``success_count`` to 0, forcing re-inference on next lookup."""
    cache_key = f"{ats_platform}__{canonical_key}"
    try:
        async with aiosqlite.connect(_DB_PATH) as db:
            await _ensure_schema(db)
            await db.execute(
                "UPDATE ats_field_cache "
                "SET success_count=0 WHERE cache_key=?",
                (cache_key,),
            )
            await db.commit()
            logger.debug(f"Cache invalidated: {cache_key!r}")
    except Exception as exc:
        logger.warning(f"field_cache invalidate error for {cache_key!r}: {exc}")


async def cache_hit_rate(ats_platform: Optional[str] = None) -> float:
    """Return the ratio of cache hits to total lookups since process start.

    Args:
        ats_platform: Optional filter; if supplied, only that platform's
                      counters are used.

    Returns:
        Float in ``[0.0, 1.0]``; ``0.0`` when no lookups have been recorded.
    """
    if ats_platform:
        total = _lookup_counts.get(ats_platform, 0)
        hits  = _hit_counts.get(ats_platform, 0)
    else:
        total = sum(_lookup_counts.values())
        hits  = sum(_hit_counts.values())
    return hits / total if total else 0.0
