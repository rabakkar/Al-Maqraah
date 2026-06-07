from __future__ import annotations

from typing import Any


RULE_KEYS = ("izhar", "idgham", "iqlab", "ikhfa")
LEVEL_KEYS = ("beginner", "intermediate", "advanced")
UNCLASSIFIED_LEVEL = "unclassified"
LEVEL_LABELS = {
    "beginner": "مبتدئ",
    "intermediate": "متوسط",
    "advanced": "متقدم",
}
STUDENT_LEVEL_LABELS = {
    UNCLASSIFIED_LEVEL: "غير مصنف",
    **LEVEL_LABELS,
}
DEFAULT_PLACEMENT_THRESHOLDS = {
    "beginner": 0,
    "intermediate": 70,
    "advanced": 85,
}

DEFAULT_LEVEL_RULES = {
    "beginner": ("izhar",),
    "intermediate": ("izhar", "idgham", "iqlab"),
    "advanced": RULE_KEYS,
}

DEFAULT_SCORING_SETTINGS: dict[str, float | int] = {
    "izhar_enabled": 1,
    "izhar_weight": 1,
    "idgham_enabled": 1,
    "idgham_weight": 1,
    "iqlab_enabled": 1,
    "iqlab_weight": 1,
    "ikhfa_enabled": 1,
    "ikhfa_weight": 1,
    "placement_threshold": 0,
    "missing_word_penalty": 0.10,
    "extra_word_penalty": 0.05,
    "different_word_penalty": 0.08,
}


def normalize_level_key(value: Any) -> str:
    level = str(value or "beginner").strip().lower()
    return level if level in LEVEL_KEYS else "beginner"


def normalize_student_level_key(value: Any) -> str:
    level = str(value or UNCLASSIFIED_LEVEL).strip().lower()
    if level == UNCLASSIFIED_LEVEL:
        return UNCLASSIFIED_LEVEL
    return level if level in LEVEL_KEYS else UNCLASSIFIED_LEVEL


def default_scoring_settings_for_level(level: Any) -> dict[str, float | int | str]:
    level_key = normalize_level_key(level)
    data = _default_scoring_data_for_level(level_key)
    return _normalize_scoring_data(data, level_key)


def normalize_scoring_settings(
    payload: dict[str, Any] | None,
    level: Any = None,
) -> dict[str, float | int | str]:
    level_key = normalize_level_key(level or (payload or {}).get("level"))
    data = _default_scoring_data_for_level(level_key)
    if payload:
        data.update(payload)

    return _normalize_scoring_data(data, level_key)


def _default_scoring_data_for_level(level: Any) -> dict[str, float | int]:
    level_key = normalize_level_key(level)
    data = dict(DEFAULT_SCORING_SETTINGS)
    data["placement_threshold"] = DEFAULT_PLACEMENT_THRESHOLDS[level_key]
    enabled_rules = set(DEFAULT_LEVEL_RULES[level_key])
    for rule in RULE_KEYS:
        data[f"{rule}_enabled"] = 1 if rule in enabled_rules else 0
    return data


def _normalize_scoring_data(data: dict[str, Any], level_key: str) -> dict[str, float | int | str]:
    normalized: dict[str, float | int | str] = {}
    for key, default in DEFAULT_SCORING_SETTINGS.items():
        value = data.get(key, default)
        if key.endswith("_weight"):
            normalized[key] = min(1.0, max(0.0, float(value or 0)))
        elif key.endswith("_penalty"):
            normalized[key] = min(1.0, max(0.0, abs(float(value or 0))))
        elif key.endswith("_enabled"):
            normalized[key] = 1 if _boolish(value) else 0
        elif key == "placement_threshold":
            normalized[key] = min(100, max(0, int(value or 0)))
        else:
            normalized[key] = max(0, int(value or 0))
    normalized["level"] = level_key
    normalized["level_label"] = LEVEL_LABELS[level_key]
    return normalized


def enabled_rule_keys(settings: dict[str, Any]) -> list[str]:
    normalized = normalize_scoring_settings(settings, settings.get("level"))
    return [rule for rule in RULE_KEYS if int(normalized.get(f"{rule}_enabled") or 0) == 1]


def calculate_weighted_score(
    summary: dict[str, Any],
    recitation_verification: dict[str, Any],
    settings: dict[str, Any],
) -> dict[str, Any]:
    scoring_settings = normalize_scoring_settings(settings)
    components: list[dict[str, Any]] = []
    active_rules = set(enabled_rule_keys(scoring_settings))

    by_rule = summary.get("by_rule") or {}
    for rule in RULE_KEYS:
        if rule not in active_rules:
            continue
        rule_stats = by_rule.get(rule) or {}
        total = int(rule_stats.get("total") or 0)
        if total <= 0:
            continue
        passed = int(rule_stats.get("passed") or 0)
        score = round((passed / total) * 100, 1)
        components.append(
            {
                "key": rule,
                "score": score,
                "weight": float(scoring_settings[f"{rule}_weight"]),
                "passed": passed,
                "total": total,
            }
        )

    active_components = [item for item in components if item["weight"] > 0]
    total_weight = sum(item["weight"] for item in active_components)
    base_score = 0
    if total_weight > 0:
        weighted_sum = sum(item["score"] * item["weight"] for item in active_components)
        base_score = round(weighted_sum / total_weight, 1)

    penalty_components = _word_penalty_components(recitation_verification, scoring_settings)
    penalty_points = round(sum(item["score"] for item in penalty_components), 1)
    final_score = _clamp_score(round(base_score - penalty_points))

    return {
        "final_score": int(final_score),
        "threshold": int(scoring_settings["placement_threshold"]),
        "passed_threshold": final_score >= int(scoring_settings["placement_threshold"]),
        "base_score": base_score,
        "penalty_points": penalty_points,
        "components": components + penalty_components,
        "total_weight": round(total_weight, 2),
        "settings": scoring_settings,
    }


def _word_penalty_components(
    recitation_verification: dict[str, Any],
    scoring_settings: dict[str, Any],
) -> list[dict[str, Any]]:
    penalty_map = (
        ("missing_words", "missing_word_penalty"),
        ("extra_words", "extra_word_penalty"),
        ("different_words", "different_word_penalty"),
        ("unmatched_words", "missing_word_penalty"),
    )
    components: list[dict[str, Any]] = []
    for count_key, penalty_key in penalty_map:
        count = max(0, int(recitation_verification.get(count_key) or 0))
        penalty = float(scoring_settings.get(penalty_key) or 0)
        if count <= 0 or penalty == 0:
            continue
        score = round(count * penalty * 100, 1)
        components.append(
            {
                "key": count_key,
                "type": "penalty",
                "score": score,
                "weight": penalty,
                "count": count,
                "passed": 0,
                "total": count,
            }
        )
    return components


def _clamp_score(score: int) -> int:
    return min(100, max(0, score))


def calculate_level_scores(
    summary: dict[str, Any],
    recitation_verification: dict[str, Any],
    level_settings: dict[str, dict[str, Any]],
) -> dict[str, dict[str, Any]]:
    return {
        level: calculate_weighted_score(
            summary,
            recitation_verification,
            level_settings.get(level) or default_scoring_settings_for_level(level),
        )
        for level in LEVEL_KEYS
    }


def classify_student_level(level_scores: dict[str, dict[str, Any]]) -> dict[str, Any]:
    for level in reversed(LEVEL_KEYS):
        result = level_scores.get(level) or {}
        score = int(result.get("final_score") or 0)
        threshold = _level_threshold(level, result)
        if level != "beginner" and not _can_place_in_upper_level(result, score):
            continue
        if score >= threshold:
            return {
                "level": level,
                "level_label": LEVEL_LABELS[level],
                "score": score,
                "threshold": threshold,
                "passed_threshold": True,
            }
    beginner_result = level_scores.get("beginner") or {}
    beginner_score = int(beginner_result.get("final_score") or 0)
    beginner_threshold = _level_threshold("beginner", beginner_result)
    return {
        "level": "beginner",
        "level_label": LEVEL_LABELS["beginner"],
        "score": beginner_score,
        "threshold": beginner_threshold,
        "passed_threshold": beginner_score >= beginner_threshold,
    }


def _can_place_in_upper_level(result: dict[str, Any], score: int) -> bool:
    if score <= 0:
        return False

    components = result.get("components")
    if not isinstance(components, list):
        return False

    for component in components:
        if not isinstance(component, dict) or component.get("type") == "penalty":
            continue
        weight = float(component.get("weight") or 0)
        total = int(component.get("total") or 0)
        if weight > 0 and total > 0:
            return True
    return False


def _level_threshold(level: str, result: dict[str, Any]) -> int:
    settings = result.get("settings") if isinstance(result.get("settings"), dict) else {}
    value = result.get("threshold", settings.get("placement_threshold"))
    if value is None:
        value = DEFAULT_PLACEMENT_THRESHOLDS[level]
    return min(100, max(0, int(value or 0)))


def _boolish(value: Any) -> bool:
    if isinstance(value, str):
        return value.strip().lower() not in {"", "0", "false", "off", "no", "لا"}
    return bool(value)
