"use client";

import { useState, useRef, useEffect } from "react";
import { useAuth } from "@/context/AuthContext";
import { supabase } from "@/lib/supabase";
import type {
  CareerPredictionResult,
  CareerCourseResult,
  CareerCollegeResult,
  CareerExamRoadmap,
} from "@/lib/ai";

// ── Types ─────────────────────────────────────────────────────────────────

type FormStep = 1 | 2 | 3 | 4;

interface StudentForm {
  student_name:   string;
  state:          string;
  board:          string;
  marks_10th:     string;
  marks_12th:     string;
  stream_12th:    string;
  entrance_exams: string[];
  community:      string;
  quota:          string[];
  interests:      string[];
}

// ── Constants ─────────────────────────────────────────────────────────────

const INDIAN_STATES = [
  "Andhra Pradesh","Arunachal Pradesh","Assam","Bihar","Chhattisgarh","Goa",
  "Gujarat","Haryana","Himachal Pradesh","Jharkhand","Karnataka","Kerala",
  "Madhya Pradesh","Maharashtra","Manipur","Meghalaya","Mizoram","Nagaland",
  "Odisha","Punjab","Rajasthan","Sikkim","Tamil Nadu","Telangana","Tripura",
  "Uttar Pradesh","Uttarakhand","West Bengal",
  "Delhi (NCT)","Jammu & Kashmir","Ladakh","Puducherry","Chandigarh",
  "Andaman & Nicobar Islands","Lakshadweep","Dadra & Nagar Haveli",
];

const ENTRANCE_EXAMS = [
  "JEE Main","JEE Advanced","NEET","VITEEE","BITSAT","SRMJEE","KCET",
  "TANCET","COMEDK","MHT-CET","AP EAMCET","TS EAMCET","KEAM","OJEE",
  "UPCET","WBJEE","GUJCET","CUET","CLAT","NDA",
];

const INTERESTS_LIST = [
  "Computer Science / AI","Electronics / VLSI","Mechanical Engineering",
  "Civil Engineering","Medicine / Healthcare","Pharmacy","Biotechnology",
  "Data Science / Analytics","Finance / CA","Business / Management",
  "Law","Architecture","Agriculture","Fashion Design","Film / Media",
  "Psychology","Education / Teaching","Defence / Military",
];

const QUOTA_OPTIONS = [
  "Sports","Management","NRI","Ex-Servicemen","Differently-abled",
  "Linguistic Minority","Government Employee",
];

const PROB_COLORS: Record<string, string> = {
  High:   "text-emerald-400 bg-emerald-400/10 border-emerald-400/30",
  Medium: "text-amber-400 bg-amber-400/10 border-amber-400/30",
  Low:    "text-red-400 bg-red-400/10 border-red-400/30",
};

const CAT_COLORS: Record<string, string> = {
  Dream:    "text-purple-400 bg-purple-400/10 border-purple-400/30",
  Moderate: "text-blue-400 bg-blue-400/10 border-blue-400/30",
  Safe:     "text-emerald-400 bg-emerald-400/10 border-emerald-400/30",
};

const IMP_COLORS: Record<string, string> = {
  Critical:  "text-red-400 bg-red-400/10 border-red-400/30",
  Important: "text-amber-400 bg-amber-400/10 border-amber-400/30",
  Optional:  "text-slate-400 bg-slate-400/10 border-slate-400/30",
};

// ── Sub-components ────────────────────────────────────────────────────────

function PillBadge({ label, color }: { label: string; color: string }) {
  return (
    <span className={`inline-flex items-center px-2 py-0.5 rounded-full text-[11px] font-semibold border ${color}`}>
      {label}
    </span>
  );
}

function CourseCard({ c }: { c: CareerCourseResult }) {
  const [open, setOpen] = useState(false);
  return (
    <div className="card p-0 overflow-hidden">
      <button
        className="w-full text-left p-4 flex items-start gap-3 hover:bg-slate-800/40 transition-colors"
        onClick={() => setOpen((v) => !v)}
      >
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 flex-wrap mb-1">
            <p className="text-white font-semibold text-sm">{c.name}</p>
            <PillBadge label={c.probability} color={PROB_COLORS[c.probability]} />
            <span className="text-xs text-slate-500">{c.duration}</span>
          </div>
          <p className="text-xs text-slate-400">{c.match_reason}</p>
        </div>
        <div className="text-right shrink-0">
          <p className="text-emerald-400 text-xs font-mono">{c.avg_salary_lpa}</p>
          <span className={`text-slate-500 transition-transform inline-block mt-1 ${open ? "rotate-180" : ""}`}>▾</span>
        </div>
      </button>
      {open && (
        <div className="border-t border-slate-800 p-4 pt-3 space-y-3">
          <div>
            <p className="text-xs text-slate-500 uppercase tracking-wider mb-1">Future scope</p>
            <p className="text-sm text-slate-300">{c.future_scope}</p>
          </div>
          <div>
            <p className="text-xs text-slate-500 uppercase tracking-wider mb-1.5">Top institutes</p>
            <div className="flex flex-wrap gap-1.5">
              {c.top_institutes.map((t) => (
                <span key={t} className="px-2 py-0.5 bg-slate-800 text-slate-300 text-xs rounded">{t}</span>
              ))}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

function CollegeCard({ c }: { c: CareerCollegeResult }) {
  const [open, setOpen] = useState(false);
  return (
    <div className="card p-0 overflow-hidden">
      <button
        className="w-full text-left p-4 flex items-start gap-3 hover:bg-slate-800/40 transition-colors"
        onClick={() => setOpen((v) => !v)}
      >
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 flex-wrap mb-1">
            <p className="text-white font-semibold text-sm">{c.name}</p>
            <PillBadge label={c.category} color={CAT_COLORS[c.category]} />
            <PillBadge label={c.probability + " chance"} color={PROB_COLORS[c.probability]} />
          </div>
          <p className="text-xs text-slate-400">{c.location}, {c.state} · {c.college_type}</p>
        </div>
        <div className="text-right shrink-0">
          <p className="text-amber-400 text-xs font-mono">{c.fees_range}</p>
          <span className={`text-slate-500 transition-transform inline-block mt-1 ${open ? "rotate-180" : ""}`}>▾</span>
        </div>
      </button>
      {open && (
        <div className="border-t border-slate-800 p-4 pt-3 space-y-3">
          <div className="grid grid-cols-2 gap-3 text-sm">
            <div>
              <p className="text-xs text-slate-500 mb-0.5">Cutoff hint</p>
              <p className="text-slate-300">{c.cutoff_hint}</p>
            </div>
            <div>
              <p className="text-xs text-slate-500 mb-0.5">Avg placement</p>
              <p className="text-emerald-400 font-mono">{c.placement_avg_lpa}</p>
            </div>
          </div>
          <div>
            <p className="text-xs text-slate-500 uppercase tracking-wider mb-1.5">Courses offered</p>
            <div className="flex flex-wrap gap-1.5">
              {c.courses_offered.map((t) => (
                <span key={t} className="px-2 py-0.5 bg-slate-800 text-slate-300 text-xs rounded">{t}</span>
              ))}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

function ExamCard({ e }: { e: CareerExamRoadmap }) {
  const [open, setOpen] = useState(false);
  return (
    <div className="card p-0 overflow-hidden">
      <button
        className="w-full text-left p-4 flex items-center gap-3 hover:bg-slate-800/40 transition-colors"
        onClick={() => setOpen((v) => !v)}
      >
        <div className="flex-1">
          <div className="flex items-center gap-2 flex-wrap">
            <p className="text-white font-semibold text-sm">{e.exam}</p>
            <PillBadge label={e.importance} color={IMP_COLORS[e.importance]} />
          </div>
          <p className="text-xs text-slate-400 mt-0.5">Prep: {e.prep_duration} · Window: {e.exam_window}</p>
        </div>
        <span className={`text-slate-500 transition-transform ${open ? "rotate-180" : ""}`}>▾</span>
      </button>
      {open && (
        <div className="border-t border-slate-800 p-4 pt-3 space-y-3">
          <div>
            <p className="text-xs text-slate-500 uppercase tracking-wider mb-1.5">Key topics</p>
            <ul className="space-y-1">
              {e.key_topics.map((t) => (
                <li key={t} className="text-sm text-slate-300 flex gap-2"><span className="text-amber-400">•</span>{t}</li>
              ))}
            </ul>
          </div>
          <div>
            <p className="text-xs text-slate-500 uppercase tracking-wider mb-1.5">Recommended resources</p>
            <ul className="space-y-1">
              {e.recommended_resources.map((r) => (
                <li key={r} className="text-sm text-slate-300 flex gap-2"><span className="text-emerald-400">→</span>{r}</li>
              ))}
            </ul>
          </div>
        </div>
      )}
    </div>
  );
}

// ── Main Page ──────────────────────────────────────────────────────────────

const EMPTY_FORM: StudentForm = {
  student_name:   "",
  state:          "",
  board:          "CBSE",
  marks_10th:     "",
  marks_12th:     "",
  stream_12th:    "",
  entrance_exams: [],
  community:      "OC",
  quota:          [],
  interests:      [],
};

export default function CareerCopilotPage() {
  const { user } = useAuth();
  const [step, setStep] = useState<FormStep>(1);
  const [form, setForm] = useState<StudentForm>(EMPTY_FORM);
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<CareerPredictionResult | null>(null);
  const [activeTab, setActiveTab] = useState<"courses" | "colleges" | "exams" | "strategy">("courses");
  const [error, setError] = useState<string | null>(null);
  const [interestInput, setInterestInput] = useState("");
  const resultRef = useRef<HTMLDivElement>(null);

  // Load saved profile on mount
  useEffect(() => {
    if (!user) return;
    (async () => {
      try {
        const session = await supabase.auth.getSession();
        const token = session.data.session?.access_token;
        if (!token) return;
        const res = await fetch("/api/ai/career-copilot", {
          headers: { Authorization: `Bearer ${token}` },
        });
        if (!res.ok) return;
        const data = await res.json();
        if (data.profile) {
          setForm({
            student_name:   data.profile.student_name ?? "",
            state:          data.profile.state ?? "",
            board:          data.profile.board ?? "CBSE",
            marks_10th:     data.profile.marks_10th?.toString() ?? "",
            marks_12th:     data.profile.marks_12th?.toString() ?? "",
            stream_12th:    data.profile.stream_12th ?? "",
            entrance_exams: data.profile.entrance_exams ?? [],
            community:      data.profile.community ?? "OC",
            quota:          data.profile.quota ?? [],
            interests:      data.profile.interests ?? [],
          });
        }
        if (data.last_prediction) {
          setResult({
            courses:      data.last_prediction.courses,
            colleges:     data.last_prediction.colleges,
            exam_roadmap: data.last_prediction.exam_roadmap,
            strategy:     data.last_prediction.strategy,
            is_fallback:  data.last_prediction.is_fallback,
          });
        }
      } catch { /* silent */ }
    })();
  }, [user]);

  function toggle<T>(arr: T[], val: T): T[] {
    return arr.includes(val) ? arr.filter((x) => x !== val) : [...arr, val];
  }

  async function handlePredict() {
    setError(null);
    if (!form.state) { setError("Please select your State."); return; }
    setLoading(true);
    setResult(null);

    try {
      const session = await supabase.auth.getSession();
      const token = session.data.session?.access_token;
      if (!token) throw new Error("Not authenticated");

      const res = await fetch("/api/ai/career-copilot", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${token}`,
        },
        body: JSON.stringify({
          ...form,
          marks_10th: form.marks_10th ? parseFloat(form.marks_10th) : undefined,
          marks_12th: form.marks_12th ? parseFloat(form.marks_12th) : undefined,
        }),
      });

      const data = await res.json();
      if (!res.ok) throw new Error(data.error ?? "Prediction failed");
      setResult(data as CareerPredictionResult);
      setTimeout(() => resultRef.current?.scrollIntoView({ behavior: "smooth" }), 100);
    } catch (err) {
      const msg = err instanceof Error ? err.message : "Something went wrong";
      setError(msg);
    } finally {
      setLoading(false);
    }
  }

  // ── Step renderers ────────────────────────────────────────────────────

  const inputCls = "w-full bg-slate-900 border border-slate-700 rounded-lg px-3 py-2.5 text-white text-sm focus:outline-none focus:border-amber-400/60 transition-colors placeholder:text-slate-600";
  const labelCls = "block text-xs text-slate-400 font-medium mb-1.5 uppercase tracking-wider";

  function StepPersonal() {
    return (
      <div className="space-y-4">
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          <div>
            <label className={labelCls}>Full Name</label>
            <input className={inputCls} placeholder="e.g. Arjun Kumar" value={form.student_name}
              onChange={(e) => setForm({ ...form, student_name: e.target.value })} />
          </div>
          <div>
            <label className={labelCls}>State *</label>
            <select className={inputCls} value={form.state}
              onChange={(e) => setForm({ ...form, state: e.target.value })}>
              <option value="">Select your state</option>
              {INDIAN_STATES.map((s) => <option key={s} value={s}>{s}</option>)}
            </select>
          </div>
          <div>
            <label className={labelCls}>Board</label>
            <select className={inputCls} value={form.board}
              onChange={(e) => setForm({ ...form, board: e.target.value })}>
              <option value="CBSE">CBSE</option>
              <option value="ICSE">ICSE</option>
              <option value="State Board">State Board</option>
              <option value="International">International (IB/Cambridge)</option>
            </select>
          </div>
          <div>
            <label className={labelCls}>Community / Category</label>
            <select className={inputCls} value={form.community}
              onChange={(e) => setForm({ ...form, community: e.target.value })}>
              {["OC","BC","MBC","SC","ST","SEBC","EWS"].map((c) => (
                <option key={c} value={c}>{c}</option>
              ))}
            </select>
          </div>
        </div>
        <div>
          <label className={labelCls}>Special Quota (select all that apply)</label>
          <div className="flex flex-wrap gap-2">
            {QUOTA_OPTIONS.map((q) => (
              <button key={q} type="button"
                onClick={() => setForm({ ...form, quota: toggle(form.quota, q) })}
                className={`px-3 py-1.5 rounded-lg text-xs font-medium border transition-all ${
                  form.quota.includes(q)
                    ? "bg-amber-400/15 border-amber-400/40 text-amber-400"
                    : "bg-slate-800/50 border-slate-700 text-slate-400 hover:border-slate-500"
                }`}>{q}</button>
            ))}
          </div>
        </div>
      </div>
    );
  }

  function StepAcademic() {
    return (
      <div className="space-y-4">
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          <div>
            <label className={labelCls}>10th Marks (%)</label>
            <input className={inputCls} type="number" min="0" max="100" step="0.1"
              placeholder="e.g. 92.5"
              value={form.marks_10th}
              onChange={(e) => setForm({ ...form, marks_10th: e.target.value })} />
          </div>
          <div>
            <label className={labelCls}>12th Marks (%) — if completed</label>
            <input className={inputCls} type="number" min="0" max="100" step="0.1"
              placeholder="e.g. 88.0"
              value={form.marks_12th}
              onChange={(e) => setForm({ ...form, marks_12th: e.target.value })} />
          </div>
        </div>
        <div>
          <label className={labelCls}>12th Stream (if applicable)</label>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-2">
            {["PCM","PCB","Commerce","Arts / Humanities"].map((s) => (
              <button key={s} type="button"
                onClick={() => setForm({ ...form, stream_12th: form.stream_12th === s ? "" : s })}
                className={`px-3 py-2.5 rounded-lg text-sm font-medium border transition-all ${
                  form.stream_12th === s
                    ? "bg-amber-400/15 border-amber-400/40 text-amber-400"
                    : "bg-slate-800/50 border-slate-700 text-slate-400 hover:border-slate-500"
                }`}>{s}</button>
            ))}
          </div>
        </div>
        <div className="bg-blue-500/5 border border-blue-500/20 rounded-lg p-3 text-sm text-blue-300">
          ℹ️ If you're in 11th or 12th, enter your current % (or expected %). If in 10th, enter only 10th marks.
        </div>
      </div>
    );
  }

  function StepExams() {
    return (
      <div className="space-y-4">
        <div>
          <label className={labelCls}>Entrance Exams you are / plan to appear for</label>
          <div className="flex flex-wrap gap-2">
            {ENTRANCE_EXAMS.map((ex) => (
              <button key={ex} type="button"
                onClick={() => setForm({ ...form, entrance_exams: toggle(form.entrance_exams, ex) })}
                className={`px-3 py-1.5 rounded-lg text-xs font-medium border transition-all ${
                  form.entrance_exams.includes(ex)
                    ? "bg-amber-400/15 border-amber-400/40 text-amber-400"
                    : "bg-slate-800/50 border-slate-700 text-slate-400 hover:border-slate-500"
                }`}>{ex}</button>
            ))}
          </div>
        </div>
        {form.entrance_exams.length > 0 && (
          <div className="flex flex-wrap gap-1.5">
            <p className="text-xs text-slate-500 w-full">Selected:</p>
            {form.entrance_exams.map((ex) => (
              <span key={ex} className="px-2 py-0.5 bg-amber-400/10 border border-amber-400/30 text-amber-400 text-xs rounded-full">
                ✓ {ex}
              </span>
            ))}
          </div>
        )}
      </div>
    );
  }

  function StepInterests() {
    const addCustom = () => {
      const val = interestInput.trim();
      if (val && !form.interests.includes(val)) {
        setForm({ ...form, interests: [...form.interests, val] });
        setInterestInput("");
      }
    };
    return (
      <div className="space-y-4">
        <div>
          <label className={labelCls}>What are you interested in? (select all that apply)</label>
          <div className="flex flex-wrap gap-2">
            {INTERESTS_LIST.map((i) => (
              <button key={i} type="button"
                onClick={() => setForm({ ...form, interests: toggle(form.interests, i) })}
                className={`px-3 py-1.5 rounded-lg text-xs font-medium border transition-all ${
                  form.interests.includes(i)
                    ? "bg-amber-400/15 border-amber-400/40 text-amber-400"
                    : "bg-slate-800/50 border-slate-700 text-slate-400 hover:border-slate-500"
                }`}>{i}</button>
            ))}
          </div>
        </div>
        <div>
          <label className={labelCls}>Add your own interest</label>
          <div className="flex gap-2">
            <input className={inputCls} placeholder="e.g. Robotics, Space Technology..."
              value={interestInput}
              onChange={(e) => setInterestInput(e.target.value)}
              onKeyDown={(e) => { if (e.key === "Enter") { e.preventDefault(); addCustom(); } }} />
            <button type="button" onClick={addCustom}
              className="px-4 py-2.5 bg-slate-800 border border-slate-700 text-slate-300 rounded-lg text-sm hover:border-slate-500 shrink-0">
              Add
            </button>
          </div>
        </div>
        {form.interests.length > 0 && (
          <div className="flex flex-wrap gap-1.5">
            {form.interests.map((i) => (
              <span key={i}
                className="inline-flex items-center gap-1 px-2 py-0.5 bg-amber-400/10 border border-amber-400/30 text-amber-400 text-xs rounded-full">
                {i}
                <button type="button"
                  onClick={() => setForm({ ...form, interests: form.interests.filter((x) => x !== i) })}
                  className="hover:text-white">×</button>
              </span>
            ))}
          </div>
        )}
        <div className="bg-amber-400/5 border border-amber-400/20 rounded-lg p-3 text-sm text-amber-300">
          💡 The more specific your interests, the better AI can tailor your course and college recommendations.
        </div>
      </div>
    );
  }

  // ── Result tabs ───────────────────────────────────────────────────────

  const TABS = [
    { key: "courses"  as const, label: "🎓 Courses",   count: result?.courses.length },
    { key: "colleges" as const, label: "🏛️ Colleges",  count: result?.colleges.length },
    { key: "exams"    as const, label: "📝 Exam Prep", count: result?.exam_roadmap.length },
    { key: "strategy" as const, label: "🗺️ Strategy" },
  ];

  const STEPS_META = [
    { num: 1 as FormStep, label: "Personal Info" },
    { num: 2 as FormStep, label: "Academic Marks" },
    { num: 3 as FormStep, label: "Entrance Exams" },
    { num: 4 as FormStep, label: "Interests" },
  ];

  return (
    <div className="max-w-5xl mx-auto px-6 py-10">
      {/* Header */}
      <div className="mb-8">
        <h1 className="text-3xl font-display font-bold text-white flex items-center gap-3">
          <span className="w-10 h-10 bg-amber-400/10 rounded-lg flex items-center justify-center text-xl">🎯</span>
          AI Career Copilot
        </h1>
        <p className="text-slate-400 mt-2 max-w-xl">
          School → College → Career. Enter your marks, interests, and community to get
          AI-powered course recommendations, college predictions, and an exam strategy.
        </p>
      </div>

      {/* Input Form */}
      <div className="card mb-8">
        {/* Step progress bar */}
        <div className="flex items-center gap-2 mb-6">
          {STEPS_META.map((s, i) => (
            <div key={s.num} className="flex items-center gap-2 flex-1 min-w-0">
              <button
                onClick={() => setStep(s.num)}
                className={`w-7 h-7 rounded-full flex items-center justify-center text-xs font-bold shrink-0 transition-all ${
                  step === s.num
                    ? "bg-amber-400 text-slate-950"
                    : step > s.num
                    ? "bg-emerald-500/20 border border-emerald-500/30 text-emerald-400"
                    : "bg-slate-800 text-slate-500 border border-slate-700"
                }`}
              >
                {step > s.num ? "✓" : s.num}
              </button>
              <span className={`text-xs font-medium hidden sm:block truncate ${
                step === s.num ? "text-white" : "text-slate-500"
              }`}>{s.label}</span>
              {i < STEPS_META.length - 1 && (
                <div className={`h-px flex-1 ${step > s.num ? "bg-emerald-500/30" : "bg-slate-800"}`} />
              )}
            </div>
          ))}
        </div>

        {/* Step content */}
        <div className="mb-6">
          {step === 1 && <StepPersonal />}
          {step === 2 && <StepAcademic />}
          {step === 3 && <StepExams />}
          {step === 4 && <StepInterests />}
        </div>

        {/* Error */}
        {error && (
          <div className="mb-4 px-3 py-2.5 bg-red-500/10 border border-red-500/30 rounded-lg text-sm text-red-400">
            ⚠️ {error}
          </div>
        )}

        {/* Navigation */}
        <div className="flex items-center justify-between">
          <button
            disabled={step === 1}
            onClick={() => setStep((s) => (s - 1) as FormStep)}
            className="px-4 py-2 rounded-lg border border-slate-700 text-slate-400 text-sm hover:text-white hover:border-slate-500 disabled:opacity-30 transition-all"
          >
            ← Back
          </button>

          {step < 4 ? (
            <button
              onClick={() => setStep((s) => (s + 1) as FormStep)}
              className="px-5 py-2.5 bg-amber-400 text-slate-950 font-semibold rounded-lg hover:bg-amber-300 transition-all text-sm"
            >
              Next — {STEPS_META[step]?.label} →
            </button>
          ) : (
            <button
              onClick={handlePredict}
              disabled={loading}
              className="px-6 py-2.5 bg-amber-400 text-slate-950 font-bold rounded-lg hover:bg-amber-300 transition-all text-sm disabled:opacity-50 flex items-center gap-2"
            >
              {loading ? (
                <>
                  <span className="w-4 h-4 border-2 border-slate-950 border-t-transparent rounded-full animate-spin" />
                  Analysing...
                </>
              ) : "🔮 Get AI Predictions"}
            </button>
          )}
        </div>
      </div>

      {/* Results */}
      {result && (
        <div ref={resultRef}>
          {/* Fallback banner */}
          {result.is_fallback && (
            <div className="mb-4 px-4 py-3 bg-amber-400/5 border border-amber-400/20 rounded-lg text-sm text-amber-300 flex items-start gap-2">
              <span className="shrink-0">⚠️</span>
              <span>{result.message ?? "Showing illustrative predictions. Connect your AI API key for personalised analysis."}</span>
            </div>
          )}

          <div className="card">
            {/* Tabs */}
            <div className="flex gap-1 border-b border-slate-800 mb-6 -mx-5 px-5 overflow-x-auto pb-0">
              {TABS.map((t) => (
                <button
                  key={t.key}
                  onClick={() => setActiveTab(t.key)}
                  className={`flex items-center gap-1.5 px-3 py-2.5 text-sm font-medium whitespace-nowrap border-b-2 transition-all -mb-px ${
                    activeTab === t.key
                      ? "border-amber-400 text-amber-400"
                      : "border-transparent text-slate-400 hover:text-white"
                  }`}
                >
                  {t.label}
                  {t.count !== undefined && (
                    <span className="px-1.5 py-0.5 bg-slate-800 rounded-full text-[10px] font-mono">{t.count}</span>
                  )}
                </button>
              ))}
            </div>

            {/* Tab: Courses */}
            {activeTab === "courses" && (
              <div className="space-y-3">
                <p className="text-sm text-slate-400 mb-4">
                  Eligible courses ranked by your academic profile and interests.
                  Click any row to see future scope and top colleges.
                </p>
                {result.courses.map((c, i) => <CourseCard key={i} c={c} />)}
              </div>
            )}

            {/* Tab: Colleges */}
            {activeTab === "colleges" && (
              <div className="space-y-3">
                <p className="text-sm text-slate-400 mb-4">
                  College predictions based on your marks, state, community benefits, and quotas.
                  <span className="ml-2 gap-1.5 inline-flex">
                    {(["Dream","Moderate","Safe"] as const).map((c) => (
                      <PillBadge key={c} label={c} color={CAT_COLORS[c]} />
                    ))}
                  </span>
                </p>
                {result.colleges.map((c, i) => <CollegeCard key={i} c={c} />)}
              </div>
            )}

            {/* Tab: Exam Prep */}
            {activeTab === "exams" && (
              <div className="space-y-3">
                <p className="text-sm text-slate-400 mb-4">
                  Personalised exam preparation roadmap for your selected exams.
                </p>
                {result.exam_roadmap.map((e, i) => <ExamCard key={i} e={e} />)}
              </div>
            )}

            {/* Tab: Strategy */}
            {activeTab === "strategy" && (
              <div className="space-y-6">
                {/* Summary */}
                <div className="bg-amber-400/5 border border-amber-400/20 rounded-lg p-4">
                  <p className="text-amber-300 text-sm leading-relaxed">{result.strategy.summary}</p>
                </div>

                {/* Dream vs Safe */}
                <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                  <div className="bg-purple-500/5 border border-purple-500/20 rounded-lg p-4">
                    <p className="text-purple-400 text-xs font-bold uppercase tracking-wider mb-3">🏆 Dream Colleges</p>
                    <ul className="space-y-1.5">
                      {result.strategy.dream_colleges.map((c) => (
                        <li key={c} className="text-sm text-slate-300 flex gap-2">
                          <span className="text-purple-400">★</span>{c}
                        </li>
                      ))}
                    </ul>
                  </div>
                  <div className="bg-emerald-500/5 border border-emerald-500/20 rounded-lg p-4">
                    <p className="text-emerald-400 text-xs font-bold uppercase tracking-wider mb-3">✅ Safe Colleges</p>
                    <ul className="space-y-1.5">
                      {result.strategy.safe_colleges.map((c) => (
                        <li key={c} className="text-sm text-slate-300 flex gap-2">
                          <span className="text-emerald-400">✓</span>{c}
                        </li>
                      ))}
                    </ul>
                  </div>
                </div>

                {/* Timeline */}
                <div>
                  <p className="text-xs text-slate-500 uppercase tracking-wider font-bold mb-3">📅 Action Timeline</p>
                  <div className="space-y-2">
                    {result.strategy.action_timeline.map((t, i) => (
                      <div key={i} className="flex gap-3 items-start">
                        <span className="shrink-0 w-2 h-2 rounded-full bg-amber-400 mt-1.5" />
                        <div>
                          <p className="text-xs text-amber-400 font-semibold">{t.month}</p>
                          <p className="text-sm text-slate-300">{t.action}</p>
                        </div>
                      </div>
                    ))}
                  </div>
                </div>

                {/* Tips */}
                <div>
                  <p className="text-xs text-slate-500 uppercase tracking-wider font-bold mb-3">💡 Personalized Tips</p>
                  <ul className="space-y-2.5">
                    {result.strategy.tips.map((t, i) => (
                      <li key={i} className="flex gap-2 text-sm text-slate-300">
                        <span className="text-amber-400 shrink-0">•</span>{t}
                      </li>
                    ))}
                  </ul>
                </div>
              </div>
            )}
          </div>

          {/* Re-run button */}
          <div className="mt-4 text-center">
            <button
              onClick={() => { setResult(null); setStep(1); }}
              className="px-4 py-2 text-sm text-slate-400 hover:text-white border border-slate-700 hover:border-slate-500 rounded-lg transition-all"
            >
              ↺ Update Profile & Re-run
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
