"use client";

import { useCallback, useEffect, useState } from "react";
import styles from "./DeviceTargetSelect.module.css";

type Device = {
  serial: string;
  present?: boolean;
  ready?: boolean;
  usable?: boolean;
  using?: boolean;
  manufacturer?: string;
  model?: string;
  marketName?: string;
  version?: string;
};

type Props = {
  value: string;
  onChange: (serial: string) => void;
  disabled?: boolean;
};

export default function DeviceTargetSelect({ value, onChange, disabled = false }: Props) {
  const [devices, setDevices] = useState<Device[]>([]);
  const [configured, setConfigured] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  const refresh = useCallback(async () => {
    try {
      const token = window.localStorage.getItem("ig-tools-token");
      const headers = token ? { Authorization: `Bearer ${token}` } : undefined;
      const configResponse = await fetch("/api/device-farm/config", {
        cache: "no-store",
        headers,
      });
      const config = await configResponse.json();
      setConfigured(Boolean(config.configured));
      if (!config.configured) {
        setDevices([]);
        return;
      }
      const response = await fetch("/api/device-farm/devices", {
        cache: "no-store",
        headers,
      });
      const payload = await response.json();
      if (!response.ok) throw new Error(payload.detail || "Device farm tidak merespons.");
      setDevices(payload.devices || []);
      setError("");
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Device farm tidak merespons.");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void refresh();
    const timer = window.setInterval(() => void refresh(), 5000);
    return () => window.clearInterval(timer);
  }, [refresh]);

  const available = devices.filter(
    (device) => device.present && device.ready && device.usable !== false
  );

  return (
    <label className={styles.field}>
      <span>Target eksekusi</span>
      <select
        className={styles.select}
        value={value}
        onChange={(event) => onChange(event.target.value)}
        disabled={disabled || loading}
      >
        <option value="">Browser server Godam</option>
        {available.map((device) => (
          <option key={device.serial} value={device.serial}>
            STF · {device.marketName || device.model || device.manufacturer || device.serial}
            {device.version ? ` · Android ${device.version}` : ""}
          </option>
        ))}
      </select>
      {value ? (
        <small className={`${styles.hint} ${styles.active}`}>
          Instagram dijalankan langsung pada perangkat STF. Session ID browser tidak diperlukan.
        </small>
      ) : !configured ? (
        <small className={`${styles.hint} ${styles.warning}`}>Integrasi STF belum aktif.</small>
      ) : error ? (
        <small className={`${styles.hint} ${styles.warning}`}>{error}</small>
      ) : available.length === 0 ? (
        <small className={styles.hint}>
          Belum ada Android online. Sambungkan perangkat ke provider STF; mode browser tetap bisa dipakai.
        </small>
      ) : (
        <small className={styles.hint}>
          Pilih Android STF atau biarkan browser server sebagai target.
        </small>
      )}
    </label>
  );
}
