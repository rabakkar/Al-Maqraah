from __future__ import annotations

import json
import math
import os
from functools import lru_cache
from pathlib import Path
from typing import Any

import numpy as np
from scipy.signal import resample_poly
import wave


STATUS_LABELS = {
    "passed": "\u0645\u0637\u0627\u0628\u0642",
    "needs_review": "\u064a\u062d\u062a\u0627\u062c \u0645\u0631\u0627\u062c\u0639\u0629",
    "unverified": "\u063a\u064a\u0631 \u0645\u0624\u0643\u062f",
}



def read_wav_mono(path: Path) -> tuple[np.ndarray, int]:
    with wave.open(str(path), "rb") as wav:
        channels = wav.getnchannels()
        sample_width = wav.getsampwidth()
        sample_rate = wav.getframerate()
        frames = wav.readframes(wav.getnframes())

    if sample_width == 1:
        raw = np.frombuffer(frames, dtype=np.uint8).astype(np.float32)
        audio = (raw - 128.0) / 128.0
    elif sample_width == 2:
        audio = np.frombuffer(frames, dtype=np.int16).astype(np.float32) / 32768.0
    elif sample_width == 4:
        audio = np.frombuffer(frames, dtype=np.int32).astype(np.float32) / 2147483648.0
    else:
        raise ValueError("\u0635\u064a\u063a\u0629 WAV \u063a\u064a\u0631 \u0645\u062f\u0639\u0648\u0645\u0629")

    if channels > 1:
        audio = audio.reshape(-1, channels).mean(axis=1)
    return audio.astype(np.float32), sample_rate



TARGET_SAMPLE_RATE = 16_000
DEFAULT_MODEL_DIR = Path(__file__).resolve().parents[1] / "muaalem-model-v3_2"


def extract_phonetic_script(
    audio_path: Path,
    model_dir: Path = DEFAULT_MODEL_DIR,
) -> dict[str, Any]:
    samples, sample_rate = read_wav_mono(audio_path)
    duration = len(samples) / sample_rate if sample_rate else 0.0
    if not len(samples):
        raise ValueError("ملف الصوت فارغ.")

    prepared = _prepare_audio(samples, sample_rate)
    extractor = _get_extractor(str(model_dir.resolve()))
    result = extractor.transcribe(prepared)

    return {
        "model": model_dir.name,
        "sample_rate": TARGET_SAMPLE_RATE,
        "audio_duration": round(duration, 2),
        "text": result["text"],
        "token_count": len(result["tokens"]),
        "average_confidence": result["average_confidence"],
        "tokens": result["tokens"],
    }


def _prepare_audio(samples: np.ndarray, sample_rate: int) -> np.ndarray:
    audio = np.asarray(samples, dtype=np.float32)
    if sample_rate != TARGET_SAMPLE_RATE:
        divisor = math.gcd(sample_rate, TARGET_SAMPLE_RATE)
        audio = resample_poly(audio, TARGET_SAMPLE_RATE // divisor, sample_rate // divisor).astype(np.float32)
    return np.clip(audio, -1.0, 1.0)


@lru_cache(maxsize=1)
def _get_extractor(model_dir: str) -> "_MuaalemPhonemeExtractor":
    return _MuaalemPhonemeExtractor(Path(model_dir))


class _MuaalemPhonemeExtractor:
    def __init__(self, model_dir: Path) -> None:
        if not model_dir.exists():
            raise FileNotFoundError(f"لم يتم العثور على مجلد المودل: {model_dir}")

        _prepare_ml_environment()
        self.model_dir = model_dir
        self.torch, self.model, self.processor, self.device, self.dtype = _load_model(model_dir)
        self.id_to_phoneme = _load_phoneme_vocab(model_dir)

    def transcribe(self, samples: np.ndarray) -> dict[str, Any]:
        features = self.processor(
            [samples],
            sampling_rate=TARGET_SAMPLE_RATE,
            return_tensors="pt",
            padding=True,
        )

        prepared_features = {}
        for key, value in features.items():
            if key == "input_features":
                prepared_features[key] = value.to(self.device, dtype=self.dtype)
            else:
                prepared_features[key] = value.to(self.device)

        with self.torch.inference_mode():
            output = self.model(**prepared_features, return_dict=False)[0]
            probabilities = self.torch.nn.functional.softmax(output["phonemes"], dim=-1).cpu()

        tokens = _ctc_greedy_decode(probabilities[0], self.id_to_phoneme)
        text = "".join(item["token"] for item in tokens)
        confidence = float(np.mean([item["confidence"] for item in tokens])) if tokens else 0.0

        return {
            "text": text,
            "average_confidence": round(confidence * 100, 2),
            "tokens": tokens,
        }


def _prepare_ml_environment() -> None:
    project_root = Path(__file__).resolve().parents[1]
    os.environ.setdefault("KMP_DUPLICATE_LIB_OK", "TRUE")
    os.environ.setdefault("USE_TF", "0")
    os.environ.setdefault("TRANSFORMERS_NO_TF", "1")
    os.environ.setdefault("USE_FLAX", "0")
    os.environ.setdefault("USE_TORCH", "1")
    os.environ.setdefault("HF_HUB_OFFLINE", "1")
    os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")
    os.environ.setdefault("NUMBA_CACHE_DIR", str(project_root / ".numba_cache"))


def _load_model(model_dir: Path) -> tuple[Any, Any, Any, Any, Any]:
    import torch
    from torch import nn
    from transformers import AutoFeatureExtractor
    from transformers.modeling_outputs import CausalLMOutput
    from transformers.models.wav2vec2_bert.configuration_wav2vec2_bert import Wav2Vec2BertConfig
    from transformers.models.wav2vec2_bert.modeling_wav2vec2_bert import (
        Wav2Vec2BertModel,
        Wav2Vec2BertPreTrainedModel,
        _HIDDEN_STATES_START_POSITION,
    )

    class MultiLevelCTCConfig(Wav2Vec2BertConfig):
        model_type = "multi_level_ctc"

        def __init__(
            self,
            level_to_vocab_size: dict[str, int] | None = None,
            level_to_loss_weight: dict[str, float] | None = None,
            **kwargs: Any,
        ) -> None:
            super().__init__(**kwargs)
            self.level_to_vocab_size = level_to_vocab_size or {}
            self.level_to_loss_weight = level_to_loss_weight or {"phonemes": 1.0}

    class Wav2Vec2BertForMultilevelCTC(Wav2Vec2BertPreTrainedModel):
        config_class = MultiLevelCTCConfig

        def __init__(self, config: MultiLevelCTCConfig) -> None:
            super().__init__(config)
            self.wav2vec2_bert = Wav2Vec2BertModel(config)
            self.dropout = nn.Dropout(config.final_dropout)
            output_hidden_size = config.output_hidden_size if config.add_adapter else config.hidden_size
            self.level_to_lm_head = nn.ModuleDict(
                {
                    level: nn.Linear(output_hidden_size, vocab_size)
                    for level, vocab_size in config.level_to_vocab_size.items()
                }
            )
            self.post_init()

        def forward(
            self,
            input_features: Any,
            attention_mask: Any = None,
            output_attentions: bool | None = None,
            output_hidden_states: bool | None = None,
            return_dict: bool | None = None,
            labels: dict[str, Any] | None = None,
        ) -> Any:
            return_dict = return_dict if return_dict is not None else self.config.use_return_dict
            outputs = self.wav2vec2_bert(
                input_features,
                attention_mask=attention_mask,
                output_attentions=output_attentions,
                output_hidden_states=output_hidden_states,
                return_dict=return_dict,
            )
            hidden_states = self.dropout(outputs[0])
            level_to_logits = {
                level: lm_head(hidden_states)
                for level, lm_head in self.level_to_lm_head.items()
            }

            if not return_dict:
                output = (level_to_logits,) + outputs[_HIDDEN_STATES_START_POSITION:]
                return ((None,) + output) if labels is not None else output

            return CausalLMOutput(
                loss=None,
                logits=level_to_logits,
                hidden_states=outputs.hidden_states,
                attentions=outputs.attentions,
            )

    config = MultiLevelCTCConfig.from_pretrained(str(model_dir), local_files_only=True)
    model = Wav2Vec2BertForMultilevelCTC.from_pretrained(
        str(model_dir),
        config=config,
        local_files_only=True,
    )
    processor = AutoFeatureExtractor.from_pretrained(str(model_dir), local_files_only=True)

    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    dtype = torch.bfloat16 if device.type == "cuda" else torch.float32
    model.to(device=device, dtype=dtype)
    model.eval()
    return torch, model, processor, device, dtype


def _load_phoneme_vocab(model_dir: Path) -> dict[int, str]:
    vocab_path = model_dir / "vocab.json"
    with vocab_path.open("r", encoding="utf-8") as file:
        vocab = json.load(file)
    phonemes = vocab.get("phonemes")
    if not isinstance(phonemes, dict):
        raise ValueError("لم يتم العثور على مستوى phonemes داخل vocab.json.")
    return {int(idx): token for token, idx in phonemes.items()}


def _ctc_greedy_decode(probabilities: Any, id_to_phoneme: dict[int, str], blank_id: int = 0) -> list[dict[str, Any]]:
    token_probs, token_ids = probabilities.max(dim=-1)
    tokens: list[dict[str, Any]] = []
    active_id: int | None = None
    active_probs: list[float] = []

    def flush() -> None:
        nonlocal active_id, active_probs
        if active_id is None or active_id == blank_id:
            active_id = None
            active_probs = []
            return
        tokens.append(
            {
                "id": int(active_id),
                "token": id_to_phoneme.get(int(active_id), ""),
                "confidence": round(float(np.mean(active_probs)), 4),
            }
        )
        active_id = None
        active_probs = []

    for token_id_tensor, probability_tensor in zip(token_ids, token_probs):
        token_id = int(token_id_tensor)
        probability = float(probability_tensor)
        if token_id == blank_id:
            flush()
            continue
        if active_id is None:
            active_id = token_id
            active_probs = [probability]
        elif token_id == active_id:
            active_probs.append(probability)
        else:
            flush()
            active_id = token_id
            active_probs = [probability]

    flush()
    return [item for item in tokens if item["token"]]
