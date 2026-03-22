"use client";

import { useEffect, useState, useCallback } from "react";
import { useAuth } from "@/context/AuthContext";
import { supabase } from "@/lib/supabase";
import Link from "next/link";

// ── Types ─────────────────────────────────────────────────────────────────
type JobRow = {
  id:         string;
  company:    string;
  role:       string;
  url:        string | null;
  status:     string;
  metadata:   Record<string, unknown>;
  created_at: string;
};

type AnalysisResult = {
  required_skills:  string[];
  nice_to_have:     string[];
  keywords:         string[];
  responsibilities: string[];
  seniority:        string;
};

type WatchlistRow = { id: string; company: string; keywords: string[]; platform: string };

// ─────────────────────────────────────────────────────────────────────────
export default function JobSearchPage() {
  const { user } = useAuth();

  // Search inputs
  const [keywords, setKeywords] = useState("");
  const [location, setLocation] = useState("");

  // JD analyzer
  const [jdText,       setJdText     ] = useState("");
  const [jdCompany,    setJdCompany  ] = useState("");
  const [jdRole,       setJdRole     ] = useState("");
  const [jdPlatform,   setJdPlatform ] = useState("linkedin");
  const [jdAnalysis,   setJdAnalysis ] = useState<AnalysisResult | null>(null);
  const [analyzing,    setAnalyzing  ] = useState(false);
  const [savingJob,    setSavingJob  ] = useState(false);
  const [savedJobId,   setSavedJobId ] = useState<string | null>(null);

  // Watchlist
  const [watchlist,    setWatchlist  ] = useState<WatchlistRow[]>([]);
  const [watchCompany, setWatchCompany] = useState("");
  const [watchKw,      setWatchKw    ] = useState("");
  const [addingWatch,  setAddingWatch] = useState(false);

  // Saved jobs
  const [savedJobs, setSavedJobs] = useState<JobRow[]>([]);
  const [jobsLoading, setJobsLoading] = useState(true);

  const load = useCallback(async () => {
    if (!user) return;
    const [wRes, jRes] = await Promise.all([
      supabase.from("company_watchlist").select("id, company, keywords, platform").eq("user_id", user.id).eq("active", true).order("created_at", { ascending: false }),
      supabase.from("jobs").select("*").eq("user_id", user.id).order("created_at", { ascending: false }).limit(30),
    ]);
    if (wRes.data) setWatchlist(wRes.data as WatchlistRow[]);
    if (jRes.data) setSavedJobs(jRes.data as JobRow[]);
    setJobsLoading(false);
  }, [user]);

  useEffect(() => { load(); }, [load]);

  // ── Open platform search in new tab ──────────────────────────────────────
  const openSearch = (platform: "linkedin" | "naukri") => {
    if (!keywords.trim()) { alert("Enter job keywords first."); return; }
    const kw  = encodeURIComponent(keywords.trim());
    const loc = encodeURIComponent(location.trim());
    const urls = {
      linkedin: `https://www.linkedin.com/jobs/search/?keywords=${kw}&location=${loc}&f_AL=true&sortBy=DD`,
      naukri:   `https://www.naukri.com/${keywords.trim().toLowerCase().replace(/\s+/g, "-")}-jobs${loc ? `?l=${loc}` : ""}`,
    };
    window.open(urls[platform], "_blank", "noopener,noreferrer");
  };

  // ── Analyze JD ────────────────────────────────────────────────────────────
  const handleAnalyzeJD = async () => {
    if (!jdText.trim()) { alert("Paste a job description first."); return; }
    setAnalyzing(true);
    setJdAnalysis(null);
    setSavedJobId(null);
    try {
      const res = await fetch("/api/ai/analyze-jd", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ jd_text: jdText }),
      });
      const data = await res.json();
      setJdAnalysis(data);
    } finally {
      setAnalyzing(false);
    }
  };

  // ── Save to Job Tracker ───────────────────────────────────────────────────
  const handleSaveJob = async () => {
    if (!user || !jdCompany.trim() || !jdRole.trim()) {
      alert("Enter Company and Role name before saving.");
      return;
    }
    setSavingJob(true);
    const { data, error } = await supabase.from("jobs").upsert([{
      user_id:  user.id,
      company:  jdCompany.trim(),
      role:     jdRole.trim(),
      status:   "SAVED",
      metadata: {
        platform:  jdPlatform,
        keywords:  jdAnalysis?.keywords ?? [],
        seniority: jdAnalysis?.seniority ?? "",
        jd_text:   jdText.slice(0, 3000),
      },
    }], { onConflict: "user_id,company,role" as any }).select("id").single();
    if (error) { alert("Error saving job: " + error.message); }
    else {
      setSavedJobId(data.id);
      load();
    }
    setSavingJob(false);
  };

  // ── Add to watchlist ──────────────────────────────────────────────────────
  const handleAddWatch = async () => {
    if (!user || !watchCompany.trim()) return;
    setAddingWatch(true);
    await supabase.from("company_watchlist").upsert([{
      user_id:  user.id,
      company:  watchCompany.trim(),
      keywords: watchKw.split(",").map((k) => k.trim()).filter(Boolean),
      platform: "both",
      active:   true,
    }], { onConflict: "user_id,company" as any });
    setWatchCompany("");
    setWatchKw("");
    setAddingWatch(false);
    load();
  };

  const removeWatch = async (id: string) => {
    await supabase.from("company_watchlist").update({ active: false }).eq("id", id);
    setWatchlist((prev) => prev.filter((w) => w.id !== id));
  };

  const STATUS_COLOR: Record<string, string> = {
    SAVED:     "bg-slate-500/15 text-slate-400",
    APPLYING:  "bg-blue-500/15 text-blue-400",
    CLOSED:    "bg-red-500/15 text-red-400",
  };

  // ─────────────────────────────────────────────────────────────────────────
  return (
    <div className="max-w-6xl mx-auto px-6 py-10 space-y-10">
      {/* Header */}
      <div>
        <p className="font-mono text-xs text-slate-500 tracking-widest uppercase mb-1">Discover</p>
        <h1 className="font-display font-bold text-3xl text-white">Job Search</h1>
        <p className="text-slate-400 font-body text-sm mt-1">
          Find jobs, analyse JDs, track companies, and kick off smart applications.
        </p>
      </div>

      {/* ── 1. Search & Launch ──────────────────────────────────────────────── */}
      <div className="card space-y-4">
        <p className="font-mono text-xs text-slate-400 uppercase tracking-wider">🔍 Search & Launch</p>
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
          <input
            type="text" placeholder="Job keywords (e.g. Python Developer)"
            value={keywords} onChange={(e) => setKeywords(e.target.value)}
            className="bg-slate-800 border border-slate-700 text-white text-sm rounded-lg px-3 py-2.5 focus:outline-none focus:border-amber-400"
          />
          <input
            type="text" placeholder="Location (e.g. Bangalore, Remote)"
            value={location} onChange={(e) => setLocation(e.target.value)}
            className="bg-slate-800 border border-slate-700 text-white text-sm rounded-lg px-3 py-2.5 focus:outline-none focus:border-amber-400"
          />
        </div>
        <div className="flex flex-wrap gap-3">
          <button onClick={() => openSearch("linkedin")}
            className="flex items-center gap-2 bg-blue-600 hover:bg-blue-500 text-white font-semibold px-5 py-2.5 rounded-lg text-sm transition-colors">
            🔵 Search LinkedIn
          </button>
          <button onClick={() => openSearch("naukri")}
            className="flex items-center gap-2 bg-orange-600 hover:bg-orange-500 text-white font-semibold px-5 py-2.5 rounded-lg text-sm transition-colors">
            🟠 Search Naukri
          </button>
          <Link href="/dashboard"
            className="flex items-center gap-2 border border-amber-400/30 text-amber-400 hover:bg-amber-400/10 font-semibold px-5 py-2.5 rounded-lg text-sm transition-colors">
            🤖 Start Auto Apply →
          </Link>
        </div>
      </div>

      {/* ── 2. JD Analyzer ─────────────────────────────────────────────────── */}
      <div className="card space-y-4">
        <p className="font-mono text-xs text-slate-400 uppercase tracking-wider">🧠 JD Analyzer</p>
        <p className="text-slate-400 text-sm">Paste a job description to extract skills, keywords, and seniority level.</p>

        <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
          <input type="text" placeholder="Company" value={jdCompany} onChange={(e) => setJdCompany(e.target.value)}
            className="bg-slate-800 border border-slate-700 text-white text-sm rounded-lg px-3 py-2 focus:outline-none focus:border-blue-500" />
          <input type="text" placeholder="Role" value={jdRole} onChange={(e) => setJdRole(e.target.value)}
            className="bg-slate-800 border border-slate-700 text-white text-sm rounded-lg px-3 py-2 focus:outline-none focus:border-blue-500" />
          <select value={jdPlatform} onChange={(e) => setJdPlatform(e.target.value)}
            className="bg-slate-800 border border-slate-700 text-white text-sm rounded-lg px-3 py-2 focus:outline-none focus:border-blue-500">
            <option value="linkedin">LinkedIn</option>
            <option value="naukri">Naukri</option>
            <option value="other">Other</option>
          </select>
        </div>

        <textarea
          rows={8}
          placeholder="Paste the full job description here…"
          value={jdText}
          onChange={(e) => setJdText(e.target.value)}
          className="w-full bg-slate-900 border border-slate-700 text-slate-200 text-sm rounded-lg px-3 py-2.5 resize-y focus:outline-none focus:border-amber-400 placeholder-slate-600"
        />

        <div className="flex flex-wrap gap-3">
          <button onClick={handleAnalyzeJD} disabled={analyzing}
            className="bg-amber-400 hover:bg-amber-300 disabled:opacity-50 text-slate-950 font-bold px-5 py-2 rounded-lg text-sm">
            {analyzing ? "⚙️  Analyzing…" : "🧠 Analyze JD"}
          </button>
          {jdAnalysis && (
            <>
              <button onClick={handleSaveJob} disabled={savingJob}
                className="bg-emerald-500 hover:bg-emerald-400 disabled:opacity-50 text-white font-bold px-5 py-2 rounded-lg text-sm">
                {savingJob ? "Saving…" : "💾 Save to Tracker"}
              </button>
              <Link href="/resume-studio"
                className="border border-blue-500/30 text-blue-400 hover:bg-blue-500/10 font-bold px-5 py-2 rounded-lg text-sm transition-colors">
                ✨ Tailor Resume →
              </Link>
            </>
          )}
        </div>

        {savedJobId && (
          <p className="text-emerald-400 text-sm font-mono">✅ Job saved to tracker!</p>
        )}

        {/* Analysis Results */}
        {jdAnalysis && (
          <div className="space-y-4 pt-2 border-t border-slate-700">
            <div className="flex items-center gap-3 flex-wrap">
              <span className="text-sm text-slate-300">Seniority:</span>
              <span className="px-3 py-0.5 rounded-full bg-purple-500/15 text-purple-400 text-sm font-mono capitalize">
                {jdAnalysis.seniority}
              </span>
            </div>

            <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
              <div>
                <p className="font-mono text-xs text-emerald-400 uppercase mb-2">Required Skills</p>
                <div className="flex flex-wrap gap-1.5">
                  {jdAnalysis.required_skills.length > 0
                    ? jdAnalysis.required_skills.map((s) => (
                        <span key={s} className="px-2 py-0.5 rounded-full bg-emerald-500/10 text-emerald-400 text-xs font-mono border border-emerald-500/20">{s}</span>
                      ))
                    : <p className="text-slate-500 text-sm">No well-known skills detected</p>
                  }
                </div>
              </div>
              <div>
                <p className="font-mono text-xs text-blue-400 uppercase mb-2">Nice to Have</p>
                <div className="flex flex-wrap gap-1.5">
                  {jdAnalysis.nice_to_have.map((s) => (
                    <span key={s} className="px-2 py-0.5 rounded-full bg-blue-500/10 text-blue-400 text-xs font-mono border border-blue-500/20">{s}</span>
                  ))}
                </div>
              </div>
            </div>

            {jdAnalysis.responsibilities.length > 0 && (
              <div>
                <p className="font-mono text-xs text-slate-400 uppercase mb-2">Key Responsibilities</p>
                <ul className="space-y-1">
                  {jdAnalysis.responsibilities.slice(0, 5).map((r, i) => (
                    <li key={i} className="text-slate-400 text-sm flex gap-2"><span className="text-slate-600">•</span>{r}</li>
                  ))}
                </ul>
              </div>
            )}
          </div>
        )}
      </div>

      {/* ── 3. Company Watchlist ────────────────────────────────────────────── */}
      <div className="card space-y-4">
        <p className="font-mono text-xs text-slate-400 uppercase tracking-wider">⭐ Company Watchlist</p>
        <p className="text-slate-400 text-sm">Track companies you want to monitor for new openings.</p>

        <div className="flex flex-wrap gap-2">
          <input type="text" placeholder="Company name (e.g. Amazon)"
            value={watchCompany} onChange={(e) => setWatchCompany(e.target.value)}
            className="flex-1 min-w-[160px] bg-slate-800 border border-slate-700 text-white text-sm rounded-lg px-3 py-2 focus:outline-none focus:border-amber-400"
          />
          <input type="text" placeholder="Keywords (comma-separated, optional)"
            value={watchKw} onChange={(e) => setWatchKw(e.target.value)}
            className="flex-1 min-w-[180px] bg-slate-800 border border-slate-700 text-white text-sm rounded-lg px-3 py-2 focus:outline-none focus:border-amber-400"
          />
          <button onClick={handleAddWatch} disabled={addingWatch || !watchCompany.trim()}
            className="bg-amber-400 hover:bg-amber-300 disabled:opacity-50 text-slate-950 font-bold px-4 py-2 rounded-lg text-sm">
            + Add
          </button>
        </div>

        {watchlist.length > 0 ? (
          <div className="flex flex-wrap gap-2">
            {watchlist.map((w) => (
              <div key={w.id} className="flex items-center gap-2 bg-slate-800 border border-slate-700 rounded-full pl-3 pr-2 py-1">
                <span className="text-sm text-white">{w.company}</span>
                {w.keywords.length > 0 && <span className="text-xs text-slate-500">· {w.keywords.slice(0, 2).join(", ")}</span>}
                <button onClick={() => removeWatch(w.id)} className="text-slate-500 hover:text-red-400 text-xs ml-1">✕</button>
              </div>
            ))}
          </div>
        ) : (
          <p className="text-slate-600 text-sm">No companies in watchlist yet.</p>
        )}
      </div>

      {/* ── 4. Saved Jobs ───────────────────────────────────────────────────── */}
      <div>
        <h2 className="font-display font-semibold text-lg text-white mb-4">
          📋 Job Tracker ({savedJobs.length})
        </h2>
        {jobsLoading ? (
          <div className="card text-center py-8">
            <p className="text-slate-500 text-sm animate-pulse font-mono">Loading…</p>
          </div>
        ) : savedJobs.length === 0 ? (
          <div className="card border-dashed text-center py-8">
            <p className="text-slate-500 text-sm">No jobs saved yet. Analyse a JD above and save it.</p>
          </div>
        ) : (
          <div className="space-y-2">
            {savedJobs.map((job) => (
              <div key={job.id} className="card py-3 flex items-center justify-between gap-4">
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2 flex-wrap">
                    <p className="font-body font-semibold text-white truncate">{job.company}</p>
                    {job.url && (
                      <a href={job.url} target="_blank" rel="noopener noreferrer" className="text-xs text-blue-400 hover:underline shrink-0">↗</a>
                    )}
                  </div>
                  <p className="text-slate-400 text-sm truncate">{job.role}</p>
                  <p className="font-mono text-xs text-slate-600 mt-0.5">
                    {new Date(job.created_at).toLocaleDateString()}
                    {(job.metadata as any)?.seniority && (
                      <span className="ml-2 text-purple-400">{(job.metadata as any).seniority}</span>
                    )}
                  </p>
                </div>
                <div className="flex items-center gap-2 shrink-0">
                  <span className={`font-mono text-xs px-2 py-0.5 rounded ${STATUS_COLOR[job.status] || "bg-slate-500/15 text-slate-400"}`}>
                    {job.status}
                  </span>
                  <Link href="/resume-studio" className="text-xs text-amber-400 hover:underline font-mono">Tailor →</Link>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
