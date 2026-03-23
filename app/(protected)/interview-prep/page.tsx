"use client";

import { useState, useRef } from "react";
import { useAuth } from "@/context/AuthContext";
import { supabase } from "@/lib/supabase";

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

const CATEGORY_COLORS: Record<string, string> = {
  Technical:     "bg-blue-500/10 border-blue-500/30 text-blue-400",
  Behavioral:    "bg-purple-500/10 border-purple-500/30 text-purple-400",
  Situational:   "bg-amber-500/10 border-amber-500/30 text-amber-400",
  "Role-specific": "bg-emerald-500/10 border-emerald-500/30 text-emerald-400",
};

function QuestionCard({ q, idx }: { q: Question; idx: number }) {
  const [open, setOpen] = useState(false);
  const colorClass = CATEGORY_COLORS[q.category] ?? "bg-slate-700/30 border-slate-600/30 text-slate-400";

  return (
    <div className="card p-0 overflow-hidden">
      <button
        className="w-full text-left p-4 flex items-start gap-3 hover:bg-slate-800/40 transition-colors"
        onClick={() => setOpen((v) => !v)}
      >
        <span className="font-mono text-xs text-slate-600 mt-0.5 shrink-0 w-5">{idx + 1}.</span>
        <div className="flex-1 min-w-0">
          <span className={`inline-block text-[10px] font-mono px-1.5 py-0.5 rounded border mb-1.5 ${colorClass}`}>
            {q.category}
          </span>
          <p className="font-body text-sm text-white leading-snug">{q.question}</p>
        </div>
        <span className={`text-slate-500 transition-transform shrink-0 mt-0.5 ${open ? "rotate-180" : ""}`}>▾</span>
      </button>

      {open && (
        <div className="px-4 pb-4 pt-0 border-t border-slate-800">
          <p className="font-mono text-[10px] text-slate-500 uppercase tracking-wider mb-2 mt-3">Suggested Answer</p>
          <p className="font-body text-sm text-slate-300 leading-relaxed whitespace-pre-line">{q.answer}</p>
        </div>
      )}
    </div>
  );
}

export default function InterviewPrepPage() {
  const { user } = useAuth();
  const [jdText, setJdText] = useState("");
  const [useResume, setUseResume] = useState(true);
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<PrepResult | null>(null);
  const [error, setError] = useState<string | null>(null);
  const resultRef = useRef<HTMLDivElement>(null);

  const handleGenerate = async () => {
    if (!jdText.trim() || jdText.trim().length < 50) {
      setError("Please paste a complete job description (at least 50 characters).");
      return;
    }
    setError(null);
    setLoading(true);
    setResult(null);

    // Optionally load resume text for personalisation
    let resumeText = "";
    if (useResume && user) {
      try {
        const { data } = await supabase
          .from("resumes")
          .select("parsed_text")
          .eq("user_id", user.id)
          .order("created_at", { ascending: false })
          .limit(1)
          .single();
        resumeText = (data as { parsed_text?: string })?.parsed_text ?? "";
      } catch {
        // non-fatal
      }
    }

    try {
      const res = await fetch("/api/ai/interview-prep", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ jd_text: jdText, resume_text: resumeText }),
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

  const grouped = result
    ? (["Technical", "Behavioral", "Situational", "Role-specific"] as const).reduce<
        Record<string, Question[]>
      >((acc, cat) => {
        const qs = result.questions.filter((q) => q.category === cat);
        if (qs.length) acc[cat] = qs;
        return acc;
      }, {})
    : {};

  return (
    <div className="max-w-3xl mx-auto px-6 py-12">
      {/* Header */}
      <div className="mb-8 animate-fadeUp">
        <p className="font-mono text-xs text-slate-500 tracking-widest uppercase mb-2">AI</p>
        <h1 className="font-display font-bold text-4xl text-white mb-2">
          Interview <span className="gradient-text">Prep</span>
        </h1>
        <p className="text-slate-400 font-body">
          Paste a job description and get 10 likely interview questions with suggested answers, personalised to your resume.
        </p>
      </div>

      {/* Input */}
      <div className="space-y-4 animate-fadeUp animate-fadeUp-delay-1">
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

        {error && (
          <div className="rounded-lg bg-red-500/10 border border-red-500/20 px-4 py-3 text-red-400 font-body text-sm">
            {error}
          </div>
        )}

        <button
          onClick={handleGenerate}
          disabled={loading}
          className="btn-primary w-full"
        >
          {loading ? (
            <span className="flex items-center justify-center gap-2">
              <span className="w-4 h-4 border-2 border-slate-900 border-t-transparent rounded-full animate-spin" />
              Generating questions…
            </span>
          ) : (
            "Generate Interview Questions →"
          )}
        </button>
      </div>

      {/* Results */}
      {result && (
        <div ref={resultRef} className="mt-12 space-y-8 animate-fadeUp">
          {/* Key topics */}
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

          {/* Questions by category */}
          {Object.entries(grouped).map(([cat, qs]) => (
            <div key={cat}>
              <p className="font-mono text-xs text-slate-400 uppercase tracking-wider mb-3">{cat} Questions</p>
              <div className="space-y-2">
                {qs.map((q, i) => (
                  <QuestionCard key={i} q={q} idx={result.questions.indexOf(q)} />
                ))}
              </div>
            </div>
          ))}

          {/* Tips */}
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
        </div>
      )}
    </div>
  );
}
