from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Literal, Sequence


RuleName = Literal["izhar", "idgham", "iqlab", "ikhfa", "unknown"]
SourceType = Literal["noon_sakinah", "tanween"]

NOON = "\u0646"
ALEF = "\u0627"
ALEF_MAKSORA = "\u0649"
TAA_MARBOOTA = "\u0629"
HAMZA = "\u0621"

SUKUN = "\u0652"
SHADDA = "\u0651"
FATHA = "\u064e"
DAMMA = "\u064f"
KASRA = "\u0650"
FATHATAN = "\u064b"
DAMMATAN = "\u064c"
KASRATAN = "\u064d"
TATWEEL = "\u0640"

TANWEEN_MARKS = {FATHATAN, DAMMATAN, KASRATAN}
HARAKAT = {FATHA, DAMMA, KASRA, FATHATAN, DAMMATAN, KASRATAN, SUKUN, SHADDA}
SHORT_VOWEL_MARKS = {FATHA, DAMMA, KASRA, FATHATAN, DAMMATAN, KASRATAN}
QURANIC_MARKS = {chr(i) for i in range(0x06D6, 0x06EE)}
DIACRITICS = HARAKAT | QURANIC_MARKS

EXEMPT_STOP_MARK_LABELS = {
    "\u06d7": "\u0642\u0644\u0649",
    "\u06da": "\u062c",
}
EXEMPT_STOP_MARKS = set(EXEMPT_STOP_MARK_LABELS)

HAMZA_FORMS = set("\u0621\u0623\u0625\u0624\u0626\u0622\u0671")
IZHAR_LETTERS = set("\u0621\u0647\u0639\u062d\u063a\u062e") | HAMZA_FORMS
IDGHAM_WITH_GHUNNAH = set("\u064a\u0646\u0645\u0648")
IDGHAM_WITHOUT_GHUNNAH = set("\u0644\u0631")
IDGHAM_LETTERS = IDGHAM_WITH_GHUNNAH | IDGHAM_WITHOUT_GHUNNAH
IQLAB_LETTERS = {"\u0628"}
IKHFA_LETTERS = set("\u0635\u0630\u062b\u0643\u062c\u0634\u0642\u0633\u0637\u0632\u062f\u0641\u062a\u0636\u0638")

ARABIC_BASE_LETTERS = set(
    "\u0627\u0628\u062a\u062b\u062c\u062d\u062e\u062f\u0630\u0631\u0632"
    "\u0633\u0634\u0635\u0636\u0637\u0638\u0639\u063a\u0641\u0642\u0643"
    "\u0644\u0645\u0646\u0647\u0648\u064a\u0649\u0629\u0621\u0623\u0625"
    "\u0624\u0626\u0622\u0671"
)

RULE_LABELS = {
    "izhar": "\u0625\u0638\u0647\u0627\u0631",
    "idgham": "\u0625\u062f\u063a\u0627\u0645",
    "iqlab": "\u0625\u0642\u0644\u0627\u0628",
    "ikhfa": "\u0625\u062e\u0641\u0627\u0621",
    "unknown": "\u063a\u064a\u0631 \u0645\u0639\u0631\u0648\u0641",
}

SOURCE_LABELS = {
    "noon_sakinah": "\u0646\u0648\u0646 \u0633\u0627\u0643\u0646\u0629",
    "tanween": "\u062a\u0646\u0648\u064a\u0646",
}


@dataclass(frozen=True)
class LetterUnit:
    index: int
    start: int
    end: int
    letter: str
    marks: str
    word_index: int


@dataclass(frozen=True)
class TajweedCase:
    case_id: int
    source_type: SourceType
    rule: RuleName
    start: int
    end: int
    source_text: str
    next_letter: str
    next_start: int
    next_end: int
    has_ghunnah: bool
    same_word: bool
    rule_detail: str

    def to_dict(self) -> dict:
        data = asdict(self)
        data["rule_label"] = RULE_LABELS[self.rule]
        data["source_label"] = SOURCE_LABELS[self.source_type]
        data["needs_ghunnah"] = self.has_ghunnah
        return data


def normalize_letter(letter: str) -> str:
    if letter in HAMZA_FORMS:
        return HAMZA
    if letter == ALEF_MAKSORA:
        return "\u064a"
    if letter == TAA_MARBOOTA:
        return "\u0647"
    return letter


def iter_letter_units(text: str) -> list[LetterUnit]:
    units: list[LetterUnit] = []
    word_index = -1
    in_word = False
    i = 0

    while i < len(text):
        ch = text[i]
        if ch.isspace():
            in_word = False
            i += 1
            continue
        if ch == TATWEEL or ch not in ARABIC_BASE_LETTERS:
            i += 1
            continue

        if not in_word:
            word_index += 1
            in_word = True

        j = i + 1
        marks: list[str] = []
        while j < len(text) and text[j] in DIACRITICS:
            marks.append(text[j])
            j += 1

        units.append(
            LetterUnit(
                index=len(units),
                start=i,
                end=j,
                letter=ch,
                marks="".join(marks),
                word_index=word_index,
            )
        )
        i = j

    return units


def classify_expected_rule(next_letter: str) -> tuple[RuleName, bool, str]:
    letter = normalize_letter(next_letter)
    if letter in IZHAR_LETTERS:
        return "izhar", False, "\u0625\u0638\u0647\u0627\u0631 \u062d\u0644\u0642\u064a"
    if letter in IQLAB_LETTERS:
        return "iqlab", True, "\u0625\u0642\u0644\u0627\u0628 \u0645\u0639 \u063a\u0646\u0629"
    if letter in IKHFA_LETTERS:
        return "ikhfa", True, "\u0625\u062e\u0641\u0627\u0621 \u062d\u0642\u064a\u0642\u064a \u0645\u0639 \u063a\u0646\u0629"
    if letter in IDGHAM_LETTERS:
        if letter in IDGHAM_WITH_GHUNNAH:
            return "idgham", True, "\u0625\u062f\u063a\u0627\u0645 \u0628\u063a\u0646\u0629"
        return "idgham", False, "\u0625\u062f\u063a\u0627\u0645 \u0628\u063a\u064a\u0631 \u063a\u0646\u0629"
    return "unknown", False, "\u063a\u064a\u0631 \u0645\u0635\u0646\u0641"


def exempt_stop_marks_between(text: str, left_end: int, right_start: int) -> tuple[str, ...]:
    if right_start <= left_end:
        return ()
    return tuple(
        char for char in text[left_end:right_start]
        if char in EXEMPT_STOP_MARKS
    )


def is_noon_sakinah_source(unit: LetterUnit, next_unit: LetterUnit) -> bool:
    if normalize_letter(unit.letter) != NOON:
        return False
    if SUKUN in unit.marks:
        return True

    has_vowel = any(mark in SHORT_VOWEL_MARKS for mark in unit.marks)
    if has_vowel or SHADDA in unit.marks:
        return False

    next_letter = normalize_letter(next_unit.letter)
    rule_letters = IZHAR_LETTERS | IDGHAM_LETTERS | IQLAB_LETTERS | IKHFA_LETTERS
    return next_letter in rule_letters


def find_tajweed_cases(
    text: str,
    enabled_rules: Sequence[RuleName] | None = None,
) -> list[TajweedCase]:
    active_rules = set(enabled_rules or ("izhar", "idgham", "iqlab", "ikhfa"))
    units = iter_letter_units(text)
    cases: list[TajweedCase] = []

    for idx, unit in enumerate(units[:-1]):
        next_unit = units[idx + 1]
        source_end = unit.end
        source_type: SourceType | None = None

        if is_noon_sakinah_source(unit, next_unit):
            source_type = "noon_sakinah"
        elif any(mark in unit.marks for mark in TANWEEN_MARKS):
            source_type = "tanween"

        if source_type is None:
            continue

        if (
            source_type == "tanween"
            and FATHATAN in unit.marks
            and next_unit.letter in {ALEF, ALEF_MAKSORA}
            and next_unit.word_index == unit.word_index
            and idx + 2 < len(units)
        ):
            source_end = next_unit.end
            next_unit = units[idx + 2]

        rule, has_ghunnah, rule_detail = classify_expected_rule(next_unit.letter)

        # In words such as "الدنيا" and "بنيان", the noon is not read as idgham.
        # It is commonly taught as absolute izhar, so the app keeps it visible as izhar.
        same_word = unit.word_index == next_unit.word_index
        if source_type == "noon_sakinah" and rule == "idgham" and same_word:
            rule, has_ghunnah, rule_detail = "izhar", False, "\u0625\u0638\u0647\u0627\u0631 \u0645\u0637\u0644\u0642"

        if rule not in active_rules:
            continue

        if exempt_stop_marks_between(
            text,
            unit.start,
            next_unit.start,
        ):
            continue

        cases.append(
            TajweedCase(
                case_id=len(cases),
                source_type=source_type,
                rule=rule,
                start=unit.start,
                end=source_end,
                source_text=text[unit.start : source_end],
                next_letter=next_unit.letter,
                next_start=next_unit.start,
                next_end=next_unit.end,
                has_ghunnah=has_ghunnah,
                same_word=same_word,
                rule_detail=rule_detail,
            )
        )

    return cases


def count_non_space_letters(text: str) -> int:
    return sum(1 for ch in text if ch in ARABIC_BASE_LETTERS)
