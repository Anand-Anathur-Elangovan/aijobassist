"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { useAuth } from "@/context/AuthContext";
import { getResumes, getJobs } from "@/lib/supabase";
import { supabase } from "@/lib/supabase";
import { useSubscription } from "@/components/SubscriptionGuard";

type ResumeRow = { id: string; title: string; created_at: string; parsed_text?: string };
type JobRow = { id: string; company: string; role: string; status: string };
type LogEntry = { ts: string; level: "info" | "warn" | "error" | "success"; msg: string };
type TaskRow = {
  id: string;
  type: string;
  status: string;
  created_at: string;
  progress?: number;
  current_job?: string;
  logs?: LogEntry[];
  paused?: boolean;
  stop_requested?: boolean;
  custom_prompt_override?: string;
  output?: { applied_count?: number; message?: string } | null;
};

export default function DashboardPage() {
  const { user } = useAuth();
  const { plan, subscription, usage, getRemaining } = useSubscription();
  const [resumes, setResumes] = useState<ResumeRow[]>([]);
  const [jobs, setJobs] = useState<JobRow[]>([]);
  const [tasks, setTasks] = useState<TaskRow[]>([]);
  const [appsCount, setAppsCount] = useState(0);
  const [loadingData, setLoadingData] = useState(true);
  const [taskLoading, setTaskLoading] = useState(false);
  const [phone, setPhone] = useState("");
  const [phoneCountry, setPhoneCountry] = useState("India (+91)");
  const [yearsExp, setYearsExp] = useState("2");
  const [skillRating, setSkillRating] = useState("8");
  const [keywords, setKeywords] = useState("Software Engineer");
  const [keywords2, setKeywords2] = useState("");
  const [keywords3, setKeywords3] = useState("");
  const [locationList, setLocationList] = useState<string[]>([]);
  const [locationInput, setLocationInput] = useState("");
  const [remoteEnabled, setRemoteEnabled] = useState(false);
  const [maxApply, setMaxApply] = useState("5");
  const [noticePeriod, setNoticePeriod] = useState("30");
  const [salaryExpectation, setSalaryExpectation] = useState("");
  const [platform, setPlatform] = useState<"linkedin" | "naukri">("linkedin");
  const [semiAuto, setSemiAuto] = useState(false);
  const [applyMode, setApplyMode] = useState<"auto" | "tailor">("auto");
  const [resumeAutoLoaded, setResumeAutoLoaded] = useState(false);
  // Tailor & Apply extra state
  const [tailorPrompt, setTailorPrompt] = useState("");
  const [favCompanies, setFavCompanies] = useState<string[]>([]);
  const [favCompanyInput, setFavCompanyInput] = useState("");
  // Naukri-specific apply type preference
  const [naukriApplyTypes, setNaukriApplyTypes] = useState<"both" | "direct_only" | "company_site_only">("both");
  // LinkedIn search filters
  const [linkedinDatePosted, setLinkedinDatePosted] = useState<"any" | "past24h" | "pastWeek" | "pastMonth">("any");
  const [linkedinExpLevel, setLinkedinExpLevel] = useState<"all" | "internship" | "entry" | "associate" | "mid" | "director" | "executive">("all");
  const [linkedinJobType, setLinkedinJobType] = useState<"all" | "fullTime" | "partTime" | "contract" | "temporary" | "internship">("all");
  // Naukri search filters
  const [naukriDatePosted, setNaukriDatePosted] = useState<"any" | "1" | "3" | "7" | "15" | "30">("any");
  const [naukriWorkMode, setNaukriWorkMode] = useState<"any" | "remote" | "hybrid" | "office">("any");
  const [naukriJobType, setNaukriJobType] = useState<"all" | "fullTime" | "partTime" | "contract" | "temporary">("all");
  // Smart Match — AI resume vs JD scoring gate
  const [smartMatch, setSmartMatch] = useState(false);
  const [matchThreshold, setMatchThreshold] = useState(70);
  // Auto Cover Letter — generate AI cover letter per application
  const [autoCoverLetter, setAutoCoverLetter] = useState(true);
  // Smart Apply Scheduler — only apply within a time window
  const [scheduleEnabled, setScheduleEnabled] = useState(false);
  const [scheduleStartHour, setScheduleStartHour] = useState(9);
  const [scheduleEndHour, setScheduleEndHour] = useState(23);
  // Platform login credentials (optional — stored client-side only, passed to bot)
  const [linkedinEmail, setLinkedinEmail] = useState("");
  const [linkedinPassword, setLinkedinPassword] = useState("");
  const [showLinkedinPwd, setShowLinkedinPwd] = useState(false);
  // Gmail follow-up settings
  const [gmailAddress, setGmailAddress] = useState("");
  const [gmailAppPassword, setGmailAppPassword] = useState("");
  const [showGmailPwd, setShowGmailPwd] = useState(false);
  const [followupDays, setFollowupDays] = useState("3");
  const [gmailSaving, setGmailSaving] = useState(false);
  const [tailorResult, setTailorResult] = useState<{
    score_before: number;
    score_after: number;
    tailored_text: string;
    tailored_summary: string;
    tailored_bullets: string[];
    ats_score: number;
    improvements: string[];
    missing_skills: string[];
    added_keywords: string[];
  } | null>(null);
  const [tailorLoading, setTailorLoading] = useState(false);
  const [resumeText, setResumeText] = useState("");
  const [jdText, setJdText] = useState("");
  const [editedResume, setEditedResume] = useState("");

  // Live run monitor state
  const [liveTask, setLiveTask] = useState<TaskRow | null>(null);
  const [livePrompt, setLivePrompt] = useState("");
  const [livePromptSaving, setLivePromptSaving] = useState(false);
  // Job history reset
  const [resetHistoryLoading, setResetHistoryLoading] = useState(false);
  const [resetSmartMatchLoading, setResetSmartMatchLoading] = useState(false);

  const fetchTasks = async () => {
    const { data } = await supabase.from("tasks").select("*").order("created_at", { ascending: false });
    if (data) {
      const rows = data as TaskRow[];
      setTasks(rows);
      // Keep liveTask in sync if it's in the list
      const running = rows.find((t) => t.status === "RUNNING");
      if (running) setLiveTask(running);
    }
  };

  useEffect(() => {
    if (!user) return;
    Promise.all([
      getResumes(user.id),
      getJobs(user.id),
      supabase.from("applications").select("id", { count: "exact", head: true }).eq("user_id", user.id),
    ]).then(([resumeRes, jobsRes, appsRes]) => {
      if (resumeRes.data) {
        setResumes(resumeRes.data as ResumeRow[]);
        // Pre-load parsed_text of the latest resume for the tailor preview
        const latest = (resumeRes.data as ResumeRow[])[0];
        if (latest?.parsed_text) {
          setResumeText(latest.parsed_text);
          setResumeAutoLoaded(true);
        }
      }
      if (jobsRes.data) setJobs(jobsRes.data as JobRow[]);
      setAppsCount(appsRes.count ?? 0);
    }).finally(() => setLoadingData(false));

    // Load gmail/follow-up settings
    supabase.from("gmail_settings").select("*").eq("user_id", user.id).maybeSingle().then(({ data }) => {
      if (data) {
        setGmailAddress(data.gmail_address || "");
        setGmailAppPassword(data.app_password || "");
        setFollowupDays(String(data.followup_days ?? 3));
      }
    });

    fetchTasks();

    // Supabase Realtime — subscribe to task row changes for this user
    const channel = supabase
      .channel("tasks-live")
      .on(
        "postgres_changes",
        { event: "*", schema: "public", table: "tasks", filter: `user_id=eq.${user.id}` },
        (payload) => {
          const updated = payload.new as TaskRow;
          setTasks((prev) => {
            const idx = prev.findIndex((t) => t.id === updated.id);
            if (idx === -1) return [updated, ...prev];
            const next = [...prev];
            next[idx] = updated;
            return next;
          });
          if (updated.status === "RUNNING") setLiveTask(updated);
          if (updated.status === "DONE" || updated.status === "FAILED") {
            setLiveTask((cur) => (cur?.id === updated.id ? updated : cur));
          }
        }
      )
      .subscribe();

    return () => { supabase.removeChannel(channel); };
  }, [user]);

  const resetJobHistory = async (targetPlatform?: "linkedin" | "naukri") => {
    setResetHistoryLoading(true);
    try {
      const { data: { session } } = await supabase.auth.getSession();
      if (!session) { alert("Not logged in"); return; }
      const url = `/api/job-history/reset${targetPlatform ? `?platform=${targetPlatform}` : ""}`;
      const res = await fetch(url, {
        method: "DELETE",
        headers: { Authorization: `Bearer ${session.access_token}` },
      });
      const json = await res.json();
      if (res.ok) {
        alert(json.message || "History reset successfully.");
      } else {
        alert("Reset failed: " + (json.error || res.statusText));
      }
    } catch (e) {
      alert("Reset failed: " + String(e));
    } finally {
      setResetHistoryLoading(false);
    }
  };

  const resetSmartMatchHistory = async () => {
    setResetSmartMatchLoading(true);
    try {
      const { data: { session } } = await supabase.auth.getSession();
      if (!session) { alert("Not logged in"); return; }
      const res = await fetch("/api/job-history/reset?type=smart_match", {
        method: "DELETE",
        headers: { Authorization: `Bearer ${session.access_token}` },
      });
      const json = await res.json();
      if (res.ok) {
        alert(json.message || "Smart Match history cleared — those jobs will be re-evaluated on next run.");
      } else {
        alert("Reset failed: " + (json.error || res.statusText));
      }
    } catch (e) {
      alert("Reset failed: " + String(e));
    } finally {
      setResetSmartMatchLoading(false);
    }
  };

  const createTask = async () => {
    const { data: userData } = await supabase.auth.getUser();
    const u = userData.user;
    if (!u) { alert("User not logged in"); return; }

    setTaskLoading(true);
    const taskType = applyMode === "tailor" ? "TAILOR_AND_APPLY" : "AUTO_APPLY";
    const { error } = await supabase.from("tasks").insert([{
      user_id: u.id,
      type: taskType,
      status: "PENDING",
      input: {
        platform,
        semi_auto: semiAuto,
        phone,
        phone_country: phoneCountry,
        years_experience: Number(yearsExp),
        skill_rating: Number(skillRating),
        keywords,
        ...(keywords2.trim() && { keywords2: keywords2.trim() }),
        ...(keywords3.trim() && { keywords3: keywords3.trim() }),
        location: [...(remoteEnabled ? ["Remote"] : []), ...locationList].join(",") || "",
        max_apply: Number(maxApply),
        notice_period: Number(noticePeriod),
        salary_expectation: salaryExpectation ? Number(salaryExpectation) : undefined,
        followup_days: Number(followupDays),
        ...(linkedinEmail && { linkedin_email: linkedinEmail }),
        ...(linkedinPassword && { linkedin_password: linkedinPassword }),
        ...(gmailAddress && { gmail_address: gmailAddress }),
        ...(gmailAppPassword && { gmail_app_password: gmailAppPassword }),
        ...(applyMode === "tailor" && {
          tailor_resume: true,
          tailor_custom_prompt: tailorPrompt,
        }),
        ...(favCompanies.length > 0 && { favorite_companies: favCompanies }),
        ...(platform === "naukri" && {
          apply_types: naukriApplyTypes,
          ...(naukriDatePosted !== "any" && { freshness_days: Number(naukriDatePosted) }),
          ...(naukriWorkMode !== "any" ? { work_mode: naukriWorkMode } : remoteEnabled ? { work_mode: "remote" } : {}),
          ...(naukriJobType !== "all" && { naukri_job_type: naukriJobType }),
        }),
        ...(platform === "linkedin" && {
          linkedin_date_posted: linkedinDatePosted,
          linkedin_remote: remoteEnabled,
          ...(linkedinExpLevel !== "all" && { linkedin_exp_level: linkedinExpLevel }),
          ...(linkedinJobType !== "all" && { linkedin_job_type: linkedinJobType }),
        }),
        ...(smartMatch && { smart_match: true, match_threshold: matchThreshold }),
        auto_cover_letter: autoCoverLetter,
        ...(scheduleEnabled && {
          schedule_start_hour: scheduleStartHour,
          schedule_end_hour:   scheduleEndHour,
        }),
      },
    }]);

    if (error) {
      console.error(error);
      alert("Error creating task: " + error.message);
    } else {
      fetchTasks();
    }
    setTaskLoading(false);
  };

  const saveGmailSettings = async () => {
    const { data: userData } = await supabase.auth.getUser();
    const u = userData.user;
    if (!u) { alert("Not logged in"); return; }
    if (!gmailAddress.trim()) { alert("Enter your Gmail address first."); return; }
    setGmailSaving(true);
    const { error } = await supabase.from("gmail_settings").upsert({
      user_id: u.id,
      gmail_address: gmailAddress.trim(),
      app_password: gmailAppPassword.trim(),
      followup_days: Number(followupDays),
    }, { onConflict: "user_id" });
    setGmailSaving(false);
    if (error) alert("Error saving: " + error.message);
    else alert("Gmail settings saved ✓");
  };

  const runTailorPreview = async () => {
    if (!resumeText.trim() || !jdText.trim()) {
      alert("Paste your resume text and job description to preview tailoring.");
      return;
    }
    setTailorLoading(true);
    setTailorResult(null);
    try {
      const res = await fetch("/api/ai/tailor-session", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          resume_text: resumeText,
          jd_text: jdText,
          custom_prompt: tailorPrompt,
          action: "tailor",
        }),
      });
      const data = await res.json();
      if (data.error) throw new Error(data.error);
      setTailorResult(data);
      setEditedResume(data.tailored_text);
    } catch (e) {
      alert("Tailoring failed: " + (e as Error).message);
    } finally {
      setTailorLoading(false);
    }
  };

  // ── Live run controls ──────────────────────────────────────
  const togglePause = async () => {
    if (!liveTask) return;
    await supabase.from("tasks").update({ paused: !liveTask.paused }).eq("id", liveTask.id);
  };

  const requestStop = async () => {
    if (!liveTask) return;
    if (!confirm("Stop the run after the current application?")) return;
    await supabase.from("tasks").update({ stop_requested: true }).eq("id", liveTask.id);
  };

  const sendLivePrompt = async () => {
    if (!liveTask || !livePrompt.trim()) return;
    setLivePromptSaving(true);
    await supabase
      .from("tasks")
      .update({ custom_prompt_override: livePrompt.trim() })
      .eq("id", liveTask.id);
    setLivePromptSaving(false);
    setLivePrompt("");
  };

  const lastSeen = user?.last_sign_in_at
    ? new Date(user.last_sign_in_at).toLocaleDateString("en-US", {
        month: "short", day: "numeric", year: "numeric",
      })
    : "—";

  const STAT_CARDS = [
    {
      label: "Resumes Uploaded",
      value: loadingData ? "…" : resumes.length.toString(),
      sub: "stored in Supabase",
      color: "text-amber-400",
    },
    {
      label: "Jobs Tracking",
      value: loadingData ? "…" : jobs.length.toString(),
      sub: "opportunities saved",
      color: jobs.length > 0 ? "text-emerald-400" : "text-slate-500",
    },
    {
      label: "Applications",
      value: loadingData ? "…" : appsCount.toString(),
      sub: "tracked applications",
      color: appsCount > 0 ? "text-sky-400" : "text-slate-500",
    },
  ];

  const QUICK_ACTIONS = [
    { href: "/job-search",    icon: "🔍", title: "Job Search",    desc: "Discover jobs & analyse JDs" },
    { href: "/resume-studio", icon: "✨", title: "Resume Studio", desc: "AI-tailor your resume to any JD" },
    { href: "/applications",  icon: "📋", title: "Applications",  desc: "Track status & follow-ups" },
    { href: "/analytics",     icon: "📊", title: "Analytics",     desc: "See your job search performance" },
    { href: "/upload-resume", icon: "📄", title: "Upload Resume",  desc: "Add or update your latest CV" },
    { href: "/job-preferences", icon: "🎯", title: "Preferences",  desc: "Set your title, salary & location" },
  ];

  return (
    <div className="max-w-6xl mx-auto px-6 py-12">
      {/* Header */}
      <div className="mb-12 animate-fadeUp">
        <p className="font-mono text-xs text-slate-500 tracking-widest uppercase mb-2">
          Overview
        </p>
        <h1 className="font-display font-bold text-4xl text-white leading-tight">
          Good to see you,{" "}
          <span className="gradient-text">
            {user?.email?.split("@")[0] ?? "there"}
          </span>
        </h1>
        <p className="text-slate-400 font-body mt-2">
          Here&apos;s a summary of your VantaHire profile.
        </p>
      </div>

      {/* Stat cards */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4 mb-12">
        {STAT_CARDS.map((card, i) => (
          <div
            key={card.label}
            className="card animate-fadeUp"
            style={{ animationDelay: `${i * 0.07}s` }}
          >
            <p className="font-mono text-xs text-slate-500 uppercase tracking-widest mb-3">
              {card.label}
            </p>
            <p className={`font-display font-bold text-3xl ${card.color} mb-1`}>
              {card.value}
            </p>
            <p className="font-body text-sm text-slate-500">{card.sub}</p>
          </div>
        ))}
      </div>

      {/* Plan & Usage */}
      {plan && (
        <div className="card mb-12 animate-fadeUp">
          <div className="flex items-center justify-between mb-4">
            <div>
              <p className="font-mono text-xs text-slate-500 uppercase tracking-widest mb-1">Current Plan</p>
              <p className="font-display font-bold text-xl text-white">{plan.name}
                {subscription?.status === "trial" && (
                  <span className="ml-2 text-xs font-mono text-amber-400 bg-amber-400/10 px-2 py-0.5 rounded-full">
                    Trial&nbsp;·&nbsp;{Math.max(0, Math.ceil((new Date(subscription.trial_ends_at ?? subscription.current_period_end ?? Date.now()).getTime() - Date.now()) / 86400000))}d left
                  </span>
                )}
              </p>
            </div>
            <Link href="/pricing" className="btn-primary text-sm px-4 py-2">
              {subscription?.plan_id === "trial" ? "Upgrade" : "Manage Plan"}
            </Link>
          </div>
          {usage.length > 0 && (
            <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-3">
              {usage.map((u) => {
                const rem = getRemaining(u.action_type);
                const pct = u.limit > 0 ? Math.min(100, (u.used / u.limit) * 100) : 0;
                const labels: Record<string, string> = {
                  auto_apply: "Auto Apply", semi_auto_apply: "Semi Auto",
                  ai_tailor: "AI Tailor", gmail_send: "Gmail", cover_letter: "Cover Letter", jd_analysis: "JD Analysis",
                };
                return (
                  <div key={u.action_type} className="bg-slate-800/50 rounded-lg p-3">
                    <p className="text-xs text-slate-400 mb-1">{labels[u.action_type] ?? u.action_type}</p>
                    <p className="font-mono text-sm text-white">{rem}/{u.limit}</p>
                    <div className="w-full bg-slate-700 rounded-full h-1.5 mt-1">
                      <div className={`h-1.5 rounded-full ${pct >= 90 ? "bg-red-500" : pct >= 60 ? "bg-amber-400" : "bg-emerald-500"}`} style={{ width: `${pct}%` }} />
                    </div>
                  </div>
                );
              })}
            </div>
          )}
        </div>
      )}

      {/* Auto Apply */}
      <div className="mb-12 animate-fadeUp animate-fadeUp-delay-3">
        <h2 className="font-display font-semibold text-lg text-white mb-4">
          Automation
        </h2>
        <div className="card space-y-4">
          {/* Mode sub-tabs */}
          <div className="flex gap-2 border-b border-slate-700 pb-3">
            {([["auto", "🚀 Auto Apply"], ["tailor", "✨ Tailor & Apply"]] as const).map(([mode, label]) => (
              <button
                key={mode}
                onClick={() => setApplyMode(mode)}
                className={`px-4 py-1.5 rounded-lg font-mono text-sm font-semibold transition-colors ${
                  applyMode === mode
                    ? "bg-amber-500 text-white"
                    : "bg-slate-800 text-slate-400 hover:text-white border border-slate-700"
                }`}
              >
                {label}
              </button>
            ))}
          </div>

          {applyMode === "tailor" && (
            <div className="space-y-3 p-3 rounded-lg border border-amber-400/20 bg-amber-400/5">
              <p className="font-mono text-xs text-amber-400 uppercase tracking-widest">
                AI tailors your resume to each JD before applying
              </p>
              <p className="font-body text-xs text-slate-400">
                When you start a run, the bot reads each job&apos;s description directly from LinkedIn and tailors your uploaded resume automatically — no pasting needed.
                Use the preview below to test the AI on any specific JD before launching.
              </p>
              {/* Preview section */}
              <div className="space-y-2">
                <div>
                  <label className="block font-mono text-xs text-slate-400 mb-1">
                    Resume Text
                    {resumeAutoLoaded
                      ? <span className="ml-2 text-emerald-400">✓ loaded from your saved resume</span>
                      : <span className="ml-2 text-slate-500">(paste if not auto-loaded)</span>}
                  </label>
                  <textarea
                    rows={4}
                    placeholder="Paste your resume text here to preview AI tailoring…"
                    value={resumeText}
                    onChange={(e) => setResumeText(e.target.value)}
                    className="w-full bg-slate-800 border border-slate-700 text-white text-sm rounded-lg px-3 py-2 focus:outline-none focus:border-amber-500 resize-y font-mono"
                  />
                </div>
                <div>
                  <label className="block font-mono text-xs text-slate-400 mb-1">
                    Paste a Job Description <span className="text-slate-500">(preview only — bot reads JDs from LinkedIn automatically)</span>
                  </label>
                  <textarea
                    rows={4}
                    placeholder="Paste the job description here…"
                    value={jdText}
                    onChange={(e) => setJdText(e.target.value)}
                    className="w-full bg-slate-800 border border-slate-700 text-white text-sm rounded-lg px-3 py-2 focus:outline-none focus:border-amber-500 resize-y font-mono"
                  />
                </div>
                <div>
                  <label className="block font-mono text-xs text-slate-400 mb-1">Custom Instruction (optional)</label>
                  <input
                    type="text"
                    placeholder='e.g. "Emphasise leadership and Python skills"'
                    value={tailorPrompt}
                    onChange={(e) => setTailorPrompt(e.target.value)}
                    className="w-full bg-slate-800 border border-slate-700 text-white text-sm rounded-lg px-3 py-2 focus:outline-none focus:border-amber-500"
                  />
                </div>
                <button
                  onClick={runTailorPreview}
                  disabled={tailorLoading}
                  className="bg-amber-500 hover:bg-amber-400 disabled:opacity-50 text-white font-bold px-4 py-2 rounded-lg text-sm transition-colors"
                >
                  {tailorLoading ? "Tailoring…" : "✨ Preview Tailored Resume"}
                </button>
              </div>

              {/* Result panel */}
              {tailorResult && (
                <div className="space-y-3 mt-2">
                  {/* Score ring row */}
                  <div className="flex gap-6 items-center">
                    {[["Before", tailorResult.score_before, "text-slate-400"], ["After", tailorResult.score_after, "text-emerald-400"], ["ATS", tailorResult.ats_score, "text-amber-400"]].map(([label, val, color]) => (
                      <div key={label as string} className="text-center">
                        <svg width="60" height="60" viewBox="0 0 60 60">
                          <circle cx="30" cy="30" r="24" fill="none" stroke="#1e293b" strokeWidth="6"/>
                          <circle cx="30" cy="30" r="24" fill="none" stroke="currentColor" strokeWidth="6"
                            strokeDasharray={`${(val as number) / 100 * 150.8} 150.8`}
                            strokeLinecap="round" transform="rotate(-90 30 30)"
                            className={color as string}
                          />
                        </svg>
                        <p className={`font-display font-bold text-lg -mt-12 mb-6 ${color}`}>{val}%</p>
                        <p className="font-mono text-xs text-slate-500">{label}</p>
                      </div>
                    ))}
                  </div>
                  {/* Edited resume textarea */}
                  <div>
                    <label className="block font-mono text-xs text-slate-400 mb-1">Tailored Resume (editable)</label>
                    <textarea
                      rows={10}
                      value={editedResume}
                      onChange={(e) => setEditedResume(e.target.value)}
                      className="w-full bg-slate-900 border border-slate-700 text-white text-xs rounded-lg px-3 py-2 focus:outline-none focus:border-amber-500 resize-y font-mono"
                    />
                  </div>
                  {/* Re-tailor */}
                  <button
                    onClick={runTailorPreview}
                    disabled={tailorLoading}
                    className="text-amber-400 border border-amber-400/30 hover:bg-amber-400/10 disabled:opacity-50 font-mono text-xs px-3 py-1.5 rounded-lg transition-colors"
                  >
                    {tailorLoading ? "Re-tailoring…" : "↻ Re-Tailor"}
                  </button>
                  {/* Improvements list */}
                  {tailorResult.improvements.length > 0 && (
                    <div>
                      <p className="font-mono text-xs text-slate-500 uppercase tracking-widest mb-1">Suggestions</p>
                      <ul className="space-y-1">
                        {tailorResult.improvements.map((tip, i) => (
                          <li key={i} className="font-body text-xs text-slate-400 flex gap-2">
                            <span className="text-amber-400">•</span>{tip}
                          </li>
                        ))}
                      </ul>
                    </div>
                  )}
                </div>
              )}
            </div>
          )}

          {/* Target Companies — visible in both Auto Apply and Tailor & Apply */}
          <div className="space-y-2 p-3 rounded-lg border border-slate-700 bg-slate-800/30">
            <label className="block font-mono text-xs text-slate-400 mb-1">
              🏢 Target Companies <span className="text-slate-500">(optional, max 5 — bot searches each company&apos;s jobs for your keywords)</span>
            </label>
            <div className="flex gap-2">
              <input
                type="text"
                placeholder="e.g. Google, Stripe, Notion…"
                value={favCompanyInput}
                onChange={(e) => setFavCompanyInput(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === "Enter") {
                    e.preventDefault();
                    const name = favCompanyInput.trim();
                    if (name && !favCompanies.includes(name) && favCompanies.length < 5) {
                      setFavCompanies([...favCompanies, name]);
                      setFavCompanyInput("");
                    }
                  }
                }}
                className="flex-1 bg-slate-800 border border-slate-700 text-white text-sm rounded-lg px-3 py-2 focus:outline-none focus:border-amber-500"
                disabled={favCompanies.length >= 5}
              />
              <button
                type="button"
                onClick={() => {
                  const name = favCompanyInput.trim();
                  if (name && !favCompanies.includes(name) && favCompanies.length < 5) {
                    setFavCompanies([...favCompanies, name]);
                    setFavCompanyInput("");
                  }
                }}
                disabled={favCompanies.length >= 5 || !favCompanyInput.trim()}
                className="bg-amber-600 hover:bg-amber-500 disabled:opacity-40 text-white text-sm font-bold px-3 py-2 rounded-lg transition-colors"
              >
                + Add
              </button>
            </div>
            {favCompanies.length > 0 && (
              <div className="flex flex-wrap gap-2 mt-1">
                {favCompanies.map((c) => (
                  <span key={c} className="flex items-center gap-1 bg-amber-500/20 border border-amber-400/40 text-amber-300 text-xs font-mono px-2 py-1 rounded-full">
                    🏢 {c}
                    <button
                      type="button"
                      onClick={() => setFavCompanies(favCompanies.filter((x) => x !== c))}
                      className="ml-1 text-amber-400 hover:text-red-400 font-bold leading-none"
                      aria-label={`Remove ${c}`}
                    >
                      ✕
                    </button>
                  </span>
                ))}
              </div>
            )}
          </div>

          {/* Platform tabs */}
          <div className="flex gap-2">
            {(["linkedin", "naukri"] as const).map((p) => (
              <button
                key={p}
                onClick={() => setPlatform(p)}
                className={`px-4 py-1.5 rounded-lg font-mono text-sm font-semibold transition-colors ${
                  platform === p
                    ? "bg-blue-500 text-white"
                    : "bg-slate-800 text-slate-400 hover:text-white border border-slate-700"
                }`}
              >
                {p === "linkedin" ? "🔵 LinkedIn" : "🟠 Naukri"}
              </button>
            ))}
          </div>

          {/* Platform login credentials (optional) */}
          <div className="space-y-2 p-3 rounded-lg border border-slate-700 bg-slate-800/30">
            <p className="font-mono text-xs text-slate-400 uppercase tracking-widest">
              {platform === "linkedin" ? "🔵 LinkedIn" : "🟠 Naukri"} Login
              <span className="ml-1 normal-case text-slate-600 font-normal">
                (optional — pre-fills the browser form)
              </span>
            </p>
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
              <div>
                <label className="block font-mono text-xs text-slate-500 mb-1">Email / Username</label>
                <input
                  type="email"
                  placeholder="your@email.com"
                  value={linkedinEmail}
                  onChange={(e) => setLinkedinEmail(e.target.value)}
                  className="w-full bg-slate-800 border border-slate-700 text-white text-sm rounded-lg px-3 py-2 focus:outline-none focus:border-blue-500"
                />
              </div>
              <div>
                <label className="block font-mono text-xs text-slate-500 mb-1">
                  Password
                  <span className="ml-1 text-slate-600">(leave blank → type in browser)</span>
                </label>
                <div className="flex gap-1">
                  <input
                    type={showLinkedinPwd ? "text" : "password"}
                    placeholder="••••••••"
                    value={linkedinPassword}
                    onChange={(e) => setLinkedinPassword(e.target.value)}
                    className="flex-1 bg-slate-800 border border-slate-700 text-white text-sm rounded-lg px-3 py-2 focus:outline-none focus:border-blue-500"
                  />
                  <button type="button" onClick={() => setShowLinkedinPwd(!showLinkedinPwd)}
                    className="px-2 text-slate-500 hover:text-white text-sm">{showLinkedinPwd ? "🙈" : "👁"}</button>
                </div>
              </div>
            </div>
          </div>

          {/* Naukri — Apply Type */}
          {platform === "naukri" && (
            <div className="space-y-2 p-3 rounded-lg border border-slate-700 bg-slate-800/30">
              <p className="font-mono text-xs text-slate-400 uppercase tracking-widest">
                🟠 Naukri — Apply Type
              </p>
              <div className="flex flex-wrap gap-2 mt-1">
                {(
                  [
                    { value: "both", label: "🔀 Both" },
                    { value: "direct_only", label: "⚡ Direct Apply Only" },
                    { value: "company_site_only", label: "🌐 Company Site Only" },
                  ] as const
                ).map(({ value, label }) => (
                  <button
                    key={value}
                    type="button"
                    onClick={() => setNaukriApplyTypes(value)}
                    className={`px-3 py-1.5 rounded-lg font-mono text-xs font-semibold transition-colors ${
                      naukriApplyTypes === value
                        ? "bg-orange-500 text-white"
                        : "bg-slate-800 text-slate-400 hover:text-white border border-slate-700"
                    }`}
                  >
                    {label}
                  </button>
                ))}
              </div>
              <p className="font-mono text-xs text-slate-600 mt-1">
                {naukriApplyTypes === "both"
                  ? "Apply using Naukri's Easy Apply AND company site forms."
                  : naukriApplyTypes === "direct_only"
                  ? "Only apply via Easy Apply (Naukri's built-in form). Skip jobs that redirect to company site."
                  : "Only apply on the company's own site. Skip Naukri Easy Apply jobs."}
              </p>
            </div>
          )}

          {/* Naukri — Search Filters */}
          {platform === "naukri" && (
            <div className="space-y-3 p-3 rounded-lg border border-slate-700 bg-slate-800/30">
              <p className="font-mono text-xs text-slate-400 uppercase tracking-widest">
                🟠 Naukri — Search Filters
              </p>

              {/* Date posted */}
              <div>
                <label className="block font-mono text-xs text-slate-500 mb-1">Date Posted</label>
                <div className="flex flex-wrap gap-2">
                  {([
                    { value: "any", label: "Any time" },
                    { value: "1",   label: "Today" },
                    { value: "3",   label: "Last 3 days" },
                    { value: "7",   label: "Last week" },
                    { value: "15",  label: "Last 2 weeks" },
                    { value: "30",  label: "Last month" },
                  ] as const).map(({ value, label }) => (
                    <button key={value} type="button" onClick={() => setNaukriDatePosted(value)}
                      className={`px-3 py-1 rounded-lg font-mono text-xs font-semibold transition-colors ${
                        naukriDatePosted === value ? "bg-orange-500 text-white" : "bg-slate-800 text-slate-400 hover:text-white border border-slate-700"
                      }`}>{label}</button>
                  ))}
                </div>
              </div>

              {/* Job type */}
              <div>
                <label className="block font-mono text-xs text-slate-500 mb-1">Job Type</label>
                <div className="flex flex-wrap gap-2">
                  {([
                    { value: "all",       label: "All" },
                    { value: "fullTime",  label: "Permanent" },
                    { value: "contract",  label: "Contract" },
                    { value: "temporary", label: "Temporary" },
                  ] as const).map(({ value, label }) => (
                    <button key={value} type="button" onClick={() => setNaukriJobType(value)}
                      className={`px-3 py-1 rounded-lg font-mono text-xs font-semibold transition-colors ${
                        naukriJobType === value ? "bg-orange-500 text-white" : "bg-slate-800 text-slate-400 hover:text-white border border-slate-700"
                      }`}>{label}</button>
                  ))}
                </div>
              </div>

              {/* Work mode */}
              <div>
                <label className="block font-mono text-xs text-slate-500 mb-1">Work Mode</label>
                <div className="flex flex-wrap gap-2">
                  {([
                    { value: "any",    label: "Any" },
                    { value: "remote", label: "🌐 Remote / WFH" },
                    { value: "hybrid", label: "🔀 Hybrid" },
                    { value: "office", label: "🏢 Office" },
                  ] as const).map(({ value, label }) => (
                    <button key={value} type="button" onClick={() => setNaukriWorkMode(value)}
                      className={`px-3 py-1 rounded-lg font-mono text-xs font-semibold transition-colors ${
                        naukriWorkMode === value ? "bg-orange-500 text-white" : "bg-slate-800 text-slate-400 hover:text-white border border-slate-700"
                      }`}>{label}</button>
                  ))}
                </div>
              </div>
            </div>
          )}

          {/* LinkedIn — Search Filters */}
          {platform === "linkedin" && (
            <div className="space-y-3 p-3 rounded-lg border border-slate-700 bg-slate-800/30">
              <p className="font-mono text-xs text-slate-400 uppercase tracking-widest">
                🔵 LinkedIn — Search Filters
              </p>

              {/* Date posted */}
              <div>
                <label className="block font-mono text-xs text-slate-500 mb-1">Date Posted</label>
                <div className="flex flex-wrap gap-2">
                  {(
                    [
                      { value: "any", label: "Any time" },
                      { value: "past24h", label: "Past 24h" },
                      { value: "pastWeek", label: "Past week" },
                      { value: "pastMonth", label: "Past month" },
                    ] as const
                  ).map(({ value, label }) => (
                    <button
                      key={value}
                      type="button"
                      onClick={() => setLinkedinDatePosted(value)}
                      className={`px-3 py-1 rounded-lg font-mono text-xs font-semibold transition-colors ${
                        linkedinDatePosted === value
                          ? "bg-blue-500 text-white"
                          : "bg-slate-800 text-slate-400 hover:text-white border border-slate-700"
                      }`}
                    >
                      {label}
                    </button>
                  ))}
                </div>
              </div>

              {/* Job type */}
              <div>
                <label className="block font-mono text-xs text-slate-500 mb-1">Job Type</label>
                <div className="flex flex-wrap gap-2">
                  {(
                    [
                      { value: "all", label: "All" },
                      { value: "fullTime", label: "Full-time" },
                      { value: "partTime", label: "Part-time" },
                      { value: "contract", label: "Contract" },
                      { value: "internship", label: "Internship" },
                    ] as const
                  ).map(({ value, label }) => (
                    <button
                      key={value}
                      type="button"
                      onClick={() => setLinkedinJobType(value)}
                      className={`px-3 py-1 rounded-lg font-mono text-xs font-semibold transition-colors ${
                        linkedinJobType === value
                          ? "bg-blue-500 text-white"
                          : "bg-slate-800 text-slate-400 hover:text-white border border-slate-700"
                      }`}
                    >
                      {label}
                    </button>
                  ))}
                </div>
              </div>

              {/* Experience level */}
              <div>
                <label className="block font-mono text-xs text-slate-500 mb-1">Experience Level</label>
                <div className="flex flex-wrap gap-2">
                  {(
                    [
                      { value: "all", label: "All" },
                      { value: "internship", label: "Internship" },
                      { value: "entry", label: "Entry" },
                      { value: "associate", label: "Associate" },
                      { value: "mid", label: "Mid-Senior" },
                      { value: "director", label: "Director" },
                    ] as const
                  ).map(({ value, label }) => (
                    <button
                      key={value}
                      type="button"
                      onClick={() => setLinkedinExpLevel(value)}
                      className={`px-3 py-1 rounded-lg font-mono text-xs font-semibold transition-colors ${
                        linkedinExpLevel === value
                          ? "bg-blue-500 text-white"
                          : "bg-slate-800 text-slate-400 hover:text-white border border-slate-700"
                      }`}
                    >
                      {label}
                    </button>
                  ))}
                </div>
              </div>

              {/* Remote toggle — synced with the Location widget above */}
              <div className="flex items-center gap-3">
                <input
                  id="linkedin-remote-toggle"
                  type="checkbox"
                  checked={remoteEnabled}
                  onChange={(e) => setRemoteEnabled(e.target.checked)}
                  className="accent-blue-500 w-4 h-4 cursor-pointer"
                />
                <label htmlFor="linkedin-remote-toggle" className="cursor-pointer font-mono text-xs text-slate-300">
                  Remote jobs only <span className="text-slate-600">(also updates the 📍 Location widget)</span>
                </label>
              </div>
            </div>
          )}

          {/* Smart Match — AI resume vs JD scoring gate */}
          <div className="space-y-3 p-3 rounded-lg border border-slate-700 bg-slate-800/30">
            <div className="flex items-start gap-3">
              <input
                id="smart-match-toggle"
                type="checkbox"
                checked={smartMatch}
                onChange={(e) => setSmartMatch(e.target.checked)}
                className="mt-0.5 accent-violet-400 w-4 h-4 cursor-pointer"
              />
              <label htmlFor="smart-match-toggle" className="cursor-pointer">
                <p className="font-body font-semibold text-white text-sm">
                  🧠 Smart Match{" "}
                  {smartMatch && (
                    <span className="ml-1 text-xs bg-violet-400/15 text-violet-400 px-2 py-0.5 rounded">ON</span>
                  )}
                </p>
                <p className="font-body text-xs text-slate-400 mt-0.5">
                  Claude AI reads your resume and the job description before every application. Jobs scoring below the
                  threshold are skipped automatically — saving quota and improving your hit rate.
                </p>
              </label>
            </div>

            {smartMatch && (
              <div className="pl-7 space-y-2">
                <div className="flex items-center justify-between">
                  <label className="font-mono text-xs text-slate-400">
                    Min match score to apply
                  </label>
                  <span className="font-mono text-sm font-bold text-violet-400">{matchThreshold}%</span>
                </div>
                <input
                  type="range"
                  min={30}
                  max={95}
                  step={5}
                  value={matchThreshold}
                  onChange={(e) => setMatchThreshold(Number(e.target.value))}
                  className="w-full accent-violet-500"
                />
                <div className="flex justify-between font-mono text-xs text-slate-600">
                  <span>30% — Apply to almost all</span>
                  <span>95% — Very selective</span>
                </div>
              </div>
            )}
          </div>

          {/* Auto Cover Letter */}
          <div className="flex items-start gap-3 p-3 rounded-lg border border-slate-700 bg-slate-800/50">
            <input
              id="auto-cover-letter-toggle"
              type="checkbox"
              checked={autoCoverLetter}
              onChange={(e) => setAutoCoverLetter(e.target.checked)}
              className="mt-0.5 accent-violet-500 w-4 h-4 cursor-pointer"
            />
            <label htmlFor="auto-cover-letter-toggle" className="cursor-pointer">
              <p className="font-body font-semibold text-white text-sm">
                Auto Cover Letter {autoCoverLetter && <span className="ml-1 text-xs bg-violet-500/15 text-violet-400 px-2 py-0.5 rounded">ON</span>}
              </p>
              <p className="font-body text-xs text-slate-400 mt-0.5">
                Claude AI writes a personalised cover letter / intro message for every application using your resume and the job description.
                Disable to skip AI generation and send a plain default note.
              </p>
            </label>
          </div>

          {/* Smart Apply Scheduler */}
          <div className="p-3 rounded-lg border border-slate-700 bg-slate-800/50 space-y-3">
            <div className="flex items-start gap-3">
              <input
                id="schedule-toggle"
                type="checkbox"
                checked={scheduleEnabled}
                onChange={(e) => setScheduleEnabled(e.target.checked)}
                className="mt-0.5 accent-cyan-400 w-4 h-4 cursor-pointer"
              />
              <label htmlFor="schedule-toggle" className="cursor-pointer">
                <p className="font-body font-semibold text-white text-sm">
                  Smart Apply Scheduler {scheduleEnabled && <span className="ml-1 text-xs bg-cyan-400/15 text-cyan-400 px-2 py-0.5 rounded">ON</span>}
                </p>
                <p className="font-body text-xs text-slate-400 mt-0.5">
                  Restrict the bot to apply only within a specific time window. Applications sent during business hours look more human.
                </p>
              </label>
            </div>
            {scheduleEnabled && (
              <div className="pl-7 flex gap-4 items-center">
                <div className="flex flex-col gap-1">
                  <label className="font-mono text-xs text-slate-400">Start hour (24h)</label>
                  <select
                    value={scheduleStartHour}
                    onChange={(e) => setScheduleStartHour(Number(e.target.value))}
                    className="bg-slate-700 border border-slate-600 text-white font-mono text-sm rounded px-2 py-1"
                  >
                    {Array.from({ length: 24 }, (_, i) => (
                      <option key={i} value={i}>{String(i).padStart(2, "0")}:00</option>
                    ))}
                  </select>
                </div>
                <span className="font-mono text-slate-400 mt-4">→</span>
                <div className="flex flex-col gap-1">
                  <label className="font-mono text-xs text-slate-400">End hour (24h)</label>
                  <select
                    value={scheduleEndHour}
                    onChange={(e) => setScheduleEndHour(Number(e.target.value))}
                    className="bg-slate-700 border border-slate-600 text-white font-mono text-sm rounded px-2 py-1"
                  >
                    {Array.from({ length: 24 }, (_, i) => (
                      <option key={i} value={i}>{String(i).padStart(2, "0")}:00</option>
                    ))}
                  </select>
                </div>
                <p className="font-mono text-xs text-slate-500 mt-4 ml-2">
                  {scheduleStartHour <= scheduleEndHour
                    ? `Applies ${String(scheduleStartHour).padStart(2,"0")}:00–${String(scheduleEndHour).padStart(2,"0")}:00`
                    : `Overnight: ${String(scheduleStartHour).padStart(2,"0")}:00–${String(scheduleEndHour).padStart(2,"0")}:00`}
                </p>
              </div>
            )}
          </div>

          {/* Mode toggle */}
          <div className="flex items-start gap-3 p-3 rounded-lg border border-slate-700 bg-slate-800/50">
            <input
              id="semi-auto-toggle"
              type="checkbox"
              checked={semiAuto}
              onChange={(e) => setSemiAuto(e.target.checked)}
              className="mt-0.5 accent-amber-400 w-4 h-4 cursor-pointer"
            />
            <label htmlFor="semi-auto-toggle" className="cursor-pointer">
              <p className="font-body font-semibold text-white text-sm">
                Semi-Auto Mode {semiAuto && <span className="ml-1 text-xs bg-amber-400/15 text-amber-400 px-2 py-0.5 rounded">ON</span>}
              </p>
              <p className="font-body text-xs text-slate-400 mt-0.5">
                {semiAuto
                  ? "Bot fills all fields and clicks Next automatically. It stops at the final Submit — you review and click it yourself."
                  : "Bot fills all fields, clicks Next, and submits every application automatically."}
              </p>
            </label>
          </div>

          {/* Job History Reset */}
          <div className="space-y-2 p-3 rounded-lg border border-slate-700 bg-slate-800/30">
            <p className="font-mono text-xs text-slate-400 uppercase tracking-widest">
              🗂️ Job History
            </p>
            <p className="font-body text-xs text-slate-500">
              The bot tracks every job URL it has already applied to or skipped (last 30 days) and skips them automatically on future runs.
              Reset to let the bot re-try those jobs.
            </p>
            <div className="flex flex-wrap gap-2 mt-1">
              <button
                type="button"
                disabled={resetHistoryLoading}
                onClick={() => resetJobHistory(platform)}
                className="disabled:opacity-50 px-3 py-1.5 rounded-lg font-mono text-xs font-semibold bg-rose-600/20 text-rose-400 border border-rose-600/40 hover:bg-rose-600/30 transition-colors"
              >
                {resetHistoryLoading ? "Resetting…" : `🔄 Reset ${platform === "naukri" ? "Naukri" : "LinkedIn"} History`}
              </button>
              <button
                type="button"
                disabled={resetHistoryLoading}
                onClick={() => resetJobHistory()}
                className="disabled:opacity-50 px-3 py-1.5 rounded-lg font-mono text-xs font-semibold bg-rose-600/10 text-rose-500 border border-rose-700/40 hover:bg-rose-600/20 transition-colors"
              >
                {resetHistoryLoading ? "Resetting…" : "🔄 Reset All Platforms"}
              </button>
              <button
                type="button"
                disabled={resetSmartMatchLoading}
                onClick={resetSmartMatchHistory}
                className="disabled:opacity-50 px-3 py-1.5 rounded-lg font-mono text-xs font-semibold bg-violet-600/20 text-violet-400 border border-violet-600/40 hover:bg-violet-600/30 transition-colors"
              >
                {resetSmartMatchLoading ? "Clearing…" : "🧠 Clear Smart Match Skips"}
              </button>
            </div>
            <p className="font-body text-xs text-slate-600">
              🧠 Smart Match Skips are tied to your current resume — uploading a new resume clears them automatically.
              Use the button above to force a re-evaluation without changing your resume.
            </p>
          </div>
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
            <div>
              <label className="block font-mono text-xs text-slate-400 mb-1">Keyword 1 <span className="text-red-400">*</span></label>
              <input
                type="text"
                placeholder="e.g. Software Engineer"
                value={keywords}
                onChange={(e) => setKeywords(e.target.value)}
                className="w-full bg-slate-800 border border-slate-700 text-white text-sm rounded-lg px-3 py-2 focus:outline-none focus:border-blue-500"
              />
            </div>
            <div>
              <label className="block font-mono text-xs text-slate-400 mb-1">Keyword 2 <span className="text-slate-500">(optional — runs after Keyword 1)</span></label>
              <input
                type="text"
                placeholder="e.g. Backend Developer"
                value={keywords2}
                onChange={(e) => setKeywords2(e.target.value)}
                className="w-full bg-slate-800 border border-slate-700 text-white text-sm rounded-lg px-3 py-2 focus:outline-none focus:border-blue-500"
              />
            </div>
            <div>
              <label className="block font-mono text-xs text-slate-400 mb-1">Keyword 3 <span className="text-slate-500">(optional — runs after Keyword 2)</span></label>
              <input
                type="text"
                placeholder="e.g. Full Stack Engineer"
                value={keywords3}
                onChange={(e) => setKeywords3(e.target.value)}
                className="w-full bg-slate-800 border border-slate-700 text-white text-sm rounded-lg px-3 py-2 focus:outline-none focus:border-blue-500"
              />
            </div>
            {/* Location widget — full width ─────────────────── */}
            <div className="sm:col-span-2 space-y-2">
              <label className="block font-mono text-xs text-slate-400">📍 Location <span className="text-slate-500 font-normal">(optional — up to 5, bot searches each)</span></label>
              {/* Remote checkbox */}
              <div className="flex items-center gap-2">
                <input
                  id="remote-loc-toggle"
                  type="checkbox"
                  checked={remoteEnabled}
                  onChange={(e) => setRemoteEnabled(e.target.checked)}
                  className="accent-emerald-400 w-4 h-4 cursor-pointer"
                />
                <label htmlFor="remote-loc-toggle" className="cursor-pointer font-mono text-sm text-slate-300">
                  🌐 Remote
                </label>
              </div>
              {/* Tag input */}
              <div className="flex gap-2">
                <input
                  type="text"
                  placeholder={locationList.length >= 5 ? "Max 5 locations" : "e.g. Bangalore (press Enter to add)"}
                  value={locationInput}
                  onChange={(e) => setLocationInput(e.target.value)}
                  onKeyDown={(e) => {
                    if (e.key === "Enter") {
                      e.preventDefault();
                      const loc = locationInput.trim();
                      if (loc && !locationList.includes(loc) && locationList.length < 5) {
                        setLocationList([...locationList, loc]);
                        setLocationInput("");
                      }
                    }
                  }}
                  disabled={locationList.length >= 5}
                  className="flex-1 bg-slate-800 border border-slate-700 text-white text-sm rounded-lg px-3 py-2 focus:outline-none focus:border-blue-500 disabled:opacity-50"
                />
                <button
                  type="button"
                  onClick={() => {
                    const loc = locationInput.trim();
                    if (loc && !locationList.includes(loc) && locationList.length < 5) {
                      setLocationList([...locationList, loc]);
                      setLocationInput("");
                    }
                  }}
                  disabled={locationList.length >= 5 || !locationInput.trim()}
                  className="bg-slate-700 hover:bg-slate-600 disabled:opacity-40 text-white text-sm font-bold px-3 py-2 rounded-lg transition-colors"
                >
                  + Add
                </button>
              </div>
              {locationList.length > 0 && (
                <div className="flex flex-wrap gap-2">
                  {locationList.map((loc) => (
                    <span key={loc} className="flex items-center gap-1 bg-blue-500/20 border border-blue-400/40 text-blue-300 text-xs font-mono px-2 py-1 rounded-full">
                      📍 {loc}
                      <button
                        type="button"
                        onClick={() => setLocationList(locationList.filter((l) => l !== loc))}
                        className="ml-1 text-blue-400 hover:text-red-400 font-bold leading-none"
                      >✕</button>
                    </span>
                  ))}
                </div>
              )}
              {!remoteEnabled && locationList.length === 0 && (
                <p className="font-mono text-xs text-slate-600">No location set — bot will search everywhere</p>
              )}
            </div>
            <div>
              <label className="block font-mono text-xs text-slate-400 mb-1">Phone Country</label>
              <select
                value={phoneCountry}
                onChange={(e) => setPhoneCountry(e.target.value)}
                className="w-full bg-slate-800 border border-slate-700 text-white text-sm rounded-lg px-3 py-2 focus:outline-none focus:border-blue-500"
              >
                <option value="India (+91)">India (+91)</option>
                <option value="United States (+1)">United States (+1)</option>
                <option value="United Kingdom (+44)">United Kingdom (+44)</option>
                <option value="Canada (+1)">Canada (+1)</option>
                <option value="Australia (+61)">Australia (+61)</option>
                <option value="Germany (+49)">Germany (+49)</option>
                <option value="Singapore (+65)">Singapore (+65)</option>
              </select>
            </div>
            <div>
              <label className="block font-mono text-xs text-slate-400 mb-1">Phone Number <span className="text-red-400">*</span></label>
              <input
                type="tel"
                placeholder="e.g. 9876543210"
                value={phone}
                onChange={(e) => setPhone(e.target.value)}
                className="w-full bg-slate-800 border border-slate-700 text-white text-sm rounded-lg px-3 py-2 focus:outline-none focus:border-blue-500"
              />
            </div>
            <div>
              <label className="block font-mono text-xs text-slate-400 mb-1">Years of Experience</label>
              <input
                type="number" min="0" max="30" placeholder="e.g. 2"
                value={yearsExp}
                onChange={(e) => setYearsExp(e.target.value)}
                className="w-full bg-slate-800 border border-slate-700 text-white text-sm rounded-lg px-3 py-2 focus:outline-none focus:border-blue-500"
              />
            </div>
            <div>
              <label className="block font-mono text-xs text-slate-400 mb-1">Skill Rating (0–10)</label>
              <input
                type="number" min="0" max="10" placeholder="e.g. 8"
                value={skillRating}
                onChange={(e) => setSkillRating(e.target.value)}
                className="w-full bg-slate-800 border border-slate-700 text-white text-sm rounded-lg px-3 py-2 focus:outline-none focus:border-blue-500"
              />
            </div>
            <div>
              <label className="block font-mono text-xs text-slate-400 mb-1">
                Max Applications
                <span className="ml-1 text-slate-500 font-normal">(max 100 per run — run again to continue)</span>
              </label>
              <input
                type="number" min="1" max="100" placeholder="e.g. 5"
                value={maxApply}
                onChange={(e) => setMaxApply(e.target.value)}
                className="w-full bg-slate-800 border border-slate-700 text-white text-sm rounded-lg px-3 py-2 focus:outline-none focus:border-blue-500"
              />
            </div>
            <div>
              <label className="block font-mono text-xs text-slate-400 mb-1">Notice Period (days)</label>
              <input
                type="number" min="0" placeholder="e.g. 30"
                value={noticePeriod}
                onChange={(e) => setNoticePeriod(e.target.value)}
                className="w-full bg-slate-800 border border-slate-700 text-white text-sm rounded-lg px-3 py-2 focus:outline-none focus:border-blue-500"
              />
            </div>
            <div>
              <label className="block font-mono text-xs text-slate-400 mb-1">Expected Salary (optional)</label>
              <input
                type="number" min="0" placeholder="e.g. 800000"
                value={salaryExpectation}
                onChange={(e) => setSalaryExpectation(e.target.value)}
                className="w-full bg-slate-800 border border-slate-700 text-white text-sm rounded-lg px-3 py-2 focus:outline-none focus:border-blue-500"
              />
            </div>
          </div>
          <div className="flex justify-end">
            <button
              onClick={() => {
                if (!phone.trim()) { alert("Please enter your phone number first."); return; }
                createTask();
              }}
              disabled={taskLoading}
              className={`disabled:opacity-50 text-white font-bold px-5 py-2.5 rounded-lg transition-colors ${
                applyMode === "tailor"
                  ? "bg-amber-500 hover:bg-amber-400"
                  : semiAuto
                  ? "bg-amber-500 hover:bg-amber-400"
                  : "bg-blue-500 hover:bg-blue-400"
              }`}
            >
              {taskLoading
                ? "Creating…"
                : applyMode === "tailor"
                ? "✨ Start Tailor & Apply"
                : semiAuto
                ? "🤝 Start Semi-Auto Apply"
                : "🚀 Start Auto Apply"}
            </button>
          </div>
        </div>
      </div>
      {/* ── Gmail & Email Follow-Up Settings ─────────────────────── */}
      <div className="mb-12 animate-fadeUp animate-fadeUp-delay-3">
        <h2 className="font-display font-semibold text-lg text-white mb-4">
          📧 Email Follow-Up
        </h2>
        <div className="card space-y-4">
          <p className="font-body text-xs text-slate-400">
            The bot checks your Gmail daily for job-related replies (acknowledgment, interview, rejection) and sends AI-drafted follow-up emails. Uses Gmail App Password — no OAuth needed.
          </p>
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
            <div>
              <label className="block font-mono text-xs text-slate-400 mb-1">Gmail Address</label>
              <input
                type="email"
                placeholder="you@gmail.com"
                value={gmailAddress}
                onChange={(e) => setGmailAddress(e.target.value)}
                className="w-full bg-slate-800 border border-slate-700 text-white text-sm rounded-lg px-3 py-2 focus:outline-none focus:border-blue-500"
              />
            </div>
            <div>
              <label className="block font-mono text-xs text-slate-400 mb-1">
                App Password
                <a href="https://myaccount.google.com/apppasswords" target="_blank" rel="noopener noreferrer"
                  className="ml-2 text-blue-400 hover:underline text-xs">(get one here ↗)</a>
              </label>
              <div className="flex gap-1">
                <input
                  type={showGmailPwd ? "text" : "password"}
                  placeholder="xxxx xxxx xxxx xxxx"
                  value={gmailAppPassword}
                  onChange={(e) => setGmailAppPassword(e.target.value)}
                  className="flex-1 bg-slate-800 border border-slate-700 text-white text-sm rounded-lg px-3 py-2 focus:outline-none focus:border-blue-500"
                />
                <button type="button" onClick={() => setShowGmailPwd(!showGmailPwd)}
                  className="px-2 text-slate-500 hover:text-white text-sm">{showGmailPwd ? "🙈" : "👁"}</button>
              </div>
            </div>
            <div>
              <label className="block font-mono text-xs text-slate-400 mb-1">Follow-Up After (days)</label>
              <input
                type="number" min="1" max="30" placeholder="e.g. 3"
                value={followupDays}
                onChange={(e) => setFollowupDays(e.target.value)}
                className="w-full bg-slate-800 border border-slate-700 text-white text-sm rounded-lg px-3 py-2 focus:outline-none focus:border-blue-500"
              />
              <p className="font-body text-xs text-slate-500 mt-1">Bot will send a follow-up email if no reply after this many days.</p>
            </div>
          </div>
          <div className="flex justify-end">
            <button
              onClick={saveGmailSettings}
              disabled={gmailSaving}
              className="bg-blue-600 hover:bg-blue-500 disabled:opacity-50 text-white font-bold px-4 py-2 rounded-lg text-sm transition-colors"
            >
              {gmailSaving ? "Saving…" : "💾 Save Email Settings"}
            </button>
          </div>
        </div>
      </div>
      {/* ── Live Run Monitor ─────────────────────────────────── */}
      {liveTask && (
        <div className="mb-12 animate-fadeUp animate-fadeUp-delay-3">
          <div className="flex items-center gap-3 mb-4">
            {liveTask.status === "RUNNING" && (
              <span className="w-2.5 h-2.5 rounded-full bg-blue-400 animate-ping inline-block" />
            )}
            <h2 className="font-display font-semibold text-lg text-white">
              {liveTask.status === "RUNNING" ? "Run in Progress" : liveTask.status === "DONE" ? "Run Complete ✅" : "Run Failed ❌"}
            </h2>
            {liveTask.status === "RUNNING" && (
              <span className="ml-auto flex gap-2">
                <button
                  onClick={togglePause}
                  className={`font-mono text-xs px-3 py-1.5 rounded-lg border transition-colors ${
                    liveTask.paused
                      ? "border-emerald-400 text-emerald-400 hover:bg-emerald-400/10"
                      : "border-amber-400 text-amber-400 hover:bg-amber-400/10"
                  }`}
                >
                  {liveTask.paused ? "▶ Resume" : "⏸ Pause"}
                </button>
                <button
                  onClick={requestStop}
                  className="font-mono text-xs px-3 py-1.5 rounded-lg border border-red-400 text-red-400 hover:bg-red-400/10 transition-colors"
                >
                  ⏹ Stop
                </button>
              </span>
            )}
          </div>

          <div className="card space-y-4">
            {/* Progress bar */}
            <div>
              <div className="flex justify-between mb-1">
                <span className="font-mono text-xs text-slate-400">
                  {liveTask.current_job
                    ? `Working on: ${liveTask.current_job.replace(/.*linkedin\.com\/jobs\/view\//, "job #")}`
                    : "Initialising…"}
                </span>
                <span className="font-mono text-xs text-slate-400">{liveTask.progress ?? 0}%</span>
              </div>
              <div className="w-full bg-slate-800 rounded-full h-2">
                <div
                  className="h-2 rounded-full bg-gradient-to-r from-blue-500 to-amber-400 transition-all duration-500"
                  style={{ width: `${liveTask.progress ?? 0}%` }}
                />
              </div>
            </div>

            {/* Live prompt injection */}
            {liveTask.status === "RUNNING" && (
              <div className="p-3 rounded-lg border border-amber-400/20 bg-amber-400/5 space-y-2">
                <p className="font-mono text-xs text-amber-400 uppercase tracking-widest">
                  Inject custom instruction for next application
                </p>
                <p className="font-body text-xs text-slate-400">
                  Typed here, picked up by the bot before it starts the next job — no restart needed.
                </p>
                <div className="flex gap-2">
                  <input
                    type="text"
                    placeholder='e.g. "Emphasise leadership and team management"'
                    value={livePrompt}
                    onChange={(e) => setLivePrompt(e.target.value)}
                    onKeyDown={(e) => { if (e.key === "Enter") sendLivePrompt(); }}
                    className="flex-1 bg-slate-800 border border-slate-700 text-white text-sm rounded-lg px-3 py-2 focus:outline-none focus:border-amber-500"
                  />
                  <button
                    onClick={sendLivePrompt}
                    disabled={livePromptSaving || !livePrompt.trim()}
                    className="bg-amber-500 hover:bg-amber-400 disabled:opacity-50 text-white font-bold px-4 py-2 rounded-lg text-sm transition-colors"
                  >
                    {livePromptSaving ? "Saving…" : "Send"}
                  </button>
                </div>
                {liveTask.custom_prompt_override && (
                  <p className="font-mono text-xs text-emerald-400">
                    ✓ Active instruction: &quot;{liveTask.custom_prompt_override}&quot;
                  </p>
                )}
              </div>
            )}

            {/* Log stream */}
            <div>
              <p className="font-mono text-xs text-slate-500 uppercase tracking-widest mb-2">Live Log</p>
              <div className="bg-slate-950 rounded-lg border border-slate-800 p-3 h-56 overflow-y-auto font-mono text-xs space-y-0.5 flex flex-col-reverse">
                {(liveTask.logs ?? []).length === 0 ? (
                  <p className="text-slate-600">Waiting for bot to start…</p>
                ) : (
                  [...(liveTask.logs ?? [])].reverse().map((entry, i) => (
                    <div key={i} className="flex gap-2 leading-5">
                      <span className="text-slate-600 shrink-0">{entry.ts}</span>
                      <span className={
                        entry.level === "success" ? "text-emerald-400" :
                        entry.level === "error"   ? "text-red-400" :
                        entry.level === "warn"    ? "text-amber-400" :
                        "text-slate-400"
                      }>
                        {entry.level === "success" ? "✅" : entry.level === "error" ? "❌" : entry.level === "warn" ? "⚠" : "·"}
                      </span>
                      <span className={
                        entry.level === "success" ? "text-emerald-300" :
                        entry.level === "error"   ? "text-red-300" :
                        entry.level === "warn"    ? "text-amber-300" :
                        "text-slate-300"
                      }>{entry.msg}</span>
                    </div>
                  ))
                )}
              </div>
            </div>

            {/* Final result */}
            {liveTask.status === "DONE" && liveTask.output && (
              <div className="flex items-center gap-3 p-3 rounded-lg bg-emerald-400/10 border border-emerald-400/20">
                <span className="text-2xl">🎉</span>
                <div>
                  <p className="font-body font-semibold text-emerald-400">
                    Applied to {liveTask.output.applied_count ?? 0} jobs
                  </p>
                  <p className="font-body text-xs text-slate-400 mt-0.5">{liveTask.output.message}</p>
                </div>
              </div>
            )}
          </div>
        </div>
      )}

      {/* Tasks */}
      <div className="mb-12 animate-fadeUp animate-fadeUp-delay-3">
        <h2 className="font-display font-semibold text-lg text-white mb-4">
          Tasks ({tasks.length})
        </h2>
        {tasks.length === 0 ? (
          <div className="card border-dashed text-center py-6">
            <p className="text-slate-500 font-body text-sm">No tasks yet. Click "Start Auto Apply" above.</p>
          </div>
        ) : (
          <div className="space-y-2">
            {tasks.map((t) => (
              <div
                key={t.id}
                onClick={() => (t.status === "RUNNING" || t.status === "DONE") && setLiveTask(t)}
                className={`card py-3 flex items-center justify-between ${
                  t.status === "RUNNING" || t.status === "DONE" ? "cursor-pointer hover:border-blue-400/30" : ""
                }`}
              >
                <div className="flex items-center gap-3">
                  <span className="text-lg">
                    {t.status === "PENDING" ? "🟡" : t.status === "RUNNING" ? "🔵" : t.status === "DONE" ? "🟢" : "🔴"}
                  </span>
                  <div>
                    <span className="font-mono text-sm text-white">{t.type}</span>
                    {t.status === "RUNNING" && (
                      <p className="font-mono text-xs text-blue-400 mt-0.5 animate-pulse">
                        Running… {t.progress ?? 0}% — click to view live log
                      </p>
                    )}
                    {t.status === "DONE" && t.output?.applied_count !== undefined && (
                      <p className="font-mono text-xs text-emerald-400 mt-0.5">
                        ✅ {t.output.applied_count} applied — click to view log
                      </p>
                    )}
                  </div>
                </div>
                <div className="flex items-center gap-4">
                  <span className={`font-mono text-xs px-2 py-0.5 rounded ${
                    t.status === "PENDING" ? "bg-yellow-400/15 text-yellow-400" :
                    t.status === "RUNNING" ? "bg-blue-400/15 text-blue-400" :
                    t.status === "DONE" ? "bg-emerald-400/15 text-emerald-400" :
                    "bg-red-400/15 text-red-400"
                  }`}>{t.status}</span>
                  <span className="font-mono text-xs text-slate-500">
                    {new Date(t.created_at).toLocaleString()}
                  </span>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Quick actions */}
      <div className="mb-12 animate-fadeUp animate-fadeUp-delay-3">
        <h2 className="font-display font-semibold text-lg text-white mb-4">
          Quick Actions
        </h2>
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
          {QUICK_ACTIONS.map(({ href, icon, title, desc }) => (
            <Link
              key={href}
              href={href}
              className="card group flex items-start gap-4 hover:border-amber-400/30 hover:bg-slate-900 transition-all duration-200"
            >
              <span className="text-2xl mt-0.5">{icon}</span>
              <div>
                <p className="font-body font-semibold text-white group-hover:text-amber-400 transition-colors">
                  {title}
                </p>
                <p className="font-body text-sm text-slate-400 mt-0.5">{desc}</p>
              </div>
              <span className="ml-auto text-slate-600 group-hover:text-amber-400 transition-colors text-lg">
                →
              </span>
            </Link>
          ))}
        </div>
      </div>

      {/* Recent resumes */}
      <div className="animate-fadeUp animate-fadeUp-delay-4">
        <div className="flex items-center justify-between mb-4">
          <h2 className="font-display font-semibold text-lg text-white">
            Recent Resumes
          </h2>
          <Link
            href="/upload-resume"
            className="font-body text-sm text-amber-400 hover:text-amber-300 transition-colors"
          >
            + Add new
          </Link>
        </div>

        {loadingData ? (
          <div className="card flex items-center gap-3 text-slate-500">
            <div className="w-4 h-4 border border-slate-600 border-t-amber-400 rounded-full animate-spin" />
            <span className="font-body text-sm">Loading resumes…</span>
          </div>
        ) : resumes.length === 0 ? (
          <div className="card border-dashed text-center py-10">
            <p className="text-slate-500 font-body text-sm">
              No resumes yet.{" "}
              <Link href="/upload-resume" className="text-amber-400 hover:underline">
                Upload your first one →
              </Link>
            </p>
          </div>
        ) : (
          <div className="space-y-2">
            {resumes.map((r) => (
              <div
                key={r.id}
                className="card py-3 flex items-center justify-between"
              >
                <div className="flex items-center gap-3">
                  <span className="text-amber-400 text-lg">📄</span>
                  <span className="font-body text-sm text-white">{r.title}</span>
                </div>
                <span className="font-mono text-xs text-slate-500">
                  {new Date(r.created_at).toLocaleDateString()}
                </span>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Session debug */}
      <details className="mt-16 group">
        <summary className="font-mono text-xs text-slate-700 cursor-pointer hover:text-slate-500 transition-colors select-none">
          ▶ Debug: current session
        </summary>
        <pre className="mt-3 p-4 rounded-lg bg-slate-900 border border-slate-800 font-mono text-xs text-slate-400 overflow-auto">
          {JSON.stringify(
            {
              id: user?.id,
              email: user?.email,
              role: user?.role,
              last_sign_in_at: user?.last_sign_in_at,
            },
            null,
            2
          )}
        </pre>
      </details>
    </div>
  );
}
