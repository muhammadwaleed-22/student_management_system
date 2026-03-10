from flask import Flask
import sqlite3
from werkzeug.security import generate_password_hash

app = Flask(__name__)
app.secret_key = "supersecretkey"


def _resequence_ids(conn, table, child_refs=None):
    cursor = conn.cursor()
    cursor.execute(f"SELECT id FROM {table} ORDER BY id ASC")
    ids = [row[0] for row in cursor.fetchall()]

    mapping = {old_id: new_id for new_id, old_id in enumerate(ids, start=1)}
    changed = {old_id: new_id for old_id, new_id in mapping.items() if old_id != new_id}
    if not changed:
        return

    if child_refs:
        for child_table, child_col in child_refs:
            case_sql = " ".join([f"WHEN {old_id} THEN {new_id}" for old_id, new_id in changed.items()])
            in_sql = ", ".join([str(old_id) for old_id in changed.keys()])
            cursor.execute(
                f"""
                UPDATE {child_table}
                SET {child_col} = CASE {child_col}
                    {case_sql}
                    ELSE {child_col}
                END
                WHERE {child_col} IN ({in_sql})
                """
            )

    cursor.execute(f"SELECT COALESCE(MAX(id), 0) FROM {table}")
    max_id = cursor.fetchone()[0]
    offset = max_id + 1000

    for old_id in changed.keys():
        cursor.execute(f"UPDATE {table} SET id=? WHERE id=?", (old_id + offset, old_id))

    for old_id, new_id in changed.items():
        cursor.execute(f"UPDATE {table} SET id=? WHERE id=?", (new_id, old_id + offset))

    cursor.execute(
        "UPDATE sqlite_sequence SET seq=(SELECT COALESCE(MAX(id), 0) FROM {0}) WHERE name=?".format(table),
        (table,),
    )


def resequence_all_ids(conn):
    _resequence_ids(conn, "users", child_refs=[("enrollments", "user_id")])
    _resequence_ids(conn, "courses", child_refs=[("enrollments", "course_id")])
    _resequence_ids(conn, "enrollments")

# -------------------- Initialize Database --------------------
def init_db():
    conn = sqlite3.connect("database.db")
    cursor = conn.cursor()

    # Users
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT UNIQUE,
        password TEXT,
        role TEXT,
        is_blocked INTEGER DEFAULT 0
    )
    """)

    cursor.execute("PRAGMA table_info(users)")
    user_columns = [col[1] for col in cursor.fetchall()]
    if "is_blocked" not in user_columns:
        cursor.execute("ALTER TABLE users ADD COLUMN is_blocked INTEGER DEFAULT 0")

    # Courses
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS courses (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT,
        fee REAL,
        duration TEXT,
        image TEXT
    )
    """)

    # Enrollments
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS enrollments (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        course_id INTEGER,
        UNIQUE(user_id, course_id)
    )
    """)

    # Default Admin
    admin_password = generate_password_hash("admin123")
    cursor.execute("""
        INSERT OR IGNORE INTO users (username, password, role)
        VALUES (?, ?, ?)
    """, ("admin", admin_password, "admin"))

    conn.commit()
    conn.close()

init_db()

from routes import *  # noqa: F401,F403

# -------------------- Run --------------------
if __name__ == "__main__":
    app.run(debug=True)
