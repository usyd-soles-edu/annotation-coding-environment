"""Local FTS5-backed codebook cue ranking."""

from __future__ import annotations

import re
import sqlite3


_STOP_WORDS = {
    "a", "about", "above", "after", "again", "against", "all", "am", "an",
    "and", "any", "are", "as", "at", "be", "because", "been", "before",
    "being", "below", "between", "both", "but", "by", "can", "did", "do",
    "does", "doing", "down", "during", "each", "few", "for", "from",
    "further", "had", "has", "have", "having", "he", "her", "here",
    "hers", "herself", "him", "himself", "his", "how", "i", "if", "in",
    "into", "is", "it", "its", "itself", "just", "me", "more", "most",
    "my", "myself", "no", "nor", "not", "now", "of", "off", "on", "once",
    "only", "or", "other", "our", "ours", "ourselves", "out", "over",
    "own", "same", "she", "should", "so", "some", "such", "than", "that",
    "the", "their", "theirs", "them", "themselves", "then", "there",
    "these", "they", "this", "those", "through", "to", "too", "under",
    "until", "up", "very", "was", "we", "were", "what", "when", "where",
    "which", "while", "who", "whom", "why", "with", "would", "you",
    "your", "yours", "yourself", "yourselves",
}

_FTS_TOKENIZERS = ("porter unicode61", "unicode61")


def _tokens(text: str) -> list[str]:
    seen: set[str] = set()
    tokens: list[str] = []
    for token in re.findall(r"[0-9A-Za-z]+", text.casefold()):
        if len(token) < 3 or token in _STOP_WORDS or token in seen:
            continue
        seen.add(token)
        tokens.append(token)
    return tokens


def _query_from_tokens(tokens: list[str]) -> str:
    return " OR ".join(tokens[:16])


def _create_temp_index(conn: sqlite3.Connection) -> bool:
    for tokenizer in _FTS_TOKENIZERS:
        try:
            conn.execute("DROP TABLE IF EXISTS temp.code_cue_fts")
            conn.execute(
                f"""
            CREATE VIRTUAL TABLE temp.code_cue_fts USING fts5(
              name,
              definition,
              cue_text,
              code_id UNINDEXED,
              tokenize = '{tokenizer}'
            )
            """
            )
            return True
        except sqlite3.OperationalError:
            try:
                conn.execute("DROP TABLE IF EXISTS temp.code_cue_fts")
            except sqlite3.OperationalError:
                pass
    return False


def _index_codes(conn: sqlite3.Connection) -> None:
    rows = conn.execute(
        """
        SELECT id, name, COALESCE(definition, '') AS definition
        FROM codebook_code
        WHERE deleted_at IS NULL AND kind = 'code'
        """
    ).fetchall()
    conn.executemany(
        """
        INSERT INTO temp.code_cue_fts (code_id, name, definition, cue_text)
        VALUES (?, ?, ?, ?)
        """,
        [
            (
                row["id"],
                row["name"] or "",
                row["definition"] or "",
                f"{row['name'] or ''} {row['name'] or ''} {row['definition'] or ''}",
            )
            for row in rows
        ],
    )


def _matched_terms(query_tokens: list[str], text: str) -> list[str]:
    text_tokens = set(_tokens(text))
    return [token for token in query_tokens if token in text_tokens]


def suggest_code_cues(
    conn: sqlite3.Connection,
    sentence_text: str,
    *,
    limit: int = 3,
) -> list[dict]:
    """Return ranked codebook cue candidates for a focused sentence."""
    query_tokens = _tokens(sentence_text)
    if not query_tokens or limit <= 0:
        return []

    if not _create_temp_index(conn):
        return []
    try:
        _index_codes(conn)
    except sqlite3.OperationalError:
        return []

    query = _query_from_tokens(query_tokens)
    if not query:
        return []

    try:
        rows = conn.execute(
            """
        SELECT code_id,
               name,
               definition,
               bm25(code_cue_fts, 4.0, 1.0, 1.0, 0.0) AS bm25_rank
            FROM temp.code_cue_fts
            WHERE code_cue_fts MATCH ?
            ORDER BY bm25_rank
            LIMIT ?
            """,
            (query, limit),
        ).fetchall()
    except sqlite3.OperationalError:
        return []

    cues: list[dict] = []
    for row in rows:
        rank = max(0.0, -float(row["bm25_rank"]))
        evidence = _matched_terms(
            query_tokens,
            f"{row['name'] or ''} {row['definition'] or ''}",
        )
        if rank <= 0 or not evidence:
            continue
        cues.append({
            "code_id": row["code_id"],
            "rank": rank,
            "matched_terms": evidence[:5],
        })
    return cues
