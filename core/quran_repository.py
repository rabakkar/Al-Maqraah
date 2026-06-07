from __future__ import annotations

import json
import re
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any

from .tajweed_rules import ARABIC_BASE_LETTERS, RuleName, find_tajweed_cases


WORD_PATTERN = re.compile(r"\S+", re.UNICODE)


@dataclass(frozen=True)
class Verse:
    surah: int
    ayah: int
    uthmani: str
    imlaey: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "surah": self.surah,
            "ayah": self.ayah,
            "uthmani": self.uthmani,
            "imlaey": self.imlaey,
        }


class QuranRepository:
    def __init__(self, data_path: Path) -> None:
        self.data_path = data_path
        self._surahs = self._load()

    def _load(self) -> list[dict[str, Any]]:
        with self.data_path.open("r", encoding="utf-8") as file:
            raw = json.load(file)

        surahs: list[dict[str, Any]] = []
        for item in raw["quran"]["sura"]:
            verses = [
                Verse(
                    surah=int(item["@index"]),
                    ayah=int(ayah["@index"]),
                    uthmani=ayah["@uthmani"],
                    imlaey=ayah["@imlaey"],
                )
                for ayah in item["aya"]
            ]
            surahs.append(
                {
                    "index": int(item["@index"]),
                    "name": item["@name"],
                    "ayah_count": len(verses),
                    "verses": verses,
                }
            )
        return surahs

    def get_surahs(self) -> list[dict[str, Any]]:
        return [
            {
                "index": surah["index"],
                "name": surah["name"],
                "ayah_count": surah["ayah_count"],
            }
            for surah in self._surahs
        ]

    def get_surah(self, surah_number: int) -> dict[str, Any]:
        if not 1 <= surah_number <= len(self._surahs):
            raise ValueError("\u0631\u0642\u0645 \u0627\u0644\u0633\u0648\u0631\u0629 \u063a\u064a\u0631 \u0635\u062d\u064a\u062d")
        return self._surahs[surah_number - 1]

    def get_verses(self, surah_number: int, ayah_from: int, ayah_to: int) -> list[Verse]:
        surah = self.get_surah(surah_number)
        ayah_count = surah["ayah_count"]
        if ayah_from < 1 or ayah_to < 1 or ayah_from > ayah_to or ayah_to > ayah_count:
            raise ValueError("\u0646\u0637\u0627\u0642 \u0627\u0644\u0622\u064a\u0627\u062a \u063a\u064a\u0631 \u0635\u062d\u064a\u062d")
        return surah["verses"][ayah_from - 1 : ayah_to]

    def build_selection(
        self,
        surah_number: int,
        ayah_from: int,
        ayah_to: int,
        enabled_rules: list[RuleName] | None = None,
    ) -> dict[str, Any]:
        surah = self.get_surah(surah_number)
        verses = self.get_verses(surah_number, ayah_from, ayah_to)

        parts: list[str] = []
        verse_offsets: list[dict[str, int]] = []
        cursor = 0
        for verse in verses:
            if parts:
                parts.append(" ")
                cursor += 1
            start = cursor
            parts.append(verse.uthmani)
            cursor += len(verse.uthmani)
            verse_offsets.append({"ayah": verse.ayah, "start": start, "end": cursor})

        combined_text = "".join(parts)
        cases = self._exclude_cross_ayah_boundary_cases(
            find_tajweed_cases(combined_text, enabled_rules=enabled_rules),
            verse_offsets,
        )
        words = self._build_words(combined_text, verse_offsets, cases)
        cases_payload = self._build_cases_payload(combined_text, verse_offsets, words, cases)

        stats = {"izhar": 0, "idgham": 0, "iqlab": 0, "ikhfa": 0, "unknown": 0}
        for case in cases:
            stats[case.rule] += 1

        return {
            "surah": {"index": surah["index"], "name": surah["name"], "ayah_count": surah["ayah_count"]},
            "ayah_from": ayah_from,
            "ayah_to": ayah_to,
            "verses": [verse.to_dict() for verse in verses],
            "combined_text": combined_text,
            "verse_offsets": verse_offsets,
            "words": words,
            "tajweed_cases": cases_payload,
            "stats": stats,
        }

    def _locate_ayah(self, position: int, verse_offsets: list[dict[str, int]]) -> int:
        for item in verse_offsets:
            if item["start"] <= position < item["end"]:
                return item["ayah"]
        return verse_offsets[-1]["ayah"]

    def _build_words(
        self,
        text: str,
        verse_offsets: list[dict[str, int]],
        cases: list[Any],
    ) -> list[dict[str, Any]]:
        words: list[dict[str, Any]] = []
        for match in WORD_PATTERN.finditer(text):
            if not any(char in ARABIC_BASE_LETTERS for char in match.group(0)):
                continue
            start, end = match.span()
            case_ids = [
                case.case_id
                for case in cases
                if _spans_overlap(start, end, case.start, max(case.next_end, case.end))
            ]
            words.append(
                {
                    "index": len(words),
                    "text": match.group(0),
                    "start": start,
                    "end": end,
                    "ayah": self._locate_ayah(start, verse_offsets),
                    "case_ids": case_ids,
                }
            )
        return words

    def _exclude_cross_ayah_boundary_cases(
        self,
        cases: list[Any],
        verse_offsets: list[dict[str, int]],
    ) -> list[Any]:
        filtered: list[Any] = []
        for case in cases:
            source_ayah = self._locate_ayah(case.start, verse_offsets)
            next_ayah = self._locate_ayah(case.next_start, verse_offsets)
            if source_ayah != next_ayah and not case.same_word:
                continue
            filtered.append(replace(case, case_id=len(filtered)))
        return filtered

    def _build_cases_payload(
        self,
        text: str,
        verse_offsets: list[dict[str, int]],
        words: list[dict[str, Any]],
        cases: list[Any],
    ) -> list[dict[str, Any]]:
        payload: list[dict[str, Any]] = []
        for case in cases:
            item = case.to_dict()
            case_span_end = max(case.next_end, case.end)
            item["ayah"] = self._locate_ayah(case.start, verse_offsets)
            item["snippet"] = _snippet(text, case.start, case_span_end)
            item["word_indexes"] = [
                word["index"]
                for word in words
                if _spans_overlap(word["start"], word["end"], case.start, case_span_end)
            ]
            payload.append(item)
        return payload


def _spans_overlap(a_start: int, a_end: int, b_start: int, b_end: int) -> bool:
    return a_start < b_end and b_start < a_end


def _snippet(text: str, start: int, end: int, radius: int = 18) -> str:
    left = max(0, start - radius)
    right = min(len(text), end + radius)
    return text[left:right].strip()
