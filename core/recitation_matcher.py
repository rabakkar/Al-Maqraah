from __future__ import annotations

import re
from dataclasses import dataclass
from difflib import SequenceMatcher
from functools import lru_cache
from pathlib import Path
from typing import Any

from .muaalem_phonetics import TARGET_SAMPLE_RATE, _prepare_audio, _prepare_ml_environment, read_wav_mono
from .scoring import DEFAULT_SCORING_SETTINGS, normalize_scoring_settings


DEFAULT_WHISPER_DIR = Path(__file__).resolve().parents[1] / "whisper-quran"
DIACRITICS_RE = re.compile(r"[\u0610-\u061a\u064b-\u065f\u0670\u06d6-\u06ed]")
HARAKAT_RE = re.compile(r"[\u0610-\u061a\u064b-\u065f\u0670\u06d6-\u06ed]")
NON_ARABIC_RE = re.compile(r"[^\u0621-\u063a\u0641-\u064a\s]")
ARABIC_WORD_RE = re.compile(r"[\u0621-\u063a\u0641-\u064a]+")
ARABIC_TOKEN_WITH_MARKS_RE = re.compile(r"[\u0610-\u061a\u0621-\u063a\u0640-\u065f\u0670\u0671\u06d6-\u06ed]+")
SUKUN = "\u0652"
KASRA = "\u0650"
SHADDA = "\u0651"
DAGGER_ALEF = "\u0670"
TATWEEL = "\u0640"
HAMZA = "\u0621"
HAMZA_ABOVE = "\u0654"
ALEF = "\u0627"
LAM = "\u0644"
HEH = "\u0647"
SAD = "\u0635"
SEEN = "\u0633"
WAW = "\u0648"
YEH = "\u064a"
SMALL_WAW = "\u06e5"
SMALL_YEH = "\u06e6"
MAX_WORD_TEXT_VARIANTS = 128
SIGNIFICANT_HARAKAT = {
    "\u064e",
    "\u064f",
    "\u0650",
    "\u0652",
}

ARABIC_REPLACEMENTS = {
    "\u0622": "\u0627",
    "\u0623": "\u0627",
    "\u0625": "\u0627",
    "\u0671": "\u0627",
    "\u0624": "\u0648",
    "\u0626": "\u064a",
    "\u0649": "\u064a",
    "\u0629": "\u0647",
}
HARAKAT_ORDER = {
    mark: index
    for index, mark in enumerate(
        "\u0610\u0611\u0612\u0613\u0614\u0615\u0616\u0617\u0618\u0619\u061a"
        "\u064b\u064c\u064d\u064e\u064f\u0650\u0651\u0652\u0653\u0654\u0655"
        "\u0656\u0657\u0658\u0659\u065a\u065b\u065c\u065d\u065e\u065f\u0670"
    )
}

PASSAGE_MIN_COVERAGE = 0.70
SHORT_PASSAGE_MIN_COVERAGE = 0.67
PASSAGE_RECOVERY_COVERAGE = 0.60
PASSAGE_RECOVERY_SIMILARITY = 0.92


@dataclass(frozen=True)
class WordToken:
    text: str
    display: str
    raw: str
    marks_by_letter: tuple[tuple[str, tuple[str, ...]], ...]
    text_variants: tuple[str, ...]
    has_harakat: bool


def verify_required_recitation(
    audio_path: Path,
    selection: dict[str, Any],
    settings: dict[str, Any] | None = None,
    model_dir: Path = DEFAULT_WHISPER_DIR,
) -> dict[str, Any]:
    expected_text = str(selection.get("combined_text", "")).strip()
    transcript = _get_transcriber(str(model_dir.resolve())).transcribe(audio_path)
    return match_recitation_text(
        expected_text,
        transcript,
        settings=settings,
        model_name=model_dir.name,
        ignored_word_indexes=_rule_word_indexes(selection),
        end_of_ayah_word_indexes=_end_of_ayah_word_indexes(selection),
    )


def match_recitation_text(
    expected_text: str,
    transcript: str,
    settings: dict[str, Any] | None = None,
    model_name: str = "whisper-quran",
    ignored_word_indexes: set[int] | None = None,
    end_of_ayah_word_indexes: set[int] | None = None,
) -> dict[str, Any]:
    scoring_settings = normalize_scoring_settings(settings or DEFAULT_SCORING_SETTINGS)
    expected_tokens = normalize_word_tokens(expected_text)
    transcript_tokens = normalize_word_tokens(transcript)
    expected_words = [token.text for token in expected_tokens]
    transcript_words = [token.text for token in transcript_tokens]
    ignored_indexes = ignored_word_indexes or set()
    end_indexes = end_of_ayah_word_indexes or set()
    word_errors = _align_word_errors(expected_tokens, transcript_tokens, ignored_indexes, end_indexes)
    matched_words = int(word_errors["matched_words"])
    expected_count = len(expected_words)
    transcript_count = len(transcript_words)
    missing_words = len(word_errors["missing_word_indexes"])
    extra_words = len(word_errors["extra_word_indexes"])
    different_words = len(word_errors["different_word_indexes"])
    unmatched_words = len(word_errors["unmatched_word_indexes"])
    pronunciation_score = round((matched_words / max(1, expected_count, transcript_count)) * 100, 1)
    coverage = matched_words / max(1, expected_count)
    similarity = SequenceMatcher(None, " ".join(expected_words), " ".join(transcript_words)).ratio()
    passage_match = _evaluate_passage_match(
        expected_count=expected_count,
        transcript_count=transcript_count,
        matched_words=matched_words,
        coverage=coverage,
        similarity=similarity,
    )
    matches_expected = bool(passage_match["matches_expected"])
    status = "passed" if matches_expected else "failed"

    return {
        "model": model_name,
        "matches_expected": matches_expected,
        "status": status,
        "transcript": transcript,
        "normalized_transcript": " ".join(transcript_words),
        "expected_words": expected_count,
        "transcript_words": transcript_count,
        "matched_words": matched_words,
        "missing_words": missing_words,
        "extra_words": extra_words,
        "different_words": different_words,
        "unmatched_words": unmatched_words,
        "missing_word_indexes": word_errors["missing_word_indexes"],
        "extra_word_indexes": word_errors["extra_word_indexes"],
        "different_word_indexes": word_errors["different_word_indexes"],
        "unmatched_word_indexes": word_errors["unmatched_word_indexes"],
        "word_evaluations": word_errors["word_evaluations"],
        "ignored_word_indexes": sorted(ignored_indexes),
        "end_of_ayah_word_indexes": sorted(end_indexes),
        "ignored_word_errors": word_errors["ignored_word_errors"],
        "pronunciation_score": pronunciation_score,
        "coverage": round(coverage * 100, 1),
        "similarity": round(similarity * 100, 1),
        "required_coverage": passage_match["required_coverage"],
        "passage_match": passage_match,
        "settings": scoring_settings,
        "message": (
            "تم التأكد من أن الطالب قرأ الآيات المطلوبة."
            if matches_expected
            else passage_match["message"]
        ),
    }


def _rule_word_indexes(selection: dict[str, Any]) -> set[int]:
    indexes: set[int] = set()
    expanded_indexes = _selection_word_token_index_map(selection)
    for case in selection.get("tajweed_cases", []):
        for index in case.get("word_indexes", []):
            if index is not None:
                indexes.update(expanded_indexes.get(int(index), [int(index)]))
    return indexes


def _end_of_ayah_word_indexes(selection: dict[str, Any]) -> set[int]:
    expanded_indexes = _selection_word_token_index_map(selection)
    indexes_by_ayah: dict[int, int] = {}
    for word in selection.get("words", []):
        try:
            ayah = int(word["ayah"])
            index = int(word["index"])
        except (KeyError, TypeError, ValueError):
            continue
        token_indexes = expanded_indexes.get(index, [index])
        last_index = token_indexes[-1] if token_indexes else index
        indexes_by_ayah[ayah] = max(last_index, indexes_by_ayah.get(ayah, last_index))
    return set(indexes_by_ayah.values())


def _selection_word_token_index_map(selection: dict[str, Any]) -> dict[int, list[int]]:
    mapping: dict[int, list[int]] = {}
    cursor = 0
    for word in selection.get("words", []):
        try:
            index = int(word["index"])
        except (KeyError, TypeError, ValueError):
            continue
        token_count = len(normalize_word_tokens(str(word.get("text", ""))))
        if token_count <= 0:
            mapping[index] = []
            continue
        mapping[index] = list(range(cursor, cursor + token_count))
        cursor += token_count
    return mapping


def normalize_words(text: str) -> list[str]:
    return [token.text for token in normalize_word_tokens(text)]


def normalize_word_tokens(text: str) -> list[WordToken]:
    tokens: list[WordToken] = []
    for raw_token in ARABIC_TOKEN_WITH_MARKS_RE.findall(text):
        for part in _split_quranic_raw_token(raw_token):
            token = _build_word_token(part)
            if token is not None:
                tokens.append(token)
    return tokens


def normalize_arabic(text: str) -> str:
    value = DIACRITICS_RE.sub("", text)
    value = value.replace("\u0640", "")
    for source, target in ARABIC_REPLACEMENTS.items():
        value = value.replace(source, target)
    value = NON_ARABIC_RE.sub(" ", value)
    return " ".join(value.split())


def _build_word_token(raw_token: str) -> WordToken | None:
    groups: list[tuple[str, list[str]]] = []
    for char in raw_token:
        normalized_letter = _normalize_word_letter(char)
        if normalized_letter:
            groups.append((normalized_letter, []))
        elif char == TATWEEL:
            continue
        elif HARAKAT_RE.fullmatch(char) and groups:
            groups[-1][1].append(char)

    if not groups:
        return None

    marks_by_letter: list[tuple[str, tuple[str, ...]]] = []
    display_parts: list[str] = []
    for letter, marks in groups:
        ordered_marks = tuple(sorted(set(marks), key=lambda mark: HARAKAT_ORDER.get(mark, 999)))
        marks_by_letter.append((letter, ordered_marks))
        display_parts.append(letter + "".join(ordered_marks))

    display = _clean_display_word(raw_token) or "".join(display_parts)
    return WordToken(
        text="".join(letter for letter, _ in marks_by_letter),
        display=display,
        raw=raw_token,
        marks_by_letter=tuple(marks_by_letter),
        text_variants=_word_text_variants(tuple(marks_by_letter)),
        has_harakat=any(marks for _, marks in marks_by_letter),
    )


def _split_quranic_raw_token(raw_token: str) -> list[str]:
    groups: list[list[str]] = []
    for char in raw_token:
        if _normalize_word_letter(char):
            groups.append([char])
        elif groups and (char == TATWEEL or HARAKAT_RE.fullmatch(char)):
            groups[-1].append(char)

    if len(groups) > 1 and _is_split_vocative_or_alert_prefix(groups):
        return ["".join(groups[0]), "".join("".join(group) for group in groups[1:])]

    return [raw_token]


def _is_split_vocative_or_alert_prefix(groups: list[list[str]]) -> bool:
    first_letter = _normalize_word_letter(groups[0][0])
    second_letter = _normalize_word_letter(groups[1][0])
    if DAGGER_ALEF not in groups[0]:
        return False
    if first_letter == YEH:
        return True
    return first_letter == HEH and second_letter in {ALEF, HAMZA}


def _normalize_word_letter(char: str) -> str:
    normalized = ARABIC_REPLACEMENTS.get(char, char)
    if re.fullmatch(r"[\u0621-\u063a\u0641-\u064a]", normalized):
        return normalized
    return ""


def _clean_display_word(raw_token: str) -> str:
    parts: list[str] = []
    for char in raw_token:
        if re.fullmatch(r"[\u0621-\u063a\u0641-\u064a\u0671]", char) or HARAKAT_RE.fullmatch(char):
            parts.append(char)
    return "".join(parts)


def _token_similarity(expected: str, actual: str) -> float:
    if expected == actual:
        return 1.0
    if not expected or not actual:
        return 0.0
    return SequenceMatcher(None, expected, actual).ratio()


def _tokens_match(expected: str, actual: str) -> bool:
    if expected == actual:
        return True
    minimum = 0.78 if min(len(expected), len(actual)) <= 4 else 0.72
    return _token_similarity(expected, actual) >= minimum


def _word_text_variants(marks_by_letter: tuple[tuple[str, tuple[str, ...]], ...]) -> tuple[str, ...]:
    variants = [""]
    last_index = len(marks_by_letter) - 1
    for index, (letter, marks) in enumerate(marks_by_letter):
        options = [letter]
        if DAGGER_ALEF in marks:
            if letter == WAW:
                options.append(ALEF)
            if letter == YEH:
                options.append(ALEF)
            options.append(f"{letter}{ALEF}")
        if SMALL_YEH in marks:
            options.append(f"{letter}{YEH}")
        if SMALL_WAW in marks:
            options.append(f"{letter}{WAW}")
        if HAMZA_ABOVE in marks:
            options.append(f"{letter}{HAMZA}")
            options.append(f"{letter}{YEH}")
        if letter == LAM and SHADDA in marks:
            options.append(f"{LAM}{LAM}")
            if DAGGER_ALEF in marks:
                options.append(f"{LAM}{LAM}{ALEF}")
        if letter == SAD and "\u06dc" in marks:
            options.append(SEEN)
        if index == last_index and letter == YEH and KASRA in marks:
            options.append(f"{YEH}{YEH}")
        if index == last_index and letter == WAW:
            options.append(f"{WAW}{ALEF}")
        variants = _combine_text_variants(variants, tuple(dict.fromkeys(options)))
    return _expand_quranic_text_variants(variants)


def _combine_text_variants(prefixes: list[str], options: tuple[str, ...]) -> list[str]:
    combined: list[str] = []
    for prefix in prefixes:
        for option in options:
            combined.append(prefix + option)
            if len(combined) >= MAX_WORD_TEXT_VARIANTS:
                return combined
    return combined


def _expand_quranic_text_variants(base_variants: list[str]) -> tuple[str, ...]:
    expanded: list[str] = []
    seen: set[str] = set()
    for variant in base_variants:
        for spelling in _hamza_text_variants(variant):
            spelling = _collapse_repeated_alef(spelling)
            if spelling and spelling not in seen:
                seen.add(spelling)
                expanded.append(spelling)
                if len(expanded) >= MAX_WORD_TEXT_VARIANTS:
                    return tuple(expanded)
    return tuple(expanded)


def _collapse_repeated_alef(value: str) -> str:
    while f"{ALEF}{ALEF}" in value:
        value = value.replace(f"{ALEF}{ALEF}", ALEF)
    return value


def _hamza_text_variants(value: str) -> tuple[str, ...]:
    variants = [""]
    index = 0
    while index < len(value):
        char = value[index]
        if char == HAMZA and index + 1 < len(value) and value[index + 1] == ALEF:
            options = (f"{HAMZA}{ALEF}", ALEF, f"{ALEF}{ALEF}")
            index += 2
        elif char == HAMZA:
            options = (HAMZA, "", ALEF, WAW, YEH)
            index += 1
        else:
            options = (char,)
            index += 1
        variants = _combine_text_variants(variants, options)
    return tuple(dict.fromkeys(variants))


def _tokens_equivalent(expected_token: WordToken, actual_token: WordToken) -> bool:
    return bool(set(expected_token.text_variants).intersection(actual_token.text_variants))


def _evaluate_passage_match(
    expected_count: int,
    transcript_count: int,
    matched_words: int,
    coverage: float,
    similarity: float,
) -> dict[str, Any]:
    required_coverage = (
        SHORT_PASSAGE_MIN_COVERAGE
        if expected_count <= 3
        else PASSAGE_MIN_COVERAGE
    )
    if expected_count <= 0 or matched_words <= 0:
        return _passage_gate_payload(
            matches_expected=False,
            reason="empty-or-unmatched",
            required_coverage=required_coverage,
            message="التسجيل لا يبدو أنه للنص المطلوب. أعد التسجيل واقرأ الآيات المعروضة.",
        )

    coverage_ok = coverage >= required_coverage
    recovery_ok = (
        coverage >= PASSAGE_RECOVERY_COVERAGE
        and similarity >= PASSAGE_RECOVERY_SIMILARITY
        and transcript_count >= max(1, round(expected_count * PASSAGE_RECOVERY_COVERAGE))
    )
    if coverage_ok or recovery_ok:
        return _passage_gate_payload(
            matches_expected=True,
            reason="same-passage",
            required_coverage=required_coverage,
            message="تم التأكد من أن الطالب قرأ النص المطلوب بدرجة كافية.",
        )

    return _passage_gate_payload(
        matches_expected=False,
        reason="coverage-below-required",
        required_coverage=required_coverage,
        message=(
            "التسجيل لا يطابق الآيات المطلوبة بدرجة كافية. "
            "أعد التسجيل واقرأ النص المعروض كاملا قبل الإرسال."
        ),
    )


def _passage_gate_payload(
    matches_expected: bool,
    reason: str,
    required_coverage: float,
    message: str,
) -> dict[str, Any]:
    return {
        "matches_expected": matches_expected,
        "reason": reason,
        "required_coverage": round(required_coverage * 100, 1),
        "message": message,
    }


def _align_word_errors(
    expected_tokens: list[WordToken],
    transcript_tokens: list[WordToken],
    ignored_word_indexes: set[int] | None = None,
    end_of_ayah_word_indexes: set[int] | None = None,
) -> dict[str, Any]:
    missing_word_indexes: list[int] = []
    extra_word_indexes: list[int] = []
    different_word_indexes: list[int] = []
    unmatched_word_indexes: list[int] = []
    ignored_word_errors: list[dict[str, Any]] = []
    word_evaluations: list[dict[str, Any]] = []
    ignored_indexes = ignored_word_indexes or set()
    end_indexes = end_of_ayah_word_indexes or set()
    alignments = _word_alignment(expected_tokens, transcript_tokens)
    matched_words = 0

    for alignment in alignments:
        op = alignment["op"]
        expected_index = alignment.get("expected_index")
        actual_index = alignment.get("actual_index")
        expected_token = expected_tokens[expected_index] if expected_index is not None else None
        actual_token = transcript_tokens[actual_index] if actual_index is not None else None
        expected_ignored = expected_index in ignored_indexes if expected_index is not None else False

        if expected_ignored:
            if (
                op == "equal"
                and expected_token is not None
                and actual_token is not None
                and not _has_harakat_difference(
                    expected_token,
                    actual_token,
                    allow_final_sukun=expected_index in end_indexes,
                )
            ):
                word_evaluations.append(
                    _word_evaluation("matched", expected_index, actual_index, expected_token, actual_token)
                )
                matched_words += 1
                continue
            evaluation = _word_evaluation("ignored_rule_word", expected_index, actual_index, expected_token, actual_token)
            ignored_word_errors.append(evaluation)
            word_evaluations.append(evaluation)
            matched_words += 1
            continue

        if op == "equal":
            if (
                expected_token is not None
                and actual_token is not None
                and _has_harakat_difference(
                    expected_token,
                    actual_token,
                    allow_final_sukun=expected_index in end_indexes,
                )
            ):
                different_word_indexes.append(int(expected_index))
                word_evaluations.append(
                    _word_evaluation("different", expected_index, actual_index, expected_token, actual_token)
                )
            else:
                word_evaluations.append(
                    _word_evaluation("matched", expected_index, actual_index, expected_token, actual_token)
                )
            matched_words += 1
        elif op == "replace":
            unmatched_word_indexes.append(int(expected_index))
            word_evaluations.append(
                _word_evaluation("unmatched_word", expected_index, actual_index, expected_token, actual_token)
            )
        elif op == "delete":
            missing_word_indexes.append(int(expected_index))
            word_evaluations.append(
                _word_evaluation("missing", expected_index, None, expected_token, None)
            )
        elif op == "insert":
            if _insertion_touches_ignored_word(alignment, ignored_indexes):
                evaluation = _word_evaluation("ignored_rule_word", None, actual_index, None, actual_token)
                ignored_word_errors.append(evaluation)
                word_evaluations.append(evaluation)
                continue
            extra_word_indexes.append(int(actual_index))
            word_evaluations.append(
                _word_evaluation("extra", None, actual_index, None, actual_token)
            )

    return {
        "missing_word_indexes": missing_word_indexes,
        "extra_word_indexes": extra_word_indexes,
        "different_word_indexes": different_word_indexes,
        "unmatched_word_indexes": unmatched_word_indexes,
        "ignored_word_errors": ignored_word_errors,
        "word_evaluations": word_evaluations,
        "matched_words": matched_words,
    }


def _word_alignment(
    expected_tokens: list[WordToken],
    transcript_tokens: list[WordToken],
) -> list[dict[str, int | str | None]]:
    rows = len(expected_tokens) + 1
    columns = len(transcript_tokens) + 1
    costs = [[0] * columns for _ in range(rows)]
    ops = [[""] * columns for _ in range(rows)]

    for row in range(1, rows):
        costs[row][0] = row
        ops[row][0] = "delete"
    for column in range(1, columns):
        costs[0][column] = column
        ops[0][column] = "insert"

    for row in range(1, rows):
        expected = expected_tokens[row - 1]
        for column in range(1, columns):
            actual = transcript_tokens[column - 1]
            same_word = _tokens_equivalent(expected, actual)
            diagonal_cost = costs[row - 1][column - 1] + (0 if same_word else 1)
            delete_cost = costs[row - 1][column] + 1
            insert_cost = costs[row][column - 1] + 1
            best_cost = min(diagonal_cost, delete_cost, insert_cost)
            costs[row][column] = best_cost
            if diagonal_cost == best_cost:
                ops[row][column] = "equal" if same_word else "replace"
            elif delete_cost == best_cost:
                ops[row][column] = "delete"
            else:
                ops[row][column] = "insert"

    alignments: list[dict[str, int | str | None]] = []
    row = len(expected_tokens)
    column = len(transcript_tokens)
    while row > 0 or column > 0:
        op = ops[row][column]
        if row > 0 and column > 0 and op in {"equal", "replace"}:
            alignments.append(
                {
                    "op": op,
                    "expected_index": row - 1,
                    "actual_index": column - 1,
                }
            )
            row -= 1
            column -= 1
        elif row > 0 and (column == 0 or op == "delete"):
            alignments.append(
                {
                    "op": "delete",
                    "expected_index": row - 1,
                    "actual_index": None,
                }
            )
            row -= 1
        else:
            alignments.append(
                {
                    "op": "insert",
                    "expected_index": row,
                    "actual_index": column - 1,
                }
            )
            column -= 1

    alignments.reverse()
    return alignments


def _insertion_touches_ignored_word(
    alignment: dict[str, int | str | None],
    ignored_indexes: set[int],
) -> bool:
    anchor = alignment.get("expected_index")
    if anchor is None:
        return False
    return int(anchor) in ignored_indexes or int(anchor) - 1 in ignored_indexes


def _has_harakat_difference(
    expected_token: WordToken,
    actual_token: WordToken,
    allow_final_sukun: bool = False,
) -> bool:
    if not _tokens_equivalent(expected_token, actual_token) or not actual_token.has_harakat:
        return False
    if expected_token.text != actual_token.text:
        return False

    last_index = min(len(expected_token.marks_by_letter), len(actual_token.marks_by_letter)) - 1
    for index, ((expected_letter, expected_marks), (actual_letter, actual_marks)) in enumerate(zip(expected_token.marks_by_letter, actual_token.marks_by_letter)):
        actual_comparison_marks = _significant_marks(actual_marks)
        expected_comparison_marks = _comparison_marks(expected_marks)
        if _is_initial_alef_hamza_spelling_difference(
            index,
            expected_letter,
            actual_letter,
            expected_comparison_marks,
            actual_comparison_marks,
        ):
            continue
        if HAMZA_ABOVE in expected_marks and set(actual_comparison_marks).intersection(expected_comparison_marks):
            continue
        if (
            allow_final_sukun
            and index == last_index
            and actual_comparison_marks == (SUKUN,)
            and expected_comparison_marks
            and expected_comparison_marks != (SUKUN,)
        ):
            continue
        if actual_comparison_marks and expected_comparison_marks and actual_comparison_marks != expected_comparison_marks:
            return True
    return False


def _is_initial_alef_hamza_spelling_difference(
    index: int,
    expected_letter: str,
    actual_letter: str,
    expected_marks: tuple[str, ...],
    actual_marks: tuple[str, ...],
) -> bool:
    return (
        index == 0
        and expected_letter == ALEF
        and actual_letter == ALEF
        and bool(expected_marks or actual_marks)
    )


def _comparison_marks(expected_marks: tuple[str, ...]) -> tuple[str, ...]:
    significant_marks = _significant_marks(expected_marks)
    if significant_marks:
        return significant_marks
    if not expected_marks:
        return (SUKUN,)
    return ()


def _significant_marks(marks: tuple[str, ...]) -> tuple[str, ...]:
    return tuple(mark for mark in marks if mark in SIGNIFICANT_HARAKAT)


def _word_evaluation(
    status: str,
    expected_index: int | None,
    actual_index: int | None,
    expected_token: WordToken | None,
    actual_token: WordToken | None,
) -> dict[str, Any]:
    return {
        "status": status,
        "expected_index": expected_index,
        "actual_index": actual_index,
        "expected": expected_token.display if expected_token else "",
        "actual": actual_token.display if actual_token else "",
        "expected_normalized": expected_token.text if expected_token else "",
        "actual_normalized": actual_token.text if actual_token else "",
        "expected_has_harakat": expected_token.has_harakat if expected_token else False,
        "actual_has_harakat": actual_token.has_harakat if actual_token else False,
    }


@lru_cache(maxsize=1)
def _get_transcriber(model_dir: str) -> "_WhisperQuranTranscriber":
    return _WhisperQuranTranscriber(Path(model_dir))


class _WhisperQuranTranscriber:
    def __init__(self, model_dir: Path) -> None:
        if not model_dir.exists():
            raise FileNotFoundError(f"لم يتم العثور على مجلد مودل whisper: {model_dir}")

        _prepare_ml_environment()
        import torch
        from transformers import AutoModelForSpeechSeq2Seq, AutoProcessor

        self.torch = torch
        self.processor = AutoProcessor.from_pretrained(str(model_dir), local_files_only=True)
        self.model = AutoModelForSpeechSeq2Seq.from_pretrained(str(model_dir), local_files_only=True)
        self.device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
        self.dtype = torch.float16 if self.device.type == "cuda" else torch.float32
        self.model.to(device=self.device, dtype=self.dtype)
        self.model.eval()

    def transcribe(self, audio_path: Path) -> str:
        samples, sample_rate = read_wav_mono(audio_path)
        if not len(samples):
            raise ValueError("ملف الصوت فارغ.")

        prepared = _prepare_audio(samples, sample_rate)
        inputs = self.processor(
            prepared,
            sampling_rate=TARGET_SAMPLE_RATE,
            return_tensors="pt",
        )
        model_inputs = {
            key: self._to_device(value)
            for key, value in inputs.items()
        }

        generate_kwargs: dict[str, Any] = {"max_new_tokens": 440}

        with self.torch.inference_mode():
            predicted_ids = self.model.generate(**model_inputs, **generate_kwargs)

        transcript = self.processor.batch_decode(predicted_ids, skip_special_tokens=True)[0]
        transcript = re.sub(r"<\|[^|]+?\|>", "", transcript)
        return transcript.strip()

    def _to_device(self, value: Any) -> Any:
        if not hasattr(value, "to"):
            return value
        if hasattr(value, "is_floating_point") and value.is_floating_point():
            return value.to(self.device, dtype=self.dtype)
        return value.to(self.device)
