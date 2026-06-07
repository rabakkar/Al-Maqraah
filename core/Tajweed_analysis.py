from __future__ import annotations

from difflib import SequenceMatcher
from typing import Any

from core.tajweed_rules import ARABIC_BASE_LETTERS, NOON, normalize_letter, iter_letter_units


MEEM = "\u0645"
NASAL_NOON = "\u06ba"
SPECIAL_PHONEME_BASE = {
    NASAL_NOON: NOON,
    "\u06fe": MEEM,
    "\u06e5": "\u0648",
    "\u06e6": "\u064a",
}

STATUS_LABELS = {
    "passed": "مطابق",
    "needs_review": "يحتاج مراجعة",
    "unmatched": "لم يتم تحديد الموضع",
}



def analyze_noon_rules_pronunciation(
    selection: dict[str, Any],
    phonetic_script: dict[str, Any],
) -> dict[str, Any]:
    rule_cases = [
        case for case in selection.get("tajweed_cases", [])
        if case.get("rule") in {"izhar", "idgham", "iqlab", "ikhfa"}
    ]
    text = selection.get("combined_text", "")
    ref_units = iter_letter_units(text)
    ref_letters = [normalize_letter(unit.letter) for unit in ref_units]
    predicted_units = _predicted_letter_units(phonetic_script)
    predicted_letters = [unit["letter"] for unit in predicted_units]
    ref_to_pred = _align_ref_to_pred(ref_letters, predicted_letters)

    evaluations = [
        _evaluate_case(case, ref_units, predicted_units, ref_to_pred)
        for case in rule_cases
    ]

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
        summary[item["status"]] += 1
        if item["rule"] in summary["by_rule"]:
            summary["by_rule"][item["rule"]]["total"] += 1
            summary["by_rule"][item["rule"]][item["status"]] += 1

    return {
        "summary": summary,
        "evaluations": evaluations,
        "alignment": {
            "reference_letters": len(ref_letters),
            "predicted_letters": len(predicted_letters),
            "mapped_letters": len(ref_to_pred),
        },
    }


def _evaluate_case(
    case: dict[str, Any],
    ref_units: list[Any],
    predicted_units: list[dict[str, Any]],
    ref_to_pred: dict[int, int],
) -> dict[str, Any]:
    source_ref_idx = _find_ref_unit_index(ref_units, int(case["start"]))
    source_end_ref_idx = _find_last_ref_unit_index(ref_units, int(case["start"]), int(case["end"]))
    next_ref_idx = _find_ref_unit_index(ref_units, int(case["next_start"]))
    evidence = _find_source_noon_evidence(
        case=case,
        ref_units=ref_units,
        source_ref_idx=source_ref_idx,
        source_end_ref_idx=source_end_ref_idx,
        next_ref_idx=next_ref_idx,
        ref_to_pred=ref_to_pred,
        ref_len=len(ref_units),
        predicted_units=predicted_units,
    )

    if evidence is None:
        return {
            **_case_base_payload(case),
            "status": "unmatched",
            "status_label": STATUS_LABELS["unmatched"],
            "noon_visible": None,
            "noon_count": 0,
            "nasal_noon_visible": None,
            "nasal_noon_count": 0,
            "meem_visible": None,
            "meem_count": 0,
            "phonetic_window": "",
            "phonetic_window_indexes": None,
            "checked_scope": "",
            "anchor_source": "unavailable",
            "reason": "لم نستطع ربط موضع النون الساكنة أو التنوين بالرسم الصوتي الناتج من المودل.",
        }

    start, end = evidence["display_window"]
    window_units = predicted_units[start:end]
    checked_units = [predicted_units[idx] for idx in evidence["checked_indexes"]]
    clear_noon_count = sum(1 for unit in checked_units if _is_clear_noon(unit))
    nasal_noon_count = sum(1 for unit in checked_units if _is_nasal_noon(unit))
    meem_count = sum(1 for unit in checked_units if unit["letter"] == MEEM)
    noon_visible = clear_noon_count > 0
    nasal_noon_visible = nasal_noon_count > 0
    meem_visible = meem_count > 0
    status, reason = _judge_rule(case, noon_visible, nasal_noon_visible, meem_visible)

    return {
        **_case_base_payload(case),
        "status": status,
        "status_label": STATUS_LABELS[status],
        "noon_visible": noon_visible,
        "noon_count": clear_noon_count,
        "nasal_noon_visible": nasal_noon_visible,
        "nasal_noon_count": nasal_noon_count,
        "meem_visible": meem_visible,
        "meem_count": meem_count,
        "phonetic_window": "".join(unit["token"] for unit in window_units),
        "phonetic_window_letters": "".join(unit["letter"] for unit in window_units),
        "phonetic_window_indexes": {"start": start, "end": end},
        "checked_scope": evidence["checked_scope"],
        "checked_indexes": evidence["checked_indexes"],
        "noon_positions": [unit["unit_index"] for unit in checked_units if _is_clear_noon(unit)],
        "nasal_noon_positions": [unit["unit_index"] for unit in checked_units if _is_nasal_noon(unit)],
        "meem_positions": [unit["unit_index"] for unit in checked_units if unit["letter"] == MEEM],
        "anchor_source": evidence["anchor_source"],
        "reason": reason,
    }


def _case_base_payload(case: dict[str, Any]) -> dict[str, Any]:
    return {
        "case_id": case["case_id"],
        "rule": case.get("rule", ""),
        "source_type": case["source_type"],
        "source_label": case.get("source_label", ""),
        "rule_label": case.get("rule_label", "إدغام"),
        "rule_detail": case.get("rule_detail", ""),
        "source_text": case.get("source_text", ""),
        "next_letter": case.get("next_letter", ""),
        "snippet": case.get("snippet", ""),
        "ayah": case.get("ayah"),
        "word_indexes": case.get("word_indexes", []),
    }


def _predicted_letter_units(phonetic_script: dict[str, Any]) -> list[dict[str, Any]]:
    tokens = phonetic_script.get("tokens") or []
    if tokens:
        units: list[dict[str, Any]] = []
        for idx, item in enumerate(tokens):
            token = str(item.get("token", ""))
            letter = _token_to_base_letter(token)
            if letter is None:
                continue
            units.append(
                {
                    "letter": letter,
                    "token": token,
                    "unit_index": len(units),
                    "token_index": idx,
                    "confidence": item.get("confidence"),
                }
            )
        return units

    return [
        {"letter": letter, "token": token, "unit_index": idx, "token_index": idx, "confidence": None}
        for idx, token in enumerate(str(phonetic_script.get("text", "")))
        if (letter := _token_to_base_letter(token)) is not None
    ]


def _token_to_base_letter(token: str) -> str | None:
    if not token:
        return None
    if token[0] in SPECIAL_PHONEME_BASE:
        return SPECIAL_PHONEME_BASE[token[0]]
    letter = normalize_letter(token[0])
    return letter if letter in ARABIC_BASE_LETTERS else None


def _is_clear_noon(unit: dict[str, Any]) -> bool:
    return unit["letter"] == NOON and unit["token"] == NOON


def _is_nasal_noon(unit: dict[str, Any]) -> bool:
    return unit["letter"] == NOON and unit["token"] == NASAL_NOON


def _judge_rule(
    case: dict[str, Any],
    noon_visible: bool,
    nasal_noon_visible: bool,
    meem_visible: bool,
) -> tuple[str, str]:
    rule = case.get("rule")
    source_name = "نون التنوين" if case.get("source_type") == "tanween" else "النون الساكنة"
    if rule == "izhar":
        if noon_visible:
            return "passed", f"ظهرت {source_name} واضحة في موضعها، وهذا يوافق الإظهار."
        return "needs_review", f"لم تظهر {source_name} واضحة في موضعها، وهذا لا يوافق الإظهار."
    if rule == "idgham":
        if noon_visible:
            return "needs_review", f"ظهرت {source_name} في موضعها قبل حرف الإدغام."
        if normalize_letter(str(case.get("next_letter", ""))) == NOON:
            return "passed", f"عوملت النون الظاهرة كجزء من حرف الإدغام التالي، ولم تظهر {source_name} مستقلة."
        return "passed", f"لم تظهر {source_name} واضحة في موضعها، وهذا يوافق الإدغام."
    if rule == "ikhfa":
        if noon_visible:
            return "needs_review", f"ظهرت {source_name} واضحة في موضع الإخفاء."
        if nasal_noon_visible:
            return "passed", f"ظهرت غنة {source_name} دون إظهارها صريحة، وهذا يوافق الإخفاء."
        return "needs_review", f"لم تظهر {source_name} واضحة، لكن لم يظهر أثر الغنة المطلوب في موضع الإخفاء."
    if rule == "iqlab":
        if noon_visible:
            return "needs_review", f"ظهرت {source_name} في موضع الإقلاب بدل قلبها إلى ميم."
        if meem_visible:
            return "passed", f"ظهرت الميم في موضع {source_name}، وهذا يوافق الإقلاب."
        return "needs_review", f"لم تظهر الميم في موضع {source_name} عند الإقلاب."
    return "unmatched", "حكم غير مدعوم في هذا التحليل."


def _align_ref_to_pred(ref_letters: list[str], predicted_letters: list[str]) -> dict[int, int]:
    mapping: dict[int, int] = {}
    matcher = SequenceMatcher(a=ref_letters, b=predicted_letters, autojunk=False)
    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag == "equal":
            for offset in range(i2 - i1):
                mapping[i1 + offset] = j1 + offset
        elif tag == "replace":
            span = min(i2 - i1, j2 - j1)
            for offset in range(span):
                if ref_letters[i1 + offset] == predicted_letters[j1 + offset]:
                    mapping[i1 + offset] = j1 + offset
    return mapping


def _find_ref_unit_index(ref_units: list[Any], char_start: int) -> int | None:
    for idx, unit in enumerate(ref_units):
        if unit.start == char_start:
            return idx
    for idx, unit in enumerate(ref_units):
        if unit.start <= char_start < unit.end:
            return idx
    return None


def _find_last_ref_unit_index(ref_units: list[Any], char_start: int, char_end: int) -> int | None:
    matches = [
        idx for idx, unit in enumerate(ref_units)
        if unit.start < char_end and char_start < unit.end
    ]
    return matches[-1] if matches else _find_ref_unit_index(ref_units, char_start)


def _find_source_noon_evidence(
    case: dict[str, Any],
    ref_units: list[Any],
    source_ref_idx: int | None,
    source_end_ref_idx: int | None,
    next_ref_idx: int | None,
    ref_to_pred: dict[int, int],
    ref_len: int,
    predicted_units: list[dict[str, Any]],
) -> dict[str, Any] | None:
    predicted_len = len(predicted_units)
    if predicted_len <= 0 or source_ref_idx is None:
        return None

    pronounced_next_ref_idx = _pronounced_next_ref_idx(ref_units, next_ref_idx)
    next_pred = _pred_index_for_ref(pronounced_next_ref_idx, ref_to_pred, ref_len, predicted_len)
    if next_pred is None:
        return None

    if case.get("rule") == "iqlab":
        checked_indexes, anchor_source, next_pred = _iqlab_checked_indexes(
            source_ref_idx=source_ref_idx,
            source_end_ref_idx=source_end_ref_idx,
            next_ref_idx=pronounced_next_ref_idx,
            ref_to_pred=ref_to_pred,
            ref_len=ref_len,
            predicted_units=predicted_units,
            ref_units=ref_units,
        )
        checked_scope = "iqlab-before-baa"
    elif case.get("source_type") == "tanween":
        checked_indexes, anchor_source = _tanween_checked_indexes(
            source_ref_idx=source_ref_idx,
            source_end_ref_idx=source_end_ref_idx,
            next_ref_idx=pronounced_next_ref_idx,
            ref_to_pred=ref_to_pred,
            ref_len=ref_len,
            predicted_len=predicted_len,
        )
        checked_scope = "tanween-gap"
    else:
        checked_indexes, anchor_source = _noon_sakinah_checked_indexes(
            source_ref_idx=source_ref_idx,
            next_ref_idx=pronounced_next_ref_idx,
            ref_to_pred=ref_to_pred,
            ref_len=ref_len,
            predicted_len=predicted_len,
        )
        checked_scope = "source-noon-position"

    next_letter = normalize_letter(str(case.get("next_letter", "")))
    next_actual = ref_to_pred.get(pronounced_next_ref_idx) if pronounced_next_ref_idx is not None else None
    checked_indexes = [
        idx for idx in checked_indexes
        if 0 <= idx < predicted_len and not (next_letter == NOON and idx == next_actual)
    ]
    if case.get("rule") == "idgham":
        checked_indexes = _filter_absorbed_idgham_markers(
            case=case,
            checked_indexes=checked_indexes,
            predicted_units=predicted_units,
            next_letter=next_letter,
            next_pred=next_actual if next_actual is not None else next_pred,
        )
        checked_indexes = _include_tanween_clear_noon_duplication(
            case=case,
            checked_indexes=checked_indexes,
            ref_units=ref_units,
            source_ref_idx=source_ref_idx,
            ref_to_pred=ref_to_pred,
            predicted_units=predicted_units,
            next_pred=next_actual if next_actual is not None else next_pred,
        )
    marker_positions = [
        idx for idx in checked_indexes
        if _is_clear_noon(predicted_units[idx]) or predicted_units[idx]["letter"] == MEEM
    ]

    display_indexes = checked_indexes + marker_positions + [next_pred]
    if not display_indexes:
        display_indexes = [next_pred]
    start = max(0, min(display_indexes) - 2)
    end = min(predicted_len, max(display_indexes) + 3)

    return {
        "checked_scope": checked_scope,
        "checked_indexes": checked_indexes,
        "display_window": (start, end),
        "anchor_source": anchor_source,
    }


def _filter_absorbed_idgham_markers(
    case: dict[str, Any],
    checked_indexes: list[int],
    predicted_units: list[dict[str, Any]],
    next_letter: str,
    next_pred: int,
) -> list[int]:
    if not case.get("has_ghunnah") and not case.get("needs_ghunnah"):
        return checked_indexes

    idgham_with_ghunnah_letters = {"\u064a", "\u0646", "\u0645", "\u0648"}
    if next_letter not in idgham_with_ghunnah_letters:
        return checked_indexes
    if next_letter == NOON:
        cluster = _same_clear_noon_cluster(predicted_units, next_pred)
        if not cluster:
            cluster = _same_letter_cluster(predicted_units, next_pred, next_letter)
        if not cluster:
            return checked_indexes
        return [idx for idx in checked_indexes if idx not in cluster]

    cluster = _same_letter_cluster(predicted_units, next_pred, next_letter)
    if not cluster:
        return checked_indexes
    if len(cluster) < 2:
        return checked_indexes

    absorbed = set(cluster)

    return [idx for idx in checked_indexes if idx not in absorbed]


def _include_tanween_clear_noon_duplication(
    case: dict[str, Any],
    checked_indexes: list[int],
    ref_units: list[Any],
    source_ref_idx: int | None,
    ref_to_pred: dict[int, int],
    predicted_units: list[dict[str, Any]],
    next_pred: int,
) -> list[int]:
    if case.get("source_type") != "tanween" or source_ref_idx is None:
        return checked_indexes
    if not 0 <= source_ref_idx < len(ref_units):
        return checked_indexes
    if normalize_letter(ref_units[source_ref_idx].letter) != NOON:
        return checked_indexes

    candidates = [ref_to_pred.get(source_ref_idx), next_pred - 1, next_pred - 2]
    for center in candidates:
        cluster = _same_clear_noon_cluster(predicted_units, center)
        cluster = {idx for idx in cluster if idx < next_pred}
        if len(cluster) >= 2:
            merged = set(checked_indexes)
            merged.add(max(cluster))
            return sorted(idx for idx in merged if 0 <= idx < len(predicted_units))
    return checked_indexes


def _same_clear_noon_cluster(
    predicted_units: list[dict[str, Any]],
    center: int | None,
) -> set[int]:
    if center is None or not 0 <= center < len(predicted_units):
        return set()
    if not _is_clear_noon(predicted_units[center]):
        return set()

    indexes = {center}
    left = center - 1
    while left >= 0 and _is_clear_noon(predicted_units[left]):
        indexes.add(left)
        left -= 1

    right = center + 1
    while right < len(predicted_units) and _is_clear_noon(predicted_units[right]):
        indexes.add(right)
        right += 1

    return indexes


def _same_letter_cluster(
    predicted_units: list[dict[str, Any]],
    center: int,
    letter: str,
) -> set[int]:
    if center is None or not 0 <= center < len(predicted_units):
        return set()
    if predicted_units[center]["letter"] != letter:
        return set()

    indexes = {center}
    left = center - 1
    while left >= 0 and predicted_units[left]["letter"] == letter:
        indexes.add(left)
        left -= 1

    right = center + 1
    while right < len(predicted_units) and predicted_units[right]["letter"] == letter:
        indexes.add(right)
        right += 1

    return indexes


def _pronounced_next_ref_idx(ref_units: list[Any], next_ref_idx: int | None) -> int | None:
    if next_ref_idx is None or next_ref_idx + 1 >= len(ref_units):
        return next_ref_idx
    current = ref_units[next_ref_idx]
    following = ref_units[next_ref_idx + 1]
    if _is_definite_article_alef(current, following):
        return next_ref_idx + 1
    return next_ref_idx


def _is_definite_article_alef(current: Any, following: Any) -> bool:
    alef_letters = {"\u0627", "\u0623", "\u0625", "\u0622", "\u0671"}
    return (
        current.letter in alef_letters
        and normalize_letter(following.letter) == "\u0644"
        and current.word_index == following.word_index
    )


def _iqlab_checked_indexes(
    source_ref_idx: int,
    source_end_ref_idx: int | None,
    next_ref_idx: int | None,
    ref_to_pred: dict[int, int],
    ref_len: int,
    predicted_units: list[dict[str, Any]],
    ref_units: list[Any],
) -> tuple[list[int], str, int]:
    predicted_len = len(predicted_units)
    next_pred, context_ok = _locate_iqlab_baa(
        source_ref_idx=source_ref_idx,
        next_ref_idx=next_ref_idx,
        ref_to_pred=ref_to_pred,
        ref_len=ref_len,
        predicted_units=predicted_units,
        ref_units=ref_units,
    )
    if not context_ok:
        return [], "missing-local-baa-context", next_pred

    candidates: list[int] = []
    if next_pred > 0:
        candidates.append(next_pred - 1)

    for ref_idx in (source_ref_idx, source_end_ref_idx):
        if ref_idx is None:
            continue
        pred_idx = ref_to_pred.get(ref_idx)
        if pred_idx is not None and pred_idx < next_pred and predicted_units[pred_idx]["letter"] == MEEM:
            candidates.append(pred_idx)

    # If alignment skipped the inserted meem, check the nearest consonants before baa only.
    if not any(predicted_units[idx]["letter"] == MEEM for idx in candidates):
        for idx in range(max(0, next_pred - 3), next_pred):
            if predicted_units[idx]["letter"] in {MEEM, NOON}:
                candidates.append(idx)

    return sorted(set(idx for idx in candidates if 0 <= idx < predicted_len)), "nearest-before-baa", next_pred


def _locate_iqlab_baa(
    source_ref_idx: int,
    next_ref_idx: int | None,
    ref_to_pred: dict[int, int],
    ref_len: int,
    predicted_units: list[dict[str, Any]],
    ref_units: list[Any],
) -> tuple[int, bool]:
    predicted_len = len(predicted_units)
    estimated = _pred_index_for_ref(next_ref_idx, ref_to_pred, ref_len, predicted_len)
    if estimated is None:
        estimated = 0
    ratio_estimated = _ratio_pred_index(next_ref_idx, ref_len, predicted_len)
    aligned = ref_to_pred.get(next_ref_idx) if next_ref_idx is not None else None
    expected_after = _reference_letters_count(ref_units, next_ref_idx, 6)
    expected_before = _reference_letters_slice(ref_units, max(0, source_ref_idx - 3), source_ref_idx)
    matches = [
        idx for idx, unit in enumerate(predicted_units)
        if unit["letter"] == "\u0628"
    ]
    if not matches:
        return _clamp_index(ratio_estimated, predicted_len), False

    scored: list[tuple[float, int, int, int]] = []
    for idx in matches:
        forward_matches = _forward_context_matches(predicted_units, idx, expected_after)
        backward_matches = _backward_context_matches(predicted_units, idx - 2, expected_before)
        marker_bonus = 0
        if idx > 0:
            if predicted_units[idx - 1]["letter"] == MEEM:
                marker_bonus = 4
            elif _is_clear_noon(predicted_units[idx - 1]):
                marker_bonus = 3
        alignment_bonus = 2 if aligned == idx else 0
        distance_penalty = min(abs(idx - estimated), abs(idx - ratio_estimated)) * 0.2
        score = (forward_matches * 5) + (backward_matches * 2) + marker_bonus + alignment_bonus - distance_penalty
        scored.append((score, forward_matches, backward_matches, idx))

    _, forward_matches, backward_matches, best_idx = max(scored, key=lambda item: (item[0], -abs(item[3] - ratio_estimated)))
    required_forward = min(3, len(expected_after)) if expected_after else 1
    close_to_text_position = abs(best_idx - ratio_estimated) <= 4
    context_ok = forward_matches >= required_forward or close_to_text_position or backward_matches >= 2
    if context_ok:
        return best_idx, True
    return _clamp_index(ratio_estimated, predicted_len), False


def _reference_letters_count(ref_units: list[Any], start: int | None, count: int) -> list[str]:
    if start is None or start < 0:
        return []
    end = min(len(ref_units), start + count)
    return [normalize_letter(unit.letter) for unit in ref_units[start:end]]


def _reference_letters_slice(ref_units: list[Any], start: int | None, end: int | None) -> list[str]:
    if start is None or end is None or start < 0 or end <= start:
        return []
    end = min(len(ref_units), end)
    return [normalize_letter(unit.letter) for unit in ref_units[start:end]]


def _forward_context_matches(
    predicted_units: list[dict[str, Any]],
    start: int,
    expected_letters: list[str],
) -> int:
    matches = 0
    for offset, expected in enumerate(expected_letters):
        idx = start + offset
        if idx >= len(predicted_units):
            break
        if predicted_units[idx]["letter"] == expected:
            matches += 1
    return matches


def _backward_context_matches(
    predicted_units: list[dict[str, Any]],
    start: int,
    expected_letters: list[str],
) -> int:
    matches = 0
    for offset, expected in enumerate(reversed(expected_letters)):
        idx = start - offset
        if idx < 0:
            break
        if predicted_units[idx]["letter"] == expected:
            matches += 1
    return matches


def _tanween_checked_indexes(
    source_ref_idx: int,
    source_end_ref_idx: int | None,
    next_ref_idx: int | None,
    ref_to_pred: dict[int, int],
    ref_len: int,
    predicted_len: int,
) -> tuple[list[int], str]:
    source_end_pred = ref_to_pred.get(source_end_ref_idx) if source_end_ref_idx is not None else None
    source_start_pred = ref_to_pred.get(source_ref_idx)
    next_pred = _pred_index_for_ref(next_ref_idx, ref_to_pred, ref_len, predicted_len)
    if next_pred is None:
        return [], "missing-next-letter"

    left = source_end_pred if source_end_pred is not None else source_start_pred
    if left is None:
        left = _nearest_pred_before(source_ref_idx, ref_to_pred)
    if left is None:
        return [], "missing-source-letter"

    start = min(predicted_len, left + 1)
    end = max(0, min(predicted_len, next_pred))
    if end < start:
        return [], "inverted-tanween-gap"
    return list(range(start, end)), "source-to-next-gap"


def _noon_sakinah_checked_indexes(
    source_ref_idx: int,
    next_ref_idx: int | None,
    ref_to_pred: dict[int, int],
    ref_len: int,
    predicted_len: int,
) -> tuple[list[int], str]:
    checked: list[int] = []
    source_pred = ref_to_pred.get(source_ref_idx)
    next_pred = _pred_index_for_ref(next_ref_idx, ref_to_pred, ref_len, predicted_len)
    if source_pred is not None and (next_pred is None or source_pred < next_pred):
        checked.append(source_pred)
        return checked, "aligned-source-noon"

    previous_pred = _nearest_pred_before(source_ref_idx, ref_to_pred)
    if previous_pred is None or next_pred is None:
        estimated = _pred_index_for_ref(source_ref_idx, ref_to_pred, ref_len, predicted_len)
        if estimated is not None and (next_pred is None or estimated < next_pred):
            return [estimated], "estimated-source-noon"
        return [], "missing-source-gap"

    start = min(predicted_len, previous_pred + 1)
    end = max(0, min(predicted_len, next_pred))
    if end < start:
        return [], "empty-source-gap"
    return list(range(start, end)), "previous-to-next-gap"


def _pred_index_for_ref(
    ref_idx: int | None,
    ref_to_pred: dict[int, int],
    ref_len: int,
    predicted_len: int,
) -> int | None:
    if ref_idx is None or predicted_len <= 0:
        return None
    if ref_idx in ref_to_pred:
        return ref_to_pred[ref_idx]
    interpolated = _interpolate_pred_index(ref_idx, ref_to_pred)
    if interpolated is not None:
        return max(0, min(predicted_len - 1, interpolated))
    if ref_len <= 0:
        return None
    return max(0, min(predicted_len - 1, round((ref_idx / ref_len) * (predicted_len - 1))))


def _ratio_pred_index(ref_idx: int | None, ref_len: int, predicted_len: int) -> int:
    if ref_idx is None or ref_len <= 0 or predicted_len <= 0:
        return 0
    return _clamp_index(round((ref_idx / ref_len) * (predicted_len - 1)), predicted_len)


def _clamp_index(index: int, predicted_len: int) -> int:
    if predicted_len <= 0:
        return 0
    return max(0, min(predicted_len - 1, index))


def _nearest_pred_before(ref_idx: int, ref_to_pred: dict[int, int]) -> int | None:
    before = [item for item in ref_to_pred if item < ref_idx]
    if not before:
        return None
    return ref_to_pred[max(before)]


def _locate_anchor(
    source_ref_idx: int | None,
    next_ref_idx: int | None,
    ref_to_pred: dict[int, int],
    ref_len: int,
    predicted_len: int,
) -> tuple[int | None, str]:
    if predicted_len <= 0:
        return None, "empty-phonetic-script"
    if next_ref_idx is not None and next_ref_idx in ref_to_pred:
        return ref_to_pred[next_ref_idx], "aligned-next-letter"
    if source_ref_idx is not None and source_ref_idx in ref_to_pred:
        return ref_to_pred[source_ref_idx], "aligned-source-letter"

    target_idx = next_ref_idx if next_ref_idx is not None else source_ref_idx
    if target_idx is None:
        return None, "missing-reference-index"

    nearest = _interpolate_pred_index(target_idx, ref_to_pred)
    if nearest is not None:
        return max(0, min(predicted_len - 1, nearest)), "interpolated"

    if ref_len <= 0:
        return None, "empty-reference"
    estimated = round((target_idx / ref_len) * max(0, predicted_len - 1))
    return max(0, min(predicted_len - 1, estimated)), "estimated-ratio"


def _interpolate_pred_index(ref_idx: int, ref_to_pred: dict[int, int]) -> int | None:
    if not ref_to_pred:
        return None
    before = [item for item in ref_to_pred if item < ref_idx]
    after = [item for item in ref_to_pred if item > ref_idx]
    if before and after:
        left_ref = max(before)
        right_ref = min(after)
        left_pred = ref_to_pred[left_ref]
        right_pred = ref_to_pred[right_ref]
        if right_ref == left_ref:
            return left_pred
        ratio = (ref_idx - left_ref) / (right_ref - left_ref)
        return round(left_pred + ratio * (right_pred - left_pred))
    if before:
        left_ref = max(before)
        return ref_to_pred[left_ref] + min(4, ref_idx - left_ref)
    right_ref = min(after)
    return ref_to_pred[right_ref] - min(4, right_ref - ref_idx)


def _case_window(
    anchor: int,
    source_ref_idx: int | None,
    next_ref_idx: int | None,
    ref_to_pred: dict[int, int],
    predicted_len: int,
) -> tuple[int, int]:
    anchors = [anchor]
    if source_ref_idx is not None and source_ref_idx in ref_to_pred:
        anchors.append(ref_to_pred[source_ref_idx])
    if next_ref_idx is not None and next_ref_idx in ref_to_pred:
        anchors.append(ref_to_pred[next_ref_idx])

    start = max(0, min(anchors) - 3)
    end = min(predicted_len, max(anchors) + 5)
    if end <= start:
        end = min(predicted_len, start + 1)
    return start, end
