from __future__ import annotations

import os
import uuid
from pathlib import Path
from typing import Any

from flask import Flask, abort, jsonify, render_template, request, send_from_directory, session
from werkzeug.utils import secure_filename

from core.Tajweed_analysis import analyze_noon_rules_pronunciation
from core.muaalem_phonetics import extract_phonetic_script
from core.quran_repository import QuranRepository
from core.recitation_matcher import verify_required_recitation
from core.scoring import (
    UNCLASSIFIED_LEVEL,
    calculate_level_scores,
    calculate_weighted_score,
    classify_student_level,
    enabled_rule_keys,
    normalize_student_level_key,
)

from database import (
    authenticate_user,
    create_assignment,
    create_teacher,
    create_user,
    get_current_assignment,
    get_scoring_settings,
    get_teacher_dashboard_data,
    has_student_submitted_assignment,
    get_latest_recitation,
    get_recitation_by_id,
    get_user,
    init_db,
    list_assignments,
    list_recitations,
    list_scoring_level_settings,
    list_students,
    list_teachers,
    save_recitation,
    update_student_level,
    update_scoring_settings,
)


BASE_DIR = Path(__file__).resolve().parent
WAQF_DATA_PATH = BASE_DIR / "data" / "quran-uthmani-waqf.json"
DATA_PATH = WAQF_DATA_PATH if WAQF_DATA_PATH.exists() else BASE_DIR / "data" / "quran-uthmani-imlaey.json"
UPLOAD_DIR = BASE_DIR / "uploads"
FRONTEND_DIR = BASE_DIR / "Al-Maqraah"

app = Flask(__name__, template_folder=str(FRONTEND_DIR), static_folder=None)
app.secret_key = os.environ.get("SECRET_KEY", "dev-maqraah-secret")
app.json.ensure_ascii = False
app.config["SEND_FILE_MAX_AGE_DEFAULT"] = 0

UPLOAD_DIR.mkdir(exist_ok=True)
init_db()

quran = QuranRepository(DATA_PATH)
NOON_RULES = ["izhar", "idgham", "iqlab", "ikhfa"]
RULE_LABELS = {
    "izhar": "إظهار",
    "idgham": "إدغام",
    "iqlab": "إقلاب",
    "ikhfa": "إخفاء",
}


def current_user() -> dict[str, Any] | None:
    user_id = session.get("user_id")
    if user_id is None:
        return None
    return get_user(int(user_id))


def require_json() -> dict[str, Any]:
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        raise ValueError("صيغة البيانات غير صحيحة.")
    return data


def calculate_score(summary: dict[str, Any]) -> int:
    total = int(summary.get("total") or 0)
    if total <= 0:
        return 0
    passed = int(summary.get("passed") or 0)
    return round((passed / total) * 100)


def apply_missing_word_rule_overrides(
    rule_analysis: dict[str, Any],
    recitation_verification: dict[str, Any],
) -> dict[str, Any]:
    missing_word_indexes = {
        int(index)
        for index in recitation_verification.get("missing_word_indexes", [])
        if index is not None
    }
    if not missing_word_indexes:
        return rule_analysis

    evaluations = rule_analysis.get("evaluations", [])
    if not isinstance(evaluations, list):
        return rule_analysis

    for item in evaluations:
        word_indexes = {int(index) for index in item.get("word_indexes", [])}
        if not word_indexes.intersection(missing_word_indexes):
            continue
        item["status"] = "needs_review"
        item["status_label"] = "يحتاج مراجعة"
        item["pronunciation_blocked"] = True
        item["missing_word_indexes"] = sorted(word_indexes.intersection(missing_word_indexes))
        item["reason"] = "الكلمة المرتبطة بهذا الحكم لم تظهر في التلاوة، لذلك اعتبر النظام الحكم غير مطبق."

    rule_analysis["summary"] = rebuild_rule_summary(evaluations)
    return rule_analysis


def rebuild_rule_summary(evaluations: list[dict[str, Any]]) -> dict[str, Any]:
    summary = {
        "total": len(evaluations),
        "passed": 0,
        "needs_review": 0,
        "unmatched": 0,
        "by_rule": {
            "izhar": {"total": 0, "passed": 0, "needs_review": 0, "unmatched": 0},
            "idgham": {"total": 0, "passed": 0, "needs_review": 0, "unmatched": 0},
            "iqlab": {"total": 0, "passed": 0, "needs_review": 0, "unmatched": 0},
            "ikhfa": {"total": 0, "passed": 0, "needs_review": 0, "unmatched": 0},
        },
    }
    for item in evaluations:
        status = item.get("status", "unmatched")
        if status not in {"passed", "needs_review", "unmatched"}:
            status = "unmatched"
        rule = item.get("rule", "")
        summary[status] += 1
        if rule in summary["by_rule"]:
            summary["by_rule"][rule]["total"] += 1
            summary["by_rule"][rule][status] += 1
    return summary


def is_student_unclassified(user: dict[str, Any]) -> bool:
    return normalize_student_level_key(user.get("student_level")) == UNCLASSIFIED_LEVEL


def enabled_rules_for_placement(level_settings: dict[str, dict[str, Any]]) -> list[str]:
    rules: set[str] = set()
    for settings in level_settings.values():
        rules.update(enabled_rule_keys(settings))
    return sorted(rules) or NOON_RULES


def build_placement_payload(
    summary: dict[str, Any],
    recitation_verification: dict[str, Any],
    level_settings: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    level_scores = calculate_level_scores(summary, recitation_verification, level_settings)
    selected = classify_student_level(level_scores)
    return {
        "selected": selected,
        "scores": {
            level: {
                "final_score": result.get("final_score", 0),
                "threshold": result.get("threshold", 0),
                "passed_threshold": bool(result.get("passed_threshold")),
                "total_weight": result.get("total_weight", 0),
                "components": result.get("components", []),
            }
            for level, result in level_scores.items()
        },
    }


def hydrate_assignment_for_display(assignment: dict[str, Any] | None) -> dict[str, Any] | None:
    if not assignment:
        return None

    item = dict(assignment)
    if item.get("submitted"):
        item["ayah_text"] = ""
        item["verses"] = []
        return item

    try:
        selection = quran.build_selection(
            int(item["surah_number"]),
            int(item["ayah_from"]),
            int(item["ayah_to"]),
            enabled_rules=NOON_RULES,
        )
    except (KeyError, TypeError, ValueError):
        return item

    if not item.get("ayah_text"):
        item["ayah_text"] = selection["combined_text"]
    item["verses"] = selection["verses"]
    return item


def recitation_to_api_payload(recitation: dict[str, Any] | None) -> dict[str, Any] | None:
    if not recitation:
        return None

    evaluations = [item.get("raw") or item for item in recitation.get("errors", [])]
    summary = recitation.get("summary", {})
    alignment = summary.get("alignment", {})
    summary_without_alignment = {key: value for key, value in summary.items() if key != "alignment"}

    return {
        "recitation_id": recitation["id"],
        "student_id": recitation.get("student_id"),
        "student_name": recitation.get("student_name", ""),
        "audio_file": recitation["audio_file"],
        "selection": {
            "surah": {
                "index": recitation["surah_number"],
                "name": recitation["surah_name"],
            },
            "ayah_from": recitation["ayah_from"],
            "ayah_to": recitation["ayah_to"],
        },
        "phonetic_script": recitation.get("phonetic_script", {}),
        "rule_analysis": {
            "summary": summary_without_alignment,
            "evaluations": evaluations,
            "alignment": alignment,
        },
        "engine_note": recitation.get("engine_note", ""),
        "score": recitation.get("score", 0),
        "created_at": recitation.get("created_at"),
    }


def recitation_to_student_payload(recitation: dict[str, Any] | None) -> dict[str, Any] | None:
    if not recitation:
        return None

    summary = recitation.get("summary", {})
    summary_without_internal = {
        key: value
        for key, value in summary.items()
        if key not in {
            "alignment",
            "component_scores",
            "scoring_settings",
            "weighted_score",
            "recitation_verification",
        }
    }
    verification = summary.get("recitation_verification", {})
    word_issues = [
        {
            "status": item.get("status"),
            "expected": item.get("expected", ""),
            "actual": item.get("actual", ""),
        }
        for item in verification.get("word_evaluations", [])
        if item.get("status") in {"missing", "extra", "different", "unmatched_word"}
    ]
    by_rule = summary.get("by_rule") or {}
    rule_feedback = []
    for rule in NOON_RULES:
        item = by_rule.get(rule) or {}
        total = int(item.get("total") or 0)
        passed = int(item.get("passed") or 0)
        needs_review = int(item.get("needs_review") or 0)
        unmatched = int(item.get("unmatched") or 0)
        issues_count = needs_review + unmatched
        rule_feedback.append(
            {
                "key": rule,
                "label": RULE_LABELS[rule],
                "total": total,
                "passed": passed,
                "needs_review": needs_review,
                "unmatched": unmatched,
                "issues_count": issues_count,
                "score": round((passed / total) * 100) if total else None,
            }
        )

    return {
        "recitation_id": recitation["id"],
        "selection": {
            "surah": {
                "index": recitation["surah_number"],
                "name": recitation["surah_name"],
            },
            "ayah_from": recitation["ayah_from"],
            "ayah_to": recitation["ayah_to"],
        },
        "score": recitation.get("score", 0),
        "created_at": recitation.get("created_at"),
        "student_view": {
            "level": summary.get("scoring_level") or (summary.get("placement") or {}).get("selected"),
            "placement": summary.get("placement"),
            "pronunciation": {
                "score": verification.get("pronunciation_score"),
                "missing_words": verification.get("missing_words", 0),
                "extra_words": verification.get("extra_words", 0),
                "different_words": verification.get("different_words", 0),
                "unmatched_words": verification.get("unmatched_words", 0),
                "matched_words": verification.get("matched_words", 0),
                "expected_words": verification.get("expected_words", 0),
                "word_issues": word_issues,
            },
            "rules": rule_feedback,
            "summary": summary_without_internal,
        },
    }


@app.get("/")
def index() -> str:
    return render_template("index.html")


@app.get("/<path:filename>")
def frontend_file(filename: str) -> Any:
    allowed_prefixes = ("assets/", "css/", "JavaScript/")
    allowed_pages = {
        "index.html",
        "login.html",
        "signup.html",
        "forgot-password.html",
        "student-profile.html",
        "teacher-dashboard.html",
        "scoring-settings.html",
        "recording.html",
        "result.html",
        "result_details.html",
        "student-result-details.html",
        "teacher-student-results.html",
        "results.html",
    }

    if filename in allowed_pages or filename.startswith(allowed_prefixes):
        return send_from_directory(FRONTEND_DIR, filename)

    abort(404)


@app.get("/uploads/<path:filename>")
def serve_upload(filename: str) -> Any:
    return send_from_directory(UPLOAD_DIR, filename)


@app.post("/api/auth/signup")
def signup() -> Any:
    try:
        data = require_json()
        full_name = str(data.get("full_name", "")).strip()
        email = str(data.get("email", "")).strip()
        password = str(data.get("password", ""))
        role = str(data.get("role", "student")).strip()
        student_level = str(data.get("student_level", UNCLASSIFIED_LEVEL)).strip()

        if not full_name or not email or not password:
            return jsonify({"error": "الرجاء تعبئة جميع الحقول."}), 400
        if role != "student":
            return jsonify({"error": "تسجيل المعلمين يتم عن طريق أدمن المقرأة فقط."}), 403

        user = create_user(full_name, email, password, role, student_level=student_level)
        session["user_id"] = user["id"]
        return jsonify({"user": user})
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400


@app.post("/api/auth/login")
def login() -> Any:
    try:
        data = require_json()
        email = str(data.get("email", "")).strip()
        password = str(data.get("password", ""))
        role = str(data.get("role", "student")).strip()

        user = authenticate_user(email, password, role)
        if user is None:
            return jsonify({"error": "بيانات الدخول غير صحيحة."}), 401

        session["user_id"] = user["id"]
        return jsonify({"user": user})
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400


@app.post("/api/auth/logout")
def logout() -> Any:
    session.clear()
    return jsonify({"ok": True})


@app.get("/api/auth/me")
def me() -> Any:
    return jsonify({"user": current_user()})


@app.get("/api/students")
def students() -> Any:
    return jsonify({"students": list_students()})


@app.get("/api/teacher/dashboard")
def teacher_dashboard_data() -> Any:
    user = current_user()
    if not user or user["role"] != "teacher":
        return jsonify({"error": "هذه البيانات متاحة للمعلمين فقط."}), 403
    return jsonify(get_teacher_dashboard_data())


@app.get("/api/scoring-settings")
def scoring_settings() -> Any:
    user = current_user()
    if not user or user["role"] != "teacher":
        return jsonify({"error": "إعدادات التقييم متاحة للمعلمين فقط."}), 403
    return jsonify({
        "settings": get_scoring_settings("beginner"),
        "levels": list_scoring_level_settings(),
    })


@app.put("/api/scoring-settings")
def update_scoring_settings_endpoint() -> Any:
    user = current_user()
    if not user or user["role"] != "teacher":
        return jsonify({"error": "إعدادات التقييم متاحة للمعلمين فقط."}), 403

    try:
        data = require_json()
        updated = update_scoring_settings(data)
        if isinstance(data.get("levels"), dict):
            return jsonify({"levels": updated})
        return jsonify({
            "settings": updated,
            "levels": list_scoring_level_settings(),
        })
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400


@app.get("/api/teachers")
def teachers() -> Any:
    return jsonify({"teachers": list_teachers()})


@app.post("/api/teachers")
def create_teacher_endpoint() -> Any:
    user = current_user()
    if not user or user["role"] != "teacher" or not user.get("is_admin"):
        return jsonify({"error": "هذه الصلاحية متاحة لأدمن المقرأة فقط."}), 403

    try:
        data = require_json()
        full_name = str(data.get("full_name", "")).strip()
        email = str(data.get("email", "")).strip()
        password = str(data.get("password", ""))
        is_admin = bool(data.get("is_admin", False))

        if not full_name or not email or not password:
            return jsonify({"error": "الرجاء تعبئة بيانات المعلم."}), 400

        teacher = create_teacher(full_name, email, password, is_admin=is_admin)
        return jsonify({"teacher": teacher})
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400


@app.get("/api/assignments")
def assignments() -> Any:
    return jsonify({"assignments": list_assignments()})


@app.post("/api/assignments")
def create_assignment_endpoint() -> Any:
    user = current_user()
    if not user or user["role"] != "teacher":
        return jsonify({"error": "هذه الصلاحية متاحة للمعلمين فقط."}), 403

    try:
        data = require_json()
        surah = int(data.get("surah", "67"))
        ayah_from = int(data.get("from", "1"))
        ayah_to = int(data.get("to", str(ayah_from)))
        selection = quran.build_selection(surah, ayah_from, ayah_to, enabled_rules=NOON_RULES)
        student_name = "جميع الطلاب"

        assignment = create_assignment(
            {
                "teacher_id": user["id"],
                "student_id": None,
                "student_name": student_name,
                "surah_number": selection["surah"]["index"],
                "surah_name": selection["surah"]["name"],
                "ayah_from": selection["ayah_from"],
                "ayah_to": selection["ayah_to"],
                "ayah_text": selection["combined_text"],
                "stats": selection["stats"],
            }
        )
        return jsonify({"assignment": assignment})
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400


@app.get("/api/assignments/current")
def current_assignment() -> Any:
    user = current_user()
    if not user or user["role"] != "student":
        return jsonify({"error": "التكليف الحالي متاح للطلاب فقط."}), 403
    assignment = hydrate_assignment_for_display(get_current_assignment(user["id"]))
    return jsonify({
        "assignment": assignment,
        "submitted": bool(assignment.get("submitted")) if assignment else False,
    })


@app.get("/api/recitations/latest")
def latest_recitation() -> Any:
    user = current_user()
    if user is None:
        return jsonify({"result": None})

    student_id = user["id"] if user["role"] == "student" else None
    recitation = get_latest_recitation(student_id)
    payload = recitation_to_student_payload(recitation) if user["role"] == "student" else recitation_to_api_payload(recitation)
    return jsonify({"result": payload})


@app.get("/api/recitations/<int:recitation_id>")
def recitation_detail(recitation_id: int) -> Any:
    user = current_user()
    if user is None:
        return jsonify({"result": None}), 401

    recitation = get_recitation_by_id(recitation_id)
    if not recitation:
        return jsonify({"result": None}), 404
    if user["role"] == "student" and recitation.get("student_id") != user["id"]:
        return jsonify({"error": "لا يمكنك عرض نتيجة طالب آخر."}), 403

    payload = recitation_to_student_payload(recitation) if user["role"] == "student" else recitation_to_api_payload(recitation)
    return jsonify({"result": payload})


@app.get("/api/recitations")
def recitations() -> Any:
    user = current_user()
    requested_student_id = request.args.get("student_id")
    items = []
    if user and user["role"] == "student":
        items = list_recitations(student_id=user["id"])
    elif user and user["role"] == "teacher" and requested_student_id:
        items = list_recitations(student_id=int(requested_student_id))
    elif user and user["role"] == "teacher":
        items = list_recitations()
    return jsonify({"recitations": items})


@app.get("/api/surahs")
def surahs() -> Any:
    return jsonify({"surahs": quran.get_surahs()})


@app.get("/api/verses")
def verses() -> Any:
    try:
        surah = int(request.args.get("surah", "1"))
        ayah_from = int(request.args.get("from", "1"))
        ayah_to = int(request.args.get("to", str(ayah_from)))
        user = current_user()
        enabled_rules = NOON_RULES
        if user and user["role"] == "student":
            if is_student_unclassified(user):
                enabled_rules = enabled_rules_for_placement(list_scoring_level_settings())
            else:
                enabled_rules = enabled_rule_keys(get_scoring_settings(user.get("student_level"))) or NOON_RULES
        selection = quran.build_selection(surah, ayah_from, ayah_to, enabled_rules=enabled_rules)
        return jsonify(
            {
                "surah": selection["surah"],
                "ayah_from": selection["ayah_from"],
                "ayah_to": selection["ayah_to"],
                "verses": selection["verses"],
                "words": selection["words"],
                "rule_cases": selection["tajweed_cases"],
                "stats": selection["stats"],
            }
        )
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400


@app.post("/api/analyze-audio")
def analyze_audio() -> Any:
    user = current_user()
    if not user or user["role"] != "student":
        return jsonify({"error": "يجب تسجيل الدخول كطالب لإرسال التسجيل."}), 403

    audio = request.files.get("audio")
    if audio is None:
        return jsonify({"error": "لم يصل ملف صوت."}), 400

    level_settings = list_scoring_level_settings()
    placement_mode = is_student_unclassified(user)
    scoring_settings = get_scoring_settings("beginner" if placement_mode else user.get("student_level"))
    enabled_rules = (
        enabled_rules_for_placement(level_settings)
        if placement_mode
        else enabled_rule_keys(scoring_settings) or NOON_RULES
    )

    try:
        assignment_id = (request.form.get("assignment_id") or "").strip()
        if not assignment_id:
            return jsonify({"error": "لا يمكن إرسال تسجيل حر. يجب أن يكون التسجيل مرتبطًا بتكليف حدده المعلم."}), 400

        assignment_id_int = int(assignment_id)
        if has_student_submitted_assignment(user["id"], assignment_id_int):
            return jsonify({"error": "تم تسليم هذا التكليف مسبقًا، ولا يمكن إرسال تسجيل آخر لنفس التكليف."}), 409

        open_assignment = get_current_assignment(user["id"])
        if open_assignment and open_assignment.get("submitted"):
            return jsonify({"error": "تم تسليم التكليف مسبقًا، ولا يمكن إرسال تسجيل آخر."}), 409
        if not open_assignment or int(open_assignment["id"]) != assignment_id_int:
            return jsonify({"error": "هذا التكليف لم يعد متاحًا للتسليم. حدّث صفحة التسجيل ثم حاول مرة أخرى عند وجود تكليف جديد."}), 409

        surah = int(open_assignment["surah_number"])
        ayah_from = int(open_assignment["ayah_from"])
        ayah_to = int(open_assignment["ayah_to"])

        selection = quran.build_selection(surah, ayah_from, ayah_to, enabled_rules=enabled_rules)
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400

    filename = secure_filename(audio.filename or "recitation.wav") or "recitation.wav"
    if not filename.lower().endswith(".wav"):
        return jsonify({"error": "النظام يقبل ملفات WAV فقط من المتصفح."}), 400

    audio_path = UPLOAD_DIR / f"{uuid.uuid4().hex}_{filename}"
    audio.save(audio_path)

    try:
        recitation_verification = verify_required_recitation(audio_path, selection, scoring_settings)
    except Exception as exc:  # pragma: no cover - returned to UI
        audio_path.unlink(missing_ok=True)
        return jsonify({"error": f"تعذر التحقق من مطابقة التلاوة للآيات المطلوبة باستخدام مودل whisper-quran: {exc}"}), 500

    if not recitation_verification.get("matches_expected"):
        audio_path.unlink(missing_ok=True)
        return jsonify(
            {
                "error": recitation_verification.get("message") or "التسجيل لا يطابق الآيات المطلوبة بدرجة كافية. أعد التسجيل بعد قراءة النص المعروض كاملا.",
                "heard_text": recitation_verification.get("transcript", ""),
                "normalized_heard_text": recitation_verification.get("normalized_transcript", ""),
                "expected_text": selection["combined_text"],
                "recitation_verification": recitation_verification,
            }
        ), 422

    try:
        phonetic_script = extract_phonetic_script(audio_path)
    except Exception as exc:  # pragma: no cover - returned to UI
        return jsonify({"error": f"تعذر استخراج الرسم الصوتي من مودل muaalem-model-v3_2: {exc}"}), 500

    rule_analysis = analyze_noon_rules_pronunciation(selection, phonetic_script)
    rule_analysis = apply_missing_word_rule_overrides(rule_analysis, recitation_verification)
    summary = dict(rule_analysis.get("summary", {}))
    summary["alignment"] = rule_analysis.get("alignment", {})
    summary["recitation_verification"] = recitation_verification
    placement = None
    if placement_mode:
        placement = build_placement_payload(summary, recitation_verification, level_settings)
        selected_level = placement["selected"]["level"]
        scoring_settings = get_scoring_settings(selected_level)
        update_student_level(user["id"], selected_level)
        summary["placement"] = placement

    summary["scoring_level"] = {
        "key": scoring_settings.get("level", user.get("student_level", "beginner")),
        "label": scoring_settings.get("level_label", ""),
    }
    scoring_result = calculate_weighted_score(summary, recitation_verification, scoring_settings)
    summary["component_scores"] = scoring_result["components"]
    summary["scoring_settings"] = scoring_result["settings"]
    summary["weighted_score"] = scoring_result
    rule_analysis["summary"] = summary
    engine_note = "تم التحقق أولًا من مطابقة التلاوة للآيات المطلوبة باستخدام whisper-quran، ثم تحليل أحكام النون الساكنة والتنوين بالاعتماد على الرسم الصوتي من muaalem-model-v3_2."
    try:
        recitation = save_recitation(
            {
                "student_id": user["id"],
                "assignment_id": assignment_id_int,
                "audio_file": audio_path.name,
                "surah_number": selection["surah"]["index"],
                "surah_name": selection["surah"]["name"],
                "ayah_from": selection["ayah_from"],
                "ayah_to": selection["ayah_to"],
                "score": scoring_result["final_score"],
                "summary": summary,
                "phonetic_script": phonetic_script,
                "engine_note": engine_note,
            },
            rule_analysis.get("evaluations", []),
        )
    except ValueError as exc:
        audio_path.unlink(missing_ok=True)
        return jsonify({"error": str(exc)}), 409

    return jsonify(
        {
            "recitation_id": recitation["id"],
            "audio_file": audio_path.name,
            "selection": {
                "surah": selection["surah"],
                "ayah_from": selection["ayah_from"],
                "ayah_to": selection["ayah_to"],
            },
            "rule_cases": selection["tajweed_cases"],
            "phonetic_script": phonetic_script,
            "rule_analysis": rule_analysis,
            "recitation_verification": recitation_verification,
            "placement": placement,
            "student_level": summary["scoring_level"],
            "scoring": scoring_result,
            "engine_note": engine_note,
            "score": recitation["score"],
        }
    )


if __name__ == "__main__":
    port = int(os.environ.get("PORT", "5000"))
    app.run(host="127.0.0.1", debug=False, port=port, threaded=True)
