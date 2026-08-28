"""
reading_list.py
Saves the books you have read inside the assistant.db database.
Supports two types of books:
  - "linked": Books connected to the library using a book_id
  - "freeform": Extra books you typed manually (title and author saved separately)

The list remains intact even if the application is restarted or the browser is closed.
"""
 
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
 
DB_PATH = Path("assistant.db")
 
EXPECTED_COLUMNS = {"id", "book_id", "freeform_title", "freeform_author", "marked_at"}
 
 
def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    existing_cols = {
        row[1] for row in conn.execute("PRAGMA table_info(read_books)").fetchall()
    }
    if existing_cols and existing_cols != EXPECTED_COLUMNS:
        # Eski surumden kalma / farkli semali bir tablo. Okuma listesi
        # kucuk/kritik olmayan bir veri oldugu icin guvenle yeniden
        # olusturuyoruz (semayi buyutup veri tasimak yerine).
        conn.execute("DROP TABLE read_books")
        existing_cols = set()
    if not existing_cols:
        conn.execute(
            """
            CREATE TABLE read_books (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                book_id INTEGER,
                freeform_title TEXT,
                freeform_author TEXT,
                marked_at TEXT NOT NULL
            )
            """
        )
    conn.commit()
    return conn
 
 
def add_linked_book(book_id: int) -> None:
    conn = _connect()
    existing = conn.execute(
        "SELECT 1 FROM read_books WHERE book_id = ?", (book_id,)
    ).fetchone()
    if not existing:
        conn.execute(
            "INSERT INTO read_books (book_id, freeform_title, freeform_author, marked_at) "
            "VALUES (?, NULL, NULL, ?)",
            (book_id, datetime.now(timezone.utc).isoformat()),
        )
        conn.commit()
    conn.close()
 
 
def remove_linked_book(book_id: int) -> None:
    conn = _connect()
    conn.execute("DELETE FROM read_books WHERE book_id = ?", (book_id,))
    conn.commit()
    conn.close()
 
 
def add_freeform_book(title: str, author: str = "") -> None:
    conn = _connect()
    conn.execute(
        "INSERT INTO read_books (book_id, freeform_title, freeform_author, marked_at) "
        "VALUES (NULL, ?, ?, ?)",
        (title.strip(), author.strip(), datetime.now(timezone.utc).isoformat()),
    )
    conn.commit()
    conn.close()
 
 
def remove_entry(entry_id: int) -> None:
    conn = _connect()
    conn.execute("DELETE FROM read_books WHERE id = ?", (entry_id,))
    conn.commit()
    conn.close()
 
 
def get_linked_book_ids() -> set:
    conn = _connect()
    rows = conn.execute(
        "SELECT book_id FROM read_books WHERE book_id IS NOT NULL"
    ).fetchall()
    conn.close()
    return {r[0] for r in rows}
 
 
def get_all_entries() -> list:
    """Her kayit: {id, book_id, freeform_title, freeform_author, marked_at}."""
    conn = _connect()
    rows = conn.execute(
        "SELECT id, book_id, freeform_title, freeform_author, marked_at FROM read_books "
        "ORDER BY marked_at DESC"
    ).fetchall()
    conn.close()
    return [
        {
            "id": r[0],
            "book_id": r[1],
            "freeform_title": r[2],
            "freeform_author": r[3],
            "marked_at": r[4],
        }
        for r in rows
    ]