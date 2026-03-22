"use client";

import { useEffect, useState, useCallback } from "react";
import { useAuth } from "@/context/AuthContext";
import { supabase } from "@/lib/supabase";
import { UsageBadge } from "@/components/SubscriptionGuard";
import type { MatchScoreResult, TailoredResumeResult, CoverLetterResult } from "@/lib/ai";

// ── Types ─────────────────────────────────────────────────────────────────
type ResumeRow = { id: string; title: string; parsed_text?: string | null };
type SavedVersion = {
  id: string;
  version_name: string;
  ats_score: number | null;
  created_at: string;
  tailored_text: string;
};

type ResultBundle = {
  score:       MatchScoreResult;
  tailored:    TailoredResumeResult;
  coverLetter: CoverLetterResult;
};

// ── Score ring component ──────────────────────────────────────────────────
function ScoreRing({ score }: { score: number }) {
  const r    = 40;
  const circ = 2 * Math.PI * r;
  const dash = (score / 100) * circ;
  const color = score >= 75 ? "#34d399" : score >= 50 ? "#fbbf24" : "#f87171";
  return (
    <svg width="100" height="100" className="rotate-[-90deg]">
      <circle cx="50" cy="50" r={r} fill="none" stroke="#1e293b" strokeWidth="10" />
      <circle
        cx="50" cy="50" r={r} fill="none" stroke={color} strokeWidth="10"
        strokeDasharray={`${dash} ${circ}`} strokeLinecap="round"
        style={{ transition: "stroke-dasharray 0.6s ease" }}
      />
      <text
        x="50" y="56" textAnchor="middle" dominantBaseline="middle"
        fill={color} fontSize="18" fontWeight="700"
        style={{ transform: "rotate(90deg) translate(0,-100px)" }}
      >
        {score}%
      </text>
    </svg>
  );
}

// ── Main Page ─────────────────────────────────────────────────────────────
export default function ResumeStudioPage() {
  const { user } = useAuth();

  const [resumeText, setResumeText] = useState("");
  const [jdText,     setJdText    ] = useState("");
  const [company,    setCompany   ] = useState("");
  const [role,       setRole      ] = useState("");

  const [loading,  setLoading ] = useState(false);
  const [results,  setResults ] = useState<ResultBundle | null>(null);
  const [activeTab, setActiveTab] = useState<"score" | "tailored" | "cover">("score");

  const [savedResumes,   setSavedResumes  ] = useState<ResumeRow[]>([]);
  const [savedVersions,  setSavedVersions ] = useState<SavedVersion[]>([]);
  const [versionName,    setVersionName   ] = useState("");
  const [saving,         setSaving        ] = useState(false);
  const [copied,         setCopied        ] = useState("");
  const [error,          setError         ] = useState("");

  // ── Load saved resumes & versions ───────────────────────────────────────
  const loadData = useCallback(async () => {
    if (!user) return;
    const [r1, r2] = await Promise.all([
      supabase.from("resumes").select("id, title, parsed_text").eq("user_id", user.id).order("created_at", { ascending: false }),
      supabase.from("resume_versions").select("id, version_name, ats_score, created_at, tailored_text").eq("user_id", user.id).order("created_at", { ascending: false }).limit(20),
    ]);
    if (r1.data) setSavedResumes(r1.data as ResumeRow[]);
    if (r2.data) setSavedVersions(r2.data as SavedVersion[]);
  }, [user]);

  useEffect(() => { loadData(); }, [loadData]);

  // ── Analyze ──────────────────────────────────────────────────────────────
  const handleAnalyze = async () => {
    if (!resumeText.trim() || !jdText.trim()) {
      setError("Please enter both your resume text and the job description.");
      return;
    }
    setError("");
    setLoading(true);
    setResults(null);
    try {
      const [scoreRes, tailorRes, coverRes] = await Promise.all([
        fetch("/api/ai/match-score",   { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ resume_text: resumeText, jd_text: jdText }) }),
        fetch("/api/ai/tailor-resume", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ resume_text: resumeText, jd_text: jdText }) }),
        fetch("/api/ai/cover-letter",  { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ resume_text: resumeText, jd_text: jdText, company, role }) }),
      ]);
      const [score, tailored, coverLetter] = await Promise.all([
        scoreRes.json(), tailorRes.json(), coverRes.json(),
      ]);
      setResults({ score, tailored, coverLetter });
      setActiveTab("score");
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Analysis failed");
    } finally {
      setLoading(false);
    }
  };

  // ── Save version ─────────────────────────────────────────────────────────
  const handleSaveVersion = async () => {
    if (!results || !user || !versionName.trim()) return;
    setSaving(true);
    await supabase.from("resume_versions").insert([{
      user_id:          user.id,
      version_name:     versionName.trim(),
      original_text:    resumeText,
      tailored_text:    results.tailored.tailored_text,
      tailored_content: results.tailored,
      ats_score:        results.tailored.ats_score,
      missing_skills:   results.score.missing_skills,
    }]);
    setVersionName("");
    setSaving(false);
    loadData();
  };

  // ── Save cover letter ────────────────────────────────────────────────────
  const handleSaveCoverLetter = async () => {
    if (!results || !user) return;
    await supabase.from("cover_letters").insert([{
      user_id:  user.id,
      type:     "cover_letter",
      content:  results.coverLetter.cover_letter,
      metadata: { company, role, email_subject: results.coverLetter.email_subject },
    }]);
    alert("Cover letter saved ✅");
  };

  const copy = (text: string, key: string) => {
    navigator.clipboard.writeText(text);
    setCopied(key);
    setTimeout(() => setCopied(""), 2000);
  };

  // ─────────────────────────────────────────────────────────────────────────
  return (
    <div className="max-w-6xl mx-auto px-6 py-10">
      {/* Header */}
      <div className="mb-8">
        <p className="font-mono text-xs text-slate-500 tracking-widest uppercase mb-1">AI Tools</p>
        <h1 className="font-display font-bold text-3xl text-white">Resume Studio</h1>
        <p className="text-slate-400 font-body text-sm mt-1">
          Paste your resume + a job description → get match score, tailored bullets, and a cover letter.
        </p>
      </div>

      {/* Input grid */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4 mb-4">
        {/* Resume */}
        <div className="card space-y-3">
          <div className="flex items-center justify-between">
            <p className="font-mono text-xs text-slate-400 uppercase tracking-wider">Your Resume</p>
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
          </div>
          <textarea
            rows={14}
            placeholder="Paste your full resume text here…"
            value={resumeText}
            onChange={(e) => setResumeText(e.target.value)}
            className="w-full bg-slate-900 border border-slate-700 text-slate-200 text-sm rounded-lg px-3 py-2.5 resize-y focus:outline-none focus:border-amber-400 placeholder-slate-600"
          />
          <p className="font-mono text-xs text-slate-600">
            {resumeText.split(/\s+/).filter(Boolean).length} words
          </p>
        </div>

        {/* JD */}
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

      {error && (
        <div className="mb-4 px-4 py-2.5 bg-red-500/10 border border-red-500/30 rounded-lg text-red-400 text-sm">{error}</div>
      )}

      {/* Analyze button */}
      <div className="flex items-center justify-center gap-4 mb-8">
        <button
          onClick={handleAnalyze}
          disabled={loading}
          className="bg-amber-400 hover:bg-amber-300 disabled:opacity-50 text-slate-950 font-bold px-8 py-3 rounded-lg transition-colors text-sm"
        >
          {loading ? "⚙️  Analyzing…" : "🧠 Analyze & Tailor Resume"}
        </button>
        <div className="flex gap-2">
          <UsageBadge actionType="ai_tailor" label="Tailor" />
          <UsageBadge actionType="cover_letter" label="Cover" />
          <UsageBadge actionType="jd_analysis" label="JD" />
        </div>
      </div>

      {/* Results */}
      {results && (
        <div className="card space-y-4">
          {/* Tabs */}
          <div className="flex gap-2 border-b border-slate-700 pb-3">
            {(["score", "tailored", "cover"] as const).map((tab) => (
              <button
                key={tab}
                onClick={() => setActiveTab(tab)}
                className={`px-4 py-1.5 rounded-lg text-sm font-mono transition-colors ${
                  activeTab === tab
                    ? "bg-amber-400/20 text-amber-400 border border-amber-400/30"
                    : "text-slate-400 hover:text-white"
                }`}
              >
                {tab === "score" ? "📊 Match Score" : tab === "tailored" ? "✨ Tailored Resume" : "📝 Cover Letter"}
              </button>
            ))}
          </div>

          {/* ── Match Score Tab ── */}
          {activeTab === "score" && (
            <div className="space-y-5">
              <div className="flex flex-wrap items-center gap-8">
                <div className="flex flex-col items-center gap-1">
                  <ScoreRing score={results.score.score} />
                  <p className="font-mono text-xs text-slate-500">JD Match Score</p>
                </div>
                <div className="flex flex-col items-center gap-1">
                  <ScoreRing score={results.tailored.ats_score} />
                  <p className="font-mono text-xs text-slate-500">ATS Score</p>
                </div>
                <div className="flex-1 min-w-[200px]">
                  <p className="font-mono text-xs text-slate-500 uppercase mb-2">Seniority Detected</p>
                  <span className="px-3 py-1 rounded-full bg-blue-500/15 text-blue-400 text-sm font-mono capitalize">
                    {results.score.matching_skills.length > 0 ? "Aligned ✓" : "Check alignment"}
                  </span>
                </div>
              </div>

              <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                <div>
                  <p className="font-mono text-xs text-emerald-400 uppercase mb-2">✅ Matching Skills ({results.score.matching_skills.length})</p>
                  <div className="flex flex-wrap gap-1.5">
                    {results.score.matching_skills.length > 0
                      ? results.score.matching_skills.map((s) => (
                          <span key={s} className="px-2 py-0.5 rounded-full bg-emerald-500/10 text-emerald-400 text-xs font-mono border border-emerald-500/20">{s}</span>
                        ))
                      : <p className="text-slate-500 text-sm">No exact keyword matches found</p>
                    }
                  </div>
                </div>
                <div>
                  <p className="font-mono text-xs text-red-400 uppercase mb-2">❌ Missing Skills ({results.score.missing_skills.length})</p>
                  <div className="flex flex-wrap gap-1.5">
                    {results.score.missing_skills.length > 0
                      ? results.score.missing_skills.map((s) => (
                          <span key={s} className="px-2 py-0.5 rounded-full bg-red-500/10 text-red-400 text-xs font-mono border border-red-500/20">{s}</span>
                        ))
                      : <p className="text-slate-500 text-sm">No critical gaps found ✓</p>
                    }
                  </div>
                </div>
              </div>

              {results.score.suggestions.length > 0 && (
                <div>
                  <p className="font-mono text-xs text-amber-400 uppercase mb-2">💡 Suggestions</p>
                  <ul className="space-y-1">
                    {results.score.suggestions.map((s, i) => (
                      <li key={i} className="text-slate-300 text-sm flex gap-2"><span className="text-amber-400 shrink-0">→</span>{s}</li>
                    ))}
                  </ul>
                </div>
              )}
            </div>
          )}

          {/* ── Tailored Resume Tab ── */}
          {activeTab === "tailored" && (
            <div className="space-y-4">
              <div className="flex items-center justify-between">
                <p className="font-mono text-xs text-slate-400 uppercase">Tailored Content</p>
                <button
                  onClick={() => copy(results.tailored.tailored_text, "tailored")}
                  className="text-xs font-mono text-slate-400 hover:text-white border border-slate-700 px-3 py-1 rounded"
                >
                  {copied === "tailored" ? "✅ Copied" : "📋 Copy"}
                </button>
              </div>

              <div className="bg-slate-900 border border-slate-700 rounded-lg p-4">
                <p className="text-sm font-mono text-amber-400 mb-2">SUMMARY</p>
                <p className="text-slate-300 text-sm leading-relaxed">{results.tailored.tailored_summary}</p>
              </div>

              <div className="bg-slate-900 border border-slate-700 rounded-lg p-4">
                <p className="text-sm font-mono text-amber-400 mb-2">KEY BULLETS</p>
                <ul className="space-y-2">
                  {results.tailored.tailored_bullets.map((b, i) => (
                    <li key={i} className="text-slate-300 text-sm flex gap-2">
                      <span className="text-amber-400 shrink-0">•</span>{b}
                    </li>
                  ))}
                </ul>
              </div>

              {results.tailored.improvements.length > 0 && (
                <div>
                  <p className="font-mono text-xs text-blue-400 uppercase mb-2">🔧 Improvements to apply manually</p>
                  <ul className="space-y-1">
                    {results.tailored.improvements.map((imp, i) => (
                      <li key={i} className="text-slate-400 text-sm flex gap-2"><span className="text-blue-400 shrink-0">→</span>{imp}</li>
                    ))}
                  </ul>
                </div>
              )}

              {/* Save version */}
              <div className="flex gap-2 pt-2 border-t border-slate-700">
                <input
                  type="text"
                  placeholder="Version name (e.g. Amazon_SDE_v1)"
                  value={versionName}
                  onChange={(e) => setVersionName(e.target.value)}
                  className="flex-1 bg-slate-800 border border-slate-700 text-white text-sm rounded-lg px-3 py-2 focus:outline-none focus:border-amber-400"
                />
                <button
                  onClick={handleSaveVersion}
                  disabled={saving || !versionName.trim()}
                  className="bg-emerald-500 hover:bg-emerald-400 disabled:opacity-50 text-white font-bold px-4 py-2 rounded-lg text-sm"
                >
                  {saving ? "Saving…" : "💾 Save Version"}
                </button>
              </div>
            </div>
          )}

          {/* ── Cover Letter Tab ── */}
          {activeTab === "cover" && (
            <div className="space-y-4">
              <div className="bg-slate-900 border border-slate-700 rounded-lg p-4">
                <div className="flex items-center justify-between mb-3">
                  <p className="font-mono text-xs text-amber-400 uppercase">Cover Letter</p>
                  <button onClick={() => copy(results.coverLetter.cover_letter, "cover")} className="text-xs font-mono text-slate-400 hover:text-white border border-slate-700 px-3 py-1 rounded">
                    {copied === "cover" ? "✅ Copied" : "📋 Copy"}
                  </button>
                </div>
                <pre className="text-slate-300 text-sm leading-relaxed whitespace-pre-wrap font-body">{results.coverLetter.cover_letter}</pre>
              </div>

              <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                <div className="bg-slate-900 border border-slate-700 rounded-lg p-3">
                  <div className="flex items-center justify-between mb-2">
                    <p className="font-mono text-xs text-blue-400 uppercase">LinkedIn Intro</p>
                    <button onClick={() => copy(results.coverLetter.linkedin_intro, "li")} className="text-xs text-slate-500 hover:text-white">
                      {copied === "li" ? "✅" : "📋"}
                    </button>
                  </div>
                  <p className="text-slate-300 text-sm">{results.coverLetter.linkedin_intro}</p>
                </div>
                <div className="bg-slate-900 border border-slate-700 rounded-lg p-3">
                  <div className="flex items-center justify-between mb-2">
                    <p className="font-mono text-xs text-emerald-400 uppercase">Short Intro Message</p>
                    <button onClick={() => copy(results.coverLetter.intro_message, "intro")} className="text-xs text-slate-500 hover:text-white">
                      {copied === "intro" ? "✅" : "📋"}
                    </button>
                  </div>
                  <p className="text-slate-300 text-sm">{results.coverLetter.intro_message}</p>
                </div>
              </div>

              <div className="bg-slate-900 border border-slate-700 rounded-lg p-3">
                <p className="font-mono text-xs text-slate-500 uppercase mb-1">Email Subject</p>
                <p className="text-slate-200 text-sm font-mono">{results.coverLetter.email_subject}</p>
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

      {/* Saved Versions */}
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
                  onClick={() => { setResumeText(v.tailored_text); window.scrollTo({ top: 0, behavior: "smooth" }); }}
                  className="text-xs font-mono text-slate-400 hover:text-white border border-slate-700 px-3 py-1 rounded"
                >
                  Load
                </button>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
