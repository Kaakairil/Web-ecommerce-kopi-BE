"""Promote a user to admin by email, over the direct Postgres connection.

Usage: python scripts/seed_admin.py user@example.com   (requires DATABASE_URL)
"""
import os
import sys

import psycopg2
from dotenv import load_dotenv

load_dotenv()


def main():
    if len(sys.argv) != 2:
        sys.exit("Usage: python scripts/seed_admin.py <email>")
    email = sys.argv[1].strip().lower()
    url = os.environ.get("DATABASE_URL")
    if not url:
        sys.exit("DATABASE_URL not set")
    conn = psycopg2.connect(url)
    try:
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE users SET is_admin = true, updated_at = now() "
                "WHERE lower(email) = %s RETURNING id, username",
                (email,),
            )
            row = cur.fetchone()
            if not row:
                sys.exit(f"No user with email {email}")
            conn.commit()
            print(f"Promoted {row[1]} (id={row[0]}) to admin.")
    finally:
        conn.close()


if __name__ == "__main__":
    main()
