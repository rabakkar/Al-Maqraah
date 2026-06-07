from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator

from werkzeug.security import check_password_hash, generate_password_hash

from core.scoring import (
    DEFAULT_PLACEMENT_THRESHOLDS,
    LEVEL_KEYS,
    RULE_KEYS,
    STUDENT_LEVEL_LABELS,
    UNCLASSIFIED_LEVEL,
    default_scoring_settings_for_level,
    normalize_level_key,
    normalize_scoring_settings,
    normalize_student_level_key,
)


BASE_DIR = Path(__file__).resolve().parent
DB_PATH = BASE_DIR / "data" / "maqraah.sqlite3"


@contextmanager
def db_connection() -> Iterator[sqlite3.Connection]:
    DB_PATH.parent.mkdir(exist_ok=True)
    connection = sqlite3.connect(DB_PATH)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    try:
        yield connection
        connection.commit()
    finally:
        connection.close()


def row_to_dict(row: sqlite3.Row | None) -> dict[str, Any] | None:
    if row is None:
        return None
    return dict(row)


def init_db() -> None:
    with db_connection() as db:
        db.executescript(
            """
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                full_name TEXT NOT NULL,
                email TEXT NOT NULL UNIQUE,
                password_hash TEXT NOT NULL,
                role TEXT NOT NULL CHECK (role IN ('student', 'teacher')),
                is_admin INTEGER NOT NULL DEFAULT 0,
                student_level TEXT NOT NULL DEFAULT 'unclassified',
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS assignments (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                teacher_id INTEGER,
                student_id INTEGER,
                student_name TEXT NOT NULL,
                surah_number INTEGER NOT NULL,
                surah_name TEXT NOT NULL,
                ayah_from INTEGER NOT NULL,
                ayah_to INTEGER NOT NULL,
                ayah_text TEXT NOT NULL DEFAULT '',
                stats_json TEXT NOT NULL DEFAULT '{}',
                status TEXT NOT NULL DEFAULT 'pending',
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (teacher_id) REFERENCES users(id) ON DELETE SET NULL,
                FOREIGN KEY (student_id) REFERENCES users(id) ON DELETE SET NULL
            );

            CREATE TABLE IF NOT EXISTS recitations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                student_id INTEGER,
                assignment_id INTEGER,
                audio_file TEXT NOT NULL,
                surah_number INTEGER NOT NULL,
                surah_name TEXT NOT NULL,
                ayah_from INTEGER NOT NULL,
                ayah_to INTEGER NOT NULL,
                score INTEGER NOT NULL DEFAULT 0,
                summary_json TEXT NOT NULL DEFAULT '{}',
                phonetic_script_json TEXT NOT NULL DEFAULT '{}',
                engine_note TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (student_id) REFERENCES users(id) ON DELETE SET NULL,
                FOREIGN KEY (assignment_id) REFERENCES assignments(id) ON DELETE SET NULL
            );

            CREATE TABLE IF NOT EXISTS recitation_errors (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                recitation_id INTEGER NOT NULL,
                case_id INTEGER,
                rule TEXT NOT NULL DEFAULT '',
                rule_label TEXT NOT NULL DEFAULT '',
                status TEXT NOT NULL DEFAULT '',
                status_label TEXT NOT NULL DEFAULT '',
                ayah INTEGER,
                source_text TEXT NOT NULL DEFAULT '',
                snippet TEXT NOT NULL DEFAULT '',
                next_letter TEXT NOT NULL DEFAULT '',
                reason TEXT NOT NULL DEFAULT '',
                phonetic_window TEXT NOT NULL DEFAULT '',
                noon_visible INTEGER,
                meem_visible INTEGER,
                raw_json TEXT NOT NULL DEFAULT '{}',
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (recitation_id) REFERENCES recitations(id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS scoring_level_settings (
                level TEXT PRIMARY KEY,
                izhar_enabled INTEGER NOT NULL DEFAULT 1,
                izhar_weight REAL NOT NULL DEFAULT 1,
                idgham_enabled INTEGER NOT NULL DEFAULT 1,
                idgham_weight REAL NOT NULL DEFAULT 1,
                iqlab_enabled INTEGER NOT NULL DEFAULT 1,
                iqlab_weight REAL NOT NULL DEFAULT 1,
                ikhfa_enabled INTEGER NOT NULL DEFAULT 1,
                ikhfa_weight REAL NOT NULL DEFAULT 1,
                pronunciation_weight REAL NOT NULL DEFAULT 1,
                min_pronunciation_score INTEGER NOT NULL DEFAULT 0,
                placement_threshold INTEGER NOT NULL DEFAULT 0,
                allowed_missing_words INTEGER NOT NULL DEFAULT 1,
                allowed_extra_words INTEGER NOT NULL DEFAULT 2,
                allowed_different_words INTEGER NOT NULL DEFAULT 2,
                missing_word_penalty REAL NOT NULL DEFAULT 0.10,
                extra_word_penalty REAL NOT NULL DEFAULT 0.05,
                different_word_penalty REAL NOT NULL DEFAULT 0.08,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );

            CREATE UNIQUE INDEX IF NOT EXISTS ux_recitations_student_assignment
            ON recitations(student_id, assignment_id)
            WHERE student_id IS NOT NULL AND assignment_id IS NOT NULL;
            """
        )
        _ensure_column(db, "users", "is_admin", "INTEGER NOT NULL DEFAULT 0")
        _ensure_column(db, "users", "student_level", "TEXT NOT NULL DEFAULT 'unclassified'")
        _ensure_scoring_penalty_columns(db, "scoring_level_settings")
        _ensure_scoring_threshold_columns(db)
        _clear_legacy_min_pronunciation_score(db)
        _ensure_default_admin(db)
        _ensure_default_level_scoring_settings(db)
        _drop_legacy_scoring_settings(db)


def _ensure_column(db: sqlite3.Connection, table: str, column: str, definition: str) -> bool:
    columns = [row["name"] for row in db.execute(f"PRAGMA table_info({table})").fetchall()]
    if column not in columns:
        db.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")
        return True
    return False


def _ensure_scoring_penalty_columns(db: sqlite3.Connection, table: str) -> None:
    _ensure_column(db, table, "missing_word_penalty", "REAL NOT NULL DEFAULT 0.10")
    _ensure_column(db, table, "extra_word_penalty", "REAL NOT NULL DEFAULT 0.05")
    _ensure_column(db, table, "different_word_penalty", "REAL NOT NULL DEFAULT 0.08")
    for column in ("missing_word_penalty", "extra_word_penalty", "different_word_penalty"):
        db.execute(f"UPDATE {table} SET {column} = ABS({column}) WHERE {column} < 0")


def _ensure_scoring_threshold_columns(db: sqlite3.Connection) -> None:
    added = _ensure_column(
        db,
        "scoring_level_settings",
        "placement_threshold",
        "INTEGER NOT NULL DEFAULT 0",
    )
    if added:
        for level, threshold in DEFAULT_PLACEMENT_THRESHOLDS.items():
            db.execute(
                "UPDATE scoring_level_settings SET placement_threshold = ? WHERE level = ?",
                (threshold, level),
            )


def _clear_legacy_min_pronunciation_score(db: sqlite3.Connection) -> None:
    columns = [row["name"] for row in db.execute("PRAGMA table_info(scoring_level_settings)").fetchall()]
    if "min_pronunciation_score" in columns:
        db.execute("UPDATE scoring_level_settings SET min_pronunciation_score = 0")


def _ensure_default_admin(db: sqlite3.Connection) -> None:
    existing_admin = db.execute(
        "SELECT id FROM users WHERE role = 'teacher' AND is_admin = 1 LIMIT 1"
    ).fetchone()
    if existing_admin is not None:
        return

    existing_user = db.execute(
        "SELECT id FROM users WHERE email = ?",
        ("admin@maqraah.local",),
    ).fetchone()
    if existing_user is not None:
        db.execute(
            "UPDATE users SET role = 'teacher', is_admin = 1 WHERE id = ?",
            (existing_user["id"],),
        )
        return

    db.execute(
        """
        INSERT INTO users (full_name, email, password_hash, role, is_admin)
        VALUES (?, ?, ?, 'teacher', 1)
        """,
        (
            "مدير المقرأة",
            "admin@maqraah.local",
            generate_password_hash("Admin@12345"),
        ),
    )


def _ensure_default_level_scoring_settings(db: sqlite3.Connection) -> None:
    for level in LEVEL_KEYS:
        existing = db.execute(
            "SELECT level FROM scoring_level_settings WHERE level = ?",
            (level,),
        ).fetchone()
        if existing is not None:
            continue
        settings = default_scoring_settings_for_level(level)
        db.execute(
            """
            INSERT INTO scoring_level_settings (
                level,
                izhar_enabled, izhar_weight,
                idgham_enabled, idgham_weight,
                iqlab_enabled, iqlab_weight,
                ikhfa_enabled, ikhfa_weight,
                min_pronunciation_score, placement_threshold,
                missing_word_penalty, extra_word_penalty, different_word_penalty
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            _settings_db_values(level, settings),
        )


def _drop_legacy_scoring_settings(db: sqlite3.Connection) -> None:
    db.execute("DROP TABLE IF EXISTS scoring_settings")


def _public_user(row: sqlite3.Row) -> dict[str, Any]:
    student_level = normalize_student_level_key(_row_value(row, "student_level", UNCLASSIFIED_LEVEL))
    return {
        "id": row["id"],
        "full_name": row["full_name"],
        "email": row["email"],
        "role": row["role"],
        "is_admin": bool(row["is_admin"]),
        "student_level": student_level,
        "student_level_label": STUDENT_LEVEL_LABELS[student_level],
        "created_at": row["created_at"],
    }


def _row_value(row: sqlite3.Row, key: str, default: Any = None) -> Any:
    return row[key] if key in row.keys() else default


def create_user(
    full_name: str,
    email: str,
    password: str,
    role: str,
    is_admin: bool = False,
    student_level: str = UNCLASSIFIED_LEVEL,
) -> dict[str, Any]:
    if role not in {"student", "teacher"}:
        raise ValueError("نوع الحساب غير صحيح.")

    normalized_level = normalize_student_level_key(student_level) if role == "student" else "beginner"
    with db_connection() as db:
        try:
            cursor = db.execute(
                """
                INSERT INTO users (full_name, email, password_hash, role, is_admin, student_level)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    full_name.strip(),
                    email.strip().lower(),
                    generate_password_hash(password),
                    role,
                    1 if is_admin else 0,
                    normalized_level,
                ),
            )
        except sqlite3.IntegrityError as exc:
            raise ValueError("البريد الإلكتروني مستخدم مسبقًا.") from exc

        user_id = int(cursor.lastrowid)
        row = db.execute(
            """
            SELECT id, full_name, email, role, is_admin, student_level, created_at
            FROM users
            WHERE id = ?
            """,
            (user_id,),
        ).fetchone()
        return _public_user(row) if row else {}


def create_teacher(full_name: str, email: str, password: str, is_admin: bool = False) -> dict[str, Any]:
    return create_user(full_name, email, password, "teacher", is_admin=is_admin)


def authenticate_user(email: str, password: str, role: str) -> dict[str, Any] | None:
    with db_connection() as db:
        row = db.execute(
            "SELECT * FROM users WHERE email = ? AND role = ?",
            (email.strip().lower(), role),
        ).fetchone()

    if row is None or not check_password_hash(row["password_hash"], password):
        return None

    return _public_user(row)


def get_user(user_id: int) -> dict[str, Any] | None:
    with db_connection() as db:
        row = db.execute(
            """
            SELECT id, full_name, email, role, is_admin, student_level, created_at
            FROM users
            WHERE id = ?
            """,
            (user_id,),
        ).fetchone()
    return _public_user(row) if row else None


def update_student_level(user_id: int, student_level: str) -> dict[str, Any] | None:
    normalized_level = normalize_student_level_key(student_level)
    if normalized_level == UNCLASSIFIED_LEVEL:
        raise ValueError("لا يمكن حفظ مستوى غير مصنف بعد التصنيف.")

    with db_connection() as db:
        db.execute(
            """
            UPDATE users
            SET student_level = ?
            WHERE id = ? AND role = 'student'
            """,
            (normalized_level, user_id),
        )
    return get_user(user_id)


def list_students() -> list[dict[str, Any]]:
    with db_connection() as db:
        rows = db.execute(
            """
            SELECT id, full_name, email, student_level, created_at
            FROM users
            WHERE role = 'student'
            ORDER BY full_name
            """
        ).fetchall()
    students = []
    for row in rows:
        student = dict(row)
        level = normalize_student_level_key(student.get("student_level"))
        student["student_level"] = level
        student["student_level_label"] = STUDENT_LEVEL_LABELS[level]
        students.append(student)
    return students


def get_teacher_dashboard_data() -> dict[str, Any]:
    with db_connection() as db:
        stats_row = db.execute(
            """
            SELECT
                (SELECT COUNT(*) FROM users WHERE role = 'student') AS students_count,
                (SELECT COUNT(*) FROM recitations) AS recitations_count,
                (
                    SELECT COUNT(*)
                    FROM recitations
                    WHERE created_at >= datetime('now', '-7 days')
                ) AS weekly_recitations_count,
                (SELECT COALESCE(ROUND(AVG(score)), 0) FROM recitations) AS average_score,
                (
                    SELECT COUNT(*)
                    FROM assignments
                    WHERE status = 'pending'
                ) AS pending_assignments_count
            """
        ).fetchone()

        student_rows = db.execute(
            """
            WITH latest AS (
                SELECT student_id, MAX(id) AS latest_recitation_id
                FROM recitations
                WHERE student_id IS NOT NULL
                GROUP BY student_id
            )
            SELECT
                u.id,
                u.full_name,
                u.email,
                u.student_level,
                u.created_at,
                r.id AS recitation_id,
                r.surah_name,
                r.ayah_from,
                r.ayah_to,
                r.score,
                r.created_at AS recitation_created_at,
                (
                    SELECT COUNT(*)
                    FROM recitations rr
                    WHERE rr.student_id = u.id
                ) AS recitations_count,
                COALESCE((
                    SELECT CASE
                        WHEN aa.id IS NULL THEN 0
                        WHEN EXISTS (
                            SELECT 1
                            FROM recitations rr_assignment
                            WHERE rr_assignment.assignment_id = aa.id
                              AND rr_assignment.student_id = u.id
                        ) THEN 0
                        ELSE 1
                    END
                    FROM (
                        SELECT id
                        FROM assignments
                        WHERE status = 'pending'
                          AND student_id IS NULL
                        ORDER BY created_at DESC, id DESC
                        LIMIT 1
                    ) aa
                ), 0) AS pending_assignments_count,
                (
                    SELECT COUNT(*)
                    FROM recitation_errors ee
                    WHERE ee.recitation_id = r.id
                      AND ee.status IN ('needs_review', 'unmatched')
                ) AS issues_count
            FROM users u
            LEFT JOIN latest l ON l.student_id = u.id
            LEFT JOIN recitations r ON r.id = l.latest_recitation_id
            WHERE u.role = 'student'
            ORDER BY r.created_at DESC, u.full_name
            """
        ).fetchall()

    stats = dict(stats_row or {})
    stats["average_score"] = int(stats.get("average_score") or 0)
    students = []
    for row in student_rows:
        student = dict(row)
        level = normalize_student_level_key(student.get("student_level"))
        student["student_level"] = level
        student["student_level_label"] = STUDENT_LEVEL_LABELS[level]
        students.append(student)
    return {"stats": stats, "students": students}


def list_teachers() -> list[dict[str, Any]]:
    with db_connection() as db:
        rows = db.execute(
            """
            SELECT id, full_name, email, role, is_admin, student_level, created_at
            FROM users
            WHERE role = 'teacher'
            ORDER BY is_admin DESC, full_name
            """
        ).fetchall()
    return [_public_user(row) for row in rows]


def get_scoring_settings(level: str | None = None) -> dict[str, Any]:
    level_key = normalize_level_key(level)
    with db_connection() as db:
        row = db.execute(
            """
            SELECT
                level,
                izhar_enabled,
                izhar_weight, idgham_weight, iqlab_weight, ikhfa_weight,
                idgham_enabled, iqlab_enabled, ikhfa_enabled,
                min_pronunciation_score, placement_threshold,
                missing_word_penalty, extra_word_penalty, different_word_penalty
            FROM scoring_level_settings
            WHERE level = ?
            """,
            (level_key,),
        ).fetchone()

    payload = dict(row) if row else default_scoring_settings_for_level(level_key)
    return normalize_scoring_settings(payload, level_key)


def list_scoring_level_settings() -> dict[str, dict[str, Any]]:
    return {level: get_scoring_settings(level) for level in LEVEL_KEYS}


def update_scoring_settings(payload: dict[str, Any]) -> dict[str, Any]:
    if isinstance(payload.get("levels"), dict):
        return update_scoring_level_settings(payload["levels"])

    level = normalize_level_key(payload.get("level"))
    settings = normalize_scoring_settings(payload, level)
    _validate_enabled_rules(settings)
    _save_level_scoring_settings(level, settings)
    return get_scoring_settings(level)


def update_scoring_level_settings(levels_payload: dict[str, Any]) -> dict[str, dict[str, Any]]:
    for level in LEVEL_KEYS:
        level_payload = levels_payload.get(level)
        if not isinstance(level_payload, dict):
            continue
        settings = normalize_scoring_settings(level_payload, level)
        _validate_enabled_rules(settings)
        _save_level_scoring_settings(level, settings)
    return list_scoring_level_settings()


def _save_level_scoring_settings(level: str, settings: dict[str, Any]) -> None:
    with db_connection() as db:
        db.execute(
            """
            INSERT INTO scoring_level_settings (
                level,
                izhar_enabled, izhar_weight,
                idgham_enabled, idgham_weight,
                iqlab_enabled, iqlab_weight,
                ikhfa_enabled, ikhfa_weight,
                min_pronunciation_score, placement_threshold,
                missing_word_penalty, extra_word_penalty, different_word_penalty
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(level) DO UPDATE SET
                izhar_enabled = excluded.izhar_enabled,
                izhar_weight = excluded.izhar_weight,
                idgham_enabled = excluded.idgham_enabled,
                idgham_weight = excluded.idgham_weight,
                iqlab_enabled = excluded.iqlab_enabled,
                iqlab_weight = excluded.iqlab_weight,
                ikhfa_enabled = excluded.ikhfa_enabled,
                ikhfa_weight = excluded.ikhfa_weight,
                min_pronunciation_score = excluded.min_pronunciation_score,
                placement_threshold = excluded.placement_threshold,
                missing_word_penalty = excluded.missing_word_penalty,
                extra_word_penalty = excluded.extra_word_penalty,
                different_word_penalty = excluded.different_word_penalty,
                updated_at = CURRENT_TIMESTAMP
            """,
            _settings_db_values(level, settings),
        )


def _settings_db_values(level: str, settings: dict[str, Any]) -> tuple[Any, ...]:
    return (
        level,
        int(settings["izhar_enabled"]),
        float(settings["izhar_weight"]),
        int(settings["idgham_enabled"]),
        float(settings["idgham_weight"]),
        int(settings["iqlab_enabled"]),
        float(settings["iqlab_weight"]),
        int(settings["ikhfa_enabled"]),
        float(settings["ikhfa_weight"]),
        int(settings.get("min_pronunciation_score", 0)),
        int(settings["placement_threshold"]),
        float(settings["missing_word_penalty"]),
        float(settings["extra_word_penalty"]),
        float(settings["different_word_penalty"]),
    )


def _validate_enabled_rules(settings: dict[str, Any]) -> None:
    if not any(int(settings.get(f"{rule}_enabled") or 0) == 1 for rule in RULE_KEYS):
        raise ValueError("اختر حكمًا واحدًا على الأقل داخل كل مستوى.")


def create_assignment(payload: dict[str, Any]) -> dict[str, Any]:
    with db_connection() as db:
        cursor = db.execute(
            """
            INSERT INTO assignments (
                teacher_id, student_id, student_name, surah_number, surah_name,
                ayah_from, ayah_to, ayah_text, stats_json
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                payload.get("teacher_id"),
                payload.get("student_id"),
                payload["student_name"],
                payload["surah_number"],
                payload["surah_name"],
                payload["ayah_from"],
                payload["ayah_to"],
                payload.get("ayah_text", ""),
                json.dumps(payload.get("stats", {}), ensure_ascii=False),
            ),
        )
        assignment_id = int(cursor.lastrowid)
        return get_assignment_by_id(assignment_id, db)


def get_assignment_by_id(assignment_id: int, db: sqlite3.Connection | None = None) -> dict[str, Any]:
    owns_connection = db is None
    if db is None:
        db = sqlite3.connect(DB_PATH)
        db.row_factory = sqlite3.Row

    try:
        row = db.execute(
            "SELECT * FROM assignments WHERE id = ?",
            (assignment_id,),
        ).fetchone()
        assignment = row_to_dict(row) or {}
        if assignment:
            assignment["stats"] = json.loads(assignment.pop("stats_json") or "{}")
        return assignment
    finally:
        if owns_connection:
            db.close()


def list_assignments(limit: int = 20) -> list[dict[str, Any]]:
    with db_connection() as db:
        rows = db.execute(
            """
            SELECT * FROM assignments
            ORDER BY created_at DESC, id DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()

    assignments: list[dict[str, Any]] = []
    for row in rows:
        item = dict(row)
        item["stats"] = json.loads(item.pop("stats_json") or "{}")
        assignments.append(item)
    return assignments


def _assignment_row_to_dict(row: sqlite3.Row | None) -> dict[str, Any] | None:
    if row is None:
        return None
    item = dict(row)
    item["stats"] = json.loads(item.pop("stats_json") or "{}")
    item["submitted"] = bool(item.pop("submitted", 0))
    item.setdefault("submitted_recitation_id", None)
    item.setdefault("submitted_at", None)
    return item


def get_current_assignment(student_id: int | None) -> dict[str, Any] | None:
    with db_connection() as db:
        if student_id is None:
            row = db.execute(
                """
                SELECT
                    *,
                    NULL AS submitted_recitation_id,
                    NULL AS submitted_at,
                    0 AS submitted
                FROM assignments
                WHERE status = 'pending'
                  AND student_id IS NULL
                ORDER BY created_at DESC, id DESC
                LIMIT 1
                """
            ).fetchone()
        else:
            row = db.execute(
                """
                SELECT
                    a.*,
                    r.id AS submitted_recitation_id,
                    r.created_at AS submitted_at,
                    1 AS submitted
                FROM recitations r
                JOIN assignments a ON a.id = r.assignment_id
                WHERE r.student_id = ?
                  AND r.assignment_id IS NOT NULL
                ORDER BY r.created_at DESC, r.id DESC
                LIMIT 1
                """,
                (student_id,),
            ).fetchone()

            if row is None:
                row = db.execute(
                    """
                    SELECT
                        *,
                        NULL AS submitted_recitation_id,
                        NULL AS submitted_at,
                        0 AS submitted
                    FROM assignments
                    WHERE status = 'pending'
                      AND student_id IS NULL
                    ORDER BY created_at DESC, id DESC
                    LIMIT 1
                    """
                ).fetchone()

    return _assignment_row_to_dict(row)


def has_student_submitted_assignment(student_id: int, assignment_id: int) -> bool:
    with db_connection() as db:
        row = db.execute(
            """
            SELECT 1
            FROM recitations
            WHERE student_id = ? AND assignment_id = ?
            LIMIT 1
            """,
            (student_id, assignment_id),
        ).fetchone()
    return row is not None


def save_recitation(payload: dict[str, Any], evaluations: list[dict[str, Any]]) -> dict[str, Any]:
    with db_connection() as db:
        try:
            cursor = db.execute(
                """
                INSERT INTO recitations (
                    student_id, assignment_id, audio_file, surah_number, surah_name,
                    ayah_from, ayah_to, score, summary_json, phonetic_script_json, engine_note
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    payload.get("student_id"),
                    payload.get("assignment_id"),
                    payload["audio_file"],
                    payload["surah_number"],
                    payload["surah_name"],
                    payload["ayah_from"],
                    payload["ayah_to"],
                    payload.get("score", 0),
                    json.dumps(payload.get("summary", {}), ensure_ascii=False),
                    json.dumps(payload.get("phonetic_script", {}), ensure_ascii=False),
                    payload.get("engine_note", ""),
                ),
            )
        except sqlite3.IntegrityError as exc:
            raise ValueError("تم تسليم هذا التكليف مسبقًا، ولا يمكن إرسال تسجيل آخر.") from exc
        recitation_id = int(cursor.lastrowid)

        db.executemany(
            """
            INSERT INTO recitation_errors (
                recitation_id, case_id, rule, rule_label, status, status_label, ayah,
                source_text, snippet, next_letter, reason, phonetic_window,
                noon_visible, meem_visible, raw_json
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                (
                    recitation_id,
                    item.get("case_id"),
                    item.get("rule", ""),
                    item.get("rule_label", ""),
                    item.get("status", ""),
                    item.get("status_label", ""),
                    item.get("ayah"),
                    item.get("source_text", ""),
                    item.get("snippet", ""),
                    item.get("next_letter", ""),
                    item.get("reason", ""),
                    item.get("phonetic_window", "") or item.get("phonetic_window_letters", ""),
                    _bool_to_int(item.get("noon_visible")),
                    _bool_to_int(item.get("meem_visible")),
                    json.dumps(item, ensure_ascii=False),
                )
                for item in evaluations
            ],
        )

        return get_recitation_by_id(recitation_id, db)


def get_recitation_by_id(recitation_id: int, db: sqlite3.Connection | None = None) -> dict[str, Any]:
    owns_connection = db is None
    if db is None:
        db = sqlite3.connect(DB_PATH)
        db.row_factory = sqlite3.Row

    try:
        row = db.execute("SELECT * FROM recitations WHERE id = ?", (recitation_id,)).fetchone()
        if row is None:
            return {}

        recitation = dict(row)
        recitation["summary"] = json.loads(recitation.pop("summary_json") or "{}")
        recitation["phonetic_script"] = json.loads(recitation.pop("phonetic_script_json") or "{}")
        errors = db.execute(
            """
            SELECT *
            FROM recitation_errors
            WHERE recitation_id = ?
            ORDER BY id
            """,
            (recitation_id,),
        ).fetchall()
        recitation["errors"] = [_error_row_to_dict(item) for item in errors]
        return recitation
    finally:
        if owns_connection:
            db.close()


def get_latest_recitation(student_id: int | None = None) -> dict[str, Any] | None:
    with db_connection() as db:
        if student_id is not None:
            row = db.execute(
                """
                SELECT id FROM recitations
                WHERE student_id = ?
                ORDER BY created_at DESC, id DESC
                LIMIT 1
                """,
                (student_id,),
            ).fetchone()
        else:
            row = db.execute(
                """
                SELECT id FROM recitations
                ORDER BY created_at DESC, id DESC
                LIMIT 1
                """
            ).fetchone()

        if row is None:
            return None
        return get_recitation_by_id(int(row["id"]), db)


def list_recitations(limit: int = 20, student_id: int | None = None) -> list[dict[str, Any]]:
    with db_connection() as db:
        if student_id is None:
            rows = db.execute(
                """
                SELECT r.*, u.full_name AS student_name
                FROM recitations r
                LEFT JOIN users u ON u.id = r.student_id
                ORDER BY r.created_at DESC, r.id DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
        else:
            rows = db.execute(
                """
                SELECT r.*, u.full_name AS student_name
                FROM recitations r
                LEFT JOIN users u ON u.id = r.student_id
                WHERE r.student_id = ?
                ORDER BY r.created_at DESC, r.id DESC
                LIMIT ?
                """,
                (student_id, limit),
            ).fetchall()

    items: list[dict[str, Any]] = []
    for row in rows:
        item = dict(row)
        item["summary"] = json.loads(item.pop("summary_json") or "{}")
        item.pop("phonetic_script_json", None)
        items.append(item)
    return items


def _error_row_to_dict(row: sqlite3.Row) -> dict[str, Any]:
    item = dict(row)
    item["noon_visible"] = _int_to_bool(item["noon_visible"])
    item["meem_visible"] = _int_to_bool(item["meem_visible"])
    item["raw"] = json.loads(item.pop("raw_json") or "{}")
    return item


def _bool_to_int(value: Any) -> int | None:
    if value is None:
        return None
    return 1 if bool(value) else 0


def _int_to_bool(value: Any) -> bool | None:
    if value is None:
        return None
    return bool(value)
