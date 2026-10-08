"use client";
import { useEffect, useMemo, useState } from "react";
import styles from "./page.module.css";

type Device = { serial: string; present?: boolean; ready?: boolean; using?: boolean; model?: string; marketName?: string; version?: string; battery?: { level?: number; scale?: number } };
type Job = { serial: string; status: string; outcome: string; message: string; logs: unknown[]; result: unknown };
type Run = { run_id: string; platform: string; target: string; status: string; archived?: boolean; persistence_error?: string;
  mode?: string; account?: string | null; actions?: string[] | null; jobs: Job[];
  summary: { total: number; running: number; error: number; stopped: number; no_comments_recorded: number; unverified: number } };
type Diagnostics = { checked_at: string; stf_ok: boolean; adb_ok: boolean; issues: string[]; scope: string;
  devices: { serial: string; adb: string; ready: boolean; busy: boolean; issues: string[] }[] };
type Preview = { plan_id: string; model_info?: { note: string }; decisions: { action: string; confidence: number }[] };
type VisionConfig = { provider: string; configured: boolean; model: string; execution_enabled: boolean; allowed_packages: string[]; mode: string };
type VisionCandidate = { label: string; description: string; x: number; y: number; confidence: number; risk: string; reason: string;
  decision: "allow" | "review" | "block"; policy_reason: string; matched_terms: string[] };
type VisionAnalysis = { analysis_id: string; serial: string; package: string; goal: string; screen_summary: string; goal_reached: boolean;
  recommended_index: number | null; candidates: VisionCandidate[]; warnings: string[]; execution_enabled: boolean };
type Frame = { url?: string; at?: number; error?: string };
type PlatformAction = { id: string; label: string; supported: boolean };
type PlatformInfo = { id: string; label: string; packages: string[]; actions: PlatformAction[] };
type View = "devices" | "diagnostics" | "runs" | "preview" | "vision" | "solo" | "stf";
const NAV: { id: View; label: string; icon: string }[] = [
  { id: "devices", label: "Perangkat", icon: "▦" }, { id: "diagnostics", label: "Diagnostik", icon: "⌕" },
  { id: "solo", label: "Automasi 1 Akun", icon: "★" }, { id: "runs", label: "Runs & Log", icon: "◷" },
  { id: "preview", label: "Simulasi", icon: "◇" },
  { id: "vision", label: "Vision Test", icon: "◎" }, { id: "stf", label: "Kontrol STF", icon: "⌘" },
];
const ACTION_ORDER = ["like", "comment", "share", "repost"];
const OUTCOMES: Record<string, string> = { running: "Berjalan", error: "Gagal", stopped: "Dihentikan", no_comments_recorded: "Nol komentar tercatat", unverified: "Hasil belum terverifikasi", needs_review: "Perlu diperiksa" };
function message(error: unknown) { return error instanceof Error ? error.message : "Permintaan gagal."; }
function authHeaders(json = false) {
  const headers = new Headers();
  try { const token = localStorage.getItem("ig-tools-token"); if (token) headers.set("Authorization", "Bearer " + token); } catch { /* Storage may be disabled. */ }
  if (json) headers.set("Content-Type", "application/json");
  return headers;
}
async function request(path: string, init: RequestInit = {}) {
  const timeout = AbortSignal.timeout(30000);
  return fetch(path, { ...init, cache: "no-store", headers: authHeaders(!!init.body), signal: init.signal ? AbortSignal.any([init.signal, timeout]) : timeout });
}
async function api<T>(path: string, init: RequestInit = {}): Promise<T> {
  const response = await request(path, init);
  const payload = await response.json().catch(() => null);
  if (!response.ok) {
    const detail = payload?.detail;
    throw new Error(typeof detail === "string" ? detail : Array.isArray(detail)
      ? detail.map((item: { msg?: string }) => item.msg || "Input tidak valid").join("; ") : "Permintaan gagal (HTTP " + response.status + ").");
  }
  if (payload === null) throw new Error("Respons JSON tidak valid.");
  return payload;
}
// Schedule after completion; slow requests never overlap.
function usePoll<T>(path: string, interval: number, revision = 0) {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState("");
  const [updated, setUpdated] = useState<number | null>(null);
  useEffect(() => {
    const controller = new AbortController();
    let timer: ReturnType<typeof setTimeout>;
    async function poll() {
      try {
        const result = await api<T>(path, { signal: controller.signal });
        if (!controller.signal.aborted) { setData(result); setError(""); setUpdated(Date.now()); }
      } catch (reason) { if (!controller.signal.aborted) setError(message(reason)); }
      finally { if (!controller.signal.aborted && interval > 0) timer = setTimeout(poll, interval); }
    }
    void poll();
    return () => { controller.abort(); clearTimeout(timer); };
  }, [path, interval, revision]);
  return { data, error, updated };
}
function useFrames(serialKey: string, interval: number, revision: number, enabled: boolean) {
  const generation = useMemo(() => ({ serialKey, interval, revision, enabled }), [serialKey, interval, revision, enabled]);
  const [snapshot, setSnapshot] = useState<{ key: typeof generation | null; frames: Record<string, Frame> }>({ key: null, frames: {} });
  useEffect(() => {
    if (!enabled || !serialKey) return;
    const controller = new AbortController();
    const frames: Record<string, Frame> = {};
    const serials = serialKey.split(",");
    let timer: ReturnType<typeof setTimeout>;
    async function refresh() {
      if (!document.hidden) {
        for (let offset = 0; offset < serials.length && !controller.signal.aborted && !document.hidden; offset += 2) {
          await Promise.all(serials.slice(offset, offset + 2).map(async serial => {
            try {
              const response = await request("/api/device-farm/devices/" + encodeURIComponent(serial) + "/screenshot", { signal: controller.signal });
              if (!response.ok) throw new Error(response.status === 429 ? "Antrean penuh; menunggu refresh" : "Frame gagal (HTTP " + response.status + ")");
              if (!response.headers.get("content-type")?.startsWith("image/")) throw new Error("Format frame tidak valid");
              const blob = await response.blob();
              if (controller.signal.aborted) return;
              const previous = frames[serial]?.url;
              frames[serial] = { url: URL.createObjectURL(blob), at: Date.now() };
              if (previous) URL.revokeObjectURL(previous);
            } catch (reason) {
              if (controller.signal.aborted) return;
              frames[serial] = { ...frames[serial], error: message(reason) };
            }
            if (!controller.signal.aborted) setSnapshot({ key: generation, frames: { ...frames } });
          }));
        }
      }
      if (!controller.signal.aborted) timer = setTimeout(refresh, interval * 1000);
    }
    void refresh();
    return () => { controller.abort(); clearTimeout(timer); Object.values(frames).forEach(frame => { if (frame.url) URL.revokeObjectURL(frame.url); }); };
  }, [serialKey, interval, revision, enabled, generation]);
  return enabled && snapshot.key === generation ? snapshot.frames : {};
}
function localTime(value: number | string | null | undefined) { return value ? new Date(value).toLocaleTimeString("id-ID") : "belum diperiksa"; }
function exportReport(value: unknown, filename: string) {
  const url = URL.createObjectURL(new Blob([JSON.stringify(value, null, 2)], { type: "application/json" }));
  const link = document.createElement("a"); link.href = url; link.download = filename; link.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}
export default function ControlCenter() {
  const [view, setView] = useState<View>("devices");
  const [revision, setRevision] = useState(0);
  const inventory = usePoll<{ devices: Device[] }>("/api/device-farm/devices", 10000, revision);
  const engine = usePoll<{ status: string }>("/api/device-farm/status", 20000, revision);
  const config = usePoll<{ public_url: string }>("/api/device-farm/config", 0, revision);
  const visionConfig = usePoll<VisionConfig>("/api/vision-test/config", 0, revision);
  const history = usePoll<{ runs: Run[] }>("/api/farm-automation/runs", 8000, revision);
  const platformInfo = usePoll<{ platforms: PlatformInfo[] }>("/api/farm-automation/platforms", 0, revision);
  const devices = useMemo(() => inventory.data?.devices || [], [inventory.data]);
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [query, setQuery] = useState("");
  const [filter, setFilter] = useState("all");
  const [tileWidth, setTileWidth] = useState(174);
  const [frameSeconds, setFrameSeconds] = useState(30);
  const [frameRevision, setFrameRevision] = useState(0);
  const [pauseFrames, setPauseFrames] = useState(false);
  const [actionError, setActionError] = useState("");
  const [notice, setNotice] = useState("");
  const [diagnostics, setDiagnostics] = useState<Diagnostics | null>(null);
  const [scanning, setScanning] = useState(false);
  const [stopping, setStopping] = useState("");
  const [controlSerial, setControlSerial] = useState("");
  const [caption, setCaption] = useState("");
  const [topics, setTopics] = useState("");
  const [platform, setPlatform] = useState("instagram");
  const [preview, setPreview] = useState<Preview | null>(null);
  const [analyzing, setAnalyzing] = useState(false);
  const [visionSerial, setVisionSerial] = useState("");
  const [visionPackage, setVisionPackage] = useState("");
  const [visionGoal, setVisionGoal] = useState("");
  const [visionAnalysis, setVisionAnalysis] = useState<VisionAnalysis | null>(null);
  const [visionLoading, setVisionLoading] = useState(false);
  const [visionClicking, setVisionClicking] = useState<number | null>(null);
  const [soloPlatform, setSoloPlatform] = useState("instagram");
  const [soloDevice, setSoloDevice] = useState("");
  const [soloTarget, setSoloTarget] = useState("");
  const [soloAccount, setSoloAccount] = useState("");
  const [soloActions, setSoloActions] = useState<Set<string>>(new Set(["like", "comment"]));
  const [soloComments, setSoloComments] = useState(1);
  const [soloPosts, setSoloPosts] = useState(1);
  const [soloTone, setSoloTone] = useState("positif");
  const [soloStarting, setSoloStarting] = useState(false);
  const [soloRunId, setSoloRunId] = useState("");
  const [soloRun, setSoloRun] = useState<Run | null>(null);
  const [soloFrame, setSoloFrame] = useState<Frame>({});
  const online = devices.filter(device => device.present && device.ready);
  const preparing = devices.filter(device => device.present && !device.ready).length;
  const chosen = online.filter(device => selected.has(device.serial));
  const visible = devices.filter(device => {
    if ((filter === "ready" && !(device.present && device.ready)) || (filter === "offline" && device.present) || (filter === "busy" && !device.using)) return false;
    return ((device.marketName || device.model || "Android") + " " + device.serial).toLowerCase().includes(query.trim().toLowerCase());
  });
  // Stable primitive key: inventory polling must not reset the screenshot timer.
  const serialKey = visible.filter(device => device.present && device.ready).map(device => device.serial).sort().join(",");
  const frames = useFrames(serialKey, frameSeconds, frameRevision, view === "devices" && !pauseFrames && !inventory.error);
  const visibleReady = visible.filter(device => device.present && device.ready);
  const allChosen = visibleReady.length > 0 && visibleReady.every(device => selected.has(device.serial));
  const stfBase = config.data?.public_url?.replace(/\/$/, "") || "";
  const stfUrl = stfBase ? stfBase + "/#/" + (controlSerial ? "control/" + encodeURIComponent(controlSerial) : "") : "";
  const runs = history.data?.runs || [];
  const healthy = engine.data?.status === "ok" && !engine.error && !inventory.error;
  function toggle(serial: string) { setSelected(current => { const next = new Set(current); if (next.has(serial)) next.delete(serial); else next.add(serial); return next; }); }
  function selectVisible() { setSelected(current => { const next = new Set(current); visibleReady.forEach(device => { if (allChosen) next.delete(device.serial); else next.add(device.serial); }); return next; }); }
  async function scan() {
    setScanning(true); setActionError("");
    try { setDiagnostics(await api<Diagnostics>("/api/device-farm/diagnostics")); } catch (reason) { setActionError(message(reason)); } finally { setScanning(false); }
  }
  async function stop(run: Run) {
    setStopping(run.run_id); setActionError("");
    try {
      await api("/api/farm-automation/runs/" + run.run_id + "/stop", { method: "POST" });
      setNotice("Permintaan berhenti dikirim. Operasi perangkat yang sudah berjalan mungkin memerlukan waktu untuk berakhir.");
      setRevision(value => value + 1);
    } catch (reason) { setActionError(message(reason)); } finally { setStopping(""); }
  }
  async function analyze() {
    setAnalyzing(true); setActionError(""); setPreview(null);
    try {
      setPreview(await api<Preview>("/api/farm-automation/ml/preview", { method: "POST", body: JSON.stringify({
        platform, caption: caption.trim(), tone: "netral", target_topics: topics.split(",").map(item => item.trim()).filter(Boolean),
        accounts: [], current_accounts: {}, device_serials: [], recent_comments: [],
      }) }));
    } catch (reason) { setActionError(message(reason)); } finally { setAnalyzing(false); }
  }
  async function analyzeVision() {
    setVisionLoading(true); setActionError(""); setNotice(""); setVisionAnalysis(null);
    try {
      setVisionAnalysis(await api<VisionAnalysis>("/api/vision-test/analyze", { method: "POST", body: JSON.stringify({
        serial: visionSerial, goal: visionGoal.trim(), expected_package: visionPackage.trim(),
      }) }));
    } catch (reason) { setActionError(message(reason)); } finally { setVisionLoading(false); }
  }
  async function executeVisionClick(index: number) {
    if (!visionAnalysis) return;
    setVisionClicking(index); setActionError(""); setNotice("");
    try {
      await api("/api/vision-test/analyses/" + visionAnalysis.analysis_id + "/click", { method: "POST", body: JSON.stringify({
        candidate_index: index, confirmation: "execute-approved-test-click",
      }) });
      setNotice("Klik uji dikirim. Ambil analisis baru karena tampilan perangkat mungkin sudah berubah.");
      setVisionAnalysis(null);
    } catch (reason) { setActionError(message(reason)); } finally { setVisionClicking(null); }
  }
  const soloPlatforms = platformInfo.data?.platforms || [];
  const soloSpec = soloPlatforms.find(item => item.id === soloPlatform);
  const soloSpecActions = soloSpec?.actions || ACTION_ORDER.map(id => ({ id, label: id, supported: id !== "repost" }));
  const soloDeviceOnline = online.some(device => device.serial === soloDevice);
  const soloJobs = soloRun?.jobs || [];
  const soloResult = (soloJobs[0]?.result || null) as Record<string, unknown> | null;
  const soloLogs = Array.isArray(soloJobs[0]?.logs) ? (soloJobs[0].logs as string[]) : [];
  // Pantau run yang sedang berjalan sampai status terminal, lalu berhenti.
  useEffect(() => {
    if (!soloRunId) return;
    let stopped = false;
    let timer: ReturnType<typeof setTimeout>;
    async function tick() {
      try {
        const run = await api<Run>("/api/farm-automation/runs/" + soloRunId);
        if (stopped) return;
        setSoloRun(run);
        if (run.status !== "running") return;
      } catch { /* run mungkin sudah diarsipkan; coba lagi. */ }
      if (!stopped) timer = setTimeout(tick, 3000);
    }
    void tick();
    return () => { stopped = true; clearTimeout(timer); };
  }, [soloRunId]);
  // Layar langsung perangkat yang dipilih, supaya proses automasi terlihat.
  useEffect(() => {
    if (view !== "solo" || !soloDevice) return;
    let stopped = false;
    let timer: ReturnType<typeof setTimeout>;
    async function refresh() {
      try {
        const response = await request("/api/device-farm/devices/" + encodeURIComponent(soloDevice) + "/screenshot");
        if (!response.ok) throw new Error(response.status === 429 ? "Antrean penuh; menunggu giliran" : "HTTP " + response.status);
        if (!response.headers.get("content-type")?.startsWith("image/")) throw new Error("Format frame tidak valid");
        const blob = await response.blob();
        if (stopped) return;
        setSoloFrame(previous => { if (previous.url) URL.revokeObjectURL(previous.url); return { url: URL.createObjectURL(blob), at: Date.now() }; });
      } catch (reason) {
        if (!stopped) setSoloFrame(previous => ({ ...previous, error: message(reason) }));
      }
      if (!stopped) timer = setTimeout(refresh, 3000);
    }
    void refresh();
    return () => { stopped = true; clearTimeout(timer); };
  }, [view, soloDevice]);
  function toggleSoloAction(id: string) {
    setSoloActions(current => { const next = new Set(current); if (next.has(id)) next.delete(id); else next.add(id); return next; });
  }
  async function startSoloRun() {
    setSoloStarting(true); setActionError(""); setNotice("");
    try {
      const started = await api<{ run_id: string }>("/api/farm-automation/single-account/runs", { method: "POST", body: JSON.stringify({
        platform: soloPlatform, device_serial: soloDevice, target: soloTarget.trim(),
        username: soloAccount.trim() || "akun-aktif",
        actions: ACTION_ORDER.filter(id => soloActions.has(id)),
        comment_count: soloComments, max_posts: soloPosts, tone: soloTone,
      }) });
      setSoloRunId(started.run_id); setSoloRun(null);
      setNotice("Run satu akun dimulai. Log perangkat muncul di bawah.");
      setRevision(value => value + 1);
    } catch (reason) { setActionError(message(reason)); } finally { setSoloStarting(false); }
  }
  return <div className={styles.shell}>
    <aside className={styles.sidebar}>
      <div className={styles.logo}><span>G</span><strong>Godam Farm</strong></div>
      <nav aria-label="Menu Command Center">{NAV.map(item => <button key={item.id} title={item.label} aria-label={item.label}
        aria-current={view === item.id ? "page" : undefined} className={view === item.id ? styles.activeNav : ""} onClick={() => setView(item.id)}>
        <span aria-hidden="true">{item.icon}</span><em>{item.label}</em></button>)}</nav>
      <div className={styles.engine}><i style={{ background: healthy ? "#32c783" : "#d89a39", boxShadow: "none" }} /><span>
        <strong>{healthy ? "STF terhubung" : engine.error ? "STF bermasalah" : "Memeriksa STF…"}</strong><small>Dicek {localTime(engine.updated)}</small>
      </span></div>
    </aside>
    <main className={styles.main}>
      <header className={styles.topbar}><div><p>DEVICEFARMER STF × GODAM · LOCALHOST</p><h1>Command Center</h1></div>
        <div className={styles.topActions}><button onClick={() => setRevision(value => value + 1)}>↻ Perbarui status</button>
          <button className={styles.primary} onClick={() => { setView("diagnostics"); void scan(); }} disabled={scanning}>{scanning ? "Memeriksa…" : "Periksa koneksi"}</button></div>
      </header>
      <section className={styles.summary} aria-label="Ringkasan perangkat">
        <div><span className={styles.blueDot} /><strong>{online.length}</strong><small>STF siap</small></div>
        <div><span className={styles.grayDot} /><strong>{preparing} / {devices.filter(device => !device.present).length}</strong><small>Menyiapkan / offline</small></div>
        <div><span className={styles.violetDot} /><strong>{devices.filter(device => device.using).length}</strong><small>Direservasi</small></div>
        <div><span className={styles.greenDot} /><strong>{chosen.length}</strong><small>Dipilih</small></div>
      </section>
      <p className={styles.muted}>Inventaris terakhir {localTime(inventory.updated)}. “STF siap” berarti koneksi perangkat tersedia, bukan tugas berhasil.</p>
      {[inventory.error, engine.error, config.error, visionConfig.error, actionError].filter(Boolean).map((error, index) => <div key={index} role="alert" className={styles.error}>{error}</div>)}
      {inventory.error && <p className={styles.warning}>Inventaris adalah data lama; refresh layar dijeda.</p>}
      {notice && <div role="status" className={styles.notice}>{notice}<button onClick={() => setNotice("")}>Tutup</button></div>}
      {view === "devices" && <>
        <section className={styles.toolbar}>
          <div className={styles.tabs}>{[["all", "Semua"], ["ready", "Siap"], ["busy", "Direservasi"], ["offline", "Offline"]].map(([id, label]) =>
            <button key={id} className={filter === id ? styles.activeTab : ""} onClick={() => setFilter(id)}>{label}</button>)}</div>
          <input aria-label="Cari perangkat" value={query} onChange={event => setQuery(event.target.value)} placeholder="Cari model atau serial…" />
          <button disabled={!visibleReady.length || !!inventory.error} onClick={selectVisible}>{allChosen ? "Batalkan yang terlihat" : "Pilih yang terlihat"}</button>
          {!!selected.size && <button onClick={() => setSelected(new Set())}>Kosongkan</button>}
        </section>
        <section className={styles.content}>
          <aside className={styles.settings}><h2>Tampilan farm</h2>
            <label><span>Ukuran kartu</span><input type="range" min="138" max="230" value={tileWidth} onChange={event => setTileWidth(Number(event.target.value))} /></label>
            <label><span>Jeda antar siklus: {frameSeconds} detik</span><input type="range" min="15" max="60" value={frameSeconds} onChange={event => setFrameSeconds(Number(event.target.value))} /></label>
            <small>Dua screenshot sekaligus. Jeda saat tab tersembunyi atau panel lain dibuka.</small>
            <button onClick={() => setPauseFrames(value => !value)}>{pauseFrames ? "Lanjutkan frame" : "Jeda frame"}</button>
            <button disabled={pauseFrames} onClick={() => setFrameRevision(value => value + 1)}>Refresh layar</button>
          </aside>
          <div className={styles.devices} style={{ gridTemplateColumns: "repeat(auto-fill, minmax(min(100%, " + tileWidth + "px), 1fr))" }}>
            {!inventory.data && !inventory.error && <div className={styles.empty}>Menghubungkan ke STF…</div>}
            {inventory.data && !visible.length && <div className={styles.empty}>Tidak ada perangkat pada filter ini.</div>}
            {visible.map(device => {
              const ready = !!(device.present && device.ready), frame = frames[device.serial], power = device.battery?.level;
              return <article key={device.serial} className={styles.phoneCard + (selected.has(device.serial) ? " " + styles.selectedCard : "")}>
                <button className={styles.selectDevice} disabled={!ready || !!inventory.error} onClick={() => toggle(device.serial)} aria-label={"Pilih " + device.serial} aria-pressed={selected.has(device.serial)}>{selected.has(device.serial) ? "✓" : ""}</button>
                <div className={styles.phoneScreen}>
                  {/* ADB screenshots use runtime blob URLs. */}
                  {/* eslint-disable-next-line @next/next/no-img-element */}
                  {ready && frame?.url ? <img src={frame.url} alt={"Layar " + device.serial} style={{ opacity: frame.error ? 0.4 : 1 }} /> : <div className={styles.placeholder}><span>{pauseFrames ? "JEDA" : ready ? "STF" : "OFF"}</span></div>}
                  <span className={styles.usbBadge}>{device.using ? "DIRESERVASI" : ready ? "SIAP" : device.present ? "MENYIAPKAN" : "OFFLINE"}</span>
                  {typeof power === "number" && <span className={styles.power}>{Math.round(power / (device.battery?.scale || 100) * 100)}%</span>}
                </div>
                <div className={styles.phoneMeta}><strong>{device.marketName || device.model || "Android"}</strong><span title={device.serial}>{device.serial}</span>
                  <small>Android {device.version || "—"} · frame {localTime(frame?.at)}</small>{frame?.error && <p className={styles.frameError}>{frame.error} — bukan layar terbaru.</p>}</div>
                <button className={styles.controlButton} disabled={!ready || !stfBase || !!inventory.error} onClick={() => { setControlSerial(device.serial); setView("stf"); }}>Kontrol di sini →</button>
              </article>;
            })}
          </div>
        </section>
      </>}
      {view === "diagnostics" && <section className={styles.panel}>
        <div className={styles.panelHeader}><div><h2>Diagnostik koneksi</h2><p>Pemeriksaan baca-saja; tidak menekan layar atau mengambil alih perangkat.</p></div><button disabled={scanning} onClick={() => void scan()}>{scanning ? "Memeriksa…" : "Periksa ulang"}</button></div>
        {!diagnostics && <p>Tekan Periksa koneksi untuk membandingkan inventaris STF dan ADB.</p>}
        {diagnostics && <><p>STF: {diagnostics.stf_ok ? "terhubung" : "gagal"} · ADB: {diagnostics.adb_ok ? "terhubung" : "gagal"} · {localTime(diagnostics.checked_at)}</p>
          <p className={styles.warning}>{diagnostics.scope}</p>{diagnostics.issues.map(issue => <p className={styles.error} key={issue}>{issue}</p>)}
          <div className={styles.tableWrap}><table><thead><tr><th>Perangkat</th><th>ADB</th><th>STF</th><th>Catatan</th></tr></thead><tbody>{diagnostics.devices.map(device => <tr key={device.serial}>
            <td><code>{device.serial}</code></td><td>{device.adb}</td><td>{device.ready ? "Siap" : "Belum siap"}</td><td>{device.issues.join(" · ") || "Tidak ada masalah koneksi terdeteksi"}</td>
          </tr>)}</tbody></table></div><button onClick={() => exportReport(diagnostics, "diagnostik-farm.json")}>Unduh laporan</button></>}
      </section>}
      {view === "solo" && <section className={styles.panel}>
        <div className={styles.panelHeader}><div><h2>Automasi satu akun · like · komentar · share · repost</h2>
          <p>Eksekusi nyata pada aplikasi perangkat (bukan simulasi). Satu run = satu perangkat = satu akun; tidak ada pergantian akun.</p></div></div>
        <p className={styles.warning}>Like reel diverifikasi dari warna hati di layar; komentar dikirim dari sheet komentar; share Instagram di reel dilewati otomatis demi keamanan (sheet tidak bisa dibaca tanpa menekan kontak/DM). Repost hanya ada di X, TikTok, dan Facebook.</p>
        <div className={styles.formGrid}>
          <label>Platform<select value={soloPlatform} onChange={event => { setSoloPlatform(event.target.value); setSoloRunId(""); setSoloRun(null); }}>
            {(soloPlatforms.length ? soloPlatforms : [{ id: "instagram", label: "Instagram" }, { id: "tiktok", label: "TikTok" }, { id: "x", label: "X" }, { id: "facebook", label: "Facebook" }, { id: "threads", label: "Threads" }]).map(item => <option key={item.id} value={item.id}>{item.label}</option>)}
          </select></label>
          <label>Perangkat (wajib satu)<select value={soloDevice} onChange={event => setSoloDevice(event.target.value)}>
            <option value="">Pilih satu perangkat online</option>
            {online.map(device => <option key={device.serial} value={device.serial}>{device.marketName || device.model || "Android"} · {device.serial}</option>)}
            {soloDevice && !soloDeviceOnline && <option value={soloDevice}>{soloDevice} (offline)</option>}
          </select></label>
          <label>Akun di perangkat (label run)<input value={soloAccount} maxLength={100} onChange={event => setSoloAccount(event.target.value)} placeholder="akun-aktif" /></label>
          <label>Target (username tanpa @)<input value={soloTarget} maxLength={200} onChange={event => setSoloTarget(event.target.value)} placeholder="username_tujuan" /></label>
        </div>
        <fieldset className={styles.actionPicker}><legend>Aksi per postingan (urutan: like → komentar → share → repost)</legend>
          {soloSpecActions.map(action => <label key={action.id} className={action.supported ? "" : styles.actionDisabled}>
            <input type="checkbox" disabled={!action.supported} checked={soloActions.has(action.id)} onChange={() => toggleSoloAction(action.id)} />
            {action.label}{!action.supported && <small> — tidak didukung {soloSpec?.label || "platform ini"}</small>}
          </label>)}
        </fieldset>
        <div className={styles.formGrid}>
          <label>Jumlah postingan (1–25)<input type="number" min={1} max={25} value={soloPosts} onChange={event => setSoloPosts(Math.min(25, Math.max(1, Number(event.target.value) || 1)))} /></label>
          {soloActions.has("comment") && <label>Komentar per postingan (1–20)<input type="number" min={1} max={20} value={soloComments} onChange={event => setSoloComments(Math.min(20, Math.max(1, Number(event.target.value) || 1)))} /></label>}
          {soloActions.has("comment") && <label>Tone komentar<select value={soloTone} onChange={event => setSoloTone(event.target.value)}>{["positif", "netral", "negatif"].map(item => <option key={item}>{item}</option>)}</select></label>}
        </div>
        <button className={styles.primary} disabled={soloStarting || !soloDeviceOnline || !soloTarget.trim() || !soloActions.size}
          onClick={() => void startSoloRun()}>
          {soloStarting ? "Memulai…" : "Jalankan automasi satu akun"}</button>
        {!soloDeviceOnline && <p className={styles.warning}>Pilih perangkat yang online sebelum menjalankan.</p>}
        {soloDevice && <div className={styles.soloLive}>
          <div className={styles.soloLiveScreen}>
            {soloFrame.url ? <img src={soloFrame.url} alt={"Layar langsung " + soloDevice} style={{ opacity: soloFrame.error ? 0.4 : 1 }} />
              : <div className={styles.placeholder}><span>LIVE</span></div>}
          </div>
          <small>Layar langsung {soloDevice} · {localTime(soloFrame.at)}{soloFrame.error ? " · " + soloFrame.error : ""}</small>
        </div>}
        {soloRun && <div className={styles.previewResult}>
          <h3>Run {soloRun.run_id.slice(0, 8)} · {soloRun.platform} · {soloRun.target}</h3>
          <p>Status: {OUTCOMES[soloRun.status] || soloRun.status} · mode: {soloRun.mode === "single-account" ? "satu akun" : "banyak perangkat"}{soloRun.account ? ` · akun: ${soloRun.account}` : ""}{Array.isArray(soloRun.actions) && ` · aksi: ${(soloRun.actions as string[]).join(", ")}`}</p>
          {soloJobs.map(job => <div key={job.serial}>
            <p><strong>{job.serial}</strong> — {OUTCOMES[job.outcome] || job.outcome}: {job.message}</p>
            {soloResult && <p>Hasil: {Object.entries(soloResult).filter(([key]) => ["likes_sent", "comments_posted", "shares_sent", "reposts_sent", "posts_processed"].includes(key)).map(([key, value]) => `${key}=${String(value)}`).join(" · ")}</p>}
            {soloLogs.length > 0 && <details open={soloRun.status === "running"}><summary>Log perangkat ({soloLogs.length})</summary>
              <pre>{soloLogs.slice(-40).join("\n")}</pre></details>}
          </div>)}
        </div>}
      </section>}
      {view === "runs" && <section className={styles.panel}>
        <h2>Runs & log perangkat</h2><p>Worker selesai ≠ tugas berhasil. Hasil legacy belum diverifikasi oleh aplikasi tujuan. Hingga 100 laporan terakhir ditampilkan.</p>
        {history.error && <p role="alert" className={styles.error}>{history.error} — daftar mungkin tidak terbaru.</p>}
        {!runs.length && <p>Belum ada laporan. Laporan terminal yang dibaca panel disimpan ke volume backend.</p>}
        {runs.map(run => <details className={styles.runDetails} key={run.run_id} open={runs.length === 1}>
          <summary>{run.platform} · {run.target} · {OUTCOMES[run.status] || run.status} {run.archived ? "(arsip)" : ""}</summary>
          <p>{run.summary.total} perangkat · {run.summary.running} berjalan · {run.summary.error} gagal · {run.summary.no_comments_recorded} nol komentar · {run.summary.unverified} belum diverifikasi · {run.summary.stopped} dihentikan</p>
          {run.persistence_error && <p className={styles.error}>{run.persistence_error}</p>}
          <div className={styles.panelHeader}><code>{run.run_id}</code><div><button onClick={() => exportReport(run, "run-" + run.run_id + ".json")}>Unduh JSON</button>
            {run.status === "running" && !run.archived && <button className={styles.stopButton} disabled={!!stopping} onClick={() => void stop(run)}>{stopping === run.run_id ? "Mengirim…" : "Hentikan run"}</button>}</div></div>
          <div className={styles.tableWrap}><table><thead><tr><th>Perangkat</th><th>Hasil</th><th>Detail</th></tr></thead><tbody>{run.jobs.map(job => <tr key={job.serial}>
            <td><code>{job.serial}</code></td><td>{OUTCOMES[job.outcome] || job.outcome}</td><td><p>Pesan worker (mentah): {job.message}</p><details><summary>Log & hasil mentah</summary><pre>{JSON.stringify({ worker_status: job.status, result: job.result, logs: job.logs }, null, 2)}</pre></details></td>
          </tr>)}</tbody></table></div>
        </details>)}
      </section>}
      {view === "preview" && <section className={styles.panel}>
        <h2>Simulasi skor · tidak mengendalikan akun</h2>
        <p className={styles.warning}>Model eksperimen dengan bobot heuristik, bukan ML terlatih/terkalibrasi. Angka tidak menunjukkan peluang tugas berhasil. Tidak ada like, komentar, share, atau pergantian akun yang dijalankan.</p>
        <div className={styles.formGrid}>
          <label>Platform<select value={platform} onChange={event => { setPlatform(event.target.value); setPreview(null); }}>{["instagram", "tiktok", "x", "facebook", "threads"].map(item => <option key={item}>{item}</option>)}</select></label>
          <label>Topik pembanding (opsional, pisahkan koma)<input value={topics} onChange={event => { setTopics(event.target.value); setPreview(null); }} placeholder="teknologi, pendidikan" /></label>
          <label className={styles.fullWidth}>Teks konteks, bukan URL akun<textarea rows={5} maxLength={5000} value={caption} onChange={event => { setCaption(event.target.value); setPreview(null); }} /></label>
        </div>
        <p>Inventaris akun tidak tersedia. Tidak ada akun contoh yang dianggap login dan tidak ada rencana switch akun.</p>
        <button disabled={analyzing || !caption.trim()} onClick={() => void analyze()}>{analyzing ? "Menghitung…" : "Hitung simulasi"}</button>
        {preview && <div className={styles.previewResult}><h3>Hasil simulasi (tanpa eksekusi)</h3><p>{preview.model_info?.note}</p>
          {preview.decisions.map(decision => <p key={decision.action}>{decision.action}: skor mentah {decision.confidence.toFixed(3)} / 1 — bukan persentase sukses</p>)}</div>}
      </section>}
      {view === "vision" && <section className={styles.panel}>
        <div className={styles.panelHeader}><div><h2>AI Vision Test</h2><p>Screenshot STF → OpenAI Vision → policy lokal → kandidat klik. Tidak ada klik otomatis dari respons model.</p></div>
          <span className={`${styles.statusPill} ${visionConfig.data?.configured ? styles.statusReady : styles.statusBlocked}`}>
            {visionConfig.data?.configured ? "API siap" : "API belum dikonfigurasi"}
          </span></div>
        <p className={styles.warning}>Hanya untuk package aplikasi uji milik Anda yang masuk allowlist server. Login, izin, pembayaran, penghapusan, publikasi, pesan, dan engagement sosial selalu diblokir.</p>
        <div className={styles.visionMeta}>
          <span>Provider: {visionConfig.data?.provider || "—"}</span><span>Model: {visionConfig.data?.model || "—"}</span>
          <span>Eksekusi: {visionConfig.data?.execution_enabled ? "aktif, tetap perlu klik operator" : "dry-run"}</span>
        </div>
        <div className={styles.formGrid}>
          <label>Perangkat<select value={visionSerial} onChange={event => { setVisionSerial(event.target.value); setVisionAnalysis(null); }}>
            <option value="">Pilih perangkat STF siap</option>{online.map(device => <option key={device.serial} value={device.serial}>{device.marketName || device.model || "Android"} · {device.serial}</option>)}
          </select></label>
          <label>Package aplikasi uji<input value={visionPackage} onChange={event => { setVisionPackage(event.target.value); setVisionAnalysis(null); }} placeholder="com.perusahaan.aplikasi.debug" /></label>
          <label className={styles.fullWidth}>Sasaran pengujian<textarea rows={4} maxLength={1000} value={visionGoal} onChange={event => { setVisionGoal(event.target.value); setVisionAnalysis(null); }} placeholder="Contoh: buka halaman Profil dari layar utama aplikasi staging" /></label>
        </div>
        <div className={styles.allowedPackages}><strong>Package yang diizinkan server:</strong>
          {visionConfig.data?.allowed_packages.length ? visionConfig.data.allowed_packages.map(item => <code key={item}>{item}</code>) : <span>Belum ada. Isi VISION_TEST_ALLOWED_PACKAGES.</span>}
        </div>
        <button disabled={visionLoading || !visionConfig.data?.configured || !visionSerial || !visionPackage.trim() || !visionGoal.trim()}
          onClick={() => void analyzeVision()}>{visionLoading ? "Menganalisis screenshot…" : "Analisis layar (dry-run)"}</button>
        {visionAnalysis && <section className={styles.visionResult}>
          <div className={styles.panelHeader}><div><h3>Hasil vision</h3><p>{visionAnalysis.screen_summary}</p></div><span className={styles.statusPill}>{visionAnalysis.goal_reached ? "Sasaran sudah tercapai" : "Perlu aksi berikutnya"}</span></div>
          {visionAnalysis.warnings.map(item => <p className={styles.warning} key={item}>{item}</p>)}
          <div className={styles.candidateGrid}>{visionAnalysis.candidates.map((candidate, index) => <article key={`${index}-${candidate.label}`} className={`${styles.candidate} ${styles["decision_" + candidate.decision]}`}>
            <header><strong>{index + 1}. {candidate.label}</strong><span>{candidate.decision.toUpperCase()}</span></header>
            <p>{candidate.description}</p><small>Skor visual: {candidate.confidence.toFixed(2)} · risiko: {candidate.risk} · koordinat: {candidate.x},{candidate.y}</small>
            <p>{candidate.policy_reason}</p>{candidate.matched_terms.length > 0 && <small>Istilah terlindungi: {candidate.matched_terms.join(", ")}</small>}
            {visionAnalysis.execution_enabled && candidate.decision === "allow" && <button disabled={visionClicking !== null}
              onClick={() => void executeVisionClick(index)}>{visionClicking === index ? "Mengirim klik…" : "Klik kandidat ini"}</button>}
          </article>)}</div>
        </section>}
      </section>}
      {view === "stf" && <section className={styles.panel}>
        <div className={styles.panelHeader}><div><h2>Kontrol STF {controlSerial && "· " + controlSerial}</h2><p>Kontrol manual asli STF di Command Center. Reservasi/login tetap dikelola STF.</p></div>
          <div><button onClick={() => setControlSerial("")}>Daftar STF</button>{stfUrl && <a href={stfUrl} target="_blank" rel="noreferrer">Buka tab terpisah ↗</a>}</div></div>
        {stfUrl ? <iframe key={stfUrl} className={styles.stfFrame} title="Kontrol DeviceFarmer STF" src={stfUrl} allow="clipboard-read; clipboard-write; fullscreen" /> : <p>Menunggu konfigurasi STF…</p>}
      </section>}
    </main>
  </div>;
}
