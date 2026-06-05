# Spectre Backend — Deployment Guide

> **Last updated:** 5 Juni 2026
> **Applies to:** `spectre-backend-single` repository

---

## Table of Contents

- [Overview](#overview)
- [Architecture](#architecture)
- [Prerequisites](#prerequisites)
- [Repository Structure](#repository-structure)
- [Deployment Flow](#deployment-flow)
  - [Old Flow (Deprecated)](#old-flow-deprecated)
  - [New Flow (Current)](#new-flow-current)
- [Day-to-Day Operations](#day-to-day-operations)
  - [Push Code Changes](#push-code-changes)
  - [Manage Environment Variables](#manage-environment-variables)
  - [Update Model Files](#update-model-files)
  - [Manual Deploy to HF](#manual-deploy-to-hf)
- [Git LFS](#git-lfs)
- [GitHub Actions CI/CD](#github-actions-cicd)
- [Environment Variables](#environment-variables)
- [Troubleshooting](#troubleshooting)

---

## Overview

Spectre Backend di-deploy ke **HuggingFace Spaces** menggunakan Docker SDK.
Repository ini menggunakan **dual-remote git** strategy:

- **GitHub** (`origin`) — source of truth, development, code review
- **HuggingFace** (`hf`) — deployment target, auto-synced via GitHub Actions

Setiap kali code di-push ke branch `main` di GitHub, **GitHub Actions** secara otomatis
men-sync code tersebut ke HuggingFace Spaces, yang kemudian men-trigger rebuild dan redeploy.

---

## Architecture

```
┌─────────────────┐     git push      ┌──────────────────────┐
│   Developer PC  │ ─────────────────► │  GitHub (origin)     │
│                 │                    │  spectre-backend-    │
│  spectre-backend│                    │  single              │
└─────────────────┘                    └──────────┬───────────┘
                                                  │
                                                  │ GitHub Action
                                                  │ (auto trigger on push to main)
                                                  │
                                                  ▼
                                       ┌──────────────────────┐
                                       │  HuggingFace Spaces  │
                                       │  (hf remote)         │
                                       │                      │
                                       │  thewhitenigs/        │
                                       │  spectre-backend     │
                                       │                      │
                                       │  Docker Build ──►    │
                                       │  Live API Server     │
                                       └──────────────────────┘

┌─────────────────┐    deploy_env.py   ┌──────────────────────┐
│  .env.spaces    │ ─────────────────► │  HF Spaces Secrets   │
│  (local file)   │   (HuggingFace    │  (runtime env vars)  │
│                 │    Hub API)        │                      │
└─────────────────┘                    └──────────────────────┘
```

### Key URLs

| Resource | URL |
|----------|-----|
| GitHub Repository | https://github.com/fadhiilahahmadzikri/spectre-backend-single |
| HuggingFace Space | https://huggingface.co/spaces/thewhitenigs/spectre-backend |
| Live API (Swagger) | https://thewhitenigs-spectre-backend.hf.space/docs |
| Live API (ReDoc) | https://thewhitenigs-spectre-backend.hf.space/redoc |
| GitHub Actions | https://github.com/fadhiilahahmadzikri/spectre-backend-single/actions |

---

## Prerequisites

| Tool | Purpose | Install |
|------|---------|---------|
| Git | Version control | https://git-scm.com |
| Git LFS | Large file storage (model files) | `git lfs install` |
| GitHub CLI (`gh`) | GitHub operations | https://cli.github.com |
| Python 3.11+ | Backend runtime + scripts | https://python.org |
| `huggingface_hub` | HF API for env deployer | `pip install huggingface_hub` |

### Authentication

```bash
# GitHub (diperlukan untuk push)
gh auth login

# HuggingFace (diperlukan untuk deploy_env.py)
huggingface-cli login
```

---

## Repository Structure

```
spectre-backend-single/
├── .github/
│   └── workflows/
│       └── deploy-hf.yml          # Auto-deploy ke HF on push to main
├── artifact/
│   ├── best_model.keras           # Model utama (196MB, Git LFS)
│   └── multimodel/
│       └── ilhamcaesar/
│           └── model_final_v1.2.keras  # Model tambahan (201MB, Git LFS)
├── migrations/                    # Alembic database migrations
├── scripts/
│   ├── deploy_env.py              # ★ Env deployer ke HF Spaces
│   ├── run-tests.ps1
│   └── ...
├── seeds/                         # Database seeders
├── src/spectre/                   # ★ Backend source code (FastAPI)
├── supabase/                      # Supabase project config
├── tests/                         # Pytest + Postman tests
├── .env                           # Local env (TIDAK di-commit)
├── .env.docker                    # Docker env (TIDAK di-commit)
├── .env.example                   # Template env (di-commit)
├── .env.spaces                    # HF Spaces env (TIDAK di-commit)
├── .gitattributes                 # Git LFS rules
├── .gitignore                     # Git ignore rules
├── .huggingfaceignore             # HF build ignore rules
├── Dockerfile                     # Production Docker image
├── Makefile                       # Development commands
├── alembic.ini                    # Alembic config
├── docker-compose*.yml            # Local Docker infrastructure
├── pyproject.toml                 # Python project config
└── start.sh                       # Container startup script
```

---

## Deployment Flow

### Old Flow (Deprecated)

> ⚠️ **JANGAN gunakan flow ini lagi.**

```
# DEPRECATED — menggunakan deploy.py + HuggingFace Hub API upload
python deploy.py --repo thewhitenigs/spectre-backend --mode sync
```

Masalah dengan flow lama:
- `deploy.py` adalah script 1000+ baris yang melakukan terlalu banyak hal
- Upload via HuggingFace Hub API, bukan git — tidak ada version control di HF
- Monorepo (frontend + backend campur) menyebabkan file yang tidak perlu ikut ter-deploy
- Tidak ada CI/CD — deploy harus manual setiap kali
- Sulit di-maintain dan di-debug

### New Flow (Current)

```
git push origin main
  └──► GitHub Action (deploy-hf.yml)
         └──► git push hf main
                └──► HuggingFace Spaces rebuild (Docker)
```

**Keuntungan:**
- **Otomatis** — push ke GitHub = deploy ke HF
- **Version controlled** — HF Space punya git history yang sama dengan GitHub
- **Clean** — hanya backend code yang ada di repository
- **LFS** — model files di-handle oleh Git LFS, compatible dengan HF
- **Reproducible** — bisa rollback ke commit manapun
- **Traceable** — semua deploy tercatat di GitHub Actions

---

## Day-to-Day Operations

### Push Code Changes

Ini adalah operasi paling umum. Cukup push ke `main`:

```bash
# 1. Buat perubahan code
# 2. Commit
git add -A
git commit -m "feat: deskripsi perubahan"

# 3. Push ke GitHub (otomatis deploy ke HF)
git push origin main
```

Setelah push:
1. GitHub Action `Deploy to HuggingFace Spaces` akan berjalan otomatis
2. Action men-push code ke HF Spaces
3. HF Spaces men-detect perubahan dan rebuild Docker image
4. Server baru akan live dalam ~2-5 menit

**Cek status deploy:**
```bash
# Via GitHub CLI
gh run list --repo fadhiilahahmadzikri/spectre-backend-single --limit 5

# Lihat detail run tertentu
gh run view <RUN_ID> --repo fadhiilahahmadzikri/spectre-backend-single
```

### Manage Environment Variables

Environment variables di HF Spaces dikelola sebagai **Secrets** (encrypted).
Gunakan `scripts/deploy_env.py` untuk push env vars dari file `.env.spaces`.

```bash
# Push semua env vars dari .env.spaces
python scripts/deploy_env.py

# Push dengan auto-confirm (skip prompt)
python scripts/deploy_env.py --yes

# Push dari file env lain
python scripts/deploy_env.py --env .env.production

# List secrets yang sudah ada di HF
python scripts/deploy_env.py --list

# Hapus secret tertentu
python scripts/deploy_env.py --delete SECRET_KEY

# Target space lain
python scripts/deploy_env.py --repo user/other-space --env .env.custom
```

**Penting:**
- File `.env.spaces` TIDAK di-commit ke git (repo ini public!)
- Setiap kali push secrets, HF Space akan auto-rebuild
- Gunakan `.env.example` sebagai referensi untuk key yang diperlukan

### Update Model Files

Model files di-track via **Git LFS**. Untuk update model:

```bash
# 1. Replace file model di artifact/
cp path/to/new_model.keras artifact/best_model.keras

# 2. Git otomatis detect via LFS
git add artifact/best_model.keras
git commit -m "model: update best_model.keras v2"

# 3. Push (LFS object akan di-upload ke GitHub LFS storage)
git push origin main
# → GitHub Action akan push ke HF termasuk LFS objects
```

**Catatan tentang LFS:**
- File `.keras`, `.h5`, `.onnx`, `.pt`, dll otomatis di-track LFS via `.gitattributes`
- GitHub Free account punya 1GB LFS storage (cukup untuk 2 model saat ini)
- HuggingFace natively support Git LFS

### Manual Deploy to HF

Biasanya tidak perlu, tapi jika GitHub Action gagal:

```bash
# Push manual ke HF remote
git push hf main --force
```

---

## Git LFS

### File yang di-track LFS

Semua file binary besar otomatis di-track berdasarkan extension di `.gitattributes`:

| Extension | Contoh |
|-----------|--------|
| `.keras` | `artifact/best_model.keras` |
| `.h5` | Model weights (HDF5) |
| `.onnx` | ONNX model files |
| `.pt`, `.pth` | PyTorch model files |
| `.bin` | Binary weights |
| `.safetensors` | Safe serialized tensors |
| `.tflite` | TensorFlow Lite models |
| `.pkl`, `.pickle` | Pickled objects |

### Useful Commands

```bash
# Cek file apa saja yang di-track LFS
git lfs ls-files

# Cek status LFS
git lfs status

# Pull LFS objects (jika clone baru)
git lfs pull
```

---

## GitHub Actions CI/CD

### `deploy-hf.yml` — Auto Deploy to HuggingFace Spaces

**Trigger:** Push ke branch `main`

**Flow:**
1. Checkout repository (with full history + LFS)
2. Push ke HuggingFace Spaces remote
3. Retry otomatis hingga 3x jika kena rate limit (429)

**Required Secrets:**

| Secret | Lokasi | Deskripsi |
|--------|--------|-----------|
| `HF_TOKEN` | GitHub repo Settings → Secrets | HuggingFace API token untuk push |

**Cara set/update `HF_TOKEN`:**
```bash
# Via GitHub CLI (otomatis dari HF login lokal)
$token = Get-Content "$env:USERPROFILE\.cache\huggingface\token" -Raw
$token.Trim() | gh secret set HF_TOKEN --repo fadhiilahahmadzikri/spectre-backend-single

# Atau manual di GitHub UI:
# Settings → Secrets and variables → Actions → New repository secret
```

---

## Environment Variables

### File-file Env

| File | Purpose | Di-commit? |
|------|---------|------------|
| `.env` | Local development | ❌ |
| `.env.docker` | Docker local dev | ❌ |
| `.env.example` | Template/dokumentasi | ✅ |
| `.env.spaces` | HF Spaces production values | ❌ |

### Cara Env Masuk ke HF Spaces

```
.env.spaces (local file)
    │
    │  python scripts/deploy_env.py
    │  (via HuggingFace Hub API)
    ▼
HF Spaces Secrets (encrypted storage)
    │
    │  HF runtime injection
    ▼
Container env vars (os.environ)
    │
    │  pydantic-settings
    ▼
Spectre Settings object (src/spectre/config.py)
```

### Menambah Env Var Baru

1. Tambahkan key + default value ke `.env.example` (untuk dokumentasi)
2. Tambahkan key + real value ke `.env.spaces`
3. Tambahkan field ke `Settings` class di `src/spectre/config.py` (jika diperlukan)
4. Run `python scripts/deploy_env.py` untuk push ke HF
5. Commit `.env.example` perubahan ke git

---

## Troubleshooting

### GitHub Action gagal dengan error 429

**Penyebab:** HuggingFace rate limiting.

**Solusi:** Workflow sudah punya retry logic (3x dengan exponential backoff).
Jika masih gagal, tunggu beberapa menit lalu re-run:
```bash
gh run rerun <RUN_ID> --repo fadhiilahahmadzikri/spectre-backend-single
```

### HF Space stuck di BUILDING

**Cek status:**
```bash
# Via API
curl https://huggingface.co/api/spaces/thewhitenigs/spectre-backend
```

**Solusi:** Restart Space di HF UI → Settings → Restart Space.

### LFS objects tidak ter-push

```bash
# Verifikasi LFS tracking
git lfs ls-files

# Force push LFS objects
git lfs push origin main --all
git lfs push hf main --all
```

### Env vars tidak ter-apply

```bash
# List secrets yang ada di HF
python scripts/deploy_env.py --list

# Re-push semua env vars
python scripts/deploy_env.py --yes

# Catatan: setiap push secrets akan trigger rebuild
```

### Clone repository baru

```bash
# Clone dengan LFS
git clone https://github.com/fadhiilahahmadzikri/spectre-backend-single.git
cd spectre-backend-single
git lfs pull

# Tambahkan HF remote
git remote add hf https://huggingface.co/spaces/thewhitenigs/spectre-backend
```

### Rollback ke versi sebelumnya

```bash
# Lihat history
git log --oneline -10

# Revert ke commit tertentu
git revert <COMMIT_HASH>
git push origin main
# → otomatis deploy versi reverted ke HF
```

---

> **Catatan:** File `deploy.py` (script lama) masih ada di repository untuk referensi,
> tapi **tidak digunakan lagi** untuk deployment. Semua deployment sekarang via git push.
