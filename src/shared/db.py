"""SQLite 连接 + 初始化 schema"""
import sqlite3
from pathlib import Path
from .config import DB_PATH


def get_conn() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    conn = get_conn()
    conn.executescript("""
    CREATE TABLE IF NOT EXISTS domain_top_repos (
        id          INTEGER PRIMARY KEY AUTOINCREMENT,
        week        TEXT NOT NULL,
        domain_id   TEXT NOT NULL,
        category    TEXT NOT NULL,   -- 'historical' | 'recent_year'
        rank        INTEGER,
        repo        TEXT NOT NULL,
        stars       INTEGER,
        created_at  TEXT,
        description TEXT,
        UNIQUE(week, domain_id, category, repo)
    );

    CREATE TABLE IF NOT EXISTS general_top_repos (
        id              INTEGER PRIMARY KEY AUTOINCREMENT,
        week            TEXT NOT NULL,
        category        TEXT NOT NULL,   -- 'recent_year' | 'this_week'
        rank            INTEGER,
        repo            TEXT NOT NULL,
        stars           INTEGER,
        delta_stars     INTEGER DEFAULT 0,
        new_issues      INTEGER DEFAULT 0,
        new_prs         INTEGER DEFAULT 0,
        new_commits     INTEGER DEFAULT 0,
        issue_titles    TEXT DEFAULT '[]',
        pr_titles       TEXT DEFAULT '[]',
        commit_msgs     TEXT DEFAULT '[]',
        analysis_progress  TEXT DEFAULT '',
        analysis_pain      TEXT DEFAULT '',
        analysis_focus     TEXT DEFAULT '',
        analysis_verdict   TEXT DEFAULT '',
        description     TEXT,
        language        TEXT,
        created_at      TEXT,
        UNIQUE(week, category, repo)
    );

    CREATE TABLE IF NOT EXISTS domain_snapshots (
        id          INTEGER PRIMARY KEY AUTOINCREMENT,
        week        TEXT NOT NULL,
        domain_id   TEXT NOT NULL,
        supply      INTEGER,
        demand      INTEGER,
        d1          INTEGER,
        d1_track    TEXT,
        d2          INTEGER,
        d3          INTEGER,
        d4          INTEGER,
        created_at  TEXT DEFAULT (datetime('now')),
        UNIQUE(week, domain_id)
    );

    CREATE TABLE IF NOT EXISTS project_stars (
        id          INTEGER PRIMARY KEY AUTOINCREMENT,
        week        TEXT NOT NULL,
        repo        TEXT NOT NULL,
        domain_id   TEXT NOT NULL,
        stars       INTEGER,
        delta       INTEGER DEFAULT 0,
        UNIQUE(week, repo)
    );

    CREATE TABLE IF NOT EXISTS pypi_weekly (
        id          INTEGER PRIMARY KEY AUTOINCREMENT,
        week        TEXT NOT NULL,
        package     TEXT NOT NULL,
        downloads   INTEGER,
        UNIQUE(week, package)
    );

    CREATE TABLE IF NOT EXISTS project_registry (
        id          INTEGER PRIMARY KEY AUTOINCREMENT,
        ar_id       TEXT NOT NULL UNIQUE,   -- 'AR-001'
        repo        TEXT NOT NULL UNIQUE,   -- 'owner/name'
        first_seen  TEXT NOT NULL,          -- week string e.g. '2026-W19'
        domain_ids  TEXT NOT NULL DEFAULT '[]',  -- JSON array of domain_id strings
        stars       INTEGER DEFAULT 0,
        delta_stars INTEGER DEFAULT 0,      -- vs last week
        description TEXT,
        language    TEXT,
        homepage    TEXT,
        gh_created  TEXT,                   -- GitHub repo creation date
        updated_at  TEXT DEFAULT (datetime('now'))
    );

    CREATE TABLE IF NOT EXISTS run_log (
        id          INTEGER PRIMARY KEY AUTOINCREMENT,
        week        TEXT,
        started_at  TEXT,
        finished_at TEXT,
        status      TEXT,
        notes       TEXT
    );
    """)
    conn.commit()
    conn.close()
