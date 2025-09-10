"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { ingestRepo, getStatus } from "@/lib/api";

export default function UploadPage() {
  const [file, setFile] = useState<File | null>(null);
  const [status, setStatus] = useState<string>("idle");
  const router = useRouter();

  async function handleUpload() {
    if (!file) return;
    setStatus("Uploading…");

    try {
      const { repoId, jobId } = await ingestRepo(file);

      setStatus("Processing…");

      let done = false;
      while (!done) {
        const s = await getStatus(jobId);
        if (s.phase === "done") {
          done = true;
          router.push(`/repo/${repoId}`);
        } else {
          await new Promise((r) => setTimeout(r, 1500));
        }
      }
    } catch (err) {
      console.error(err);
      setStatus("Error during upload");
    }
  }

  return (
    <div className="flex min-h-screen items-center justify-center bg-slate-900 text-white">
      <div className="rounded-2xl border border-white/20 bg-white/5 p-10">
        <h1 className="mb-4 text-lg font-bold">Upload Repository</h1>
        <input
          type="file"
          onChange={(e) => setFile(e.target.files?.[0] || null)}
          className="mb-4"
        />
        <button
          onClick={handleUpload}
          className="rounded-xl bg-white/10 px-4 py-2 hover:bg-white/20"
        >
          {status === "idle" ? "Upload" : status}
        </button>
      </div>
    </div>
  );
}
