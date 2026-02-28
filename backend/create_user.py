import argparse
import os
import sqlite3
from datetime import datetime, timezone

from dotenv import load_dotenv
from werkzeug.security import generate_password_hash


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def main() -> None:
    parser = argparse.ArgumentParser(description="Create or update a backend user")
    parser.add_argument("--username", required=True, help="Username to create/update")
    parser.add_argument("--password", required=True, help="Plain-text password")
    args = parser.parse_args()

    load_dotenv()
    db_path = os.getenv("DB_PATH", "./data/print_jobs.db")

    conn = sqlite3.connect(db_path)
    try:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT NOT NULL UNIQUE,
                password_hash TEXT NOT NULL,
                created_at TEXT NOT NULL
            )
            """
        )
        conn.execute(
            """
            INSERT INTO users (username, password_hash, created_at)
            VALUES (?, ?, ?)
            ON CONFLICT(username) DO UPDATE SET
                password_hash = excluded.password_hash
            """,
            (args.username.strip(), generate_password_hash(args.password), utc_now_iso()),
        )
        conn.commit()
    finally:
        conn.close()

    print(f"User upserted: {args.username}")


if __name__ == "__main__":
    main()
