"use client";

import { usePresence } from "./presence-context";
import styles from "./LiveStats.module.css";

/** Dua angka "hidup" di landing page: pengguna online & bot yang berjalan. */
export default function LiveStats() {
  const { online, runningBots, ready } = usePresence();

  return (
    <div className={styles.row} aria-live="polite">
      <div className={styles.stat} title="Jumlah tab yang sedang membuka website ini (diperbarui langsung)">
        <span className={`${styles.dot} ${ready ? styles.dotLive : ""}`} aria-hidden="true" />
        <strong className={styles.value}>{ready ? online : "—"}</strong>
        <span className={styles.label}>pengguna online</span>
      </div>
      <span className={styles.sep} aria-hidden="true" />
      <div className={styles.stat} title="Script bot (Chromium) yang sedang benar-benar berjalan di server">
        <span className={styles.icon} aria-hidden="true">🤖</span>
        <strong className={styles.value}>{ready ? runningBots : "—"}</strong>
        <span className={styles.label}>bot berjalan</span>
      </div>
    </div>
  );
}
