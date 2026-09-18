"""
database.py
All SQLite work lives here so the route code in app.py stays readable.

Two tables:
    users    - the employee and guard accounts that can log in
    visitors - one row per invitation, from invite to gate entry
"""

import sqlite3
from datetime import datetime

from flask import g
from werkzeug.security import generate_password_hash

from config import Config

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    username      TEXT    NOT NULL UNIQUE,
    password_hash TEXT    NOT NULL,
    full_name     TEXT    NOT NULL,
    role          TEXT    NOT NULL CHECK (role IN ('employee', 'guard')),
    created_at    TEXT    NOT NULL
);

CREATE TABLE IF NOT EXISTS visitors (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    token          TEXT    NOT NULL UNIQUE,
    email          TEXT    NOT NULL,
    name           TEXT,
    phone          TEXT,
    company        TEXT,
    purpose        TEXT,
    person_to_meet TEXT    NOT NULL,
    unit           TEXT,
    visit_datetime TEXT    NOT NULL,
    status         TEXT    NOT NULL DEFAULT 'INVITED',
    invited_by     INTEGER NOT NULL,
    created_at     TEXT    NOT NULL,
    registered_at  TEXT,
    entry_time     TEXT,
    verified_by    TEXT,
    remarks        TEXT,
    FOREIGN KEY (invited_by) REFERENCES users (id)
);

CREATE INDEX IF NOT EXISTS idx_visitors_token  ON visitors (token);
CREATE INDEX IF NOT EXISTS idx_visitors_status ON visitors (status);
"""

# The four states a visitor record can be in.
STATUS_INVITED = "INVITED"      # employee sent the invitation, visitor has not filled the form
STATUS_REGISTERED = "REGISTERED"  # visitor filled the form, QR pass issued
STATUS_ENTERED = "ENTERED"      # guard scanned the QR and allowed entry
STATUS_REJECTED = "REJECTED"    # guard refused entry


def get_db():
    """Return a per-request database connection."""
    if "db" not in g:
        g.db = sqlite3.connect(Config.DB_PATH, detect_types=sqlite3.PARSE_DECLTYPES)
        g.db.row_factory = sqlite3.Row
        g.db.execute("PRAGMA foreign_keys = ON")
    return g.db


def close_db(exception=None):
    db = g.pop("db", None)
    if db is not None:
        db.close()


def now():
    """Timestamp used everywhere, stored as plain text for easy reading."""
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def init_db(app):
    """Create the tables (if missing) and seed the two default accounts."""
    with app.app_context():
        db = get_db()
        db.executescript(SCHEMA)
        db.commit()
        _seed_user(db, Config.EMPLOYEE_USERNAME, Config.EMPLOYEE_PASSWORD,
                   Config.EMPLOYEE_NAME, "employee")
        _seed_user(db, Config.GUARD_USERNAME, Config.GUARD_PASSWORD,
                   Config.GUARD_NAME, "guard")
        db.commit()
        close_db()


def _seed_user(db, username, password, full_name, role):
    existing = db.execute("SELECT id FROM users WHERE username = ?", (username,)).fetchone()
    if existing:
        return
    db.execute(
        "INSERT INTO users (username, password_hash, full_name, role, created_at) "
        "VALUES (?, ?, ?, ?, ?)",
        (username, generate_password_hash(password), full_name, role, now()),
    )


# ----------------------------------------------------------------------
# Query helpers used by the routes
# ----------------------------------------------------------------------

def find_user(username):
    return get_db().execute(
        "SELECT * FROM users WHERE username = ?", (username,)
    ).fetchone()


def find_visitor_by_token(token):
    return get_db().execute(
        "SELECT * FROM visitors WHERE token = ?", (token,)
    ).fetchone()


def find_visitor_by_id(visitor_id):
    return get_db().execute(
        "SELECT * FROM visitors WHERE id = ?", (visitor_id,)
    ).fetchone()


def list_visitors(status=None, search=None, limit=200):
    sql = (
        "SELECT v.*, u.full_name AS host_name FROM visitors v "
        "JOIN users u ON u.id = v.invited_by WHERE 1 = 1"
    )
    params = []
    if status:
        sql += " AND v.status = ?"
        params.append(status)
    if search:
        sql += " AND (v.name LIKE ? OR v.email LIKE ? OR v.company LIKE ? OR v.phone LIKE ?)"
        like = f"%{search}%"
        params += [like, like, like, like]
    sql += " ORDER BY v.id DESC LIMIT ?"
    params.append(limit)
    return get_db().execute(sql, params).fetchall()


def status_counts():
    rows = get_db().execute(
        "SELECT status, COUNT(*) AS total FROM visitors GROUP BY status"
    ).fetchall()
    counts = {
        STATUS_INVITED: 0,
        STATUS_REGISTERED: 0,
        STATUS_ENTERED: 0,
        STATUS_REJECTED: 0,
    }
    for row in rows:
        counts[row["status"]] = row["total"]
    counts["TOTAL"] = sum(counts.values())
    return counts


def expected_today():
    """Visitors holding a valid pass for today — the guard's working list."""
    today = datetime.now().strftime("%Y-%m-%d")
    return get_db().execute(
        "SELECT v.*, u.full_name AS host_name FROM visitors v "
        "JOIN users u ON u.id = v.invited_by "
        "WHERE v.status IN (?, ?) AND date(v.visit_datetime) = ? "
        "ORDER BY v.visit_datetime ASC",
        (STATUS_REGISTERED, STATUS_ENTERED, today),
    ).fetchall()
