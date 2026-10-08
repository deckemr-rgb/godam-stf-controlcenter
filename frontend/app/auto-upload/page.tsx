"use client";

import Link from "next/link";
import { useCallback, useEffect, useRef, useState } from "react";
import styles from "./page.module.css";
import { bacaForm, simpanForm } from "../components/formStore";
import DeviceTargetSelect from "../components/DeviceTargetSelect";

type LiveStatus = {
  status: string;
  message: string;
  logs: string[];
  result?: { post_url?: string; status?: string } | null;
};

type Konfigurasi = { supabase: boolean; max_video_mb: number; jenis: string[] };

// Batas badan permintaan fungsi serverless Vercel.
const BATAS_PROXY_MB = 4;

function apiUrl(path: string): string {
  return path;
}

const selesai = (status: string) => status === "completed" || status === "error";

export default function AutoUploadPage() {
  const [konfig, setKonfig] = useState<Konfigurasi | null>(null);
  const [berkas, setBerkas] = useState<File | null>(null);
  const [username, setUsername] = useState("");
  const [sessionId, setSessionId] = useState("");
  const [caption, setCaption] = useState("");
  const [deviceSerial, setDeviceSerial] = useState("");

  const [token, setToken] = useState("");
  const [status, setStatus] = useState<LiveStatus | null>(null);
  const [frameUrl, setFrameUrl] = useState("");
  const [tahap, setTahap] = useState("");
  const [galat, setGalat] = useState("");
  const [sibuk, setSibuk] = useState(false);
  const tokenRef = useRef("");

  // ===== ISIAN TERSIMPAN PER AKUN (berkas video tidak bisa ikut disimpan) =====
  useEffect(() => {
    const requestedDevice = new URLSearchParams(window.location.search).get("device") || "";
    const tersimpan = bacaForm("auto-upload", {
      username: "",
      sessionId: "",
      caption: "",
      deviceSerial: "",
    });
    /* eslint-disable react-hooks/set-state-in-effect -- memulihkan isian
       tersimpan hanya sekali saat halaman dibuka. Sengaja dilakukan setelah
       render pertama, bukan lewat nilai awal useState, supaya HTML dari server
       dan dari browser tetap sama (localStorage tidak ada di server). */
    if (tersimpan.username) setUsername(tersimpan.username);
    if (tersimpan.sessionId) setSessionId(tersimpan.sessionId);
    if (tersimpan.caption) setCaption(tersimpan.caption);
    if (requestedDevice || tersimpan.deviceSerial) {
      setDeviceSerial(requestedDevice || tersimpan.deviceSerial);
    }
    /* eslint-enable react-hooks/set-state-in-effect */
  }, []);

  // Disimpan saat diketik (bukan lewat useEffect) supaya isian tersimpan tidak
  // tertimpa nilai kosong ketika halaman baru dimuat.
  function ubahIsian(bagian: {
    username?: string;
    sessionId?: string;
    caption?: string;
    deviceSerial?: string;
  }) {
    const berikutnya = { username, sessionId, caption, deviceSerial, ...bagian };
    if (bagian.username !== undefined) setUsername(bagian.username);
    if (bagian.sessionId !== undefined) setSessionId(bagian.sessionId);
    if (bagian.caption !== undefined) setCaption(bagian.caption);
    if (bagian.deviceSerial !== undefined) setDeviceSerial(bagian.deviceSerial);
    simpanForm("auto-upload", berikutnya);
  }

  useEffect(() => {
    void (async () => {
      try {
        const res = await fetch(apiUrl("/api/upload/config"), { cache: "no-store" });
        if (res.ok) setKonfig(await res.json());
      } catch {
        setGalat("Backend tidak merespons. Pastikan servernya berjalan.");
      }
    })();
  }, []);

  // ===== PANTAU PROSES UNGGAH =====
  const tarikStatus = useCallback(async () => {
    if (!tokenRef.current) return;
    try {
      const res = await fetch(apiUrl(`/api/live/${tokenRef.current}/status`), { cache: "no-store" });
      if (!res.ok) return;
      setStatus(await res.json());
    } catch {
      // coba lagi pada putaran berikutnya
    }
  }, []);

  useEffect(() => {
    if (!token || (status && selesai(status.status))) return;
    tokenRef.current = token;
    const timer = window.setInterval(() => {
      void tarikStatus();
      if (!document.hidden) setFrameUrl(`${apiUrl(`/api/live/${token}/frame`)}?t=${Date.now()}`);
    }, 1200);
    return () => window.clearInterval(timer);
  }, [token, status, tarikStatus]);

  // Tutup browser di server kalau halaman ditinggalkan saat masih berjalan.
  useEffect(() => {
    const tutup = () => {
      if (tokenRef.current) {
        try {
          navigator.sendBeacon(apiUrl(`/api/live/${tokenRef.current}/close`), "");
        } catch {
          // abaikan
        }
      }
    };
    window.addEventListener("pagehide", tutup);
    return () => window.removeEventListener("pagehide", tutup);
  }, []);

  /** Kirim berkas ke Supabase (langsung dari browser) atau ke backend. */
  async function kirimBerkas(file: File): Promise<{ file_id?: string; storage_path?: string }> {
    if (konfig?.supabase) {
      setTahap("Mengunggah video ke penyimpanan ...");
      const res = await fetch(apiUrl(`/api/upload/signed?nama=${encodeURIComponent(file.name)}`), {
        method: "POST",
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || "Gagal menyiapkan penyimpanan.");
      const unggah = await fetch(data.url, {
        method: "PUT",
        headers: { authorization: `Bearer ${data.token}`, "x-upsert": "true" },
        body: file,
      });
      if (!unggah.ok) throw new Error("Gagal mengunggah video ke penyimpanan.");
      return { storage_path: data.path };
    }

    setTahap("Mengirim video ke server ...");
    const form = new FormData();
    form.append("file", file);
    const res = await fetch(apiUrl("/api/upload/file"), { method: "POST", body: form });
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || "Gagal mengirim video.");
    return { file_id: data.file_id };
  }

  async function mulai() {
    setGalat("");
    if (!berkas) return setGalat("Pilih dulu video dari laptopmu.");
    if (!username.trim()) return setGalat("Isi nama akun Instagram-nya.");
    if (!deviceSerial && !sessionId.trim()) {
      return setGalat("Session ID wajib untuk mode browser server, atau pilih perangkat STF.");
    }

    setSibuk(true);
    setStatus(null);
    setFrameUrl("");
    try {
      const sumber = await kirimBerkas(berkas);
      setTahap("Membuka Instagram ...");
      const res = await fetch(apiUrl("/api/upload/start"), {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          username: username.trim(),
          session_id: sessionId.trim(),
          device_serial: deviceSerial,
          caption,
          ...sumber,
        }),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || "Gagal memulai unggahan.");
      setToken(data.token);
      setTahap("");
    } catch (err) {
      setGalat(err instanceof Error ? err.message : "Gagal memulai unggahan.");
      setTahap("");
    } finally {
      setSibuk(false);
    }
  }

  async function hentikan() {
    if (!tokenRef.current) return;
    try {
      await fetch(apiUrl(`/api/live/${tokenRef.current}/close`), { method: "POST" });
    } catch {
      // abaikan
    }
    tokenRef.current = "";
    setToken("");
    setStatus(null);
    setFrameUrl("");
  }

  const berjalan = !!token && !(status && selesai(status.status));
  const tautan = status?.result?.post_url || "";
  const terlaluBesar =
    !!berkas && !konfig?.supabase && berkas.size > BATAS_PROXY_MB * 1_048_576;

  return (
    <div className={styles.page}>
      <header className={styles.topbar}>
        <Link href="/" className={styles.back} title="Kembali ke beranda">←</Link>
        <span className={styles.brand}>IG · AUTO UPLOAD</span>
        <span className={styles.headStatus}>{status?.status || (berjalan ? "memulai" : "idle")}</span>
      </header>

      <main className={styles.main}>
        <section className={styles.panel}>
          <h1>Unggah Video ke Instagram</h1>
          <p className={styles.sub}>
            Pilih video, tentukan browser server atau perangkat STF, lalu biarkan
            Godam mengunggahnya. Prosesnya bisa kamu tonton langsung di bawah.
          </p>

          <div className={styles.form}>
            <DeviceTargetSelect
              value={deviceSerial}
              onChange={(serial) => ubahIsian({ deviceSerial: serial })}
              disabled={sibuk || berjalan}
            />
            <label className={styles.filePicker}>
              <input
                type="file"
                accept="video/mp4,video/quicktime,video/webm,.mp4,.mov,.m4v,.webm"
                onChange={(e) => setBerkas(e.target.files?.[0] || null)}
              />
              <span className={styles.fileBtn}>Pilih video</span>
              <span className={styles.fileName}>
                {berkas
                  ? `${berkas.name} — ${(berkas.size / 1_048_576).toFixed(1)} MB`
                  : "belum ada berkas dipilih"}
              </span>
            </label>

            {terlaluBesar && (
              <p className={styles.warn}>
                Video ini {(berkas.size / 1_048_576).toFixed(1)} MB, sedangkan lewat
                website batasnya {BATAS_PROXY_MB} MB. Nyalakan penyimpanan Supabase di
                server untuk berkas sebesar ini.
              </p>
            )}

            <label>
              <span>Nama akun Instagram</span>
              <input
                value={username}
                onChange={(e) => ubahIsian({ username: e.target.value })}
                placeholder="mis. tokoku"
                autoComplete="off"
              />
            </label>

            <label>
              <span>Session ID {deviceSerial ? "(tidak dipakai di perangkat STF)" : ""}</span>
              <input
                value={sessionId}
                onChange={(e) => ubahIsian({ sessionId: e.target.value })}
                placeholder="tempel sessionid cookie"
                autoComplete="off"
                disabled={!!deviceSerial}
              />
            </label>

            <label>
              <span>Caption</span>
              <textarea
                rows={4}
                value={caption}
                onChange={(e) => ubahIsian({ caption: e.target.value })}
                placeholder="Tulis caption di sini. Boleh pakai hashtag."
                maxLength={2200}
              />
              <span className={styles.hitung}>{caption.length}/2200</span>
            </label>

            {galat && <p className={styles.error} role="alert">{galat}</p>}
            {tahap && <p className={styles.tahap}>{tahap}</p>}

            <button className={styles.mulaiBtn} onClick={mulai} disabled={sibuk || berjalan}>
              {berjalan ? "Sedang mengunggah..." : sibuk ? "Menyiapkan..." : "Unggah ke Instagram"}
            </button>
          </div>
        </section>

        {token && (
          <section className={styles.panel}>
            <div className={styles.liveHead}>
              <h2>{deviceSerial ? "Perangkat STF Live" : "Chrome Live"}</h2>
              <span className={`${styles.badge} ${styles[status?.status || ""] || ""}`}>
                {status?.status || "memulai"}
              </span>
              <button className={styles.stopBtn} onClick={hentikan}>
                {berjalan ? "Stop" : "Tutup"}
              </button>
            </div>
            <p className={styles.pesan}>{status?.message}</p>

            {tautan && (
              <a className={styles.tautan} href={tautan} target="_blank" rel="noreferrer">
                Buka postingan yang baru diunggah →
              </a>
            )}

            <div className={styles.stage}>
              {frameUrl ? (
                // eslint-disable-next-line @next/next/no-img-element
                <img src={frameUrl} alt="Layar bot" className={styles.frame} draggable={false} />
              ) : (
                <p className={styles.hint}>Menunggu frame...</p>
              )}
            </div>

            <div className={styles.logBody}>
              {(status?.logs || []).map((baris, i) => (
                <p key={i}>{baris}</p>
              ))}
            </div>
          </section>
        )}
      </main>
    </div>
  );
}
