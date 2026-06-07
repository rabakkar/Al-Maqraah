# -*- coding: utf-8 -*-
"""
Tajweed Local Inference
-----------------------
First run  : installs dependencies + downloads the model (~1-2 GB)
After that : runs fully offline
"""

import subprocess
import sys
import os

# ── Step 1: Install dependencies (skipped if already installed) ───────
REQUIRED = [
    "huggingface_hub",
    "quran-muaalem @ git+https://github.com/obadx/quran-muaalem.git",
    "quran-transcript",
    "librosa",
    "torch",
    "soundfile",
]

def install(package):
    subprocess.check_call([sys.executable, "-m", "pip", "install", "-q", package])

print("🔧 Checking dependencies...")
for pkg in REQUIRED:
    try:
        # quick check — just try importing the main packages
        if "huggingface_hub" in pkg:
            import huggingface_hub
        elif "quran-muaalem" in pkg:
            import quran_muaalem
        elif "quran-transcript" in pkg:
            import quran_transcript
        elif "librosa" in pkg:
            import librosa
        elif "torch" in pkg:
            import torch
    except ImportError:
        print(f"  ⬇ Installing {pkg} ...")
        install(pkg)

print("✅ All dependencies ready!\n")

# ── Step 2: Download model once, then load from local path ───────────
from huggingface_hub import snapshot_download

MODEL_DIR = os.path.join(os.path.dirname(__file__), "muaalem-model-v3_2")

if not os.path.isdir(MODEL_DIR) or not os.listdir(MODEL_DIR):
    print("⬇  Downloading model for the first time (~1-2 GB) ...")
    snapshot_download(
        repo_id="obadx/muaalem-model-v3_2",
        local_dir=MODEL_DIR,
        local_dir_use_symlinks=False,
    )
    print("✅ Model downloaded!\n")
else:
    print(f"✅ Model found at: {MODEL_DIR}\n")

# ── Step 3: Imports ───────────────────────────────────────────────────
import torch
import numpy as np
import librosa
import torch.nn.functional as F
from quran_muaalem import Muaalem
from quran_muaalem.decode import phonemes_level_greedy_decode

# ── Step 4: Load model from local path (offline) ─────────────────────
print("🔄 Loading model...")
os.environ["TRANSFORMERS_OFFLINE"] = "1"
os.environ["HF_DATASETS_OFFLINE"]  = "1"

muaalem = Muaalem(
    model_name_or_path=MODEL_DIR,
    device="cuda" if torch.cuda.is_available() else "cpu",
    dtype=torch.float32,
)
print(f"✅ Model ready! (device: {muaalem.device})\n")


