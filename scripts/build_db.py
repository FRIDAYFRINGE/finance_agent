"""Database build and seeding script for Financial Analyst Agent.

Reads curated source CSV files from data/raw/ and builds a fully normalized
SQLite database with 5 tables:
- sectors
- companies
- financials
- valuations
- news_events

Usage:
    python scripts/build_db.py [--rebuild] [--db-path PATH] [--raw-dir PATH]
"""

import argparse
import csv
import os
import sqlite3
import sys
from pathlib import Path


def get_connection(db_path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA foreign_keys = ON;")
    conn.row_factory = sqlite3.Row
    return conn


def create_schema(conn: sqlite3.Connection):
    """Creates the 5 core tables with proper primary and foreign keys."""
    cursor = conn.cursor()
    
    cursor.executescript("""
    CREATE TABLE IF NOT EXISTS sectors (
        id            INTEGER PRIMARY KEY AUTOINCREMENT,
        name          TEXT NOT NULL UNIQUE,
        display_name  TEXT NOT NULL,
        overview      TEXT,
        tailwinds     TEXT,
        headwinds     TEXT,
        data_as_of    TEXT
    );

    CREATE TABLE IF NOT EXISTS companies (
        id                   INTEGER PRIMARY KEY AUTOINCREMENT,
        ticker               TEXT NOT NULL UNIQUE,
        name                 TEXT NOT NULL,
        sector_id            INTEGER NOT NULL,
        sub_sector           TEXT,
        description          TEXT,
        headcount            INTEGER,
        headcount_change_pct REAL,
        data_as_of           TEXT,
        FOREIGN KEY (sector_id) REFERENCES sectors(id) ON DELETE CASCADE
    );

    CREATE TABLE IF NOT EXISTS financials (
        id                   INTEGER PRIMARY KEY AUTOINCREMENT,
        company_id           INTEGER NOT NULL,
        fiscal_year          INTEGER NOT NULL,
        revenue              REAL,
        revenue_growth_pct   REAL,
        net_income           REAL,
        gross_margin_pct     REAL,
        operating_margin_pct REAL,
        ebitda               REAL,
        free_cash_flow       REAL,
        total_debt           REAL,
        cash                 REAL,
        debt_to_ebitda       REAL,
        eps                  REAL,
        roe_pct              REAL,
        source               TEXT,
        source_url           TEXT,
        FOREIGN KEY (company_id) REFERENCES companies(id) ON DELETE CASCADE,
        UNIQUE(company_id, fiscal_year)
    );

    CREATE TABLE IF NOT EXISTS valuations (
        id                INTEGER PRIMARY KEY AUTOINCREMENT,
        company_id        INTEGER NOT NULL,
        as_of_date        TEXT NOT NULL,
        market_cap        REAL,
        enterprise_value  REAL,
        pe_ttm            REAL,
        pe_forward        REAL,
        ev_ebitda         REAL,
        price             REAL,
        dividend_yield    REAL,
        source            TEXT,
        source_url        TEXT,
        FOREIGN KEY (company_id) REFERENCES companies(id) ON DELETE CASCADE,
        UNIQUE(company_id, as_of_date)
    );

    CREATE TABLE IF NOT EXISTS news_events (
        id            INTEGER PRIMARY KEY AUTOINCREMENT,
        company_id    INTEGER NOT NULL,
        event_date    TEXT,
        event_type    TEXT,
        headline      TEXT NOT NULL,
        summary       TEXT,
        source_url    TEXT,
        sentiment     TEXT,
        FOREIGN KEY (company_id) REFERENCES companies(id) ON DELETE CASCADE
    );

    CREATE INDEX IF NOT EXISTS idx_companies_sector ON companies(sector_id);
    CREATE INDEX IF NOT EXISTS idx_financials_company ON financials(company_id);
    CREATE INDEX IF NOT EXISTS idx_valuations_company ON valuations(company_id);
    CREATE INDEX IF NOT EXISTS idx_news_company ON news_events(company_id);
    CREATE INDEX IF NOT EXISTS idx_news_type ON news_events(event_type);
    """)
    conn.commit()


def seed_sectors(conn: sqlite3.Connection, raw_dir: Path) -> dict[str, int]:
    """Populates sectors table from sectors.csv and returns {sector_name: sector_id} mapping."""
    filepath = raw_dir / "sectors.csv"
    if not filepath.exists():
        raise FileNotFoundError(f"Missing {filepath}")

    cursor = conn.cursor()
    sector_map = {}
    with open(filepath, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            cursor.execute("""
                INSERT INTO sectors (name, display_name, overview, tailwinds, headwinds, data_as_of)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (
                row["name"].strip(),
                row["display_name"].strip(),
                row["overview"].strip(),
                row["tailwinds"].strip(),
                row["headwinds"].strip(),
                row["data_as_of"].strip()
            ))
            sector_map[row["name"].strip()] = cursor.lastrowid

    conn.commit()
    return sector_map


def seed_companies(conn: sqlite3.Connection, raw_dir: Path, sector_map: dict[str, int]) -> dict[str, int]:
    """Populates companies table from companies.csv and returns {ticker: company_id} mapping."""
    filepath = raw_dir / "companies.csv"
    if not filepath.exists():
        raise FileNotFoundError(f"Missing {filepath}")

    cursor = conn.cursor()
    company_map = {}
    with open(filepath, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            sector_id = int(row["sector_id"])
            cursor.execute("""
                INSERT INTO companies (ticker, name, sector_id, sub_sector, description, headcount, headcount_change_pct, data_as_of)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                row["ticker"].strip().upper(),
                row["name"].strip(),
                sector_id,
                row["sub_sector"].strip(),
                row["description"].strip(),
                int(row["headcount"]) if row["headcount"] else None,
                float(row["headcount_change_pct"]) if row["headcount_change_pct"] else None,
                row["data_as_of"].strip()
            ))
            company_map[row["ticker"].strip().upper()] = cursor.lastrowid

    conn.commit()
    return company_map


def seed_financials(conn: sqlite3.Connection, raw_dir: Path, company_map: dict[str, int]):
    """Populates financials table from sector-specific CSV files."""
    financial_files = [
        raw_dir / "financials_tech.csv",
        raw_dir / "financials_retail.csv",
        raw_dir / "financials_logistics.csv",
    ]

    cursor = conn.cursor()
    total_records = 0
    for filepath in financial_files:
        if not filepath.exists():
            raise FileNotFoundError(f"Missing {filepath}")
        with open(filepath, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                ticker = row["ticker"].strip().upper()
                if ticker not in company_map:
                    raise ValueError(f"Unknown ticker '{ticker}' in {filepath}")
                company_id = company_map[ticker]

                cursor.execute("""
                    INSERT INTO financials (
                        company_id, fiscal_year, revenue, revenue_growth_pct, net_income,
                        gross_margin_pct, operating_margin_pct, ebitda, free_cash_flow,
                        total_debt, cash, debt_to_ebitda, eps, roe_pct, source, source_url
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    company_id,
                    int(row["fiscal_year"]),
                    float(row["revenue"]) if row["revenue"] else None,
                    float(row["revenue_growth_pct"]) if row["revenue_growth_pct"] else None,
                    float(row["net_income"]) if row["net_income"] else None,
                    float(row["gross_margin_pct"]) if row["gross_margin_pct"] else None,
                    float(row["operating_margin_pct"]) if row["operating_margin_pct"] else None,
                    float(row["ebitda"]) if row["ebitda"] else None,
                    float(row["free_cash_flow"]) if row["free_cash_flow"] else None,
                    float(row["total_debt"]) if row["total_debt"] else None,
                    float(row["cash"]) if row["cash"] else None,
                    float(row["debt_to_ebitda"]) if row["debt_to_ebitda"] else None,
                    float(row["eps"]) if row["eps"] else None,
                    float(row["roe_pct"]) if row["roe_pct"] else None,
                    row["source"].strip() if row.get("source") else None,
                    row["source_url"].strip() if row.get("source_url") else None,
                ))
                total_records += 1

    conn.commit()
    return total_records


def seed_valuations(conn: sqlite3.Connection, raw_dir: Path, company_map: dict[str, int]) -> int:
    """Populates valuations table from valuations.csv."""
    filepath = raw_dir / "valuations.csv"
    if not filepath.exists():
        raise FileNotFoundError(f"Missing {filepath}")

    cursor = conn.cursor()
    count = 0
    with open(filepath, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            ticker = row["ticker"].strip().upper()
            if ticker not in company_map:
                raise ValueError(f"Unknown ticker '{ticker}' in {filepath}")
            company_id = company_map[ticker]

            cursor.execute("""
                INSERT INTO valuations (
                    company_id, as_of_date, market_cap, enterprise_value, pe_ttm,
                    pe_forward, ev_ebitda, price, dividend_yield, source, source_url
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                company_id,
                row["as_of_date"].strip(),
                float(row["market_cap"]) if row["market_cap"] else None,
                float(row["enterprise_value"]) if row["enterprise_value"] else None,
                float(row["pe_ttm"]) if row["pe_ttm"] else None,
                float(row["pe_forward"]) if row["pe_forward"] else None,
                float(row["ev_ebitda"]) if row["ev_ebitda"] else None,
                float(row["price"]) if row["price"] else None,
                float(row["dividend_yield"]) if row["dividend_yield"] else None,
                row["source"].strip() if row.get("source") else None,
                row["source_url"].strip() if row.get("source_url") else None,
            ))
            count += 1

    conn.commit()
    return count


def seed_news_events(conn: sqlite3.Connection, raw_dir: Path, company_map: dict[str, int]) -> int:
    """Populates news_events table from news_events.csv."""
    filepath = raw_dir / "news_events.csv"
    if not filepath.exists():
        raise FileNotFoundError(f"Missing {filepath}")

    cursor = conn.cursor()
    count = 0
    with open(filepath, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            ticker = row["ticker"].strip().upper()
            if ticker not in company_map:
                raise ValueError(f"Unknown ticker '{ticker}' in {filepath}")
            company_id = company_map[ticker]

            cursor.execute("""
                INSERT INTO news_events (
                    company_id, event_date, event_type, headline, summary, source_url, sentiment
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (
                company_id,
                row["event_date"].strip(),
                row["event_type"].strip(),
                row["headline"].strip(),
                row["summary"].strip(),
                row["source_url"].strip() if row.get("source_url") else None,
                row["sentiment"].strip() if row.get("sentiment") else "neutral",
            ))
            count += 1

    conn.commit()
    return count


def verify_database(conn: sqlite3.Connection):
    """Runs data integrity checks and prints summary stats."""
    cursor = conn.cursor()

    # 1. Foreign key integrity check
    cursor.execute("PRAGMA foreign_key_check;")
    fk_errors = cursor.fetchall()
    if fk_errors:
        raise RuntimeError(f"Foreign key integrity check failed: {fk_errors}")

    print("\n" + "=" * 60)
    print(" DATABASE INTEGRITY & SUMMARY VERIFICATION")
    print("=" * 60)

    # 2. Table row counts
    tables = ["sectors", "companies", "financials", "valuations", "news_events"]
    total_rows = 0
    print("\n--- Row Counts per Table ---")
    for tbl in tables:
        cursor.execute(f"SELECT COUNT(*) as count FROM {tbl}")
        cnt = cursor.fetchone()["count"]
        total_rows += cnt
        print(f"  {tbl:<15}: {cnt:>4} rows")
    print(f"  {'TOTAL':<15}: {total_rows:>4} records")

    # 3. Companies per sector
    print("\n--- Companies per Sector ---")
    cursor.execute("""
        SELECT s.display_name, s.name, COUNT(c.id) as company_count
        FROM sectors s
        LEFT JOIN companies c ON c.sector_id = s.id
        GROUP BY s.id
    """)
    for row in cursor.fetchall():
        print(f"  {row['display_name']:<15} ({row['name']}): {row['company_count']} companies")

    # 4. Data coverage per company check
    cursor.execute("""
        SELECT c.ticker, c.name,
               COUNT(DISTINCT f.id) as fin_count,
               COUNT(DISTINCT v.id) as val_count,
               COUNT(DISTINCT n.id) as news_count
        FROM companies c
        LEFT JOIN financials f ON f.company_id = c.id
        LEFT JOIN valuations v ON v.company_id = c.id
        LEFT JOIN news_events n ON n.company_id = c.id
        GROUP BY c.id
    """)
    rows = cursor.fetchall()
    missing_coverage = [r["ticker"] for r in rows if r["fin_count"] < 2 or r["val_count"] < 1 or r["news_count"] < 2]
    if missing_coverage:
        print(f"\nWARNING: Incomplete data coverage for tickers: {missing_coverage}")
    else:
        print("\nAll 21 companies have complete coverage (>=2 financial years, 1 valuation snapshot, >=2 news events).")

    # 5. Dynamic Sector Aggregates demonstration (SQL Verification)
    print("\n--- Dynamically Computed Sector Aggregates (SQL) ---")
    cursor.execute("""
        SELECT 
            s.display_name,
            COUNT(DISTINCT c.id) as total_companies,
            ROUND(AVG(v.pe_ttm), 1) as avg_pe_ttm,
            ROUND(AVG(v.ev_ebitda), 1) as avg_ev_ebitda,
            ROUND(AVG(f.gross_margin_pct), 1) as avg_gross_margin,
            ROUND(AVG(f.operating_margin_pct), 1) as avg_operating_margin,
            ROUND(AVG(f.revenue_growth_pct), 1) as avg_growth_pct
        FROM sectors s
        JOIN companies c ON c.sector_id = s.id
        LEFT JOIN valuations v ON v.company_id = c.id
        LEFT JOIN financials f ON f.company_id = c.id 
            AND f.fiscal_year = (SELECT MAX(f2.fiscal_year) FROM financials f2 WHERE f2.company_id = c.id)
        GROUP BY s.id
    """)
    for r in cursor.fetchall():
        print(f"  [{r['display_name']}] Avg P/E: {r['avg_pe_ttm']}x | Avg EV/EBITDA: {r['avg_ev_ebitda']}x | "
              f"Gross Margin: {r['avg_gross_margin']}% | Operating Margin: {r['avg_operating_margin']}% | YoY Growth: {r['avg_growth_pct']}%")

    # 6. Check hiring signals for data-grounding stress test
    print("\n--- Hiring & Headcount Stress Test Validation ---")
    cursor.execute("""
        SELECT c.ticker, c.name, c.headcount, c.headcount_change_pct, n.headline
        FROM companies c
        JOIN news_events n ON n.company_id = c.id
        WHERE n.event_type = 'hiring'
        LIMIT 3
    """)
    for r in cursor.fetchall():
        print(f"  {r['ticker']} ({r['name']}): Headcount {r['headcount']:,} ({r['headcount_change_pct']:+.1f}%) | Event: {r['headline']}")

    print("=" * 60 + "\n")


def build_database(db_path: Path, raw_dir: Path, rebuild: bool = False):
    """Main build workflow."""
    if rebuild and db_path.exists():
        print(f"Removing existing database at {db_path} (--rebuild requested)...")
        db_path.unlink()

    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = get_connection(db_path)

    try:
        print(f"Initializing database schema at {db_path}...")
        create_schema(conn)

        print("Seeding sectors...")
        sector_map = seed_sectors(conn, raw_dir)

        print("Seeding companies...")
        company_map = seed_companies(conn, raw_dir, sector_map)

        print("Seeding financials...")
        fin_count = seed_financials(conn, raw_dir, company_map)

        print("Seeding valuations...")
        val_count = seed_valuations(conn, raw_dir, company_map)

        print("Seeding news events...")
        news_count = seed_news_events(conn, raw_dir, company_map)

        print(f"Seeding completed: {len(sector_map)} sectors, {len(company_map)} companies, "
              f"{fin_count} financial rows, {val_count} valuations, {news_count} news events.")

        verify_database(conn)
        print(f"Database successfully built and verified at: {db_path}")

    finally:
        conn.close()


def main():
    parser = argparse.ArgumentParser(description="Build and populate the Financial Analyst Agent SQLite database.")
    parser.add_argument("--rebuild", action="store_true", help="Drop and rebuild existing database.")
    parser.add_argument("--db-path", default="data/financial_agent.db", help="Target SQLite database path.")
    parser.add_argument("--raw-dir", default="data/raw", help="Directory containing raw CSV files.")
    args = parser.parse_args()

    project_root = Path(__file__).resolve().parent.parent
    db_path = project_root / args.db_path
    raw_dir = project_root / args.raw_dir

    build_database(db_path=db_path, raw_dir=raw_dir, rebuild=args.rebuild)


if __name__ == "__main__":
    main()
