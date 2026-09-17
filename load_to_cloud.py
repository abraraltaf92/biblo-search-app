"""
Load the pipeline's modeled data (analytics schema) into a cloud Postgres
(Neon / Supabase / Railway) so the deployed search app has data to serve.

Usage:
  1. Run your local pipeline so analytics.dim_bookstore / dim_book / fact_inventory exist.
  2. Set two env vars:
       LOCAL_DB_URL  = your local pipeline DB (default postgresql://biblo:biblo@localhost:5433/biblo)
       CLOUD_DB_URL  = the hosted Postgres connection string (from Neon/Supabase)
  3. python load_to_cloud.py

It copies the three analytics tables from local -> cloud. Re-run any time you
refresh the data locally.
"""

from __future__ import annotations

import os
import sys

import psycopg

LOCAL_DB_URL = os.environ.get("LOCAL_DB_URL", "postgresql://biblo:biblo@localhost:5433/biblo")
CLOUD_DB_URL = os.environ.get("CLOUD_DB_URL")

TABLES = {
    "dim_bookstore": """
        CREATE TABLE analytics.dim_bookstore (
            bookstore_id bigint, store_name text, city text, postcode text,
            street text, housenumber text, website text,
            latitude double precision, longitude double precision
        );""",
    "dim_book": """
        CREATE TABLE analytics.dim_book (
            book_id text, title text, authors text,
            first_publish_year int, edition_count int, first_seen_subject text
        );""",
    "fact_inventory": """
        CREATE TABLE analytics.fact_inventory (
            inventory_id bigint, bookstore_id bigint, book_id text,
            price_usd numeric, quantity int, in_stock boolean
        );""",
}


def main() -> None:
    if not CLOUD_DB_URL:
        print("ERROR: set CLOUD_DB_URL to your hosted Postgres connection string.", file=sys.stderr)
        sys.exit(1)

    print("Connecting to local and cloud databases...")
    local = psycopg.connect(LOCAL_DB_URL)
    cloud = psycopg.connect(CLOUD_DB_URL)

    with cloud, cloud.cursor() as ccur:
        ccur.execute("CREATE SCHEMA IF NOT EXISTS analytics;")
        for name, ddl in TABLES.items():
            ccur.execute(f"DROP TABLE IF EXISTS analytics.{name} CASCADE;")
            ccur.execute(ddl)
        cloud.commit()

        for name in TABLES:
            with local.cursor() as lcur:
                lcur.execute(f"SELECT * FROM analytics.{name};")
                cols = [c.name for c in lcur.description]
                rows = lcur.fetchall()
            if not rows:
                print(f"  {name}: 0 rows (skipped)")
                continue
            placeholders = ", ".join(["%s"] * len(cols))
            collist = ", ".join(cols)
            ccur.executemany(
                f"INSERT INTO analytics.{name} ({collist}) VALUES ({placeholders})",
                rows,
            )
            cloud.commit()
            print(f"  {name}: loaded {len(rows)} rows")

    print("Done. Cloud database is ready for the search app.")


if __name__ == "__main__":
    main()
