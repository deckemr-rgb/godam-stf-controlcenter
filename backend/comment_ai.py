"""Generator komentar Instagram memakai DeepSeek API.

Mendukung 3 pilihan nada (tone) komentar:

- ``positif`` (default): apresiasi & dukungan, nada hangat.
- ``netral``  : faktual/observatif, tanpa memuji atau menyalahkan.
- ``negatif`` : kritis & menyoroti kekurangan, tapi tetap sopan (tidak
  menghina, tidak menyerang pribadi, tanpa SARA/ujaran kebencian/hoaks).

Caption dikirim UTUH supaya komentar nyambung dengan isi postingan.
Kalau DeepSeek gagal (tanpa API key / error / kuota habis), pemanggil bisa
menyediakan ``local_fallback`` (bank komentar lokal di ``tasks.py``) supaya
job tetap jalan.
"""

from __future__ import annotations

import asyncio
import inspect
import os
import random
import re
from typing import Any, Callable, Sequence

import httpx

TONES: tuple[str, ...] = ("positif", "netral", "negatif")
DEFAULT_TONE = "positif"

MAX_COMMENT_COUNT = 100
BATCH_SIZE = 10


def normalize_tone(value: Any) -> str:
    """Kembalikan tone yang valid; apa pun yang aneh dianggap ``positif``."""
    tone = str(value or "").strip().lower()
    return tone if tone in TONES else DEFAULT_TONE


# ============================================================
#  GAYA / ATURAN PER TONE
# ============================================================

_TONE_GAYA: dict[str, Sequence[str]] = {
    "positif": (
        "santai, hangat, dan mengapresiasi",
        "cerewet dikit tapi tetap relevan dan nyambung",
        "to the point, punchline singkat yang bikin senyum",
        "gaya anak Jaksel yang natural, campur dikit istilah Inggris",
    ),
    "netral": (
        "datar, faktual, kayak mengamati dari luar",
        "informatif, sesekali menambahkan konteks",
        "santai tapi tanpa memuji dan tanpa menyalahkan",
        "bertanya dengan sopan untuk hal yang belum jelas",
    ),
    "negatif": (
        "kritis dan terus terang, tetap sopan",
        "menyoroti kekurangan dengan alasan yang jelas",
        "sedikit ketus/nyinyir ringan, tapi TIDAK kasar dan TIDAK menghina",
        "menahan diri: kecewa pada isi kontennya, bukan menyerang orangnya",
    ),
}

_TONE_ATURAN: dict[str, str] = {
    "positif": """- Nada POSITIF: apresiasi, dukung, dan hargai isi kontennya.
- Pujian harus spesifik ke isi caption/video, bukan pujian generik "keren banget" doang.
- Boleh pakai istilah sehari-hari: "gila sih", "gokil", "relate", "vibesnya", "auto", "bestie", "cuy", "jujurly", "worth it".
- Kalau caption berisi duka/bencana/musibah: nada empati dan menenangkan (tetap hangat, tidak lebay).
- Kalau caption lucu/entertainment: boleh ikut bercanda ringan.
- Kalau caption berita/politik: tetap sopan, tidak menyerang pihak mana pun.""",
    "netral": """- Nada NETRAL: datar, objektif, dan informatif. Boleh mengamati, meringkas, atau bertanya.
- JANGAN memuji berlebihan, JANGAN pula menyalahkan/menyerang siapa pun.
- Boleh menambahkan konteks atau fakta umum yang relevan, dan boleh bertanya sopan.
- Jangan sarkastik, jangan sinis, jangan provokatif.
- Kalau caption duka/bencana: sampaikan simpati sederhana dan tetap tenang, tanpa menghakimi.""",
    "negatif": """- Nada NEGATIF: kritis, tunjukkan rasa kurang puas atau kekurangan dari isi konten ini.
- Kritik harus ke ISINYA (konten, penyampaian, kelengkapan info), JANGAN ke fisik/pribadi/keluarga siapa pun.
- WAJIB tetap sopan dan beradab. DILARANG: kata kasar, hinaan, body shaming, bullying, SARA, ujaran kebencian, ancaman, menuduh tanpa dasar, atau menyebarkan hoaks.
- Tidak boleh menyerukan kekerasan, boikot fisik, doxxing, atau ajakan melanggar hukum.
- Sampaikan kritik dengan alasan singkat, bukan sekadar mencela.
- Kalau caption berisi duka/bencana/musibah: cukup bahas tanggung jawab/penanganan secara sopan, JANGAN menyalahkan korban.
- Kalau caption berita/politik: kritik hanya pada kebijakan/konten, bukan menyerang identitas atau golongan.""",
}

# Fallback sederhana per tone, dipakai kalau tidak ada ``local_fallback``.
_SIMPLE_FALLBACK: dict[str, Sequence[str]] = {
    "positif": (
        "keren banget, thanks udah share.",
        "informasi yang bermanfaat, aku suka.",
        "wah, ini bikin penasaran.",
        "seru banget, lanjutkan.",
        "ini penting banget, wajib tahu.",
    ),
    "netral": (
        "info ini lumayan, ditunggu update berikutnya.",
        "jadi lebih paham setelah nonton ini.",
        "nonton sampai habis, isinya lumayan jelas.",
        "menarik, topik ini memang sedang ramai dibahas.",
        "boleh dijelaskan lagi bagian yang tadi?",
    ),
    "negatif": (
        "sayangnya isinya masih kurang lengkap.",
        "menurutku penjelasannya masih terlalu dangkal.",
        "harusnya bagian ini dibahas lebih detail.",
        "masih banyak yang belum jelas, semoga ada lanjutannya.",
        "cukup disayangkan dibahas setengah-setengah.",
    ),
}


def _bersihkan_komentar(raw: str, sudah_ada: set[str] | None = None) -> list[str]:
    """Rapikan output DeepSeek jadi daftar komentar bersih, pendek, dan unik."""
    sudah_ada = sudah_ada if sudah_ada is not None else set()
    hasil: list[str] = []
    for line in str(raw or "").splitlines():
        teks = line.strip()
        if not teks:
            continue
        # Buang penomoran/bullet dan tanda kutip di ujung.
        teks = re.sub(r"^\s*(?:[-*•]|\d+[\.\)])\s*", "", teks)
        teks = teks.strip().strip("\"'“”‘’")
        teks = re.sub(r"\s+", " ", teks).strip()
        if len(teks) < 3 or len(teks) > 220:
            continue
        kunci = teks.lower()
        if kunci in sudah_ada:
            continue
        sudah_ada.add(kunci)
        hasil.append(teks)
    return hasil


def _buat_prompt(caption: str, jumlah: int, tone: str, variasi: int = 0) -> str:
    """Susun prompt DeepSeek: nyambung ke caption + sesuai tone yang dipilih."""
    tone = normalize_tone(tone)
    gaya = _TONE_GAYA[tone]
    gaya_pilih = gaya[variasi % len(gaya)]
    return f"""Kamu itu anak Gen Z Indonesia yang santai dan aktif main Instagram.
Tugasmu: tulis {jumlah} komentar Instagram untuk postingan ini.

CAPTION LENGKAP POSTINGAN (baca semua paragraf sampai habis, termasuk hashtag):
---
{caption}
---

ATURAN GAYA:
- Bahasa Indonesia gaul Gen Z, santai. JANGAN formal/kaku/kayak pembaca berita.
- Gaya kali ini: {gaya_pilih}.
- Maksimal 20 kata per komentar, boleh singkat 3-8 kata.
- WAJIB nyambung ke isi caption: sebut hal spesifik dari caption/video, bukan komentar generik.
- Jangan menyalin kalimat caption mentah-mentah, tanggapi dengan gayamu sendiri.
- Jangan pakai hashtag, jangan pakai tanda kutip, emoji maksimal 1.
- Setiap komentar harus beda sudut pandang.

ATURAN NADA (pilih nada {tone.upper()}):
{_TONE_ATURAN[tone]}

LARANGAN UMUM (berlaku untuk semua nada):
- Tidak ada ujaran kebencian, SARA, pelecehan, ancaman, atau konten seksual.
- Tidak ada ajakan kekerasan atau melanggar hukum.
- Tidak ada spam/link promosi.

FORMAT OUTPUT:
- Tulis {jumlah} komentar, satu komentar per baris.
- Tanpa nomor, tanpa bullet, tanpa tanda kutip, tanpa penjelasan tambahan.
- Langsung teks komentarnya saja.
"""


def _simple_fallback(tone: str, count: int) -> list[str]:
    tone = normalize_tone(tone)
    bank = list(_SIMPLE_FALLBACK[tone])
    if not bank:
        return []
    random.shuffle(bank)
    hasil = bank[:count]
    i = 0
    while len(hasil) < count:
        hasil.append(bank[i % len(bank)])
        i += 1
    return hasil[:count]


async def generate_comments_with_deepseek(
    caption: str,
    count: int = 6,
    tone: str = DEFAULT_TONE,
    api_key: str | None = None,
    max_retries: int = 3,
) -> list[str]:
    """Buat ``count`` komentar via DeepSeek API sesuai ``tone``.

    Mengembalikan daftar kosong kalau DeepSeek tidak menghasilkan apa pun
    (pemanggil yang menentukan fallback-nya).
    """
    tone = normalize_tone(tone)
    try:
        count = max(1, min(MAX_COMMENT_COUNT, int(count)))
    except Exception:
        count = 6

    if not caption or len(str(caption).strip()) < 3:
        return []

    api_key = api_key or os.getenv("DEEPSEEK_API_KEY", "").strip()
    if not api_key:
        return []

    base_url = os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com/v1").rstrip("/")
    model = os.getenv("DEEPSEEK_MODEL", "deepseek-chat")
    caption = re.sub(r"\s+", " ", str(caption)).strip()

    semua: list[str] = []
    sudah_ada: set[str] = set()
    max_batches = (count + BATCH_SIZE - 1) // BATCH_SIZE + 2
    timeout = httpx.Timeout(60.0, connect=15.0)

    async with httpx.AsyncClient(timeout=timeout) as client:
        batch_ke = 0
        while len(semua) < count and batch_ke < max_batches:
            butuh = min(BATCH_SIZE, count - len(semua))
            payload = {
                "model": model,
                "messages": [
                    {
                        "role": "system",
                        "content": (
                            "Kamu komentator Instagram Gen Z Indonesia. "
                            f"Nada komentar yang diminta: {tone}. "
                            "Selalu sopan, tidak menghina, tidak SARA, tidak hoaks."
                        ),
                    },
                    {"role": "user", "content": _buat_prompt(caption, butuh, tone, batch_ke)},
                ],
                "temperature": 1.1,
                "top_p": 0.95,
                "max_tokens": 800,
            }
            sukses = False
            for attempt in range(max_retries + 1):
                try:
                    resp = await client.post(
                        f"{base_url}/chat/completions",
                        headers={
                            "Authorization": f"Bearer {api_key}",
                            "Content-Type": "application/json",
                        },
                        json=payload,
                    )
                    if resp.status_code == 200:
                        raw = resp.json()["choices"][0]["message"]["content"]
                        baru = _bersihkan_komentar(raw, sudah_ada)
                        if baru:
                            semua.extend(baru)
                        sukses = True
                        break
                    # 401/402/403 = masalah kredensial/kuota, tidak perlu diulang.
                    if resp.status_code in (401, 402, 403):
                        break
                except Exception:
                    pass
                if attempt < max_retries:
                    await asyncio.sleep(1.5 * (attempt + 1))
            if not sukses:
                break
            batch_ke += 1

    return semua[:count]


async def generate_comments(
    caption: str,
    count: int = 6,
    tone: str = DEFAULT_TONE,
    local_fallback: Callable[[str, int, str], Any] | None = None,
    api_key: str | None = None,
) -> list[str]:
    """DeepSeek dulu; kalau gagal pakai ``local_fallback`` lalu fallback sederhana.

    ``local_fallback`` boleh fungsi biasa maupun async (mis. bank lokal async).
    """
    tone = normalize_tone(tone)
    try:
        count = max(0, int(count))
    except Exception:
        count = 6
    if count <= 0:
        return []

    komentar: list[str] = []
    try:
        komentar = await generate_comments_with_deepseek(caption, count, tone, api_key=api_key)
    except Exception:
        komentar = []

    if len(komentar) < count and local_fallback is not None:
        try:
            tambahan = local_fallback(caption, count - len(komentar), tone)
            if inspect.isawaitable(tambahan):
                tambahan = await tambahan
        except Exception:
            tambahan = []
        for teks in tambahan or []:
            if len(komentar) >= count:
                break
            if teks and teks.lower() not in {k.lower() for k in komentar}:
                komentar.append(teks)

    if len(komentar) < count:
        for teks in _simple_fallback(tone, count - len(komentar)):
            if len(komentar) >= count:
                break
            komentar.append(teks)

    return komentar[:count]
