"""
ingest.py
Excel (data/books.xlsx) -> SQLite (assistant.db)
Generates embeddings for each book using qwen3-embedding-0.6b and stores them as BLOBs.

Columns: id, title_tr, title_en, author, genre, broad_genre, page, summary
"""

import sys
import sqlite3
from pathlib import Path

import numpy as np
import pandas as pd
from openai import OpenAI

from foundry_utils import ensure_model_loaded, get_client, resolve_model_id

EXCEL_PATH = Path("data/books.xlsx")
DB_PATH = Path("assistant.db")
EMBEDDING_MODEL_ALIAS = "qwen3-embedding-0.6b"

REQUIRED_COLUMNS = [
    "id", "title_tr", "title_en", "author",
    "genre", "broad_genre", "page", "summary",
]


def get_embedding_client():
    """Foundry Local sunucusuna baglanir, embedding modelini yukler."""
    ensure_model_loaded(EMBEDDING_MODEL_ALIAS)
    client = get_client()
    model_id = resolve_model_id(client, EMBEDDING_MODEL_ALIAS)
    return client, model_id


def embed_text(client: OpenAI, model_id: str, text: str) -> np.ndarray:
    resp = client.embeddings.create(model=model_id, input=text)
    return np.array(resp.data[0].embedding, dtype=np.float32)


def create_table(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS books (
            id INTEGER PRIMARY KEY,
            title_tr TEXT,
            title_en TEXT,
            author TEXT,
            genre TEXT,
            broad_genre TEXT,
            page INTEGER,
            summary TEXT,
            embedding BLOB
        )
        """
    )
    conn.commit()


def build_embedding_text(row: pd.Series) -> str:
    """Embedding icin kullanilacak birlesik metin."""
    parts = [
        row.get("title_tr"),
        row.get("title_en"),
        row.get("author"),
        row.get("genre"),
        row.get("broad_genre"),
        row.get("summary"),
    ]
    parts = [str(p) for p in parts if p not in (None, "", float("nan"))]
    return " | ".join(parts)


def main() -> None:
    if not EXCEL_PATH.exists():
        print(f"HATA: {EXCEL_PATH} bulunamadi.")
        sys.exit(1)

    df = pd.read_excel(EXCEL_PATH)
    df = df.where(pd.notnull(df), None)

    missing = [c for c in REQUIRED_COLUMNS if c not in df.columns]
    if missing:
        print(f"HATA: Excel'de eksik kolonlar: {missing}")
        sys.exit(1)

    print(f"{len(df)} satir okundu. Foundry Local'a baglaniliyor...")
    client, model_id = get_embedding_client()
    print(f"Embedding modeli hazir: {model_id}")

    conn = sqlite3.connect(DB_PATH)
    create_table(conn)

    inserted, skipped = 0, 0
    for _, row in df.iterrows():
        text = build_embedding_text(row)
        if not text.strip():
            print(f"[ATLANDI] id={row.get('id')} -> embed edilecek metin yok")
            skipped += 1
            continue

        try:
            embedding = embed_text(client, model_id, text)
        except Exception as exc:  # Foundry Local gecici hata verebilir
            print(f"[UYARI] id={row.get('id')} embedding alinamadi: {exc}")
            skipped += 1
            continue

        conn.execute(
            """
            INSERT OR REPLACE INTO books
                (id, title_tr, title_en, author, genre, broad_genre, page, summary, embedding)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                int(row["id"]) if row["id"] is not None else None,
                row["title_tr"],
                row["title_en"],
                row["author"],
                row["genre"],
                row["broad_genre"],
                int(row["page"]) if row["page"] is not None else None,
                row["summary"],
                embedding.tobytes(),
            ),
        )
        inserted += 1

        if inserted % 25 == 0:
            conn.commit()
            print(f"  {inserted} kitap islendi...")

    conn.commit()
    conn.close()
    print(f"Bitti. Eklenen: {inserted}, Atlanan: {skipped}")


if __name__ == "__main__":
    main()