import json
import sqlite3
from pathlib import Path

from sentence_transformers import SentenceTransformer

from app.memory.contracts import (
    MEMORY_AUTHORITY_NONE,
    MemoryKind,
    MemorySource,
    MemoryStatus,
)
from app.memory.schema import (
    migrate_memory_schema,
    new_memory_id,
)


# =========================================================
# DATABASE
# =========================================================

DATA_DIR = (
    Path.home()
    / "Library"
    / "Application Support"
    / "Kuma"
    / "data"
)

DATA_DIR.mkdir(
    parents=True,
    exist_ok=True,
    mode=0o700,
)

DB_PATH = DATA_DIR / "kuma_memory.db"


# =========================================================
# EMBEDDING MODEL
# =========================================================

_embedding_model = None


def get_embedding_model():

    global _embedding_model

    if _embedding_model is None:

        print("KUMA: Loading memory model...")

        _embedding_model = SentenceTransformer(
            "all-MiniLM-L6-v2"
        )

        print("KUMA: Memory model ready.")

    return _embedding_model


def create_embedding(text: str):

    model = get_embedding_model()

    embedding = model.encode(
        text,
        normalize_embeddings=True
    )

    return embedding.tolist()


def memory_embedding_text(
    category: str,
    key: str,
    value: str
):

    return (
        f"Category: {category}. "
        f"Memory: {key}. "
        f"Value: {value}."
    )


# =========================================================
# DATABASE CONNECTION
# =========================================================

def get_connection():

    return sqlite3.connect(DB_PATH)


# =========================================================
# INITIALIZATION
# =========================================================

def initialize_memory():

    with get_connection() as connection:

        # ---------------------------------------------
        # Conversation history
        # ---------------------------------------------

        connection.execute("""
            CREATE TABLE IF NOT EXISTS messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                role TEXT NOT NULL,
                content TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # ---------------------------------------------
        # Long-term memories
        # ---------------------------------------------

        connection.execute("""
            CREATE TABLE IF NOT EXISTS memories (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                category TEXT NOT NULL,
                key TEXT NOT NULL,
                value TEXT NOT NULL,
                embedding TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # ---------------------------------------------
        # Migration for existing databases
        # ---------------------------------------------

        columns = connection.execute(
            "PRAGMA table_info(memories)"
        ).fetchall()

        column_names = [
            column[1]
            for column in columns
        ]

        if "embedding" not in column_names:

            connection.execute(
                """
                ALTER TABLE memories
                ADD COLUMN embedding TEXT
                """
            )

        # MEMORY-1B — additive, idempotent database schema.
        # Conversation history and mission tables are not
        # rewritten by this migration.
        migrate_memory_schema(
            connection
        )

        connection.commit()


# =========================================================
# CONVERSATION MEMORY
# =========================================================

def save_message(
    role: str,
    content: str
):

    with get_connection() as connection:

        connection.execute(
            """
            INSERT INTO messages (role, content)
            VALUES (?, ?)
            """,
            (role, content),
        )

        connection.commit()


def get_recent_messages(
    limit: int = 10
):

    with get_connection() as connection:

        rows = connection.execute(
            """
            SELECT role, content
            FROM messages
            ORDER BY id DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()

    rows.reverse()

    return rows


# =========================================================
# LONG-TERM MEMORY
# =========================================================

def save_memory(
    category: str,
    key: str,
    value: str
):

    embedding_text = memory_embedding_text(
        category,
        key,
        value
    )

    try:
        embedding = create_embedding(
            embedding_text
        )
        embedding_json = json.dumps(
            embedding
        )
    except Exception as e:
        print(
            f"KUMA MEMORY EMBEDDING ERROR: {e}"
        )
        embedding_json = None

    with get_connection() as connection:

        connection.execute(
            "BEGIN IMMEDIATE"
        )

        try:
            existing = connection.execute(
                """
                SELECT id, memory_id
                FROM memories
                WHERE category = ?
                  AND key = ?
                  AND status = ?
                  AND authority = ?
                ORDER BY updated_at DESC, id DESC
                LIMIT 1
                """,
                (
                    category,
                    key,
                    MemoryStatus.ACTIVE.value,
                    MEMORY_AUTHORITY_NONE,
                ),
            ).fetchone()

            supersedes = (
                existing[1]
                if existing
                else None
            )

            if existing:
                connection.execute(
                    """
                    UPDATE memories
                    SET status = ?,
                        updated_at = CURRENT_TIMESTAMP
                    WHERE category = ?
                      AND key = ?
                      AND status = ?
                    """,
                    (
                        MemoryStatus.SUPERSEDED.value,
                        category,
                        key,
                        MemoryStatus.ACTIVE.value,
                    ),
                )

            memory_id = new_memory_id()

            connection.execute(
                """
                INSERT INTO memories (
                    category,
                    key,
                    value,
                    embedding,
                    memory_id,
                    kind,
                    source,
                    confidence,
                    importance,
                    status,
                    supersedes,
                    subject,
                    authority
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    category,
                    key,
                    value,
                    embedding_json,
                    memory_id,
                    MemoryKind.UNCLASSIFIED.value,
                    MemorySource.USER_STATEMENT.value,
                    1.0,
                    0.5,
                    MemoryStatus.ACTIVE.value,
                    supersedes,
                    "user",
                    MEMORY_AUTHORITY_NONE,
                ),
            )

            connection.commit()

        except BaseException:
            connection.rollback()
            raise


def get_memory(
    category: str,
    key: str
):

    with get_connection() as connection:

        row = connection.execute(
            """
            SELECT value
            FROM memories
            WHERE category = ?
              AND key = ?
              AND status = ?
              AND authority = ?
            ORDER BY updated_at DESC, id DESC
            LIMIT 1
            """,
            (
                category,
                key,
                MemoryStatus.ACTIVE.value,
                MEMORY_AUTHORITY_NONE,
            ),
        ).fetchone()

    if row:
        return row[0]

    return None


def get_all_memories():

    with get_connection() as connection:

        rows = connection.execute(
            """
            SELECT category, key, value
            FROM memories
            WHERE status = ?
              AND authority = ?
            ORDER BY updated_at DESC, id DESC
            """,
            (
                MemoryStatus.ACTIVE.value,
                MEMORY_AUTHORITY_NONE,
            ),
        ).fetchall()

    return rows


# =========================================================
# SEMANTIC MEMORY SEARCH
# =========================================================

def search_memories(
    query: str,
    limit: int = 5,
    threshold: float = 0.25
):

    if not query.strip():

        return []


    query_embedding = create_embedding(
        query
    )


    with get_connection() as connection:

        rows = connection.execute(
            """
            SELECT id, category, key, value, embedding
            FROM memories
            WHERE embedding IS NOT NULL
            """
        ).fetchall()


    if not rows:

        return []


    scored_memories = []


    for (
        memory_id,
        category,
        key,
        value,
        embedding_json,
    ) in rows:

        try:

            memory_embedding = json.loads(
                embedding_json
            )

            # Embeddings are normalized, so
            # cosine similarity = dot product.

            score = sum(
                q * m
                for q, m in zip(
                    query_embedding,
                    memory_embedding
                )
            )

            if score >= threshold:

                scored_memories.append(
                    (
                        score,
                        category,
                        key,
                        value,
                    )
                )

        except Exception as e:

            print(
                f"KUMA MEMORY SEARCH ERROR: {e}"
            )


    scored_memories.sort(
        reverse=True,
        key=lambda item: item[0]
    )


    return [
        (
            category,
            key,
            value,
        )
        for (
            score,
            category,
            key,
            value,
        ) in scored_memories[:limit]
    ]

# =========================================================
# MEMORY EMBEDDING BACKFILL
# =========================================================

def backfill_embeddings():

    with get_connection() as connection:

        rows = connection.execute(
            """
            SELECT id, category, key, value
            FROM memories
            WHERE embedding IS NULL
            """
        ).fetchall()

    if not rows:

        print("KUMA: All memories already have embeddings.")

        return 0

    updated = 0

    for memory_id, category, key, value in rows:

        try:

            text = memory_embedding_text(
                category,
                key,
                value,
            )

            embedding = create_embedding(text)

            embedding_json = json.dumps(
                embedding
            )

            with get_connection() as connection:

                connection.execute(
                    """
                    UPDATE memories
                    SET embedding = ?
                    WHERE id = ?
                    """,
                    (
                        embedding_json,
                        memory_id,
                    ),
                )

                connection.commit()

            updated += 1

        except Exception as e:

            print(
                f"KUMA: Failed to embed memory "
                f"{memory_id}: {e}"
            )

    print(
        f"KUMA: Backfilled {updated} memories."
    )

    return updated
# =========================================================
# DELETE MEMORY
# =========================================================

def delete_memory(
    category: str,
    key: str
) -> bool:
    """
    Delete a long-term memory.

    Returns:
        True  -> a memory was actually deleted.
        False -> no matching memory existed.
    """

    with get_connection() as connection:

        cursor = connection.execute(
            """
            DELETE FROM memories
            WHERE category = ?
            AND key = ?
            """,
            (category, key),
        )

        connection.commit()

        return cursor.rowcount > 0


# =========================================================
# CLEAR MEMORY
# =========================================================

def clear_memory():

    with get_connection() as connection:

        connection.execute(
            "DELETE FROM messages"
        )

        connection.execute(
            "DELETE FROM memories"
        )

        connection.commit()