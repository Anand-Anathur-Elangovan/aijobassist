"use client";

import { useState, useRef } from "react";
import { useAuth } from "@/context/AuthContext";
import { supabase } from "@/lib/supabase";
import type { LearningResource, SkillGapResult } from "@/lib/ai";
import type { FeedbackResult, HistoryEntry } from "@/app/api/ai/interview-prep/feedback/route";

type Question = {
  category: "Technical" | "Behavioral" | "Situational" | "Role-specific";
  question: string;
  answer: string;
};

type PrepResult = {
  questions: Question[];
  key_topics: string[];
  preparation_tips: string[];
};

type Mode = "questions" | "skillgap";

const CATEGORY_COLORS: Record<string, string> = {
  Technical:       "bg-blue-500/10 border-blue-500/30 text-blue-400",
  Behavioral:      "bg-purple-500/10 border-purple-500/30 text-purple-400",
  Situational:     "bg-amber-500/10 border-amber-500/30 text-amber-400",
  "Role-specific": "bg-emerald-500/10 border-emerald-500/30 text-emerald-400",
};

const PRIORITY_COLORS: Record<string, string> = {
  High:   "bg-red-500/10 border-red-500/30 text-red-400",
  Medium: "bg-amber-500/10 border-amber-500/30 text-amber-400",
  Low:    "bg-slate-500/10 border-slate-500/30 text-slate-400",
};

const PLATFORM_ICONS: Record<string, string> = {
  "YouTube":                  "▶",
  "Udemy":                    "🎓",
  "Coursera":                 "📖",
  "Official Docs / Practice": "📄",
  "FreeCodeCamp":             "🆓",
};

// ── Interactive Practice Card ─────────────────────────────────────────────
function PracticeCard({
  q, idx, history, jdText, company, role, resumeText,
  onAnswered,
}: {
  q: Question;
  idx: number;
  history: HistoryEntry[];
  jdText: string;
  company: string;
  role: string;
  resumeText: string;
  onAnswered: (entry: HistoryEntry) => void;
}) {
  const colorClass = CATEGORY_COLORS[q.category] ?? "bg-slate-700/30 border-slate-600/30 text-slate-400";
  const [open,        setOpen       ] = useState(false);
  const [showSuggest, setShowSuggest] = useState(false);
  const [userAnswer,  setUserAnswer ] = useState("");
  const [feedback,    setFeedback   ] = useState<FeedbackResult | null>(null);
  const [submitting,  setSubmitting ] = useState(false);
  const [error,       setError      ] = useState<string | null>(null);

  const practiced = history.some((h) => h.question === q.question);

  const submitAnswer = async () => {
    if (!userAnswer.trim()) return;
    setSubmitting(true);
    setError(null);
    try {
      const { data: { session } } = await supabase.auth.getSession();
      const tok = session?.access_token ?? "";
      const res = await fetch("/api/ai/interview-prep/feedback", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          ...(tok ? { Authorization: `Bearer ${tok}` } : {}),
        },
        body: JSON.stringify({
          question:    q.question,
          user_answer: userAnswer,
          jd_text:     jdText,
          company,
          role,
          resume_text: resumeText,
          history,     // full session history for context-aware feedback
        }),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.error ?? "Failed to get feedback");
      setFeedback(data as FeedbackResult);
      onAnswered({ question: q.question, user_answer: userAnswer, ai_feedback: data.feedback });
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Something went wrong.");
    } finally {
      setSubmitting(false);
    }
  };

  const scoreColor = !feedback ? "" :
    feedback.score >= 8 ? "text-emerald-400" :
    feedback.score >= 5 ? "text-amber-400" : "text-red-400";

  return (
    <div className={`card p-0 overflow-hidden ${practiced ? "border-emerald-500/20" : ""}`}>
      {/* Header row */}
      <button
        className="w-full text-left p-4 flex items-start gap-3 hover:bg-slate-800/40 transition-colors"
        onClick={() => setOpen((v) => !v)}
      >
        <span className="font-mono text-xs text-slate-600 mt-0.5 shrink-0 w-5">{idx + 1}.</span>
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 flex-wrap mb-1.5">
            <span className={`inline-block text-[10px] font-mono px-1.5 py-0.5 rounded border ${colorClass}`}>
              {q.category}
            </span>
            {practiced && (
              <span className="text-[10px] font-mono px-1.5 py-0.5 rounded border bg-emerald-500/10 border-emerald-500/30 text-emerald-400">
                ✓ Practiced
              </span>
            )}
          </div>
          <p className="font-body text-sm text-white leading-snug">{q.question}</p>
        </div>
        <span className={`text-slate-500 transition-transform shrink-0 mt-0.5 ${open ? "rotate-180" : ""}`}>▾</span>
      </button>

      {open && (
        <div className="border-t border-slate-800 px-4 pb-4 pt-3 space-y-4">
          {/* Suggested answer (collapsible) */}
          <div>
            <button
              onClick={() => setShowSuggest((v) => !v)}
              className="font-mono text-[10px] text-slate-500 uppercase tracking-wider flex items-center gap-1"
            >
              {showSuggest ? "▾" : "▸"} Suggested answer
            </button>
            {showSuggest && (
              <p className="mt-2 font-body text-sm text-slate-300 leading-relaxed whitespace-pre-line">
                {q.answer}
              </p>
            )}
          </div>

          {/* Practice input */}
          {!feedback ? (
            <div className="space-y-2">
              <p className="font-mono text-[10px] text-amber-400 uppercase tracking-wider">
                🎤 Practice — type your answer
              </p>
              <textarea
                rows={4}
                value={userAnswer}
                onChange={(e) => setUserAnswer(e.target.value)}
                placeholder="Type your answer here… AI will evaluate it in context of your full session."
                className="w-full bg-slate-900 border border-slate-700 rounded-lg px-3 py-2 text-sm text-white font-body resize-none focus:outline-none focus:border-amber-400/50 placeholder-slate-600"
              />
              {error && <p className="text-xs text-red-400 font-mono">{error}</p>}
              <button
                onClick={submitAnswer}
                disabled={submitting || !userAnswer.trim()}
                className="btn-primary text-xs px-4 py-2 disabled:opacity-50"
              >
                {submitting ? (
                  <span className="flex items-center gap-2">
                    <span className="w-3 h-3 border-2 border-slate-900 border-t-transparent rounded-full animate-spin" />
                    Getting feedback…
                  </span>
                ) : "Get AI Feedback →"}
              </button>
            </div>
          ) : (
            <div className="space-y-3">
              {/* Score */}
              <div className="flex items-center gap-3">
                <div className={`font-mono font-bold text-2xl ${scoreColor}`}>
                  {feedback.score}<span className="text-sm text-slate-500">/10</span>
                </div>
                <p className="text-sm text-slate-300 font-body flex-1">{feedback.feedback}</p>
              </div>

              {/* Strengths */}
              {feedback.strengths.length > 0 && (
                <div>
                  <p className="font-mono text-[10px] text-emerald-400 uppercase tracking-wider mb-1">Strengths</p>
                  <ul className="space-y-0.5">
                    {feedback.strengths.map((s, i) => (
                      <li key={i} className="text-xs text-slate-300 font-body">✓ {s}</li>
                    ))}
                  </ul>
                </div>
              )}

              {/* Improvements */}
              {feedback.improvements.length > 0 && (
                <div>
                  <p className="font-mono text-[10px] text-amber-400 uppercase tracking-wider mb-1">Improve</p>
                  <ul className="space-y-0.5">
                    {feedback.improvements.map((s, i) => (
                      <li key={i} className="text-xs text-slate-300 font-body">→ {s}</li>
                    ))}
                  </ul>
                </div>
              )}

              {/* Follow-up question */}
              {feedback.follow_up && (
                <div className="bg-slate-800/50 rounded-lg px-3 py-2 border border-slate-700/50">
                  <p className="font-mono text-[10px] text-blue-400 uppercase tracking-wider mb-1">Likely follow-up</p>
                  <p className="text-xs text-slate-200 font-body italic">&ldquo;{feedback.follow_up}&rdquo;</p>
                </div>
              )}

              {/* Re-try */}
              <button
                onClick={() => { setFeedback(null); setUserAnswer(""); }}
                className="text-xs font-mono text-slate-500 hover:text-white border border-slate-700 px-3 py-1 rounded transition-colors"
              >
                Try again
              </button>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

// ── Skill Gap card (unchanged) ─────────────────────────────────────────────
function SkillCard({ resource }: { resource: LearningResource }) {
  const [open, setOpen] = useState(false);
  const priorityClass = PRIORITY_COLORS[resource.priority] ?? PRIORITY_COLORS.Low;
  return (
    <div className="card p-0 overflow-hidden">
      <button
        className="w-full text-left p-4 flex items-center gap-3 hover:bg-slate-800/40 transition-colors"
        onClick={() => setOpen((v) => !v)}
      >
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 flex-wrap mb-0.5">
            <p className="text-white font-semibold text-sm">{resource.skill}</p>
            <span className={`text-[10px] font-mono px-1.5 py-0.5 rounded border ${priorityClass}`}>
              {resource.priority} priority
            </span>
            <span className="text-[10px] text-slate-500 font-mono">⏱ {resource.time_to_learn}</span>
          </div>
          <p className="text-xs text-slate-500">{resource.resources.length} resources · click to expand</p>
        </div>
        <span className={`text-slate-500 transition-transform shrink-0 ${open ? "rotate-180" : ""}`}>▾</span>
      </button>
      {open && (
        <div className="border-t border-slate-800 p-4 pt-3 space-y-2">
          {resource.resources.map((r, i) => (
            <div key={i} className="flex items-start gap-2 p-2 bg-slate-800/50 rounded-lg">
              <span className="text-amber-400 shrink-0 text-sm">{PLATFORM_ICONS[r.platform] ?? "→"}</span>
              <div className="min-w-0">
                <p className="text-xs font-semibold text-amber-300">{r.platform}</p>
                <p className="text-xs text-slate-300 mt-0.5">Search: <span className="font-mono text-slate-200">&ldquo;{r.search_query}&rdquo;</span></p>
                <p className="text-[10px] text-slate-500 mt-0.5">⏱ {r.duration}</p>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

// ── Main Page ─────────────────────────────────────────────────────────────
export default function InterviewPrepPage() {
  const { user } = useAuth();

  // Shared inputs
  const [mode,      setMode     ] = useState<Mode>("questions");
  const [company,   setCompany  ] = useState("");
  const [role,      setRole     ] = useState("");
  const [jdText,    setJdText   ] = useState("");
  const [useResume, setUseResume] = useState(true);
  const [resumeText, setResumeText] = useState("");  // cached once loaded

  // Interview questions mode
  const [loading,  setLoading ] = useState(false);
  const [result,   setResult  ] = useState<PrepResult | null>(null);
  const [error,    setError   ] = useState<string | null>(null);

  // Session memory: accumulates as user practices questions
  const [sessionHistory, setSessionHistory] = useState<HistoryEntry[]>([]);

  // Skill gap mode
  const [sgLoading, setSgLoading] = useState(false);
  const [sgResult,  setSgResult ] = useState<SkillGapResult | null>(null);
  const [sgError,   setSgError  ] = useState<string | null>(null);

  const resultRef = useRef<HTMLDivElement>(null);

  // ── Shared resume loader ──────────────────────────────────────────────
  async function loadResume(): Promise<string> {
    if (!useResume || !user) return "";
    if (resumeText) return resumeText;  // cached
    try {
      const { data } = await supabase
        .from("resumes")
        .select("parsed_text")
        .eq("user_id", user.id)
        .order("created_at", { ascending: false })
        .limit(1)
        .single();
      const text = (data as { parsed_text?: string })?.parsed_text ?? "";
      setResumeText(text);
      return text;
    } catch { return ""; }
  }

  async function getToken(): Promise<string> {
    const session = await supabase.auth.getSession();
    return session.data.session?.access_token ?? "";
  }

  // ── Interview Questions ───────────────────────────────────────────────
  const handleGenerate = async () => {
    if (!jdText.trim() || jdText.trim().length < 50) {
      setError("Please paste a complete job description (at least 50 characters).");
      return;
    }
    setError(null);
    setLoading(true);
    setResult(null);
    setSessionHistory([]);  // reset session when regenerating
    const loadedResume = await loadResume();
    const token = await getToken();
    try {
      const res = await fetch("/api/ai/interview-prep", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          ...(token ? { Authorization: `Bearer ${token}` } : {}),
        },
        body: JSON.stringify({ jd_text: jdText, resume_text: loadedResume, company, role }),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.error ?? "Failed to generate questions");
      setResult(data as PrepResult);
      setTimeout(() => resultRef.current?.scrollIntoView({ behavior: "smooth" }), 100);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Something went wrong.");
    } finally {
      setLoading(false);
    }
  };

  // ── Skill Gap Analysis ────────────────────────────────────────────────
  const handleSkillGap = async () => {
    if (!jdText.trim() || jdText.trim().length < 50) {
      setSgError("Please paste a complete job description (at least 50 characters).");
      return;
    }
    setSgError(null);
    setSgLoading(true);
    setSgResult(null);
    const loadedResume = await loadResume();
    const token = await getToken();
    if (!token) {
      setSgError("Please log in to use Skill Gap Analysis.");
      setSgLoading(false);
      return;
    }
    try {
      const res = await fetch("/api/ai/skill-gap", {
        method: "POST",
        headers: { "Content-Type": "application/json", Authorization: `Bearer ${token}` },
        body: JSON.stringify({ jd_text: jdText, resume_text: loadedResume }),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.error ?? "Failed to analyze skill gap");
      setSgResult(data as SkillGapResult);
      setTimeout(() => resultRef.current?.scrollIntoView({ behavior: "smooth" }), 100);
    } catch (e: unknown) {
      setSgError(e instanceof Error ? e.message : "Something went wrong.");
    } finally {
      setSgLoading(false);
    }
  };

  const handleAnswered = (entry: HistoryEntry) => {
    setSessionHistory((prev) => {
      // Replace if already practiced, else append
      const exists = prev.findIndex((h) => h.question === entry.question);
      if (exists >= 0) {
        const next = [...prev];
        next[exists] = entry;
        return next;
      }
      return [...prev, entry];
    });
  };

  const grouped = result
    ? (["Technical", "Behavioral", "Situational", "Role-specific"] as const).reduce<
        Record<string, Question[]>
      >((acc, cat) => {
        const qs = result.questions.filter((q) => q.category === cat);
        if (qs.length) acc[cat] = qs;
        return acc;
      }, {})
    : {};

  const activeError   = mode === "questions" ? error   : sgError;
  const activeLoading = mode === "questions" ? loading : sgLoading;

  return (
    <div className="max-w-3xl mx-auto px-6 py-12">
      {/* Header */}
      <div className="mb-8 animate-fadeUp">
        <p className="font-mono text-xs text-slate-500 tracking-widest uppercase mb-2">AI</p>
        <h1 className="font-display font-bold text-4xl text-white mb-2">
          Interview <span className="gradient-text">Prep</span>
        </h1>
        <p className="text-slate-400 font-body">
          Paste a job description to generate interview questions or analyse your skill gaps — both personalised to your resume.
        </p>
      </div>

      {/* Mode toggle */}
      <div className="flex gap-1 p-1 bg-slate-900 border border-slate-700 rounded-xl mb-6 animate-fadeUp">
        {([
          { key: "questions" as Mode, label: "🎤 Interview Questions" },
          { key: "skillgap"  as Mode, label: "🔍 Skill Gap Analysis" },
        ]).map(({ key, label }) => (
          <button
            key={key}
            onClick={() => setMode(key)}
            className={`flex-1 py-2 px-3 rounded-lg text-sm font-semibold transition-all ${
              mode === key
                ? "bg-amber-400 text-slate-950"
                : "text-slate-400 hover:text-white"
            }`}
          >
            {label}
          </button>
        ))}
      </div>

      {/* Input */}
      <div className="space-y-4 animate-fadeUp animate-fadeUp-delay-1">
        {/* Company + Role */}
        <div className="grid grid-cols-2 gap-3">
          <div>
            <label className="font-mono text-xs text-slate-400 uppercase tracking-wider block mb-1.5">
              Company <span className="text-slate-600 normal-case font-normal">(optional)</span>
            </label>
            <input
              value={company}
              onChange={(e) => setCompany(e.target.value)}
              placeholder="e.g. Google"
              className="w-full bg-slate-900 border border-slate-700 rounded-xl px-3 py-2.5 text-sm text-white font-body focus:outline-none focus:border-amber-400/50 placeholder-slate-600"
            />
          </div>
          <div>
            <label className="font-mono text-xs text-slate-400 uppercase tracking-wider block mb-1.5">
              Role <span className="text-slate-600 normal-case font-normal">(optional)</span>
            </label>
            <input
              value={role}
              onChange={(e) => setRole(e.target.value)}
              placeholder="e.g. Senior Backend Engineer"
              className="w-full bg-slate-900 border border-slate-700 rounded-xl px-3 py-2.5 text-sm text-white font-body focus:outline-none focus:border-amber-400/50 placeholder-slate-600"
            />
          </div>
        </div>

        {/* JD Textarea */}
        <div>
          <label className="font-mono text-xs text-slate-400 uppercase tracking-wider block mb-2">
            Job Description
          </label>
          <textarea
            value={jdText}
            onChange={(e) => setJdText(e.target.value)}
            placeholder="Paste the full job description here…"
            rows={10}
            className="w-full bg-slate-900 border border-slate-700 rounded-xl px-4 py-3 text-sm text-white font-body resize-none focus:outline-none focus:border-amber-400/50 placeholder-slate-600"
          />
          <p className="font-mono text-[10px] text-slate-600 mt-1">{jdText.length} chars</p>
        </div>

        <label className="flex items-center gap-2 cursor-pointer select-none">
          <div
            onClick={() => setUseResume((v) => !v)}
            className={`w-9 h-5 rounded-full transition-colors relative ${useResume ? "bg-amber-400" : "bg-slate-700"}`}
          >
            <span className={`absolute top-0.5 w-4 h-4 bg-white rounded-full shadow transition-all ${useResume ? "left-4" : "left-0.5"}`} />
          </div>
          <span className="font-body text-sm text-slate-300">Personalise with my resume</span>
        </label>

        {activeError && (
          <div className="rounded-lg bg-red-500/10 border border-red-500/20 px-4 py-3 text-red-400 font-body text-sm">
            {activeError}
          </div>
        )}

        <button
          onClick={mode === "questions" ? handleGenerate : handleSkillGap}
          disabled={activeLoading}
          className="btn-primary w-full"
        >
          {activeLoading ? (
            <span className="flex items-center justify-center gap-2">
              <span className="w-4 h-4 border-2 border-slate-900 border-t-transparent rounded-full animate-spin" />
              {mode === "questions" ? "Generating questions…" : "Analysing skill gap…"}
            </span>
          ) : mode === "questions" ? "Generate Interview Questions →" : "Analyze Skill Gap →"}
        </button>
      </div>

      {/* Results */}
      <div ref={resultRef}>

        {/* ── Interview Questions Results ── */}
        {result && mode === "questions" && (
          <div className="mt-12 space-y-8 animate-fadeUp">
            {result.key_topics?.length > 0 && (
              <div className="card">
                <p className="font-mono text-xs text-slate-400 uppercase tracking-wider mb-3">🎯 Key Topics to Prepare</p>
                <div className="flex flex-wrap gap-2">
                  {result.key_topics.map((t) => (
                    <span key={t} className="font-mono text-xs bg-amber-400/10 border border-amber-400/20 text-amber-300 px-2 py-1 rounded">
                      {t}
                    </span>
                  ))}
                </div>
              </div>
            )}

            {/* Session progress bar */}
            {result.questions.length > 0 && (
              <div className="flex items-center gap-3">
                <div className="flex-1 h-1.5 bg-slate-800 rounded-full overflow-hidden">
                  <div
                    className="h-full bg-emerald-500 rounded-full transition-all"
                    style={{ width: `${(sessionHistory.length / result.questions.length) * 100}%` }}
                  />
                </div>
                <span className="font-mono text-xs text-slate-500 shrink-0">
                  {sessionHistory.length}/{result.questions.length} practiced
                </span>
              </div>
            )}

            {Object.entries(grouped).map(([cat, qs]) => (
              <div key={cat}>
                <p className="font-mono text-xs text-slate-400 uppercase tracking-wider mb-3">{cat} Questions</p>
                <div className="space-y-2">
                  {qs.map((q, i) => (
                    <PracticeCard
                      key={i}
                      q={q}
                      idx={result.questions.indexOf(q)}
                      history={sessionHistory}
                      jdText={jdText}
                      company={company}
                      role={role}
                      resumeText={resumeText}
                      onAnswered={handleAnswered}
                    />
                  ))}
                </div>
              </div>
            ))}

            {result.preparation_tips?.length > 0 && (
              <div className="card bg-amber-400/5 border-amber-400/20">
                <p className="font-mono text-xs text-amber-400 uppercase tracking-wider mb-3">💡 Preparation Tips</p>
                <ul className="space-y-2">
                  {result.preparation_tips.map((tip, i) => (
                    <li key={i} className="text-slate-300 text-sm font-body">→ {tip}</li>
                  ))}
                </ul>
              </div>
            )}

            {/* Session summary when all practiced */}
            {sessionHistory.length === result.questions.length && result.questions.length > 0 && (
              <div className="card bg-emerald-500/5 border-emerald-500/20">
                <p className="font-mono text-xs text-emerald-400 uppercase tracking-wider mb-2">
                  🎉 Session Complete — {result.questions.length} questions practiced
                </p>
                <p className="text-sm text-slate-300 font-body">
                  Average score:{" "}
                  <strong className="text-emerald-400">
                    {/* We don&apos;t store scores in history, shown per-card */}
                    {result.questions.length} / {result.questions.length} answered
                  </strong>
                </p>
                <button
                  onClick={() => { setResult(null); setSessionHistory([]); }}
                  className="mt-3 text-xs font-mono text-slate-400 hover:text-white border border-slate-700 px-3 py-1 rounded"
                >
                  Start new session
                </button>
              </div>
            )}
          </div>
        )}

        {/* ── Skill Gap Results ── */}
        {sgResult && mode === "skillgap" && (
          <div className="mt-12 space-y-8 animate-fadeUp">
            {/* Score + skill pills */}
            <div className="card">
              <div className="flex flex-col md:flex-row md:items-center gap-6">
                {/* Score circle */}
                <div className="shrink-0 flex flex-col items-center">
                  <div className={`w-24 h-24 rounded-full flex flex-col items-center justify-center border-4 ${
                    sgResult.score >= 70 ? "border-emerald-500 bg-emerald-500/10" :
                    sgResult.score >= 45 ? "border-amber-400 bg-amber-400/10" :
                    "border-red-500 bg-red-500/10"
                  }`}>
                    <span className={`font-mono font-bold text-2xl ${
                      sgResult.score >= 70 ? "text-emerald-400" :
                      sgResult.score >= 45 ? "text-amber-400" : "text-red-400"
                    }`}>{sgResult.score}%</span>
                    <span className="font-mono text-[10px] text-slate-500">ATS Match</span>
                  </div>
                </div>
                {/* Skill breakdown */}
                <div className="flex-1 space-y-3">
                  {sgResult.matching_skills?.length > 0 && (
                    <div>
                      <p className="font-mono text-[10px] text-emerald-400 uppercase tracking-wider mb-1.5">✓ Skills you have ({sgResult.matching_skills.length})</p>
                      <div className="flex flex-wrap gap-1.5">
                        {sgResult.matching_skills.map((s) => (
                          <span key={s} className="px-2 py-0.5 bg-emerald-500/10 border border-emerald-500/30 text-emerald-300 text-xs rounded-full font-mono">{s}</span>
                        ))}
                      </div>
                    </div>
                  )}
                  {sgResult.missing_skills?.length > 0 && (
                    <div>
                      <p className="font-mono text-[10px] text-red-400 uppercase tracking-wider mb-1.5">✗ Missing skills ({sgResult.missing_skills.length})</p>
                      <div className="flex flex-wrap gap-1.5">
                        {sgResult.missing_skills.map((s) => (
                          <span key={s} className="px-2 py-0.5 bg-red-500/10 border border-red-500/30 text-red-300 text-xs rounded-full font-mono">{s}</span>
                        ))}
                      </div>
                    </div>
                  )}
                </div>
              </div>
              {sgResult.suggestions?.length > 0 && (
                <div className="mt-4 pt-4 border-t border-slate-800">
                  <p className="font-mono text-[10px] text-slate-400 uppercase tracking-wider mb-2">Suggestions</p>
                  <ul className="space-y-1">
                    {sgResult.suggestions.map((s, i) => (
                      <li key={i} className="text-sm text-slate-300">→ {s}</li>
                    ))}
                  </ul>
                </div>
              )}
            </div>

            {/* 2-week learning plan */}
            {sgResult.learning_plan?.length > 0 && (
              <div>
                <p className="font-mono text-xs text-slate-400 uppercase tracking-wider mb-3">📚 2-Week Learning Plan</p>
                <div className="space-y-2">
                  {sgResult.learning_plan.map((r, i) => (
                    <SkillCard key={i} resource={r} />
                  ))}
                </div>
              </div>
            )}

            {/* Schedule */}
            {sgResult.two_week_schedule?.length > 0 && (
              <div className="card bg-blue-500/5 border-blue-500/20">
                <p className="font-mono text-xs text-blue-400 uppercase tracking-wider mb-4">📅 Day-by-Day Schedule</p>
                <div className="space-y-2.5">
                  {sgResult.two_week_schedule.map((item, i) => (
                    <div key={i} className="flex gap-3 items-start">
                      <span className="shrink-0 w-5 h-5 rounded-full bg-blue-500/20 border border-blue-500/30 text-blue-400 text-[10px] flex items-center justify-center font-mono font-bold mt-0.5">{i + 1}</span>
                      <p className="text-sm text-slate-300">{item}</p>
                    </div>
                  ))}
                </div>
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
