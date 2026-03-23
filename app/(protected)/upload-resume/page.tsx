"use client";

import { useState, useRef, useCallback } from "react";
import { useAuth } from "@/context/AuthContext";
import { uploadResume, saveResumeMeta, getResumes } from "@/lib/supabase";
import { useEffect } from "react";

type ResumeRow = { id: string; title: string; content: { file_url: string; file_name: string }; updated_at: string; created_at: string; parsed_text?: string | null };

type UploadState = "idle" | "uploading" | "success" | "error";

export default function UploadResumePage() {
  const { user } = useAuth();
  const [dragOver, setDragOver] = useState(false);
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [uploadState, setUploadState] = useState<UploadState>("idle");
  const [uploadedUrl, setUploadedUrl] = useState<string | null>(null);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);
  const [resumes, setResumes] = useState<ResumeRow[]>([]);
  const [loadingResumes, setLoadingResumes] = useState(true);
  const [reparsingId, setReparsingId] = useState<string | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const fetchResumes = useCallback(async () => {
    if (!user) return;
    const { data } = await getResumes(user.id);
    if (data) setResumes(data as ResumeRow[]);
    setLoadingResumes(false);
  }, [user]);

  useEffect(() => {
    fetchResumes();
  }, [fetchResumes]);

  const handleReparse = async (r: ResumeRow) => {
    if (!user || reparsingId) return;
    setReparsingId(r.id);
    try {
      const res = await fetch("/api/ai/parse-resume", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ file_url: r.content.file_url, user_id: user.id, resume_id: r.id }),
      });
      if (res.ok) {
        await fetchResumes();
      }
    } catch {
      // non-fatal
    } finally {
      setReparsingId(null);
    }
  };

  const handleFile = (file: File) => {
    // Validate type — PDF, Word (.doc/.docx), and plain text (.txt)
    const allowedTypes = [
      "application/pdf",
      "application/msword",
      "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
      "text/plain",
    ];
    if (!allowedTypes.includes(file.type)) {
      setErrorMsg("Only PDF, Word (.doc/.docx), and plain text (.txt) files are accepted.");
      return;
    }
    // Validate size (5 MB)
    if (file.size > 5 * 1024 * 1024) {
      setErrorMsg("File size must be under 5 MB.");
      return;
    }
    setErrorMsg(null);
    setSelectedFile(file);
    setUploadState("idle");
    setUploadedUrl(null);
  };

  const onDrop = (e: React.DragEvent) => {
    e.preventDefault();
    setDragOver(false);
    const file = e.dataTransfer.files[0];
    if (file) handleFile(file);
  };

  const handleUpload = async () => {
    if (!selectedFile || !user) return;
    setUploadState("uploading");
    setErrorMsg(null);

    const { url, error } = await uploadResume(selectedFile, user.id);

    if (error || !url) {
      setErrorMsg(error?.message ?? "Upload failed. Check your Supabase storage config.");
      setUploadState("error");
      return;
    }

    // Extract resume text server-side (PDF / DOCX → plain text for AI features)
    let parsedText: string | undefined;
    try {
      const parseRes = await fetch("/api/ai/parse-resume", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ file_url: url, user_id: user.id }),
      });
      if (parseRes.ok) {
        const data = await parseRes.json();
        parsedText = data.parsed_text as string;
      }
    } catch {
      // Non-fatal — AI features will gracefully degrade if text extraction fails
    }

    const { error: metaError } = await saveResumeMeta(user.id, url, selectedFile.name, parsedText);
    if (metaError) {
      setErrorMsg(metaError.message);
      setUploadState("error");
      return;
    }

    setUploadedUrl(url);
    setUploadState("success");
    setSelectedFile(null);
    if (fileInputRef.current) fileInputRef.current.value = "";
    fetchResumes();
  };

  const formatSize = (bytes: number) =>
    bytes < 1024 * 1024
      ? `${(bytes / 1024).toFixed(0)} KB`
      : `${(bytes / (1024 * 1024)).toFixed(1)} MB`;

  return (
    <div className="max-w-3xl mx-auto px-6 py-12">
      {/* Header */}
      <div className="mb-10 animate-fadeUp">
        <p className="font-mono text-xs text-slate-500 tracking-widest uppercase mb-2">
          Resume
        </p>
        <h1 className="font-display font-bold text-4xl text-white mb-2">
          Upload your <span className="gradient-text">resume</span>
        </h1>
        <p className="text-slate-400 font-body">
          PDF, Word (.doc / .docx), or plain text (.txt) — up to 5 MB. Stored securely in Supabase Storage.
        </p>
      </div>

      {/* Drop zone */}
      <div
        className={`animate-fadeUp animate-fadeUp-delay-1 relative rounded-xl border-2 border-dashed transition-all duration-200 cursor-pointer mb-6
          ${dragOver
            ? "border-amber-400 bg-amber-400/5"
            : selectedFile
            ? "border-amber-400/40 bg-amber-400/3"
            : "border-slate-700 bg-slate-900 hover:border-slate-600"
          }`}
        onClick={() => fileInputRef.current?.click()}
        onDragOver={(e) => { e.preventDefault(); setDragOver(true); }}
        onDragLeave={() => setDragOver(false)}
        onDrop={onDrop}
      >
        <div className="flex flex-col items-center justify-center py-14 px-8 text-center pointer-events-none">
          <div className={`w-14 h-14 rounded-xl mb-4 flex items-center justify-center
            ${dragOver ? "bg-amber-400/20" : "bg-slate-800"}`}>
            <svg className={`w-7 h-7 transition-colors ${dragOver ? "text-amber-400" : "text-slate-500"}`}
              fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
              <path strokeLinecap="round" strokeLinejoin="round"
                d="M12 16.5V9.75m0 0 3 3m-3-3-3 3M6.75 19.5a4.5 4.5 0 0 1-1.41-8.775 5.25 5.25 0 0 1 10.338-2.32 3.75 3.75 0 0 1 3.357 5.098m-5.034 2.997h.01" />
            </svg>
          </div>

          {selectedFile ? (
            <>
              <p className="font-body font-semibold text-white mb-1">{selectedFile.name}</p>
              <p className="font-mono text-xs text-amber-400">{formatSize(selectedFile.size)}</p>
              <p className="font-body text-xs text-slate-500 mt-2">Click to change file</p>
            </>
          ) : (
            <>
              <p className="font-body font-semibold text-white mb-1">
                {dragOver ? "Drop your file here" : "Drop your file here, or click to browse"}
              </p>
              <p className="font-body text-sm text-slate-500">PDF or .docx • Max 5 MB</p>
            </>
          )}
        </div>
        <input
          ref={fileInputRef}
          type="file"
          accept=".pdf,.doc,.docx,application/pdf,application/msword,application/vnd.openxmlformats-officedocument.wordprocessingml.document"
          className="sr-only"
          onChange={(e) => {
            const file = e.target.files?.[0];
            if (file) handleFile(file);
          }}
        />
      </div>

      {errorMsg && (
        <div className="mb-4 rounded-lg bg-red-500/10 border border-red-500/20 px-4 py-3 text-red-400 font-body text-sm animate-fadeUp">
          {errorMsg}
        </div>
      )}

      {uploadState === "success" && (
        <div className="mb-4 rounded-lg bg-emerald-500/10 border border-emerald-500/20 px-4 py-3 text-emerald-400 font-body text-sm animate-fadeUp">
          ✓ Resume uploaded successfully.{" "}
          {uploadedUrl && (
            <a href={uploadedUrl} target="_blank" rel="noopener noreferrer"
              className="underline hover:text-emerald-300">
              View file →
            </a>
          )}
        </div>
      )}

      {/* Upload button */}
      {selectedFile && (
        <div className="animate-fadeUp">
          <button
            onClick={handleUpload}
            disabled={uploadState === "uploading"}
            className="btn-primary w-full"
          >
            {uploadState === "uploading" ? (
              <span className="flex items-center justify-center gap-2">
                <span className="w-4 h-4 border-2 border-slate-900 border-t-transparent rounded-full animate-spin" />
                Uploading…
              </span>
            ) : (
              "Upload Resume →"
            )}
          </button>
        </div>
      )}

      {/* Previously uploaded */}
      <div className="mt-12 animate-fadeUp animate-fadeUp-delay-3">
        <h2 className="font-display font-semibold text-lg text-white mb-4">
          Uploaded Resumes
        </h2>

        {loadingResumes ? (
          <div className="card text-slate-500 text-sm font-body">Loading…</div>
        ) : resumes.length === 0 ? (
          <div className="card border-dashed text-center py-8">
            <p className="text-slate-500 font-body text-sm">No resumes uploaded yet.</p>
          </div>
        ) : (
          <div className="space-y-2">
            {resumes.map((r) => (
              <div key={r.id} className="card py-3 flex items-center justify-between group">
                <div className="flex items-center gap-3 min-w-0">
                  <span className="text-amber-400 text-lg flex-shrink-0">📄</span>
                  <div className="min-w-0">
                    <span className="font-body text-sm text-white truncate block">{r.title}</span>
                    {r.parsed_text
                      ? <span className="font-mono text-[10px] text-emerald-500">✓ AI context ready</span>
                      : <span className="font-mono text-[10px] text-slate-500">No AI context</span>
                    }
                  </div>
                </div>
                <div className="flex items-center gap-3 ml-4 flex-shrink-0">
                  <span className="font-mono text-xs text-slate-500">
                    {new Date(r.created_at).toLocaleDateString()}
                  </span>
                  {!r.parsed_text && (
                    <button
                      onClick={() => handleReparse(r)}
                      disabled={reparsingId === r.id}
                      className="font-body text-xs text-violet-400 hover:text-violet-300 border border-violet-400/30 rounded px-2 py-0.5 transition-colors disabled:opacity-50"
                    >
                      {reparsingId === r.id ? "Parsing…" : "Re-parse AI"}
                    </button>
                  )}
                  <a
                    href={r.content?.file_url}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="font-body text-xs text-amber-400 hover:text-amber-300 opacity-0 group-hover:opacity-100 transition-opacity"
                  >
                    View →
                  </a>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
