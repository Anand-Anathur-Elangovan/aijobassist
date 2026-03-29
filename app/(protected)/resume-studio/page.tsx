"use client";

import { useEffect, useState, useCallback, useRef } from "react";
import { useAuth } from "@/context/AuthContext";
import { supabase } from "@/lib/supabase";
import { UsageBadge } from "@/components/SubscriptionGuard";
import type {
  TailoredResumeResult,
  CoverLetterResult,
  AnalyzeResumeResult,
} from "@/lib/ai";

// ── Types ──────────────────────────────────────────────────────────────────
type ResumeRow    = { id: string; title: string; parsed_text?: string | null };
type SavedVersion = {
  id: string; version_name: string;
  ats_score: number | null; created_at: string; tailored_text: string;
};
type ActiveTab = "analyze" | "tailor" | "cover";

// ── Helpers ────────────────────────────────────────────────────────────────
function safeArr<T>(val: T[] | undefined | null): T[] {
  return Array.isArray(val) ? val : [];
}

function escHtml(s: string): string {
  return s
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

// ── Resume HTML Builder — converts plain-text resume into printable HTML ──
function buildResumeHTMLPage(text: string, company: string, role: string): string {
  const safeTitle = `${company || "Resume"}_${role || "Tailored"}`.replace(/\s+/g, "_");
  const lines     = text.split("\n");
  let   body      = "";
  let   inList    = false;
  let   nameSet   = false;

  for (const rawLine of lines) {
    const line = rawLine.trim();

    if (!line) {
      if (inList) { body += "</ul>"; inList = false; }
      body += `<div style="height:5pt"></div>`;
      continue;
    }

    // ── Heuristic: first non-blank line before any section is the candidate name
    if (!nameSet && !/^[•\-\*→]/.test(line)) {
      const looksLikeName = /^[A-Z][a-z]+(\s[A-Z][a-z]+){1,3}$/.test(line);
      if (looksLikeName) {
        body += `<div style="font-size:18pt;font-weight:700;text-align:center;margin-bottom:4pt;">${escHtml(line)}</div>`;
        nameSet = true;
        continue;
      }
    }

    // ── Contact / sub-header line (email/phone/linkedin patterns)
    if (
      !nameSet &&
      (line.includes("@") || line.includes("|") || /\+?\d[\d\s\-]{7,}/.test(line))
    ) {
      body += `<div style="font-size:10pt;text-align:center;color:#444;margin-bottom:10pt;">${escHtml(line)}</div>`;
      nameSet = true;
      continue;
    }

    // ── Section header: ALL CAPS or known section keywords
    const isSectionHeader =
      /^[A-Z][A-Z\s&\/]{3,}$/.test(line) ||
      /^(professional\s+)?(summary|experience|education|skills|projects?|certifications?|achievements?|awards?|publications?|languages?|interests?|references?|work\s+history|objective|profile|highlights?|volunteering)/i.test(
        line,
      );

    if (isSectionHeader) {
      if (inList) { body += "</ul>"; inList = false; }
      body += `
        <div style="margin-top:14pt;border-bottom:1.5px solid #1a1a1a;padding-bottom:3pt;margin-bottom:7pt;">
          <span style="font-size:11pt;font-weight:700;text-transform:uppercase;letter-spacing:0.6px;">${escHtml(line)}</span>
        </div>`;
      continue;
    }

    // ── Bullet point
    if (/^[•\-\*→]\s*\S/.test(line)) {
      if (!inList) {
        body += `<ul style="margin:0 0 4pt 18pt;padding:0;">`;
        inList = true;
      }
      body += `<li style="margin-bottom:2.5pt;line-height:1.45;">${escHtml(line.replace(/^[•\-\*→]\s*/, ""))}</li>`;
      continue;
    }

    if (inList) { body += "</ul>"; inList = false; }

    // ── Company / role / date line (has | or – separators, or starts with a date)
    if (
      /\s[|–\-]\s/.test(line) ||
      /^(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec|\d{4})\b/.test(line)
    ) {
      body += `<div style="font-weight:600;margin-top:8pt;margin-bottom:2pt;line-height:1.3;">${escHtml(line)}</div>`;
      continue;
    }

    // ── Skills list (comma-separated, no verb)
    if (line.includes(",") && line.split(",").length > 3 && !/[.?!]$/.test(line)) {
      body += `<p style="margin-bottom:4pt;line-height:1.4;">${escHtml(line)}</p>`;
      continue;
    }

    // ── Default paragraph
    body += `<p style="margin-bottom:3pt;line-height:1.45;">${escHtml(line)}</p>`;
  }

  if (inList) body += "</ul>";

  return `<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8"/>
  <title>${escHtml(safeTitle)}</title>
  <style>
    *  { box-sizing: border-box; margin: 0; padding: 0; }
    html, body {
      font-family: Calibri, "Segoe UI", Arial, Helvetica, sans-serif;
      font-size: 11pt;
      color: #111;
      background: #fff;
      line-height: 1.45;
    }
    .page { max-width: 8in; margin: 0 auto; padding: 0.65in 0.8in; }
    @media print {
      html, body { background: #fff; }
      .page { padding: 0; max-width: 100%; }
      @page { margin: 0.65in 0.8in; size: letter portrait; }
      .no-print { display: none !important; }
    }
    .toolbar {
      position: fixed; top: 0; left: 0; right: 0;
      background: #1e293b; color: #fff; padding: 10px 20px;
      display: flex; align-items: center; justify-content: space-between;
      font-family: Arial, sans-serif; font-size: 13px; z-index: 999;
    }
    .btn {
      background: #f59e0b; color: #000; border: none;
      padding: 6px 18px; border-radius: 6px; cursor: pointer;
      font-weight: 700; font-size: 13px;
    }
    .spacer { height: 50px; }
  </style>
</head>
<body>
  <div class="toolbar no-print">
    <span>📄 <strong>${escHtml(safeTitle)}.pdf</strong> — preview before saving</span>
    <button class="btn" onclick="window.print()">⬇ Save / Print as PDF</button>
  </div>
  <div class="spacer no-print"></div>
  <div class="page">
    ${body}
  </div>
</body>
</html>`;
}

// ── Score Ring ─────────────────────────────────────────────────────────────
function ScoreRing({ score, label }: { score: number | undefined | null; label: string }) {
  const s     = Math.round(Math.min(100, Math.max(0, score ?? 0)));
  const r     = 40;
  const circ  = 2 * Math.PI * r;
  const dash  = (s / 100) * circ;
  const color = s >= 75 ? "#34d399" : s >= 50 ? "#fbbf24" : "#f87171";
  return (
    <div className="flex flex-col items-center gap-1">
      <svg width="100" height="100" className="rotate-[-90deg]">
        <circle cx="50" cy="50" r={r} fill="none" stroke="#1e293b" strokeWidth="10" />
        <circle
          cx="50" cy="50" r={r} fill="none" stroke={color} strokeWidth="10"
          strokeDasharray={`${dash} ${circ}`} strokeLinecap="round"
          style={{ transition: "stroke-dasharray 0.6s ease" }}
        />
        <text x="50" y="56" textAnchor="middle" dominantBaseline="middle"
          fill={color} fontSize="18" fontWeight="700"
          style={{ transform: "rotate(90deg) translate(0,-100px)" }}
        >
          {s}%
        </text>
      </svg>
      <p className="font-mono text-xs text-slate-500">{label}</p>
    </div>
  );
}

// ── Main Page ──────────────────────────────────────────────────────────────
export default function ResumeStudioPage() {
  const { user } = useAuth();

  // Inputs
  const [resumeText, setResumeText] = useState("");
  const [jdText,     setJdText    ] = useState("");
  const [company,    setCompany   ] = useState("");
  const [role,       setRole      ] = useState("");

  // Tracks the uploaded PDF's storage URL so it can be referenced later
  const [originalFileUrl, setOriginalFileUrl] = useState("");

  // Results
  const [analysis,    setAnalysis   ] = useState<AnalyzeResumeResult | null>(null);
  const [tailored,    setTailored   ] = useState<TailoredResumeResult | null>(null);
  const [coverLetter, setCoverLetter] = useState<CoverLetterResult | null>(null);

  // Workflow
  const [activeTab,    setActiveTab   ] = useState<ActiveTab>("analyze");
  const [refinePrompt, setRefinePrompt] = useState("");

  // Loading
  const [analyzing,       setAnalyzing      ] = useState(false);
  const [tailoring,       setTailoring      ] = useState(false);
  const [generatingCover, setGeneratingCover] = useState(false);
  const [uploadingPdf,    setUploadingPdf   ] = useState(false);
  const [savingLib,       setSavingLib      ] = useState(false);

  // DB + UI
  const [savedResumes,  setSavedResumes ] = useState<ResumeRow[]>([]);
  const [savedVersions, setSavedVersions] = useState<SavedVersion[]>([]);
  const [savedLibMsg,   setSavedLibMsg  ] = useState("");   // success/error after save
  const [copied,        setCopied       ] = useState("");
  const [error,         setError        ] = useState("");

  const fileInputRef = useRef<HTMLInputElement>(null);

  // ── Load saved resumes & versions ──────────────────────────────────────
  const loadData = useCallback(async () => {
    if (!user) return;
    const [r1, r2] = await Promise.all([
      supabase
        .from("resumes")
        .select("id, title, parsed_text")
        .eq("user_id", user.id)
        .order("created_at", { ascending: false }),
      supabase
        .from("resume_versions")
        .select("id, version_name, ats_score, created_at, tailored_text")
        .eq("user_id", user.id)
        .order("created_at", { ascending: false })
        .limit(20),
    ]);
    if (r1.data) setSavedResumes(r1.data as ResumeRow[]);
    if (r2.data) setSavedVersions(r2.data as SavedVersion[]);
  }, [user]);

  useEffect(() => { loadData(); }, [loadData]);

  // ── PDF Upload + Parse ─────────────────────────────────────────────────
  const handlePdfUpload = async (file: File) => {
    if (!user) {
      setError("Please sign in to upload PDF files, or paste resume text directly.");
      return;
    }
    if (file.size > 5 * 1024 * 1024) { setError("File too large. Maximum 5 MB."); return; }
    const ext = file.name.split(".").pop()?.toLowerCase() ?? "";
    if (!["pdf", "docx", "doc", "txt"].includes(ext)) {
      setError("Unsupported file type. Use PDF, DOCX, DOC, or TXT.");
      return;
    }
    setUploadingPdf(true);
    setError("");
    try {
      const filePath = `${user.id}/temp_${Date.now()}_${file.name}`;
      const { error: uploadErr } = await supabase.storage
        .from("resumes").upload(filePath, file, { upsert: true });
      if (uploadErr) throw new Error(`Upload failed: ${uploadErr.message}`);

      const { data: urlData } = supabase.storage.from("resumes").getPublicUrl(filePath);
      const fileUrl = urlData.publicUrl;
      setOriginalFileUrl(fileUrl);

      const res  = await fetch("/api/ai/parse-resume", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ file_url: fileUrl, user_id: user.id }),
      });
      const data = await res.json();
      if (!res.ok || !data.parsed_text) throw new Error(data.error || "Failed to extract text");
      setResumeText(data.parsed_text as string);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "PDF upload failed. Please paste text directly.");
    } finally {
      setUploadingPdf(false);
    }
  };

  // ── Analyze ────────────────────────────────────────────────────────────
  const handleAnalyze = async () => {
    if (!resumeText.trim() || !jdText.trim()) {
      setError("Please enter both resume text and job description.");
      return;
    }
    setError("");
    setAnalyzing(true);
    setAnalysis(null);
    try {
      const res  = await fetch("/api/ai/analyze-resume", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ resume_text: resumeText, jd_text: jdText }),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.error || "Analysis failed");
      if (typeof data.score !== "number") throw new Error("Invalid response from server");
      setAnalysis(data as AnalyzeResumeResult);
      setActiveTab("analyze");
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Analysis failed. Please try again.");
    } finally {
      setAnalyzing(false);
    }
  };

  // ── Tailor / Refine ────────────────────────────────────────────────────
  const handleTailor = async (refineText = "") => {
    if (!resumeText.trim() || !jdText.trim()) {
      setError("Resume and job description are required.");
      return;
    }
    setError("");
    setSavedLibMsg("");
    setTailoring(true);
    try {
      const res  = await fetch("/api/ai/tailor-resume", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          resume_text: resumeText,
          jd_text:     jdText,
          ...(refineText.trim() ? { custom_prompt: refineText } : {}),
        }),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.error || "Tailoring failed");
      if (typeof data.tailored_text !== "string") throw new Error("Invalid response from server");
      setTailored(data as TailoredResumeResult);
      setActiveTab("tailor");
      if (refineText) setRefinePrompt("");
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Tailoring failed. Please try again.");
    } finally {
      setTailoring(false);
    }
  };

  // ── Cover Letter ───────────────────────────────────────────────────────
  const handleCoverLetter = async () => {
    if (!resumeText.trim() || !jdText.trim()) {
      setError("Resume and job description are required.");
      return;
    }
    setError("");
    setGeneratingCover(true);
    try {
      const res  = await fetch("/api/ai/cover-letter", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ resume_text: resumeText, jd_text: jdText, company, role }),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.error || "Cover letter generation failed");
      if (typeof data.cover_letter !== "string") throw new Error("Invalid response from server");
      setCoverLetter(data as CoverLetterResult);
      setActiveTab("cover");
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Cover letter generation failed.");
    } finally {
      setGeneratingCover(false);
    }
  };

  // ── Download PDF ───────────────────────────────────────────────────────
  // Opens a new window with a professionally formatted, print-ready version
  // of the tailored resume. Browser "Save as PDF" produces the final file.
  const handleDownloadPDF = () => {
    if (!tailored?.tailored_text) return;
    const html = buildResumeHTMLPage(tailored.tailored_text, company, role);
    const win  = window.open("", "_blank", "width=960,height=720,toolbar=0,menubar=0");
    if (!win) {
      setError("Please allow pop-ups for this site, then click Download PDF again.");
      return;
    }
    win.document.open();
    win.document.write(html);
    win.document.close();
  };

  // ── Save to My Resumes (for Automation) ───────────────────────────────
  const handleSaveToLibrary = async () => {
    if (!tailored?.tailored_text || !user) return;
    if (!company.trim() && !role.trim()) {
      setError("Please fill in Company and Role before saving so it can be identified in automation.");
      return;
    }
    setSavingLib(true);
    setSavedLibMsg("");
    setError("");
    try {
      const session = await supabase.auth.getSession();
      const token   = session.data.session?.access_token ?? "";

      const res  = await fetch("/api/resumes/save-tailored", {
        method: "POST",
        headers: {
          "Content-Type":  "application/json",
          "Authorization": `Bearer ${token}`,
        },
        body: JSON.stringify({
          tailored_text: tailored.tailored_text,
          company,
          role,
        }),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.error || "Save failed");
      setSavedLibMsg(`✅ Saved as "${data.title}" — available in automation resume picker`);
      loadData(); // refresh the saved resumes list
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Save failed. Please try again.");
    } finally {
      setSavingLib(false);
    }
  };

  // ── Save Cover Letter ──────────────────────────────────────────────────
  const handleSaveCoverLetter = async () => {
    if (!coverLetter || !user) return;
    try {
      await supabase.from("cover_letters").insert([{
        user_id:  user.id,
        type:     "cover_letter",
        content:  coverLetter.cover_letter ?? "",
        metadata: { company, role, email_subject: coverLetter.email_subject ?? "" },
      }]);
      alert("Cover letter saved ✅");
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Failed to save cover letter");
    }
  };

  const copy = (text: string | undefined | null, key: string) => {
    if (!text) return;
    navigator.clipboard.writeText(text);
    setCopied(key);
    setTimeout(() => setCopied(""), 2000);
  };

  const anyLoading    = analyzing || tailoring || generatingCover;
  const hasResults    = !!(analysis || tailored || coverLetter);
  const availableTabs = (["analyze", "tailor", "cover"] as ActiveTab[]).filter((t) =>
    t === "analyze" ? !!analysis : t === "tailor" ? !!tailored : !!coverLetter,
  );

  // ─────────────────────────────────────────────────────────────────────────
  return (
    <div className="max-w-6xl mx-auto px-6 py-10">
      {/* Header */}
      <div className="mb-8">
        <p className="font-mono text-xs text-slate-500 tracking-widest uppercase mb-1">AI Tools</p>
        <h1 className="font-display font-bold text-3xl text-white">Resume Studio</h1>
        <p className="text-slate-400 font-body text-sm mt-1">
          Upload your resume + paste a JD → analyze, tailor, refine, then download a clean PDF.
        </p>
      </div>

      {/* ── Input Grid ─────────────────────────────────────────────────── */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4 mb-4">

        {/* Resume */}
        <div className="card space-y-3">
          <div className="flex items-center justify-between flex-wrap gap-2">
            <p className="font-mono text-xs text-slate-400 uppercase tracking-wider">Your Resume</p>
            <div className="flex items-center gap-2 flex-wrap">
              {savedResumes.length > 0 && (
                <select
                  className="bg-slate-800 border border-slate-700 text-slate-300 text-xs rounded px-2 py-1"
                  defaultValue=""
                  onChange={(e) => {
                    const r = savedResumes.find((x) => x.id === e.target.value);
                    if (r?.parsed_text) setResumeText(r.parsed_text);
                  }}
                >
                  <option value="">Load saved…</option>
                  {savedResumes.map((r) => (
                    <option key={r.id} value={r.id}>{r.title}</option>
                  ))}
                </select>
              )}
              <input
                ref={fileInputRef}
                type="file"
                accept=".pdf,.docx,.doc,.txt"
                className="hidden"
                onChange={(e) => {
                  const f = e.target.files?.[0];
                  if (f) handlePdfUpload(f);
                  e.target.value = "";
                }}
              />
              <button
                onClick={() => fileInputRef.current?.click()}
                disabled={uploadingPdf}
                className="bg-slate-700 hover:bg-slate-600 disabled:opacity-50 text-slate-300 text-xs px-3 py-1 rounded border border-slate-600 transition-colors"
              >
                {uploadingPdf ? "⏳ Parsing…" : "📎 Upload PDF / DOCX"}
              </button>
            </div>
          </div>
          {originalFileUrl && (
            <p className="font-mono text-xs text-emerald-500">✓ Original file loaded — text extracted below</p>
          )}
          <textarea
            rows={14}
            placeholder="Paste your full resume text here, or upload a PDF above…"
            value={resumeText}
            onChange={(e) => setResumeText(e.target.value)}
            className="w-full bg-slate-900 border border-slate-700 text-slate-200 text-sm rounded-lg px-3 py-2.5 resize-y focus:outline-none focus:border-amber-400 placeholder-slate-600"
          />
          <p className="font-mono text-xs text-slate-600">
            {resumeText.split(/\s+/).filter(Boolean).length} words
          </p>
        </div>

        {/* Job Description */}
        <div className="card space-y-3">
          <p className="font-mono text-xs text-slate-400 uppercase tracking-wider">Job Description</p>
          <div className="grid grid-cols-2 gap-2">
            <input
              type="text" placeholder="Company (e.g. Amazon)"
              value={company} onChange={(e) => setCompany(e.target.value)}
              className="bg-slate-800 border border-slate-700 text-white text-sm rounded-lg px-3 py-2 focus:outline-none focus:border-blue-500"
            />
            <input
              type="text" placeholder="Role (e.g. SDE-2)"
              value={role} onChange={(e) => setRole(e.target.value)}
              className="bg-slate-800 border border-slate-700 text-white text-sm rounded-lg px-3 py-2 focus:outline-none focus:border-blue-500"
            />
          </div>
          <textarea
            rows={12}
            placeholder="Paste the full job description here…"
            value={jdText}
            onChange={(e) => setJdText(e.target.value)}
            className="w-full bg-slate-900 border border-slate-700 text-slate-200 text-sm rounded-lg px-3 py-2.5 resize-y focus:outline-none focus:border-amber-400 placeholder-slate-600"
          />
          <p className="font-mono text-xs text-slate-600">
            {jdText.split(/\s+/).filter(Boolean).length} words
          </p>
        </div>
      </div>

      {/* Error Banner */}
      {error && (
        <div className="mb-4 px-4 py-2.5 bg-red-500/10 border border-red-500/30 rounded-lg text-red-400 text-sm flex justify-between items-start gap-2">
          <span>{error}</span>
          <button onClick={() => setError("")} className="text-red-400 hover:text-red-300 shrink-0">✕</button>
        </div>
      )}

      {/* ── Action Buttons ──────────────────────────────────────────────── */}
      <div className="flex flex-wrap items-center justify-center gap-3 mb-8">
        <button
          onClick={handleAnalyze}
          disabled={anyLoading}
          className="bg-amber-400 hover:bg-amber-300 disabled:opacity-50 text-slate-950 font-bold px-6 py-3 rounded-lg transition-colors text-sm"
        >
          {analyzing ? "⚙️ Analyzing…" : "🔍 Analyze Resume"}
        </button>
        <button
          onClick={() => handleTailor()}
          disabled={anyLoading}
          className="bg-blue-500 hover:bg-blue-400 disabled:opacity-50 text-white font-bold px-6 py-3 rounded-lg transition-colors text-sm"
        >
          {tailoring && !refinePrompt ? "⚙️ Tailoring…" : "✨ Tailor Resume"}
        </button>
        <button
          onClick={handleCoverLetter}
          disabled={anyLoading}
          className="bg-slate-600 hover:bg-slate-500 disabled:opacity-50 text-white font-bold px-6 py-3 rounded-lg transition-colors text-sm"
        >
          {generatingCover ? "⚙️ Generating…" : "📝 Cover Letter"}
        </button>
        <div className="flex gap-2">
          <UsageBadge actionType="jd_analysis" label="Analyze"  />
          <UsageBadge actionType="ai_tailor"   label="Tailor"   />
          <UsageBadge actionType="cover_letter" label="Cover"   />
        </div>
      </div>

      {/* ── Results ─────────────────────────────────────────────────────── */}
      {hasResults && (
        <div className="card space-y-4">

          {/* Tab bar */}
          {availableTabs.length > 1 && (
            <div className="flex gap-2 border-b border-slate-700 pb-3">
              {availableTabs.map((tab) => (
                <button
                  key={tab}
                  onClick={() => setActiveTab(tab)}
                  className={`px-4 py-1.5 rounded-lg text-sm font-mono transition-colors ${
                    activeTab === tab
                      ? "bg-amber-400/20 text-amber-400 border border-amber-400/30"
                      : "text-slate-400 hover:text-white"
                  }`}
                >
                  {tab === "analyze" ? "📊 Analysis" : tab === "tailor" ? "✨ Tailored" : "📝 Cover Letter"}
                </button>
              ))}
            </div>
          )}

          {/* ── ANALYSIS TAB ── */}
          {activeTab === "analyze" && analysis && (
            <div className="space-y-6">
              {/* Score + Fit */}
              <div className="flex flex-wrap items-center gap-8">
                <ScoreRing score={analysis.score} label="Match Score" />
                <div className="flex-1 min-w-[180px]">
                  <p className="font-mono text-xs text-slate-500 uppercase mb-1">Role Fit</p>
                  <span className={`px-3 py-1 rounded-full text-sm font-mono ${
                    (analysis.score ?? 0) >= 75
                      ? "bg-emerald-500/15 text-emerald-400"
                      : (analysis.score ?? 0) >= 50
                        ? "bg-amber-500/15 text-amber-400"
                        : "bg-red-500/15 text-red-400"
                  }`}>
                    {(analysis.score ?? 0) >= 75 ? "Strong Match ✓" : (analysis.score ?? 0) >= 50 ? "Partial Match" : "Needs Work"}
                  </span>
                </div>
              </div>

              {/* Skills grid */}
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                {safeArr(analysis.missing_skills).length > 0 && (
                  <div>
                    <p className="font-mono text-xs text-red-400 uppercase mb-2">
                      ❌ Missing Skills ({safeArr(analysis.missing_skills).length})
                    </p>
                    <div className="flex flex-wrap gap-1.5">
                      {safeArr(analysis.missing_skills).map((s) => (
                        <span key={s} className="px-2 py-0.5 rounded-full bg-red-500/10 text-red-400 text-xs font-mono border border-red-500/20">{s}</span>
                      ))}
                    </div>
                  </div>
                )}
                {safeArr(analysis.recommended_skills).length > 0 && (
                  <div>
                    <p className="font-mono text-xs text-blue-400 uppercase mb-2">
                      💡 Recommended ({safeArr(analysis.recommended_skills).length})
                    </p>
                    <div className="flex flex-wrap gap-1.5">
                      {safeArr(analysis.recommended_skills).map((s) => (
                        <span key={s} className="px-2 py-0.5 rounded-full bg-blue-500/10 text-blue-400 text-xs font-mono border border-blue-500/20">{s}</span>
                      ))}
                    </div>
                  </div>
                )}
              </div>

              {/* Keywords */}
              {safeArr(analysis.keywords_to_add).length > 0 && (
                <div>
                  <p className="font-mono text-xs text-amber-400 uppercase mb-2">🔑 ATS Keywords to Add</p>
                  <div className="flex flex-wrap gap-1.5">
                    {safeArr(analysis.keywords_to_add).map((k) => (
                      <span key={k} className="px-2 py-0.5 rounded-full bg-amber-500/10 text-amber-400 text-xs font-mono border border-amber-500/20">{k}</span>
                    ))}
                  </div>
                </div>
              )}

              {/* Section improvements */}
              {safeArr(analysis.improvements).length > 0 && (
                <div>
                  <p className="font-mono text-xs text-slate-400 uppercase mb-3">🔧 Section-by-Section Improvements</p>
                  <div className="space-y-3">
                    {safeArr(analysis.improvements).map((imp, i) => imp && (
                      <div key={i} className="bg-slate-900 border border-slate-700 rounded-lg p-4 space-y-2">
                        <div className="flex items-center gap-2 flex-wrap">
                          <span className="px-2 py-0.5 rounded bg-slate-700 text-slate-300 text-xs font-mono uppercase">{imp.section ?? "general"}</span>
                          <span className="text-red-400 text-xs">{imp.issue ?? ""}</span>
                        </div>
                        <p className="text-slate-300 text-sm"><span className="text-amber-400">→ </span>{imp.suggestion ?? ""}</p>
                        {imp.example && (
                          <div className="bg-slate-800 rounded px-3 py-2 text-xs text-emerald-400 font-mono leading-relaxed">e.g. {imp.example}</div>
                        )}
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {/* Certifications + Positioning */}
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                {safeArr(analysis.certifications).length > 0 && (
                  <div>
                    <p className="font-mono text-xs text-emerald-400 uppercase mb-2">🎓 Certifications to Consider</p>
                    <ul className="space-y-1">
                      {safeArr(analysis.certifications).map((c, i) => (
                        <li key={i} className="text-slate-300 text-sm flex gap-2"><span className="text-emerald-400 shrink-0">•</span>{c}</li>
                      ))}
                    </ul>
                  </div>
                )}
                {safeArr(analysis.role_changes).length > 0 && (
                  <div>
                    <p className="font-mono text-xs text-purple-400 uppercase mb-2">🎯 Positioning Suggestions</p>
                    <ul className="space-y-1">
                      {safeArr(analysis.role_changes).map((r, i) => (
                        <li key={i} className="text-slate-300 text-sm flex gap-2"><span className="text-purple-400 shrink-0">•</span>{r}</li>
                      ))}
                    </ul>
                  </div>
                )}
              </div>

              {/* CTA */}
              <div className="pt-2 border-t border-slate-700 flex justify-end">
                <button
                  onClick={() => handleTailor()}
                  disabled={anyLoading}
                  className="bg-blue-500 hover:bg-blue-400 disabled:opacity-50 text-white font-bold px-6 py-2 rounded-lg text-sm transition-colors"
                >
                  {tailoring ? "⚙️ Tailoring…" : "✨ Tailor Resume with These Fixes →"}
                </button>
              </div>
            </div>
          )}

          {/* ── TAILORED RESUME TAB ── */}
          {activeTab === "tailor" && tailored && (
            <div className="space-y-5">
              {/* ATS Score */}
              {tailored.ats_score != null && (
                <div className="flex items-center gap-4">
                  <ScoreRing score={tailored.ats_score} label="ATS Score" />
                  <p className="text-slate-400 text-sm">ATS optimisation score after tailoring</p>
                </div>
              )}

              {/* ── Resume Preview Panel (looks like paper) ── */}
              <div>
                <div className="flex items-center justify-between mb-2">
                  <p className="font-mono text-xs text-slate-400 uppercase">Resume Preview</p>
                  <button
                    onClick={() => copy(tailored.tailored_text, "tailored")}
                    className="text-xs font-mono text-slate-400 hover:text-white border border-slate-700 px-3 py-1 rounded transition-colors"
                  >
                    {copied === "tailored" ? "✅ Copied" : "📋 Copy Text"}
                  </button>
                </div>

                {/* Paper-like preview */}
                <div className="bg-white text-gray-900 rounded-lg shadow-lg p-8 font-sans text-sm leading-relaxed overflow-auto max-h-[600px] border border-slate-300">
                  <pre className="whitespace-pre-wrap break-words text-[11pt] leading-[1.5] font-[Calibri,Arial,sans-serif] text-gray-900">
                    {tailored.tailored_text ?? ""}
                  </pre>
                </div>

                <p className="font-mono text-xs text-slate-500 mt-1.5">
                  ↑ Review your tailored resume — use Refine below to make changes, then Download PDF when ready.
                </p>
              </div>

              {/* Summary highlight */}
              {tailored.tailored_summary && (
                <div className="bg-slate-900 border border-slate-700 rounded-lg p-4">
                  <p className="text-sm font-mono text-amber-400 mb-2">AI-GENERATED SUMMARY</p>
                  <p className="text-slate-300 text-sm leading-relaxed">{tailored.tailored_summary}</p>
                </div>
              )}

              {/* Manual improvements */}
              {safeArr(tailored.improvements).length > 0 && (
                <div>
                  <p className="font-mono text-xs text-blue-400 uppercase mb-2">🔧 Additional improvements to apply manually</p>
                  <ul className="space-y-1">
                    {safeArr(tailored.improvements).map((imp, i) => (
                      <li key={i} className="text-slate-400 text-sm flex gap-2">
                        <span className="text-blue-400 shrink-0">→</span>{imp}
                      </li>
                    ))}
                  </ul>
                </div>
              )}

              {/* ── Refine Section ── */}
              <div className="bg-slate-900 border border-slate-600 rounded-lg p-4 space-y-3">
                <p className="font-mono text-xs text-purple-400 uppercase">🔄 Refine Further</p>
                <p className="text-slate-500 text-xs">Describe what to change — AI will apply your feedback to the current draft.</p>
                <textarea
                  rows={3}
                  placeholder='e.g. "Make it more senior", "Expand AWS experience section", "Shorter summary under 3 lines"'
                  value={refinePrompt}
                  onChange={(e) => setRefinePrompt(e.target.value)}
                  className="w-full bg-slate-800 border border-slate-700 text-slate-200 text-sm rounded-lg px-3 py-2 resize-y focus:outline-none focus:border-purple-400 placeholder-slate-600"
                />
                <button
                  onClick={() => handleTailor(refinePrompt)}
                  disabled={anyLoading || !refinePrompt.trim()}
                  className="bg-purple-600 hover:bg-purple-500 disabled:opacity-50 text-white font-bold px-5 py-2 rounded-lg text-sm transition-colors"
                >
                  {tailoring ? "⚙️ Refining…" : "🔄 Apply Refinement"}
                </button>
              </div>

              {/* ── Download + Save to Library ── */}
              <div className="bg-slate-800 border border-slate-600 rounded-lg p-4 space-y-3">
                <p className="font-mono text-xs text-slate-300 uppercase">📥 Download &amp; Save</p>

                <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                  {/* Download PDF */}
                  <button
                    onClick={handleDownloadPDF}
                    className="bg-amber-400 hover:bg-amber-300 text-slate-950 font-bold px-5 py-2.5 rounded-lg text-sm transition-colors flex items-center justify-center gap-2"
                  >
                    🖨 Download PDF
                  </button>

                  {/* Save to Resumes Library */}
                  <button
                    onClick={handleSaveToLibrary}
                    disabled={savingLib}
                    className="bg-emerald-600 hover:bg-emerald-500 disabled:opacity-50 text-white font-bold px-5 py-2.5 rounded-lg text-sm transition-colors flex items-center justify-center gap-2"
                  >
                    {savingLib ? "⏳ Saving…" : "💾 Save to My Resumes"}
                  </button>
                </div>

                <p className="text-slate-500 text-xs">
                  <strong className="text-slate-400">Download PDF</strong> opens a formatted preview — use your browser's{" "}
                  <em>Save as PDF</em> option. Filename: <span className="font-mono text-amber-400">{
                    [company, role].filter(Boolean).join("_").replace(/\s+/g, "_") || "Resume"
                  }_Resume.pdf</span>
                  <br/>
                  <strong className="text-slate-400">Save to My Resumes</strong> stores this tailored version in your library so it can be selected during auto-apply automation.
                </p>

                {savedLibMsg && (
                  <p className="text-emerald-400 text-sm font-mono">{savedLibMsg}</p>
                )}
              </div>
            </div>
          )}

          {/* ── COVER LETTER TAB ── */}
          {activeTab === "cover" && coverLetter && (
            <div className="space-y-4">
              <div className="bg-slate-900 border border-slate-700 rounded-lg p-4">
                <div className="flex items-center justify-between mb-3">
                  <p className="font-mono text-xs text-amber-400 uppercase">Cover Letter</p>
                  <button
                    onClick={() => copy(coverLetter.cover_letter, "cover")}
                    className="text-xs font-mono text-slate-400 hover:text-white border border-slate-700 px-3 py-1 rounded"
                  >
                    {copied === "cover" ? "✅ Copied" : "📋 Copy"}
                  </button>
                </div>
                <pre className="text-slate-300 text-sm leading-relaxed whitespace-pre-wrap font-body">
                  {coverLetter.cover_letter ?? ""}
                </pre>
              </div>

              <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                <div className="bg-slate-900 border border-slate-700 rounded-lg p-3">
                  <div className="flex items-center justify-between mb-2">
                    <p className="font-mono text-xs text-blue-400 uppercase">LinkedIn Intro</p>
                    <button onClick={() => copy(coverLetter.linkedin_intro, "li")} className="text-xs text-slate-500 hover:text-white">
                      {copied === "li" ? "✅" : "📋"}
                    </button>
                  </div>
                  <p className="text-slate-300 text-sm">{coverLetter.linkedin_intro ?? ""}</p>
                </div>
                <div className="bg-slate-900 border border-slate-700 rounded-lg p-3">
                  <div className="flex items-center justify-between mb-2">
                    <p className="font-mono text-xs text-emerald-400 uppercase">Short Intro Message</p>
                    <button onClick={() => copy(coverLetter.intro_message, "intro")} className="text-xs text-slate-500 hover:text-white">
                      {copied === "intro" ? "✅" : "📋"}
                    </button>
                  </div>
                  <p className="text-slate-300 text-sm">{coverLetter.intro_message ?? ""}</p>
                </div>
              </div>

              <div className="bg-slate-900 border border-slate-700 rounded-lg p-3">
                <p className="font-mono text-xs text-slate-500 uppercase mb-1">Email Subject</p>
                <p className="text-slate-200 text-sm font-mono">{coverLetter.email_subject ?? ""}</p>
              </div>

              <button
                onClick={handleSaveCoverLetter}
                className="bg-blue-500 hover:bg-blue-400 text-white font-bold px-4 py-2 rounded-lg text-sm"
              >
                💾 Save Cover Letter
              </button>
            </div>
          )}
        </div>
      )}

      {/* ── Saved Versions ──────────────────────────────────────────────── */}
      {savedVersions.length > 0 && (
        <div className="mt-8">
          <h2 className="font-display font-semibold text-white text-lg mb-3">📁 Saved Versions</h2>
          <div className="space-y-2">
            {savedVersions.map((v) => (
              <div key={v.id} className="card py-3 flex items-center justify-between">
                <div>
                  <p className="font-mono text-sm text-white">{v.version_name}</p>
                  <p className="font-body text-xs text-slate-500 mt-0.5">
                    {new Date(v.created_at).toLocaleDateString()}
                    {v.ats_score != null && <span className="ml-3 text-emerald-400">ATS {v.ats_score}%</span>}
                  </p>
                </div>
                <button
                  onClick={() => {
                    setResumeText(v.tailored_text ?? "");
                    window.scrollTo({ top: 0, behavior: "smooth" });
                  }}
                  className="text-xs font-mono text-slate-400 hover:text-white border border-slate-700 px-3 py-1 rounded"
                >
                  Load
                </button>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* ── My Resumes Library (for Automation) ─────────────────────────── */}
      {savedResumes.filter((r) => {
        try {
          const c = r as ResumeRow & { content?: { tailored?: boolean } };
          return c.content?.tailored;
        } catch { return false; }
      }).length > 0 && (
        <div className="mt-6">
          <h2 className="font-display font-semibold text-white text-lg mb-3">🤖 Tailored Resumes (for Automation)</h2>
          <p className="text-slate-500 text-xs mb-3 font-body">These resumes are available in the automation agent&apos;s resume picker.</p>
          <div className="space-y-2">
            {savedResumes
              .filter((r) => {
                const c = r as ResumeRow & { content?: { tailored?: boolean } };
                return c.content?.tailored;
              })
              .map((r) => (
                <div key={r.id} className="card py-3 flex items-center justify-between">
                  <p className="font-mono text-sm text-emerald-400">{r.title}</p>
                  <button
                    onClick={() => {
                      if (r.parsed_text) setResumeText(r.parsed_text);
                      window.scrollTo({ top: 0, behavior: "smooth" });
                    }}
                    className="text-xs font-mono text-slate-400 hover:text-white border border-slate-700 px-3 py-1 rounded"
                  >
                    Edit
                  </button>
                </div>
              ))}
          </div>
        </div>
      )}
    </div>
  );
}
