# Deploy via SSH ke VPS Hostinger

Repo: `https://github.com/uppvision-lgtm/godam.git`  
Domain: `https://auto-comment.tech`

## 1. Push dulu dari laptop

File Docker harus ada di GitHub sebelum VPS bisa `git pull`.

## 2. Setup sekali di VPS (`root@PORTAL`)

```bash
curl -fsSL https://get.docker.com | sh
systemctl enable --now docker

git clone https://github.com/uppvision-lgtm/godam.git /opt/godam
cd /opt/godam

python3 -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"

nano .env
```

Isi `.env`:

```env
DEBUG=false
FRONTEND_URL=https://auto-comment.tech,https://www.auto-comment.tech
ACME_EMAIL=admin@auto-comment.tech
CREDENTIAL_ENCRYPTION_KEY=HASIL_GENERATE
SECRET_KEY=string-acak-panjang
```

```bash
docker compose up -d --build
docker compose ps
```

Build pertama 10–20 menit.

Kalau repo private:

```bash
ssh-keygen -t ed25519 -C "vps-godam" -N "" -f ~/.ssh/godam
cat ~/.ssh/godam.pub
```

Tambahkan public key di GitHub → **Settings → Deploy keys**, lalu clone pakai SSH:

```bash
git clone git@github.com:uppvision-lgtm/godam.git /opt/godam
```

## 3. Domain + SSL

Di DNS `auto-comment.tech`, A record `@` ke IP public VPS. CNAME `www` → `auto-comment.tech`.

Firewall Hostinger harus **Accept TCP 80 dan 443**. Caddy di compose mengambil sertifikat Let's Encrypt sendiri; HTTP di domain akan redirect ke HTTPS.

## 4. Auto-deploy (opsional)

GitHub Secrets:

| Secret | Isi |
|---|---|
| `VPS_HOST` | IP VPS |
| `VPS_USER` | `root` |
| `VPS_SSH_KEY` | private key yang bisa SSH ke VPS |
| `VPS_PORT` | opsional, default `22` |

Setiap push ke `main` akan `git pull` + `docker compose up` di `/opt/godam`.

## Update manual

```bash
cd /opt/godam
git pull origin main
docker compose up -d --build
```
