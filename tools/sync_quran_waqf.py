from __future__ import annotations

import json
from pathlib import Path
from urllib.request import Request, urlopen


PROJECT_ROOT = Path(__file__).resolve().parents[1]
BASE_QURAN_PATH = PROJECT_ROOT / "data" / "quran-uthmani-imlaey.json"
OUTPUT_QURAN_PATH = PROJECT_ROOT / "data" / "quran-uthmani-waqf.json"
QURAN_API_URL = "https://api.alquran.cloud/v1/quran/quran-uthmani"


def main() -> None:
    local = json.loads(BASE_QURAN_PATH.read_text(encoding="utf-8"))
    remote = _fetch_quran_uthmani()
    remote_surahs = remote["data"]["surahs"]
    bismillah = remote_surahs[0]["ayahs"][0]["text"].lstrip("\ufeff").strip()

    for surah in local["quran"]["sura"]:
        surah_index = int(surah["@index"])
        remote_ayahs = remote_surahs[surah_index - 1]["ayahs"]
        if len(remote_ayahs) != len(surah["aya"]):
            raise RuntimeError(f"ayah count mismatch in surah {surah_index}")

        for local_ayah, remote_ayah in zip(surah["aya"], remote_ayahs):
            if int(local_ayah["@index"]) != int(remote_ayah["numberInSurah"]):
                raise RuntimeError(f"ayah index mismatch in surah {surah_index}")
            text = str(remote_ayah["text"]).lstrip("\ufeff").strip()
            if surah_index not in {1, 9} and int(local_ayah["@index"]) == 1:
                text = _remove_api_bismillah(text, bismillah)
            local_ayah["@uthmani"] = text

    OUTPUT_QURAN_PATH.write_text(
        json.dumps(local, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(f"wrote {OUTPUT_QURAN_PATH}")


def _fetch_quran_uthmani() -> dict:
    request = Request(QURAN_API_URL, headers={"User-Agent": "Al-Maqraah/1.0"})
    with urlopen(request, timeout=90) as response:
        return json.loads(response.read().decode("utf-8-sig"))


def _remove_api_bismillah(text: str, bismillah: str) -> str:
    prefix = f"{bismillah} "
    if text.startswith(prefix):
        return text[len(prefix):]
    return text


if __name__ == "__main__":
    main()
