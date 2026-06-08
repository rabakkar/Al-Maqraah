<div align="center">

<img src="Al-Maqraah/assets/icons/g-maqraah-logo.png" alt="Al-Maqra'ah Logo" width="160"/>

# Al-Maqra'ah — المقرأة

### Automatic Qur'an Recitation Level Evaluation

*An AI-powered web application for automatic evaluation of Qur'an recitation, focusing on the rules of Nūn Sākinah and Tanwīn.*

[![Watch Demo](https://img.shields.io/badge/▶_Watch_Demo-red?style=for-the-badge&logo=youtube&logoColor=white)](https://youtu.be/nG270QGE8Oc)
[![Live Page](https://img.shields.io/badge/🌐_Project_Page-8c6d3c?style=for-the-badge)](https://rabakkar.github.io/Al-Maqraah/)

</div>

---

## 🎥 Demo Video

<div align="center">

<a href="https://youtu.be/nG270QGE8Oc" target="_blank">
  <img src="https://img.youtube.com/vi/nG270QGE8Oc/maxresdefault.jpg" alt="Watch the Al-Maqra'ah demo on YouTube" width="700"/>
</a>

<p><em>▶ Click the thumbnail above to watch the full demonstration on YouTube</em></p>

</div>

---

## Table of Contents

* [Overview](#overview)
* [System Architecture](#system-architecture)
* [AI Pipeline](#ai-pipeline)
* [Project Structure](#project-structure)
* [Prerequisites](#prerequisites)
* [Installation](#installation)
* [Running the Application](#running-the-application)
* [User Roles & Workflow](#user-roles--workflow)
* [Scoring System](#scoring-system)
* [Key Modules](#key-modules)
* [Database Schema](#database-schema)
* [Configuration](#configuration)
* [Supported Tajwīd Rules](#supported-tajwīd-rules)
* [Limitations](#limitations)
* [Team](#team)

---

## Overview

**Al-Maqra'ah** (المقرأة) is a placement-based Qur'an recitation assessment system. The teacher publishes an assigned passage; each student records one recitation; the system automatically verifies, analyses, scores, and classifies the student into one of three proficiency levels.

### What the system does

1. **Verifies** that the student read the assigned passage (Whisper-Quran ASR model)
2. **Extracts** a fine-grained Qur'anic Phonetic Script from the audio (Muaalem Wav2Vec2-BERT model)
3. **Analyses** every Nūn Sākinah and Tanwīn case in the passage against the phonetic output (custom rule-based engine)
4. **Scores** the recitation using teacher-configured weights and word-error penalties
5. **Classifies** the student as beginner, intermediate, or advanced based on teacher-defined thresholds

### What it does NOT do

* Does not evaluate recitation fluency, speed, or melodic aspects
* Does not support narrations other than Hafs ʿan ʿĀsim
* Does not train or fine-tune any AI model (pre-trained models are used as-is)
* Does not allow the student to resubmit for the same assignment after the final submission

---

## System Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                      Browser (Frontend)                     │
│  Vanilla JS + HTML + CSS  │  MediaRecorder API (audio)     │
└───────────────┬─────────────────────────────────────────────┘
                │  HTTP / REST
┌───────────────▼─────────────────────────────────────────────┐
│                Flask Application (app.py)                   │
│  Authentication · Assignment API · Recitation API           │
│  Teacher API   · Admin API     · Static Files               │
└───────┬─────────────────────────────────────────┬───────────┘
        │                                         │
┌───────▼──────────────────┐        ┌────────────▼───────────┐
│     Core Modules          │        │      Database Layer     │
│  Tajweed_analysis.py      │        │  SQLite via database.py │
│  recitation_matcher.py    │        │  5 tables              │
│  muaalem_phonetics.py     │        └────────────────────────┘
│  quran_repository.py      │
│  scoring.py               │
│  tajweed_rules.py         │
└───────┬──────────────────┘
        │
┌───────▼──────────────────────────────────────────────────┐
│               Pre-Trained AI Models (local)              │
│  whisper-quran/          tarteel-ai/whisper-base-ar-quran │
│  muaalem-model-v3_2/     obadx/muaalem-model-v3_2        │
└──────────────────────────────────────────────────────────┘
```

---

## AI Pipeline

When a student submits a recitation, the backend runs the following pipeline:

```
Audio (WAV) ──► [1. Validation] ──► [2. Whisper-Quran]
                                           │
                                    Passage verified?
                                       No ──► Reject (422)
                                       Yes ──► Continue
                                           │
                                    [3. Muaalem Model]
                                           │
                                    Qur'anic Phonetic Script
                                           │
                                    [4. Rule Engine]
                                    (Tajweed_analysis.py)
                                           │
                                    Per-case verdicts
                                    passed / needs_review / unmatched
                                           │
                                    [5. Scoring Engine]
                                    (scoring.py)
                                           │
                                    Weighted score (0–100)
                                    Word-error penalties applied
                                           │
                                    [6. Level Classification]
                                    advanced (≥threshold) ?
                                    intermediate (≥threshold) ?
                                    beginner (fallback)
                                           │
                                    [7. Save to Database]
                                           │
                                    Result displayed to student & teacher
```

### Pre-Trained Models

|Model|Hugging Face ID|Purpose|
|-|-|-|
|Whisper-Quran|`tarteel-ai/whisper-base-ar-quran`|ASR — verifies that the student read the assigned passage|
|Muaalem|`obadx/muaalem-model-v3_2`|Wav2Vec2-BERT with multi-level CTC — produces Qur'anic Phonetic Script|

---

## Project Structure

```
project/
├── app.py                      # Flask application entry point, all API routes
├── database.py                 # All database operations (SQLite)
├── setup_models.py             # Downloads and verifies pre-trained models
├── tajweed_local.py            # Local tajweed testing utility
├── requirements.txt            # Python dependencies
│
├── core/
│   ├── Tajweed_analysis.py     # Rule-based Tajwīd analysis engine ⭐
│   ├── scoring.py              # Weighted scoring and level classification ⭐
│   ├── recitation_matcher.py   # Whisper verification + word-level matching
│   ├── muaalem_phonetics.py    # Muaalem model wrapper
│   ├── quran_repository.py     # Qur'an text loading and normalisation
│   └── tajweed_rules.py        # Tajwīd rule definitions and stop-mark data
│
├── Al-Maqraah/                 # Frontend HTML/CSS/JS
│   ├── index.html              # Public landing page
│   ├── login.html
│   ├── signup.html
│   ├── recording.html          # Student recording page
│   ├── result.html             # Student result page
│   ├── result_details.html     # Teacher result detail page
│   ├── teacher-dashboard.html
│   ├── scoring-settings.html   # Teacher scoring configuration
│   ├── teacher-student-results.html
│   ├── JavaScript/             # Frontend JS modules
│   ├── css/                    # Stylesheets
│   └── assets/                 # Images and icons
│
├── data/
│   ├── quran-uthmani-waqf.json          # Uthmani Qur'an text (primary, with waqf)
│   ├── quran-uthmani-imlaey.json        # Imlaey script (for display)
│   ├── alquran-cloud-quran-uthmani.raw.json  # Raw Qur'an source
│   └── maqraah.sqlite3                  # SQLite database
│
├── whisper-quran/              # Whisper model files (created by setup_models.py)
├── muaalem-model-v3_2/         # Muaalem model files (created by setup_models.py)
└── uploads/                    # Uploaded audio files (created automatically)
```

---

## Prerequisites

* Python 3.10 or later
* \~4 GB free disk space (for the two AI model downloads)
* Internet connection (for initial model download only)
* A microphone-capable browser (Chrome or Firefox recommended)
* **No GPU required** — the system runs on CPU

---

## Installation

### Step 1 — Clone the repository

```bash
git clone <repository-url>
cd project
```

### Step 2 — Create a virtual environment (recommended)

```bash
python -m venv venv
source venv/bin/activate        # Linux / macOS
venv\\Scripts\\activate           # Windows
```

### Step 3 — Install Python dependencies

```bash
pip install -r requirements.txt
```

### Step 4 — Download the AI models

```bash
python setup_models.py
```

This downloads the Whisper-Quran and Muaalem models from Hugging Face into the `whisper-quran/` and `muaalem-model-v3_2/` folders. Run this once; subsequent runs skip already-downloaded files.

To download only one model:

```bash
python setup_models.py --skip-muaalem   # Whisper only
python setup_models.py --skip-whisper   # Muaalem only
```

---

## Running the Application

```bash
python app.py
```

Then open your browser at:

```
http://127.0.0.1:5000
```

The port can be changed via the `PORT` environment variable:

```bash
PORT=8080 python app.py
```

---

## User Roles & Workflow

### Three Roles

|Role|Created by|Capabilities|
|-|-|-|
|**Student**|Self-registration (sign-up page)|Record recitation, view result|
|**Teacher**|Teacher-Administrator|Create assignment, configure scoring, view all student results|
|**Teacher-Administrator**|Another Teacher-Administrator (or first account in DB)|All Teacher capabilities + create new teacher accounts|

### Workflow

```
Teacher                              Student
──────                               ───────
1. Log in
2. Open Scoring Settings
   → Configure rules, weights,
     thresholds per level
3. Create / Update Assignment
   → Select surah + āyah range     4. Log in (or sign up)
                                    5. Open recording page
                                       → See assigned passage
                                    6. Record recitation
                                    7. Listen back, re-record if needed
                                    8. Submit final recording
                                         ↓
                                    [System evaluates]
                                         ↓
                                    9. View result:
                                       assigned level + per-rule breakdown

10. Open Students → select level
    → See list of students
    → Open student history
    → Open detailed recitation page
```

> \*\*Important:\*\* After submission, the assignment disappears from the student's view. If the teacher publishes a \*\*new\*\* assignment, it becomes visible and the student can submit again.

---

## Scoring System

Each proficiency level has independent settings:

|Setting|Description|Range|
|-|-|-|
|`placement_threshold`|Minimum score to reach this level|0 – 100|
|`izhar_enabled` / `izhar_weight`|Whether Izhār counts and its weight|0 or 1 / 0.0 – 1.0|
|`idgham_enabled` / `idgham_weight`|Same for Idghām|0 or 1 / 0.0 – 1.0|
|`iqlab_enabled` / `iqlab_weight`|Same for Iqlāb|0 or 1 / 0.0 – 1.0|
|`ikhfa_enabled` / `ikhfa_weight`|Same for Ikhfā'|0 or 1 / 0.0 – 1.0|
|`missing_word_penalty`|Penalty per missing word|0.0 – 1.0|
|`extra_word_penalty`|Penalty per extra word|0.0 – 1.0|
|`different_word_penalty`|Penalty per different word|0.0 – 1.0|

### Score Formula

```
rule_score(r)   = passed(r) / total(r) × 100
base_score      = Σ( rule_score(r) × weight(r) ) / Σ( weight(r) )
penalty_points  = Σ( count(type) × penalty(type) × 100 )
final_score     = clamp( base_score − penalty_points, 0, 100 )
```

### Level Classification

The system checks thresholds from highest to lowest:

```
if final_score >= advanced_threshold  → advanced
elif final_score >= intermediate_threshold → intermediate
elif final_score >= beginner_threshold → beginner
```

### Default Settings (configurable by teacher)

|Level|Threshold|Active Rules|
|-|-|-|
|Beginner|0|Izhār only|
|Intermediate|70|Izhār, Idghām, Iqlāb|
|Advanced|85|All four rules|

---

## Key Modules

### `core/Tajweed_analysis.py`

**The Tajwīd rule engine.** Locates every Nūn Sākinah and Tanwīn case in the reference text, aligns it with the Muaalem phonetic output, and produces a verdict (`passed`, `needs_review`, or `unmatched`) with an Arabic explanation for each case.

Key functions:

* `analyze_noon_rules_pronunciation(selection, phonetic_script)` — public entry point
* `_judge_rule(case, noon_visible, nasal_noon_visible, meem_visible)` — per-rule verdict logic

### `core/scoring.py`

**The scoring and classification engine.** Computes the weighted score from rule verdicts and word-error penalties, then selects the highest level whose threshold is met.

Key functions:

* `calculate_weighted_score(summary, recitation_verification, settings)`
* `classify_student_level(level_scores)`

### `core/recitation_matcher.py`

**Word-level comparison and Whisper verification.** Calls the Whisper-Quran model to transcribe the audio, normalises both the transcript and the reference text, and identifies missing, extra, and different words.

Key functions:

* `verify_required_recitation(audio_path, selection, settings)` — passage verification
* `match_recitation_text(transcript, selection)` — word matching

### `core/muaalem_phonetics.py`

**Muaalem model wrapper.** Loads the Wav2Vec2-BERT model and produces the Qur'anic Phonetic Script from a WAV file.

Key function:

* `extract_phonetic_script(audio_path)` — returns the phonetic string

### `core/quran_repository.py`

**Qur'an text loader and normaliser.** Loads the Uthmani text, identifies Tajwīd case locations, and normalises words for fair comparison.

### `core/tajweed_rules.py`

**Tajwīd rule data.** Defines the acoustic signatures for each of the four rules (which phonemes signal Izhār, Idghām, Iqlāb, Ikhfā') and the stop-mark exemption list.

---

## Database Schema

Five tables stored in `data/maqraah.sqlite3`:

```
users                     assignments
──────────────────        ───────────────────────
id                        id
full_name                 teacher_id  ──► users.id
email (unique)            student_id  ──► users.id (NULL = all students)
password_hash             surah_number / surah_name
role                      ayah_from / ayah_to / ayah_text
is_admin                  status ('pending' | 'done')
student_level             created_at
created_at

recitations               recitation_errors
───────────────────       ───────────────────────
id                        id
student_id  ──► users.id  recitation_id ──► recitations.id
assignment_id             rule
audio_file                status
score                     ayah
summary (JSON)            source_text
phonetic_script           reason
engine_note               created_at
created_at

scoring_level_settings
───────────────────────
level (primary key)
izhar_weight / idgham_weight / iqlab_weight / ikhfa_weight
missing_word_penalty / extra_word_penalty / different_word_penalty
placement_threshold
updated_at
```

---

## Configuration

|Environment Variable|Default|Description|
|-|-|-|
|`SECRET_KEY`|`dev-maqraah-secret`|Flask session secret key (change in production)|
|`PORT`|`5000`|Server port|

---

## Supported Tajwīd Rules

The system currently evaluates **four rules of Nūn Sākinah (نون ساكنة) and Tanwīn (تنوين)**:

|Rule|Arabic|Condition|Expected Sound|
|-|-|-|-|
|**Izhār**|الإظهار|Followed by a throat letter (ء ه ع ح غ خ)|Clear noon sound|
|**Idghām**|الإدغام|Followed by (ي ن م و ل ر)|Noon merged into next letter|
|**Iqlāb**|الإقلاب|Followed by (ب)|Noon converted to meem sound|
|**Ikhfā'**|الإخفاء|Followed by remaining letters|Nasal sound without clear noon|

Rules not yet supported: Mīm Sākinah, Mudūd, Qalqalah, and other Tajwīd categories.

---

## Limitations

* **Single narration:** Hafs ʿan ʿĀsim (Uthmani text) only
* **Processing time:** >30 seconds per recitation on CPU-only hardware
* **Articulation dependency:** Fast or unclear recitation may score lower
* **Recording quality:** Background noise reduces model confidence
* **Stop mark:** The *ṣalā* (ۖ) stop mark is not yet treated as exempt
* **No GPU required**, but GPU would significantly reduce processing time

---

## Team

**Graduation Project — Jamoum University College, Umm Al-Qura University**

|Name|Email|
|-|-|
|Sara Alsaedi|[sarakhalid44400@gmail.com](mailto:sarakhalid44400@gmail.com)|
|Jana Abusoudah|[Janaabusoudah@gmail.com](mailto:Janaabusoudah@gmail.com)|
|Remas Alsubhi|[Remasalharb55@gmail.com](mailto:Remasalharb55@gmail.com)|
|Amani Althahwani|[Amaniixx123@gmail.com](mailto:Amaniixx123@gmail.com)|
|Roz Bakkar|[rozabdullah72@gmail.com](mailto:rozabdullah72@gmail.com)|

**Advisor:** Dr. Khaled Albishre

---

*Al-Maqra'ah © 2026 — All rights reserved*
