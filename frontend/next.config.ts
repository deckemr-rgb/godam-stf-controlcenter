import type { NextConfig } from "next";

// Mode "standalone" hanya dipakai saat membangun image Docker untuk VPS
// (Dockerfile menyalin .next/standalone). Di Vercel mode ini membuat build
// gagal: Vercel mencari berkas jejak .next/*.nft.json yang tidak dihasilkan
// build standalone, sehingga deploy berhenti dengan ENOENT.
const nextConfig: NextConfig = {
  ...(process.env.BUILD_STANDALONE === "1" ? { output: "standalone" as const } : {}),
};

export default nextConfig;
