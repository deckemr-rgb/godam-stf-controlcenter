---
title: Instagram Auto Comment Bot API
emoji: 🤖
colorFrom: indigo
colorTo: blue
sdk: docker
app_port: 7860
pinned: false
---

# Instagram Auto Comment Bot API

Backend FastAPI + Celery worker untuk Instagram Auto Comment Bot.

Space ini adalah **satu kontainer** yang menjalankan dua proses sekaligus:

- **FastAPI API** → `uvicorn main:app` (di port 7860)
- **Celery worker** → `celery -A celery_app.celery_app worker`

## Env yang wajib diisi (di tab Settings > Variables and secrets)

| Variabel | Keterangan |
|----------|-----------|
| `REDIS_URL` | URL Redis dari Upstash (free tier, tanpa kartu kredit) |
| `CREDENTIAL_ENCRYPTION_KEY` | Kunci Fernet untuk enkripsi session |
| `FRONTEND_URL` | URL frontend Vercel, mis. `https://xxx.vercel.app` |

## Endpoint health check

```
GET https://USERNAME-NAMA-SPACE.hf.space/health
```
