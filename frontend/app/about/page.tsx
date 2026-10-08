import Link from "next/link";
import styles from "./about.module.css";

export default function AboutPage() {
  return (
    <main className={styles.page}>
      <Link className={styles.back} href="/">← Kembali</Link>
      <h1 className={styles.title}>Cara Penggunaan</h1>
      <p className={styles.lede}>
        Login otomatis memakai <strong>Session ID</strong> Instagram, tanpa
        username/password dan tanpa CAPTCHA.
      </p>
      <ol className={styles.steps}>
        <li>Ambil cookie <code className={styles.code}>sessionid</code> dari akun Instagram (browser normal, sudah login).</li>
        <li>Tempel Session ID, nama akun, dan channel target pada form.</li>
        <li>Klik <strong>Mulai</strong> — Chrome live tampil di bagian bawah sampai selesai.</li>
        <li>Log di sisi kanan menampilkan langkah yang sedang dikerjakan.</li>
      </ol>
      <p className={styles.warn}>
        Gunakan dengan risiko sendiri. Pastikan aktivitas dan komentar mematuhi
        kebijakan Instagram serta hukum yang berlaku. Jangan bagikan Session ID
        ke siapa pun.
      </p>
    </main>
  );
}
