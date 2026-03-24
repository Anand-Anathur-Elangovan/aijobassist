"use client";

import { useState, useRef, useEffect } from "react";
import { useAuth } from "@/context/AuthContext";
import { supabase } from "@/lib/supabase";
import type {
  CareerPredictionResult,
  CareerCourseResult,
  CareerCollegeResult,
  CareerExamRoadmap,
  PlacementPrepResult,
  PlacementResource,
  DriveTiming,
  OffCampusPortal,
  PlacementWeekPlan,
} from "@/lib/ai";

// ── Types ─────────────────────────────────────────────────────────────────

type FormStep = 1 | 2 | 3 | 4;
type CopilotMode = "pathfinder" | "placement";
type PlacementTab = "exam" | "calendar" | "offcampus" | "plan";

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

interface PlacementForm {
  college:         string;
  degree:          string;
  branch:          string;
  graduation_year: string;
  cgpa:            string;
  placement_exams: string[];
  target_role:     string;
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
  // ── Tech & Computing ──
  "AI / Machine Learning",
  "Cybersecurity / Ethical Hacking",
  "Cloud Computing & DevOps",
  "Blockchain & Web3",
  "Computer Science / Programming",
  "Data Science / Analytics",
  "Game Development",
  "AR / VR / Metaverse",
  "Quantum Computing",
  "Embedded Systems / IoT",
  // ── Engineering ──
  "Electronics / VLSI",
  "Mechanical Engineering",
  "Civil / Structural Engineering",
  "Aerospace / Aeronautical Eng.",
  "Biomedical Engineering",
  "Nanotechnology",
  "Automotive / EV Engineering",
  "Marine & Naval Engineering",
  "Nuclear Engineering",
  "Robotics & Automation",
  // ── Science & Research ──
  "Medicine / Healthcare (MBBS)",
  "Pharmacy / Pharmaceutical Sci.",
  "Biotechnology / Genetic Eng.",
  "Astrophysics / Space Science",
  "Forensic Science",
  "Neuroscience",
  "Marine Biology / Oceanography",
  "Actuarial Science",
  "Pure Mathematics / Statistics",
  "Climate & Environmental Science",
  // ── Business & Finance ──
  "Finance / CA / Investment Banking",
  "Business / MBA / Management",
  "Digital Marketing & E-commerce",
  "Supply Chain & Logistics",
  "HR / Organisational Psychology",
  "Development Economics",
  // ── Law & Social Sciences ──
  "Law / Legal Studies",
  "Public Policy & Governance",
  "Journalism & Mass Communication",
  "Psychology / Counselling",
  "Social Work",
  // ── Creative & Design ──
  "Architecture & Urban Design",
  "Fashion / Textile Design",
  "Animation & VFX",
  "Film / Media Production",
  "Interior Design",
  "Music Technology",
  // ── Emerging & Underrated ──
  "Sustainable Energy / Renewables",
  "Food Technology & Nutrition",
  "Sports Science / Management",
  "Aviation / Pilot Training",
  "Hotel Management / Hospitality",
  "Physiotherapy / Allied Health",
  "Agriculture & AgriTech",
  "Defence / Military Science",
  "Education / Teaching",
];

const QUOTA_OPTIONS = [
  "Sports","Management","NRI","Ex-Servicemen","Differently-abled",
  "Linguistic Minority","Government Employee",
];

const PLACEMENT_EXAMS_LIST = ["AMCAT", "eLitmus", "Cocubes", "Wheebox", "HackerRank", "MeritTrac", "eLitmus pH"];

const PLACEMENT_DEGREES = ["B.E. / B.Tech", "BCA", "B.Sc CS / IT", "MCA", "MBA", "M.Tech", "B.Sc Other", "Diploma"];

const EMPTY_PLACEMENT: PlacementForm = {
  college:         "",
  degree:          "B.E. / B.Tech",
  branch:          "",
  graduation_year: String(new Date().getFullYear() + 1),
  cgpa:            "",
  placement_exams: ["AMCAT", "eLitmus"],
  target_role:     "",
};

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
  const [mode, setMode] = useState<CopilotMode>("pathfinder");
  const [step, setStep] = useState<FormStep>(1);
  const [form, setForm] = useState<StudentForm>(EMPTY_FORM);
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<CareerPredictionResult | null>(null);
  const [activeTab, setActiveTab] = useState<"courses" | "colleges" | "exams" | "strategy">("courses");
  const [placementForm, setPlacementForm] = useState<PlacementForm>(EMPTY_PLACEMENT);
  const [placementLoading, setPlacementLoading] = useState(false);
  const [placementResult, setPlacementResult] = useState<PlacementPrepResult | null>(null);
  const [placementTab, setPlacementTab] = useState<PlacementTab>("exam");
  const [error, setError] = useState<string | null>(null);
  const [placementError, setPlacementError] = useState<string | null>(null);
  const [interestInput, setInterestInput] = useState("");
  const [showCutoff, setShowCutoff] = useState(false);
  const [cutoffMarks, setCutoffMarks] = useState({ math: "", physics: "", chemistry: "", neet: "" });
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

  async function handlePlacementPredict() {
    setPlacementError(null);
    if (!placementForm.branch.trim()) {
      setPlacementError("Please enter your branch / specialization.");
      return;
    }
    setPlacementLoading(true);
    setPlacementResult(null);

    try {
      const session = await supabase.auth.getSession();
      const token = session.data.session?.access_token;
      if (!token) throw new Error("Not authenticated");

      const res = await fetch("/api/ai/placement-prep", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${token}`,
        },
        body: JSON.stringify({
          ...placementForm,
          graduation_year: placementForm.graduation_year ? parseInt(placementForm.graduation_year, 10) : undefined,
          cgpa: placementForm.cgpa ? parseFloat(placementForm.cgpa) : undefined,
        }),
      });

      const data = await res.json();
      if (!res.ok) throw new Error(data.error ?? "Placement prediction failed");
      setPlacementResult(data as PlacementPrepResult);
      setTimeout(() => resultRef.current?.scrollIntoView({ behavior: "smooth" }), 100);
    } catch (err) {
      const msg = err instanceof Error ? err.message : "Something went wrong";
      setPlacementError(msg);
    } finally {
      setPlacementLoading(false);
    }
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
            <label className={labelCls}>Community / Category <span className="text-slate-600 normal-case font-normal tracking-normal">(optional)</span></label>
            <select className={inputCls} value={form.community}
              onChange={(e) => setForm({ ...form, community: e.target.value })}>
              {["OC","BC","MBC","SC","ST","SEBC","EWS"].map((c) => (
                <option key={c} value={c}>{c}</option>
              ))}
            </select>
          </div>
        </div>
        <div>
          <label className={labelCls}>Special Quota <span className="text-slate-600 normal-case font-normal tracking-normal">(optional — select all that apply)</span></label>
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
    const isStateBoard = form.board === "State Board";
    const maxMarks = isStateBoard ? 200 : 100;

    const enggCutoff = (() => {
      const m = parseFloat(cutoffMarks.math) || 0;
      const p = parseFloat(cutoffMarks.physics) || 0;
      const c = parseFloat(cutoffMarks.chemistry) || 0;
      return isStateBoard ? m / 2 + p / 4 + c / 4 : m + p / 2 + c / 2;
    })();

    const enggTier = (co: number) => {
      if (co >= 195) return "IIT / BITS Pilani / Top NIT tier";
      if (co >= 180) return "NIT / Top Private (VIT, Manipal, BITS)";
      if (co >= 165) return "Good Private / Anna University tier";
      if (co >= 145) return "State Govt / Aided College";
      return "Needs improvement — focus on exam prep";
    };

    const neetTier = (score: number) => {
      if (score >= 680) return "AIIMS / JIPMER / Top Govt MBBS";
      if (score >= 600) return "Govt Medical College (state merit)";
      if (score >= 500) return "Private MBBS / BDS College";
      if (score >= 400) return "BAMS / BHMS / BSMS / BPT";
      return "Allied Health Sciences / Paramedical";
    };

    const showEngg = ["CS Group", "PCM", "PCMB"].includes(form.stream_12th);
    const showNeet = ["PCB", "PCMB", "Pure Bio"].includes(form.stream_12th);
    const showPct  = ["Commerce", "Arts / Humanities"].includes(form.stream_12th);
    const neetScore = parseFloat(cutoffMarks.neet) || 0;
    const hasEnggInput = !!(cutoffMarks.math || cutoffMarks.physics || cutoffMarks.chemistry);
    const hasNeetInput = !!cutoffMarks.neet;

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

        {/* 12th Stream */}
        <div>
          <label className={labelCls}>12th Stream (if applicable)</label>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-2">
            {["CS Group", "PCM", "PCB", "PCMB", "Pure Bio", "Commerce", "Arts / Humanities"].map((s) => (
              <button key={s} type="button"
                onClick={() => setForm({ ...form, stream_12th: form.stream_12th === s ? "" : s })}
                className={`px-3 py-2 rounded-lg text-xs font-semibold border transition-all text-center ${
                  form.stream_12th === s
                    ? "bg-amber-400/15 border-amber-400/40 text-amber-400"
                    : "bg-slate-800/50 border-slate-700 text-slate-400 hover:border-slate-500"
                }`}>{s}</button>
            ))}
          </div>
          <p className="mt-1.5 text-[11px] text-slate-600 leading-relaxed">
            CS Group = CS + Physics + Maths · PCM = Physics, Chem, Maths · PCB = Physics, Chem, Bio · PCMB = all 4 · Pure Bio = Biology + Zoology + Chem
          </p>
        </div>

        {/* ── Cutoff Calculator ────────────────── */}
        <div className="border border-slate-700/60 rounded-xl overflow-hidden">
          <button
            type="button"
            onClick={() => setShowCutoff((v) => !v)}
            className="w-full flex items-center justify-between px-4 py-3 bg-slate-900/60 hover:bg-slate-800/60 transition-colors"
          >
            <span className="font-semibold text-white text-sm flex items-center gap-2">
              📐 Cutoff Calculator
              <span className="px-1.5 py-0.5 bg-amber-400/10 border border-amber-400/30 text-amber-400 text-[10px] font-medium rounded-full">
                TN TNEA · NEET · JEE
              </span>
            </span>
            <span className="text-slate-500 text-xs">{showCutoff ? "▲ Collapse" : "▼ Expand"}</span>
          </button>

          {showCutoff && (
            <div className="p-4 space-y-4 bg-slate-900/30 border-t border-slate-700/40">

              {/* Formula explanation */}
              <div className="text-xs leading-relaxed space-y-1.5 pb-3 border-b border-slate-800">
                <p className="font-semibold text-slate-200 mb-2">How College Cutoffs Are Calculated in India</p>
                <p>
                  <span className="text-amber-400 font-semibold">TN TNEA (Engineering): </span>
                  <span className="font-mono text-white text-[11px]">Cutoff = Maths÷2 + Physics÷4 + Chemistry÷4</span>
                  <span className="text-slate-500"> — max 200. State Board marks are out of 200 each; CBSE marks out of 100 are scaled ×2 first. Reservation categories (BC/MBC/SC/ST) get separate merit lists.</span>
                </p>
                <p>
                  <span className="text-rose-400 font-semibold">NEET (Medical): </span>
                  <span className="text-slate-400">Raw NEET score out of 720. Central (AIQ) and state merit lists rank students by NEET score directly. AIIMS/JIPMER use NEET + counselling rounds.</span>
                </p>
                <p>
                  <span className="text-blue-400 font-semibold">JEE Main (Engineering): </span>
                  <span className="text-slate-400">Percentile score (not raw marks). NITs/IIITs require 95+ percentile. IIT JEE Advanced needs 99+ percentile overall. State quota seats have lower cutoffs.</span>
                </p>
                <p>
                  <span className="text-purple-400 font-semibold">Other State Exams: </span>
                  <span className="text-slate-400">KCET (Karnataka), MHT-CET (Maharashtra), EAMCET (AP/TS), KCET — each has its own rank + weightage formula. Cutoff varies by branch & category.</span>
                </p>
              </div>

              {/* Engineering Cutoff (PCM / CS Group / PCMB or no stream selected) */}
              {(showEngg || !form.stream_12th) && (
                <div className="space-y-3">
                  <p className="text-xs font-semibold text-slate-300 uppercase tracking-wider">🔧 Engineering Cutoff (TN TNEA / State Board Formula)</p>
                  <div className="grid grid-cols-3 gap-2">
                    {([
                      { key: "math"      as const, label: "Maths",     color: "text-amber-400",  focus: "focus:border-amber-400/60" },
                      { key: "physics"   as const, label: "Physics",   color: "text-blue-400",   focus: "focus:border-blue-400/60" },
                      { key: "chemistry" as const, label: "Chemistry", color: "text-emerald-400", focus: "focus:border-emerald-400/60" },
                    ]).map(({ key, label, color, focus }) => (
                      <div key={key}>
                        <label className={`block text-[10px] ${color} mb-1 uppercase tracking-wider`}>{label} (/{maxMarks})</label>
                        <input
                          type="number" min="0" max={maxMarks} step="0.5"
                          placeholder={isStateBoard ? "175" : "92"}
                          className={`w-full bg-slate-800 border border-slate-700 rounded-lg px-2 py-1.5 text-white text-xs focus:outline-none ${focus} transition-colors`}
                          value={cutoffMarks[key]}
                          onChange={(e) => setCutoffMarks((m) => ({ ...m, [key]: e.target.value }))}
                        />
                      </div>
                    ))}
                  </div>

                  {hasEnggInput && (
                    <div className="bg-slate-800/60 rounded-lg p-3 flex items-center justify-between">
                      <div>
                        <p className="text-[10px] text-slate-500 uppercase tracking-wider mb-0.5">Your Engineering Cutoff</p>
                        <p className="text-2xl font-bold text-amber-400 font-mono">
                          {enggCutoff.toFixed(2)}<span className="text-sm text-slate-500"> / 200</span>
                        </p>
                        <p className="text-xs text-slate-400 mt-0.5">{enggTier(enggCutoff)}</p>
                      </div>
                      <div className="text-right text-xs text-slate-500 space-y-0.5">
                        <p className="text-[10px] text-slate-500 uppercase tracking-wider mb-1">Breakdown</p>
                        <p>Maths: <span className="text-amber-400 font-mono">
                          {isStateBoard ? ((parseFloat(cutoffMarks.math)||0)/2).toFixed(2) : (parseFloat(cutoffMarks.math)||0).toFixed(2)}
                        </span></p>
                        <p>Physics: <span className="text-blue-400 font-mono">
                          {isStateBoard ? ((parseFloat(cutoffMarks.physics)||0)/4).toFixed(2) : ((parseFloat(cutoffMarks.physics)||0)/2).toFixed(2)}
                        </span></p>
                        <p>Chem: <span className="text-emerald-400 font-mono">
                          {isStateBoard ? ((parseFloat(cutoffMarks.chemistry)||0)/4).toFixed(2) : ((parseFloat(cutoffMarks.chemistry)||0)/2).toFixed(2)}
                        </span></p>
                      </div>
                    </div>
                  )}

                  <div className="text-[11px] text-slate-600 leading-relaxed">
                    <p className="text-slate-500 font-semibold mb-0.5">Typical TN TNEA Cutoffs 2024 (General / OC):</p>
                    <div className="grid grid-cols-2 gap-x-6">
                      <p>Anna Univ. CSE: ~198–199</p>
                      <p>PSG Tech CSE: ~193–196</p>
                      <p>CIT / Govt Engg: ~160–185</p>
                      <p>Private (aided): ~140–170</p>
                    </div>
                    <p className="mt-1 text-slate-700">BC/MBC cutoffs are typically 5–15 pts lower; SC/ST cutoffs 20–40 pts lower.</p>
                  </div>
                </div>
              )}

              {/* NEET Calculator (PCB / PCMB / Pure Bio) */}
              {(showNeet || !form.stream_12th) && (
                <div className={`space-y-3 ${(showEngg || !form.stream_12th) ? "pt-3 border-t border-slate-800" : ""}`}>
                  <p className="text-xs font-semibold text-slate-300 uppercase tracking-wider">🩺 NEET Score Tier (Medical Colleges)</p>
                  <div>
                    <label className="block text-[10px] text-rose-400 mb-1 uppercase tracking-wider">NEET Score (out of 720)</label>
                    <input
                      type="number" min="0" max="720"
                      placeholder="e.g. 580"
                      className="w-1/2 bg-slate-800 border border-slate-700 rounded-lg px-2 py-1.5 text-white text-xs focus:outline-none focus:border-rose-400/60 transition-colors"
                      value={cutoffMarks.neet}
                      onChange={(e) => setCutoffMarks((m) => ({ ...m, neet: e.target.value }))}
                    />
                  </div>
                  {hasNeetInput && (
                    <div className="bg-slate-800/60 rounded-lg p-3">
                      <p className="text-[10px] text-slate-500 uppercase tracking-wider mb-0.5">Predicted College Tier</p>
                      <p className="text-sm font-semibold text-rose-400">{neetTier(neetScore)}</p>
                      <p className="text-[11px] text-slate-500 mt-1">
                        AIIMS ≥ 680 · Govt MBBS: 550–680 · Pvt MBBS: 400–550 · BDS/BAMS/BHMS: 300–450
                      </p>
                    </div>
                  )}
                </div>
              )}

              {/* Commerce / Arts percentage guide */}
              {showPct && (
                <div className="space-y-2">
                  <p className="text-xs font-semibold text-slate-300 uppercase tracking-wider">🎓 Commerce / Arts College Admissions</p>
                  <div className="text-xs text-slate-400 space-y-1">
                    <p>Most colleges admit on the basis of 12th overall % or CUET score (accepted by 250+ central universities).</p>
                    <p><span className="text-emerald-400 font-semibold">90%+ / CUET 200+:</span> SRCC, Lady Shri Ram, St. Xavier&apos;s (Delhi / Mumbai)</p>
                    <p><span className="text-amber-400 font-semibold">80–90% / CUET 150+:</span> Good central / state university colleges</p>
                    <p><span className="text-blue-400 font-semibold">70–80% / CUET 100+:</span> Private universities / deemed colleges</p>
                    <p className="text-slate-500 mt-1">CA Foundation: 10+2 pass in any stream. LAW (CLAT): all streams eligible with 45-50% cutoff.</p>
                  </div>
                </div>
              )}
            </div>
          )}
        </div>

        <div className="bg-blue-500/5 border border-blue-500/20 rounded-lg p-3 text-sm text-blue-300">
          ℹ️ If you&apos;re in 11th or 12th, enter your current % (or expected %). If in 10th, enter only 10th marks.
        </div>
      </div>
    );
  }

  function StepExams() {
    return (
      <div className="space-y-4">
        <div>
          <label className={labelCls}>Entrance Exams <span className="text-slate-600 normal-case font-normal tracking-normal">(optional — select exams you plan to appear for)</span></label>
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
          AI-powered course recommendations, college predictions, and an exam strategy. Switch to Placement Mode for AMCAT/eLitmus prep, campus drive planning, and off-campus fresher jobs.
        </p>
      </div>

      <div className="flex gap-1 p-1 bg-slate-900 border border-slate-700 rounded-xl mb-8 max-w-xl">
        {([
          { key: "pathfinder" as CopilotMode, label: "🎓 College Pathfinder" },
          { key: "placement" as CopilotMode, label: "💼 Placement Mode" },
        ]).map(({ key, label }) => (
          <button
            key={key}
            onClick={() => setMode(key)}
            className={`flex-1 py-2.5 px-3 rounded-lg text-sm font-semibold transition-all ${
              mode === key ? "bg-amber-400 text-slate-950" : "text-slate-400 hover:text-white"
            }`}
          >
            {label}
          </button>
        ))}
      </div>

      {/* Input Form */}
      {mode === "pathfinder" && (
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
      )}

      {/* Placement Mode */}
      {mode === "placement" && (
        <div className="card mb-8 space-y-6">
          <div>
            <p className="text-xs font-mono uppercase tracking-wider text-slate-500 mb-1">Campus Hiring</p>
            <h2 className="text-xl font-display font-bold text-white">College Placement Mode</h2>
            <p className="text-sm text-slate-400 mt-1 max-w-2xl">
              Build a focused AMCAT/eLitmus prep plan, see the typical campus drive calendar, and get curated off-campus portals for fresher jobs.
            </p>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <div>
              <label className={labelCls}>College</label>
              <input
                className={inputCls}
                placeholder="e.g. Anna University / SRM / VIT"
                value={placementForm.college}
                onChange={(e) => setPlacementForm({ ...placementForm, college: e.target.value })}
              />
            </div>
            <div>
              <label className={labelCls}>Degree</label>
              <select
                className={inputCls}
                value={placementForm.degree}
                onChange={(e) => setPlacementForm({ ...placementForm, degree: e.target.value })}
              >
                {PLACEMENT_DEGREES.map((d) => <option key={d} value={d}>{d}</option>)}
              </select>
            </div>
            <div>
              <label className={labelCls}>Branch / Specialization *</label>
              <input
                className={inputCls}
                placeholder="e.g. CSE / IT / ECE / Mechanical"
                value={placementForm.branch}
                onChange={(e) => setPlacementForm({ ...placementForm, branch: e.target.value })}
              />
            </div>
            <div>
              <label className={labelCls}>Target Role</label>
              <input
                className={inputCls}
                placeholder="e.g. Software Engineer / Analyst / Data Analyst"
                value={placementForm.target_role}
                onChange={(e) => setPlacementForm({ ...placementForm, target_role: e.target.value })}
              />
            </div>
            <div>
              <label className={labelCls}>Graduation Year</label>
              <input
                className={inputCls}
                type="number"
                min="2024"
                max="2035"
                value={placementForm.graduation_year}
                onChange={(e) => setPlacementForm({ ...placementForm, graduation_year: e.target.value })}
              />
            </div>
            <div>
              <label className={labelCls}>CGPA <span className="text-slate-600 normal-case font-normal tracking-normal">(optional)</span></label>
              <input
                className={inputCls}
                type="number"
                min="0"
                max="10"
                step="0.01"
                placeholder="e.g. 8.12"
                value={placementForm.cgpa}
                onChange={(e) => setPlacementForm({ ...placementForm, cgpa: e.target.value })}
              />
            </div>
          </div>

          <div>
            <label className={labelCls}>Placement Exams</label>
            <div className="flex flex-wrap gap-2">
              {PLACEMENT_EXAMS_LIST.map((exam) => (
                <button
                  key={exam}
                  type="button"
                  onClick={() => setPlacementForm({ ...placementForm, placement_exams: toggle(placementForm.placement_exams, exam) })}
                  className={`px-3 py-1.5 rounded-lg text-xs font-medium border transition-all ${
                    placementForm.placement_exams.includes(exam)
                      ? "bg-amber-400/15 border-amber-400/40 text-amber-400"
                      : "bg-slate-800/50 border-slate-700 text-slate-400 hover:border-slate-500"
                  }`}
                >
                  {exam}
                </button>
              ))}
            </div>
          </div>

          <div className="bg-blue-500/5 border border-blue-500/20 rounded-lg p-4 text-sm text-blue-300">
            Includes: AMCAT/eLitmus prep map, campus drive calendar, HR tips, resume fixes, and fresher-focused off-campus aggregators.
          </div>

          {placementError && (
            <div className="px-3 py-2.5 bg-red-500/10 border border-red-500/30 rounded-lg text-sm text-red-400">
              ⚠️ {placementError}
            </div>
          )}

          <div className="flex justify-end">
            <button
              onClick={handlePlacementPredict}
              disabled={placementLoading}
              className="px-6 py-2.5 bg-amber-400 text-slate-950 font-bold rounded-lg hover:bg-amber-300 transition-all text-sm disabled:opacity-50 flex items-center gap-2"
            >
              {placementLoading ? (
                <>
                  <span className="w-4 h-4 border-2 border-slate-950 border-t-transparent rounded-full animate-spin" />
                  Building placement plan...
                </>
              ) : "🚀 Build Placement Plan"}
            </button>
          </div>
        </div>
      )}

      {/* Results */}
      {mode === "pathfinder" && result && (
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

      {mode === "placement" && placementResult && (
        <div ref={resultRef}>
          {placementResult.is_fallback && (
            <div className="mb-4 px-4 py-3 bg-amber-400/5 border border-amber-400/20 rounded-lg text-sm text-amber-300 flex items-start gap-2">
              <span className="shrink-0">⚠️</span>
              <span>Showing structured fallback guidance. Connect your AI key for more personalised placement planning.</span>
            </div>
          )}

          <div className="card">
            <div className="flex gap-1 border-b border-slate-800 mb-6 -mx-5 px-5 overflow-x-auto pb-0">
              {([
                { key: "exam" as PlacementTab, label: "📝 Exam Prep" },
                { key: "calendar" as PlacementTab, label: "📅 Drive Calendar" },
                { key: "offcampus" as PlacementTab, label: "🌐 Off-Campus Jobs" },
                { key: "plan" as PlacementTab, label: "🗺️ 4-Week Plan" },
              ]).map((t) => (
                <button
                  key={t.key}
                  onClick={() => setPlacementTab(t.key)}
                  className={`flex items-center gap-1.5 px-3 py-2.5 text-sm font-medium whitespace-nowrap border-b-2 transition-all -mb-px ${
                    placementTab === t.key
                      ? "border-amber-400 text-amber-400"
                      : "border-transparent text-slate-400 hover:text-white"
                  }`}
                >
                  {t.label}
                </button>
              ))}
            </div>

            {placementTab === "exam" && (
              <div className="space-y-6">
                <div>
                  <p className="text-xs text-slate-500 uppercase tracking-wider font-bold mb-3">AMCAT Prep</p>
                  <div className="space-y-2">
                    {placementResult.amcat_prep.map((item, i) => (
                      <div key={i} className="rounded-lg border border-slate-800 bg-slate-900/40 p-4">
                        <div className="flex items-center justify-between gap-3 mb-1">
                          <p className="text-sm font-semibold text-white">{item.topic}</p>
                          <span className="font-mono text-[10px] text-amber-400">{item.duration}</span>
                        </div>
                        <p className="text-xs text-slate-400">{item.resource} · {item.platform}</p>
                        <p className="text-sm text-slate-300 mt-2">{item.notes}</p>
                      </div>
                    ))}
                  </div>
                </div>
                <div>
                  <p className="text-xs text-slate-500 uppercase tracking-wider font-bold mb-3">eLitmus Prep</p>
                  <div className="space-y-2">
                    {placementResult.elitmus_prep.map((item, i) => (
                      <div key={i} className="rounded-lg border border-slate-800 bg-slate-900/40 p-4">
                        <div className="flex items-center justify-between gap-3 mb-1">
                          <p className="text-sm font-semibold text-white">{item.topic}</p>
                          <span className="font-mono text-[10px] text-blue-400">{item.duration}</span>
                        </div>
                        <p className="text-xs text-slate-400">{item.resource} · {item.platform}</p>
                        <p className="text-sm text-slate-300 mt-2">{item.notes}</p>
                      </div>
                    ))}
                  </div>
                </div>
              </div>
            )}

            {placementTab === "calendar" && (
              <div className="space-y-3">
                {placementResult.campus_drive_calendar.map((drive, i) => (
                  <div key={i} className="rounded-lg border border-slate-800 bg-slate-900/40 p-4">
                    <div className="flex flex-col md:flex-row md:items-center md:justify-between gap-2 mb-2">
                      <p className="text-white font-semibold">{drive.company}</p>
                      <span className="font-mono text-xs text-amber-400">{drive.typical_months}</span>
                    </div>
                    <div className="grid grid-cols-1 md:grid-cols-3 gap-3 text-sm">
                      <div>
                        <p className="text-xs text-slate-500 mb-0.5">Role</p>
                        <p className="text-slate-300">{drive.role}</p>
                      </div>
                      <div>
                        <p className="text-xs text-slate-500 mb-0.5">CTC range</p>
                        <p className="text-emerald-400 font-mono">{drive.ctc_range}</p>
                      </div>
                      <div>
                        <p className="text-xs text-slate-500 mb-0.5">Eligibility</p>
                        <p className="text-slate-300">{drive.eligibility}</p>
                      </div>
                    </div>
                  </div>
                ))}
              </div>
            )}

            {placementTab === "offcampus" && (
              <div className="space-y-3">
                {placementResult.off_campus_portals.map((portal, i) => (
                  <div key={i} className="rounded-lg border border-slate-800 bg-slate-900/40 p-4">
                    <div className="flex flex-col md:flex-row md:items-center md:justify-between gap-2 mb-2">
                      <p className="text-white font-semibold">{portal.name}</p>
                      <a href={`https://${portal.url}`} target="_blank" rel="noreferrer" className="text-xs text-amber-400 hover:text-amber-300 font-mono">
                        {portal.url} ↗
                      </a>
                    </div>
                    <p className="text-sm text-slate-300 mb-1">{portal.focus}</p>
                    <p className="text-sm text-slate-400">{portal.tips}</p>
                  </div>
                ))}
              </div>
            )}

            {placementTab === "plan" && (
              <div className="space-y-6">
                <div>
                  <p className="text-xs text-slate-500 uppercase tracking-wider font-bold mb-3">4-Week Action Plan</p>
                  <div className="space-y-3">
                    {placementResult.four_week_plan.map((week, i) => (
                      <div key={i} className="rounded-lg border border-slate-800 bg-slate-900/40 p-4">
                        <p className="text-amber-400 font-semibold text-sm mb-2">{week.week}</p>
                        <ul className="space-y-1.5">
                          {week.tasks.map((task, j) => (
                            <li key={j} className="flex gap-2 text-sm text-slate-300">
                              <span className="text-amber-400 shrink-0">•</span>{task}
                            </li>
                          ))}
                        </ul>
                      </div>
                    ))}
                  </div>
                </div>
                <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                  <div className="bg-blue-500/5 border border-blue-500/20 rounded-lg p-4">
                    <p className="text-blue-400 text-xs font-bold uppercase tracking-wider mb-3">🎤 HR Tips</p>
                    <ul className="space-y-1.5">
                      {placementResult.hr_tips.map((tip, i) => (
                        <li key={i} className="text-sm text-slate-300 flex gap-2"><span className="text-blue-400">•</span>{tip}</li>
                      ))}
                    </ul>
                  </div>
                  <div className="bg-emerald-500/5 border border-emerald-500/20 rounded-lg p-4">
                    <p className="text-emerald-400 text-xs font-bold uppercase tracking-wider mb-3">📄 Resume Tips</p>
                    <ul className="space-y-1.5">
                      {placementResult.resume_tips.map((tip, i) => (
                        <li key={i} className="text-sm text-slate-300 flex gap-2"><span className="text-emerald-400">•</span>{tip}</li>
                      ))}
                    </ul>
                  </div>
                </div>
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
