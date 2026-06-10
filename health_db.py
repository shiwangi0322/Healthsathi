"""
HealthSathi — modules/health_db.py
Database connection module.
FIX: Drops and recreates tables if schema is wrong.
"""

import sqlite3
import os
from typing import Optional, Dict, List

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB_PATH  = os.path.join(BASE_DIR, "database", "health.db")


def get_db() -> sqlite3.Connection:
    """Get database connection."""
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def _check_schema(conn: sqlite3.Connection) -> bool:
    """Check if symptoms table has the correct 'keyword' column."""
    try:
        conn.execute("SELECT keyword FROM symptoms LIMIT 1")
        return True
    except sqlite3.OperationalError:
        return False


def init_db() -> None:
    """
    Initialize database.
    AUTO-FIXES: If old schema detected (missing 'keyword' column),
    drops all tables and recreates them correctly.
    """
    conn = get_db()

    # Check if schema is correct
    needs_reset = not _check_schema(conn)

    if needs_reset:
        print("  [DB] Old schema detected — dropping and recreating tables...")
        conn.executescript("""
            DROP TABLE IF EXISTS symptoms;
            DROP TABLE IF EXISTS diseases;
            DROP TABLE IF EXISTS first_aid;
            DROP TABLE IF EXISTS users;
            DROP TABLE IF EXISTS conversations;
        """)
        conn.commit()

    # Create all tables
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS symptoms (
            id       INTEGER PRIMARY KEY AUTOINCREMENT,
            keyword  TEXT    UNIQUE NOT NULL,
            response TEXT    NOT NULL
        );
        CREATE TABLE IF NOT EXISTS diseases (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            name          TEXT    UNIQUE NOT NULL,
            symptoms_list TEXT    NOT NULL,
            precautions   TEXT    NOT NULL
        );
        CREATE TABLE IF NOT EXISTS first_aid (
            id      INTEGER PRIMARY KEY AUTOINCREMENT,
            keyword TEXT    UNIQUE NOT NULL,
            steps   TEXT    NOT NULL
        );
        CREATE TABLE IF NOT EXISTS users (
            id        INTEGER PRIMARY KEY AUTOINCREMENT,
            full_name TEXT    NOT NULL,
            phone     TEXT    UNIQUE NOT NULL,
            email     TEXT,
            password  TEXT    NOT NULL,
            created   TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS conversations (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id     INTEGER,
            user_text   TEXT NOT NULL,
            ai_response TEXT NOT NULL,
            intent      TEXT,
            created     TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
    """)
    conn.commit()

    # Seed data if empty
    count = conn.execute("SELECT COUNT(*) FROM symptoms").fetchone()[0]
    if count == 0:
        _seed_all(conn)
    else:
        print("  [DB] Database OK — {} symptoms loaded.".format(count))

    conn.close()


def _seed_all(conn: sqlite3.Connection) -> None:
    """Insert all health data."""
    from modules.health_data import symptoms_data, diseases_data, first_aid_data  # noqa: PLC0415

    s_count = 0
    for kw, resp in symptoms_data:
        try:
            conn.execute("INSERT OR IGNORE INTO symptoms (keyword, response) VALUES (?,?)", (kw.lower().strip(), resp))
            s_count += 1
        except sqlite3.Error:
            pass

    d_count = 0
    for name, syms, prec in diseases_data:
        try:
            conn.execute("INSERT OR IGNORE INTO diseases (name, symptoms_list, precautions) VALUES (?,?,?)", (name.lower().strip(), syms, prec))
            d_count += 1
        except sqlite3.Error:
            pass

    f_count = 0
    for kw, steps in first_aid_data:
        try:
            conn.execute("INSERT OR IGNORE INTO first_aid (keyword, steps) VALUES (?,?)", (kw.lower().strip(), steps))
            f_count += 1
        except sqlite3.Error:
            pass

    conn.commit()
    print("  [DB] Seeded: {} symptoms, {} diseases, {} first_aid".format(s_count, d_count, f_count))


# ── Search functions ──────────────────────────────────────────

def search_symptoms(keyword: str) -> Optional[str]:
    conn = get_db()
    try:
        row = conn.execute(
            "SELECT response FROM symptoms WHERE keyword = ?",
            (keyword.strip().lower(),)
        ).fetchone()
        return str(row["response"]) if row else None
    finally:
        conn.close()


def search_diseases(name: str) -> Optional[Dict[str, str]]:
    conn = get_db()
    try:
        row = conn.execute(
            "SELECT symptoms_list, precautions FROM diseases WHERE name = ?",
            (name.strip().lower(),)
        ).fetchone()
        if row:
            return {"symptoms": str(row["symptoms_list"]), "precautions": str(row["precautions"])}
        return None
    finally:
        conn.close()


def search_first_aid(keyword: str) -> Optional[str]:
    conn = get_db()
    try:
        row = conn.execute(
            "SELECT steps FROM first_aid WHERE keyword = ?",
            (keyword.strip().lower(),)
        ).fetchone()
        return str(row["steps"]) if row else None
    finally:
        conn.close()


def get_all_keywords() -> Dict[str, List[str]]:
    conn = get_db()
    try:
        syms = [str(r[0]) for r in conn.execute("SELECT keyword FROM symptoms").fetchall()]
        dis  = [str(r[0]) for r in conn.execute("SELECT name FROM diseases").fetchall()]
        fa   = [str(r[0]) for r in conn.execute("SELECT keyword FROM first_aid").fetchall()]
        return {"symptoms": syms, "diseases": dis, "first_aid": fa}
    finally:
        conn.close()


def save_conversation(user_id: Optional[int], user_text: str, ai_response: str, intent: str) -> None:
    conn = get_db()
    try:
        conn.execute(
            "INSERT INTO conversations (user_id, user_text, ai_response, intent) VALUES (?,?,?,?)",
            (user_id, user_text, ai_response, intent)
        )
        conn.commit()
    except Exception:
        pass
    finally:
        conn.close()


def get_user_history(user_id: Optional[int], limit: int = 10) -> list:
    conn = get_db()
    try:
        rows = conn.execute(
            "SELECT user_text, ai_response, intent, created FROM conversations WHERE user_id = ? ORDER BY created DESC LIMIT ?",
            (user_id, limit)
        ).fetchall()
        return [{"user": r["user_text"], "ai": r["ai_response"], "intent": r["intent"], "time": r["created"]} for r in rows]
    except Exception:
        return []
    finally:
        conn.close()