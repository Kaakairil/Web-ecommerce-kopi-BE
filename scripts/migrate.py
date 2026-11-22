"""Apply versioned SQL migrations in order. Tracks applied versions in schema_migrations.

Usage: python scripts/migrate.py   (requires DATABASE_URL in env)
"""
import os
import sys
from pathlib import Path

import psycopg2
from dotenv import load_dotenv

load_dotenv()  # backend/.env

MIGRATIONS_DIR = Path(__file__).resolve().parent.parent / "db" / "migrations"


def get_connection():
    url = os.environ.get("DATABASE_URL")
    if not url:
        sys.exit("DATABASE_URL not set (postgresql://postgres:***@db.<ref>.supabase.co:5432/postgres)")
    return psycopg2.connect(url)


def applied_versions(conn) -> set:
    with conn.cursor() as cur:
        cur.execute(
            "CREATE TABLE IF NOT EXISTS schema_migrations ("
            " version TEXT PRIMARY KEY, applied_at TIMESTAMPTZ NOT NULL DEFAULT now())"
        )
        conn.commit()
        cur.execute("SELECT version FROM schema_migrations")
        return {row[0] for row in cur.fetchall()}


def main():
    files = sorted(p for p in MIGRATIONS_DIR.glob("*.sql"))
    if not files:
        sys.exit(f"No .sql files in {MIGRATIONS_DIR}")
    conn = get_connection()
    try:
        done = applied_versions(conn)
        for path in files:
            version = path.name
            if version in done:
                print(f"  skip   {version} (already applied)")
                continue
            sql = path.read_text(encoding="utf-8")
            with conn.cursor() as cur:
                cur.execute(sql)
                cur.execute(
                    "INSERT INTO schema_migrations (version) VALUES (%s)", (version,)
                )
            conn.commit()
            print(f"  apply  {version}")
        print("Migrations up to date.")
    except Exception as e:
        conn.rollback()
        print(f"FAILED: {e}")
        sys.exit(1)
    finally:
        conn.close()


if __name__ == "__main__":
    main()
