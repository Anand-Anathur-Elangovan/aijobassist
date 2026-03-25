"use client";

import { useState, useEffect, useRef } from "react";
import Link from "next/link";
import { useAuth } from "@/context/AuthContext";
import { supabase } from "@/lib/supabase";
import ExecutionModeModal, { type ExecutionMode, type RailwayQuotaInfo } from "@/components/ExecutionModeModal";
import ApprovalPanel from "@/components/ApprovalPanel";
import LogPanel from "@/components/LogPanel";
import type { LogEntry } from "@/lib/types";

type KeyInfo = {
  id: string;
  key_prefix: string;
  label: string;
  is_active: boolean;
  last_used: string | null;
  created_at: string;
};

export default function AgentPage() {
  const { user } = useAuth();
  const [keyInfo, setKeyInfo] = useState<KeyInfo | null>(null);
  const [newKey, setNewKey] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [generating, setGenerating] = useState(false);
  const [copied, setCopied] = useState(false);
  const [step, setStep] = useState(1);

  // ── Railway Cloud state ──────────────────────────────────────
  const [railwayConfigured,  setRailwayConfigured]  = useState(false);
  const [railwayQuota,       setRailwayQuota]        = useState<RailwayQuotaInfo>({ used: 0, limit: 5, remaining: 5 });
  const [preferredMode,      setPreferredMode]       = useState<ExecutionMode>("own_machine");
  const [showBanner,         setShowBanner]          = useState(true);
  const [showExecModal,      setShowExecModal]       = useState(false);
  const [pendingTaskType,    setPendingTaskType]      = useState<"AUTO_APPLY" | "TAILOR_AND_APPLY">("AUTO_APPLY");
  const [railwaySessionId,   setRailwaySessionId]    = useState<string | null>(null);
  const [liveScreenshot,     setLiveScreenshot]      = useState<string | null>(null);
  const [railwayStatus,      setRailwayStatus]       = useState<"idle" | "running" | "done">("idle");
  const [railwayProgress,    setRailwayProgress]     = useState(0);
  const [railwayCurrentJob,  setRailwayCurrentJob]   = useState<string | null>(null);
  const [railwayLogs,        setRailwayLogs]         = useState<Array<{ message: string; level?: string; ts?: string }>>([]);
  const [railwayStopping,    setRailwayStopping]     = useState(false);
  const logsEndRef = useRef<HTMLDivElement>(null);
  const evtSourceRef = useRef<EventSource | null>(null);

  // ── Supabase task polling (for approval flow + structured logs) ──
  const [approvalPayload, setApprovalPayload] = useState<{
    task_id: string
    job_title: string
    company: string
    url: string
    screenshot_b64: string | null
    waiting_since: string
  } | null>(null);
  const [taskLogs,        setTaskLogs]        = useState<LogEntry[]>([]);
  const [taskStatus,      setTaskStatus]      = useState<string | null>(null);
  const [activeTaskId,    setActiveTaskId]    = useState<string | null>(null);
  const pollIntervalRef = useRef<ReturnType<typeof setInterval> | null>(null);

  useEffect(() => {
    fetchKey();
    fetchRailwayInfo();
    // Check if banner was dismissed
    if (typeof window !== "undefined") {
      const dismissed = localStorage.getItem("railway_banner_dismissed");
      if (dismissed === "1") setShowBanner(false);
    }
  }, [user]);

  // ── Poll Supabase for active task (approval + live logs) ─────
  useEffect(() => {
    if (!user) return;

    async function pollActiveTask() {
      const { data: tasks } = await supabase
        .from("tasks")
        .select("id, status, logs, approval_payload")
        .eq("user_id", user!.id)
        .in("status", ["PENDING", "RUNNING", "WAITING_APPROVAL"])
        .order("created_at", { ascending: false })
        .limit(1);

      const task = tasks?.[0];
      if (!task) {
        setTaskStatus(null);
        setApprovalPayload(null);
        return;
      }

      setActiveTaskId(task.id);
      setTaskStatus(task.status);

      // Parse structured logs (handle old plain-string entries for backward compat)
      const raw: unknown[] = Array.isArray(task.logs) ? task.logs : [];
      const parsed: LogEntry[] = raw.map((entry) => {
        if (typeof entry === "string") {
          return { ts: new Date().toISOString(), level: "info" as const, category: "system" as const, msg: entry, meta: {} };
        }
        return entry as LogEntry;
      });
      setTaskLogs(parsed);

      // Approval panel
      if (task.status === "WAITING_APPROVAL" && task.approval_payload) {
        setApprovalPayload({ ...task.approval_payload, task_id: task.id });
      } else {
        setApprovalPayload(null);
      }
    }

    // Poll every 2 seconds
    pollActiveTask();
    pollIntervalRef.current = setInterval(pollActiveTask, 2000);
    return () => {
      if (pollIntervalRef.current) clearInterval(pollIntervalRef.current);
    };
  }, [user]);

  // Auto-scroll logs
  useEffect(() => {
    logsEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [railwayLogs]);

  async function fetchKey() {
    if (!user) return;
    const session = await supabase.auth.getSession();
    const token = session.data.session?.access_token;
    if (!token) return;

    const res = await fetch("/api/agent-key", {
      headers: { Authorization: `Bearer ${token}` },
    });
    if (!res.ok) { setKeyInfo(null); setLoading(false); return; }
    const data = await res.json();
    setKeyInfo(data.key ?? null);
    setLoading(false);
  }

  // ── Railway helpers ──────────────────────────────────────────

  async function fetchRailwayInfo() {
    if (!user) return;
    const session = await supabase.auth.getSession();
    const token   = session.data.session?.access_token;
    if (!token) return;

    // Fetch user profile for railway_configured + preferred_execution_mode
    const { data: profile } = await supabase
      .from("user_profiles")
      .select("railway_configured, preferred_execution_mode")
      .eq("user_id", user.id)
      .single();

    if (profile) {
      setRailwayConfigured(!!profile.railway_configured);
      setPreferredMode((profile.preferred_execution_mode as ExecutionMode) ?? "own_machine");
    }

    // Fetch today's Railway quota
    const res = await fetch("/api/railway/status?ping=false", {
      headers: { Authorization: `Bearer ${token}` },
    }).catch(() => null);
    // Quota is fetched via billing endpoint — use Supabase directly
    const today = new Date().toISOString().split("T")[0];
    const { data: usageRow } = await supabase
      .from("railway_daily_usage")
      .select("minutes_used")
      .eq("user_id", user.id)
      .eq("usage_date", today)
      .single();
    const used = Number(usageRow?.minutes_used ?? 0);
    // Get plan limit
    const { data: sub } = await supabase
      .from("subscriptions")
      .select("plan_id")
      .eq("user_id", user.id)
      .in("status", ["active", "past_due"])
      .single();
    let limit = 5;
    if (sub?.plan_id) {
      const { data: pl } = await supabase
        .from("plan_limits")
        .select("daily_limit")
        .eq("plan_id", sub.plan_id)
        .eq("action_type", "railway_minutes")
        .single();
      if (pl) limit = pl.daily_limit;
    }
    setRailwayQuota({ used, limit, remaining: Math.max(0, limit - used) });
    void res; // stop lint warning
  }

  function openExecutionModal(taskType: "AUTO_APPLY" | "TAILOR_AND_APPLY") {
    setPendingTaskType(taskType);
    setShowExecModal(true);
  }

  async function handleExecutionConfirm(mode: ExecutionMode, remember: boolean) {
    setShowExecModal(false);

    if (remember) {
      await supabase
        .from("user_profiles")
        .update({ preferred_execution_mode: mode })
        .eq("user_id", user?.id ?? "");
      setPreferredMode(mode);
    }

    if (mode === "own_machine") {
      // Direct user to the dashboard to start via .exe — existing flow
      alert("Make sure the VantaHire.exe desktop agent is running, then go to Dashboard and click Apply.");
      return;
    }

    // Railway cloud flow
    await triggerRailwayCloud(pendingTaskType);
  }

  async function triggerRailwayCloud(taskType: string) {
    if (!user) return;
    const session = await supabase.auth.getSession();
    const token   = session.data.session?.access_token;
    if (!token) return;

    // Create a task row first, then trigger Railway
    const { data: newTask, error: taskErr } = await supabase
      .from("tasks")
      .insert({
        user_id:        user.id,
        type:           taskType,
        status:         "PENDING",
        execution_mode: "railway",
        input:          {},
      })
      .select("id")
      .single();

    if (taskErr || !newTask) {
      alert("Failed to create task. Please try again.");
      return;
    }

    const res = await fetch("/api/railway/trigger", {
      method:  "POST",
      headers: {
        "Content-Type":  "application/json",
        "Authorization": `Bearer ${token}`,
      },
      body: JSON.stringify({
        task_id:    newTask.id,
        task_type:  taskType,
        task_input: {},
      }),
    });

    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      alert(`Failed to start Railway job: ${err.error ?? res.statusText}`);
      return;
    }

    const data = await res.json();
    setRailwaySessionId(data.session_id);
    setRailwayStatus("running");
    setRailwayLogs([]);
    setLiveScreenshot(null);
    setRailwayProgress(0);
    setRailwayCurrentJob(null);

    // Refresh quota
    await fetchRailwayInfo();

    // Start SSE screenshot stream
    startScreenshotStream(data.session_id);
  }

  function startScreenshotStream(sessionId: string) {
    // Close any existing stream
    evtSourceRef.current?.close();

    const evtSource = new EventSource(`/api/railway/stream?session_id=${sessionId}`);
    evtSourceRef.current = evtSource;

    evtSource.addEventListener("screenshot", (e) => {
      const payload = JSON.parse(e.data);
      setLiveScreenshot(`data:image/jpeg;base64,${payload.data}`);
    });

    evtSource.addEventListener("log", (e) => {
      const entry = JSON.parse(e.data);
      setRailwayLogs((prev) => [...prev, entry]);
    });

    evtSource.addEventListener("progress", (e) => {
      const payload = JSON.parse(e.data);
      setRailwayProgress(payload.progress ?? 0);
      setRailwayCurrentJob(payload.current_job ?? null);
    });

    evtSource.addEventListener("done", (e) => {
      const payload = JSON.parse(e.data);
      setRailwayStatus("done");
      setRailwayLogs((prev) => [
        ...prev,
        { message: `Session ended — status: ${payload.status}`, level: "info", ts: new Date().toISOString() },
      ]);
      evtSource.close();
      evtSourceRef.current = null;
      fetchRailwayInfo(); // refresh quota
    });

    evtSource.onerror = () => {
      setRailwayStatus("done");
      evtSource.close();
      evtSourceRef.current = null;
    };
  }

  async function stopRailwaySession() {
    if (!railwaySessionId || railwayStopping) return;
    setRailwayStopping(true);

    const session = await supabase.auth.getSession();
    const token   = session.data.session?.access_token;
    if (!token) { setRailwayStopping(false); return; }

    await fetch("/api/railway/stop", {
      method:  "POST",
      headers: {
        "Content-Type":  "application/json",
        "Authorization": `Bearer ${token}`,
      },
      body: JSON.stringify({ session_id: railwaySessionId }),
    });

    evtSourceRef.current?.close();
    setRailwayStatus("done");
    setRailwayStopping(false);
    fetchRailwayInfo();
  }

  function dismissBanner() {
    setShowBanner(false);
    if (typeof window !== "undefined") {
      localStorage.setItem("railway_banner_dismissed", "1");
    }
  }

  async function generateKey() {
    if (!user) return;
    setGenerating(true);
    const session = await supabase.auth.getSession();
    const token = session.data.session?.access_token;
    if (!token) return;

    const res = await fetch("/api/agent-key", {
      method: "POST",
      headers: { Authorization: `Bearer ${token}` },
    });
    if (!res.ok) { setGenerating(false); return; }
    const data = await res.json();
    if (data.key) {
      setNewKey(data.key);
      await fetchKey();
    }
    setGenerating(false);
  }

  async function revokeKey() {
    if (!user || !confirm("Revoke your agent key? The desktop agent will stop working until you generate a new one.")) return;
    const session = await supabase.auth.getSession();
    const token = session.data.session?.access_token;
    if (!token) return;

    await fetch("/api/agent-key", {
      method: "DELETE",
      headers: { Authorization: `Bearer ${token}` },
    });
    setKeyInfo(null);
    setNewKey(null);
  }

  function copyKey() {
    if (!newKey) return;
    navigator.clipboard.writeText(newKey);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  }

  const STEPS = [
    {
      title: "Download the Agent",
      icon: "📥",
      content: (
        <div className="space-y-4">
          <p className="text-slate-300 text-sm">
            Download the VantaHire desktop agent. It opens a real browser on your computer and automates job applications on LinkedIn and Naukri.
          </p>

          {/* Prerequisites */}
          <div className="bg-amber-400/5 border border-amber-400/25 rounded-lg p-4 space-y-3">
            <p className="text-amber-400 text-xs font-bold uppercase tracking-wider">⚠️ Prerequisites — Do this first</p>
            <div className="space-y-2 text-sm">
              <div className="flex items-start gap-2">
                <span className="text-slate-500 mt-0.5 shrink-0">1.</span>
                <p className="text-slate-300"><strong className="text-white">Windows 10 / 11 (64-bit)</strong> required. macOS coming soon.</p>
              </div>
              <div className="flex items-start gap-2">
                <span className="text-slate-500 mt-0.5 shrink-0">2.</span>
                <div>
                  <p className="text-slate-300">After downloading, open <strong className="text-white">Command Prompt</strong> (search &#34;cmd&#34; in Start) and run this <strong className="text-white">one-time</strong> command to install the browser engine:</p>
                  <div className="mt-2 flex items-center gap-2 bg-slate-950 border border-slate-700 rounded px-3 py-2">
                    <code className="text-emerald-400 text-xs font-mono flex-1">playwright install chromium</code>
                    <button
                      onClick={() => { navigator.clipboard.writeText("playwright install chromium"); }}
                      className="text-xs text-slate-500 hover:text-slate-300 shrink-0"
                    >copy</button>
                  </div>
                  <p className="text-xs text-slate-500 mt-1">This downloads ~130 MB of browser files. Only needed once per machine.</p>
                </div>
              </div>
              <div className="flex items-start gap-2">
                <span className="text-slate-500 mt-0.5 shrink-0">3.</span>
                <p className="text-slate-300">Have your <strong className="text-white">LinkedIn</strong> and/or <strong className="text-white">Naukri</strong> login credentials ready — the agent will ask for them on first run.</p>
              </div>
            </div>
          </div>

          {/* Download buttons */}
          <div className="flex gap-3">
            <a
              href="https://github.com/Anand-Anathur-Elangovan/aijobassist/releases/download/v1.0.0/VantaHire.exe"
              download
              className="flex items-center gap-2 px-4 py-2.5 bg-amber-400 text-slate-950 font-semibold rounded-lg hover:bg-amber-300 transition-all text-sm"
            >
              <span>⊞</span> Windows (.exe)
            </a>
            <a
              href="#"
              className="flex items-center gap-2 px-4 py-2.5 bg-slate-800 text-white font-semibold rounded-lg hover:bg-slate-700 transition-all text-sm border border-slate-700"
              onClick={(e) => {
                e.preventDefault();
                alert("macOS build coming soon!");
              }}
            >
              <span>🍎</span> macOS (.dmg)
            </a>
          </div>
          <p className="text-xs text-slate-500">
            v1.0.0 · ~74 MB · No installation needed — just run the .exe after the one-time Playwright setup above
          </p>
        </div>
      ),
    },
    {
      title: "Generate Your API Key",
      icon: "🔑",
      content: (
        <div className="space-y-3">
          <p className="text-slate-300 text-sm">
            Your API key connects the desktop agent to your VantaHire account. It&apos;s shown <strong>only once</strong> — copy it immediately.
          </p>

          {newKey ? (
            <div className="space-y-2">
              <div className="flex items-center gap-2 bg-slate-900 border border-emerald-500/30 rounded-lg p-3">
                <code className="text-emerald-400 text-sm font-mono flex-1 break-all select-all">{newKey}</code>
                <button
                  onClick={copyKey}
                  className="px-3 py-1.5 bg-emerald-500/10 text-emerald-400 text-xs rounded hover:bg-emerald-500/20 shrink-0"
                >
                  {copied ? "✓ Copied" : "Copy"}
                </button>
              </div>
              <p className="text-xs text-amber-400">
                ⚠️ Save this key now! It won&apos;t be shown again. If lost, generate a new one.
              </p>
            </div>
          ) : keyInfo ? (
            <div className="space-y-2">
              <div className="flex items-center gap-3 bg-slate-900 border border-slate-800 rounded-lg p-3">
                <div className="flex-1">
                  <p className="text-sm text-white font-mono">{keyInfo.key_prefix}••••••••••••</p>
                  <p className="text-xs text-slate-500 mt-1">
                    Created {new Date(keyInfo.created_at).toLocaleDateString()}
                    {keyInfo.last_used && ` · Last used ${new Date(keyInfo.last_used).toLocaleDateString()}`}
                  </p>
                </div>
                <span className="px-2 py-0.5 bg-emerald-500/10 text-emerald-400 text-xs rounded-full">Active</span>
              </div>
              <div className="flex gap-2">
                <button
                  onClick={generateKey}
                  disabled={generating}
                  className="px-3 py-1.5 bg-amber-400/10 text-amber-400 text-xs rounded hover:bg-amber-400/20 disabled:opacity-50"
                >
                  Regenerate Key
                </button>
                <button
                  onClick={revokeKey}
                  className="px-3 py-1.5 bg-red-500/10 text-red-400 text-xs rounded hover:bg-red-500/20"
                >
                  Revoke
                </button>
              </div>
            </div>
          ) : (
            <button
              onClick={generateKey}
              disabled={generating}
              className="px-5 py-2.5 bg-amber-400 text-slate-950 font-semibold rounded-lg hover:bg-amber-300 transition-all text-sm disabled:opacity-50"
            >
              {generating ? "Generating..." : "Generate API Key"}
            </button>
          )}
        </div>
      ),
    },
    {
      title: "Connect the Agent",
      icon: "🔗",
      content: (
        <div className="space-y-3">
          <p className="text-slate-300 text-sm">
            Run the VantaHire agent and paste your API key when prompted. Make sure you have run <code className="text-emerald-400 text-xs bg-slate-900 px-1.5 py-0.5 rounded">playwright install chromium</code> first (Step 1).
          </p>
          <div className="bg-slate-900 border border-slate-800 rounded-lg p-4 space-y-2">
            <div className="flex items-center gap-2 text-xs text-slate-500 font-mono">
              <span className="text-slate-600">$</span> Double-click <strong className="text-white">VantaHire.exe</strong> to launch
            </div>
            <pre className="text-sm text-emerald-400 font-mono leading-relaxed">{`
==================================================
  VantaHire Agent Setup
==================================================

  Enter your API key: vh_••••••••••••
  ✓ Connected to VantaHire
  ✓ Account: ${user?.email ?? "you@email.com"}
  ✓ Plan: Free Trial (9 days left)

  Agent is running. Waiting for tasks...
`}</pre>
          </div>
          <p className="text-xs text-slate-500">
            The agent saves your key locally (encrypted) — you only need to enter it once.
          </p>
        </div>
      ),
    },
    {
      title: "Launch a Task",
      icon: "🚀",
      content: (
        <div className="space-y-3">
          <p className="text-slate-300 text-sm">
            Go to your <strong>Dashboard</strong>, fill in your preferences, and click <strong>Apply</strong>. The desktop agent will pick it up automatically.
          </p>
          <div className="grid grid-cols-2 gap-3 text-sm">
            {[
              { icon: "🤖", label: "Auto Apply", desc: "Full automation on LinkedIn/Naukri" },
              { icon: "✏️", label: "Tailor & Apply", desc: "AI-tailors resume per JD then applies" },
              { icon: "📄", label: "Tailor Resume", desc: "Generate a tailored resume for any JD" },
              { icon: "📧", label: "Gmail Monitor", desc: "Auto-classify & reply to recruiters" },
            ].map((t) => (
              <div key={t.label} className="bg-slate-800/40 rounded-lg p-3">
                <p className="text-white font-medium">{t.icon} {t.label}</p>
                <p className="text-slate-400 text-xs mt-1">{t.desc}</p>
              </div>
            ))}
          </div>
          <div className="bg-blue-500/5 border border-blue-500/20 rounded-lg p-3 text-sm text-blue-300">
            ℹ️ The agent opens a <strong>visible Chromium browser</strong> — you can watch it work and intervene at any time. Pause, stop, or override the AI prompt from your dashboard.
          </div>
        </div>
      ),
    },
  ];

  if (loading) {
    return (
      <div className="min-h-screen flex items-center justify-center">
        <div className="w-8 h-8 border-2 border-amber-400 border-t-transparent rounded-full animate-spin" />
      </div>
    );
  }

  return (
    <div className="max-w-4xl mx-auto px-6 py-10">

      {/* ── ExecutionModeModal (global, hidden by default) ───── */}
      <ExecutionModeModal
        isOpen={showExecModal}
        onClose={() => setShowExecModal(false)}
        onConfirm={handleExecutionConfirm}
        railwayConfigured={railwayConfigured}
        quota={railwayQuota}
        taskType={pendingTaskType}
        defaultMode={preferredMode}
      />

      {/* ── Railway setup banner (shown if not yet configured) ── */}
      {!railwayConfigured && showBanner && (
        <div className="mb-6 flex items-start gap-3 bg-violet-500/5 border border-violet-500/25 rounded-xl px-4 py-3">
          <span className="text-violet-400 text-xl shrink-0 mt-0.5">☁️</span>
          <div className="flex-1 min-w-0">
            <p className="text-sm text-white font-medium">
              Run automation in the cloud — no install needed
            </p>
            <p className="text-xs text-slate-400 mt-0.5">
              Set up Railway Cloud once and launch jobs directly from your browser. Takes about 1 minute.
            </p>
          </div>
          <div className="flex items-center gap-2 shrink-0">
            <Link
              href="/agent/setup"
              className="text-xs px-3 py-1.5 bg-violet-600 hover:bg-violet-500 text-white rounded-lg transition-all font-medium"
            >
              Set up →
            </Link>
            <button
              onClick={dismissBanner}
              className="text-slate-500 hover:text-slate-300 text-xl leading-none"
            >
              ×
            </button>
          </div>
        </div>
      )}

      {/* ── Cloud Quick Launch (shown once Railway is configured) ── */}
      {railwayConfigured && railwayStatus === "idle" && (
        <div className="mb-6 bg-slate-900/60 border border-violet-500/20 rounded-xl p-5">
          <div className="flex items-center justify-between mb-3">
            <div>
              <h2 className="font-bold text-white flex items-center gap-2">
                <span className="text-violet-400">☁️</span> Cloud Quick Launch
              </h2>
              <p className="text-xs text-slate-400 mt-0.5">
                Run directly from browser — no .exe needed
              </p>
            </div>
            <div className="text-right text-xs text-slate-500">
              <p>{railwayQuota.used.toFixed(1)} / {railwayQuota.limit} min used today</p>
              <div className="w-28 h-1 bg-slate-700 rounded-full mt-1 overflow-hidden">
                <div
                  className="h-full bg-violet-500 rounded-full transition-all"
                  style={{ width: `${Math.min(100, (railwayQuota.used / railwayQuota.limit) * 100)}%` }}
                />
              </div>
            </div>
          </div>
          <div className="flex gap-3">
            <button
              onClick={() => openExecutionModal("AUTO_APPLY")}
              disabled={railwayQuota.remaining <= 0}
              className="flex-1 py-2.5 text-sm font-semibold rounded-lg bg-violet-600 hover:bg-violet-500 text-white transition-all disabled:opacity-40 disabled:cursor-not-allowed"
            >
              🤖 Start Auto Apply
            </button>
            <button
              onClick={() => openExecutionModal("TAILOR_AND_APPLY")}
              disabled={railwayQuota.remaining <= 0}
              className="flex-1 py-2.5 text-sm font-semibold rounded-lg bg-violet-600/30 hover:bg-violet-600/50 border border-violet-500/40 text-violet-200 transition-all disabled:opacity-40 disabled:cursor-not-allowed"
            >
              ✏️ Start Tailor &amp; Apply
            </button>
          </div>
          {railwayQuota.remaining <= 0 && (
            <p className="text-xs text-red-400 mt-2 text-center">
              Daily limit reached. Upgrade your plan for more cloud minutes.
            </p>
          )}
        </div>
      )}

      {/* ── Live Railway screenshot panel ───────────────────── */}
      {railwayStatus !== "idle" && (
        <div className="mb-6 bg-slate-900/60 border border-violet-500/30 rounded-xl overflow-hidden">
          {/* Panel header */}
          <div className="flex items-center justify-between px-5 py-3 border-b border-slate-800">
            <div className="flex items-center gap-3">
              {railwayStatus === "running" && (
                <span className="w-2 h-2 bg-emerald-400 rounded-full animate-pulse" />
              )}
              <div>
                <p className="text-sm font-bold text-white">
                  {railwayStatus === "running" ? "☁️ Cloud Automation Running" : "☁️ Session Ended"}
                </p>
                {railwayCurrentJob && (
                  <p className="text-xs text-slate-400 mt-0.5 truncate max-w-64">{railwayCurrentJob}</p>
                )}
              </div>
            </div>
            <div className="flex items-center gap-3">
              {/* Progress */}
              {railwayStatus === "running" && (
                <div className="flex items-center gap-2">
                  <div className="w-24 h-1.5 bg-slate-700 rounded-full overflow-hidden">
                    <div
                      className="h-full bg-violet-500 rounded-full transition-all"
                      style={{ width: `${railwayProgress}%` }}
                    />
                  </div>
                  <span className="text-xs text-slate-400">{railwayProgress}%</span>
                </div>
              )}
              {/* Stop / Close */}
              {railwayStatus === "running" ? (
                <button
                  onClick={stopRailwaySession}
                  disabled={railwayStopping}
                  className="px-3 py-1.5 text-xs font-semibold bg-red-500/10 text-red-400 hover:bg-red-500/20 border border-red-500/20 rounded-lg transition-all disabled:opacity-50"
                >
                  {railwayStopping ? "Stopping…" : "⏹ Stop"}
                </button>
              ) : (
                <button
                  onClick={() => { setRailwayStatus("idle"); setRailwaySessionId(null); setLiveScreenshot(null); setRailwayLogs([]); }}
                  className="px-3 py-1.5 text-xs text-slate-400 hover:text-white border border-slate-700 rounded-lg transition-colors"
                >
                  Close
                </button>
              )}
            </div>
          </div>

          {/* Screenshot + logs side-by-side */}
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-0 divide-y lg:divide-y-0 lg:divide-x divide-slate-800">
            {/* Live screenshot */}
            <div className="relative bg-slate-950 flex items-center justify-center" style={{ minHeight: "280px" }}>
              {liveScreenshot ? (
                // eslint-disable-next-line @next/next/no-img-element
                <img
                  src={liveScreenshot}
                  alt="Live automation screenshot"
                  className="w-full object-contain"
                />
              ) : (
                <div className="flex flex-col items-center gap-3 text-slate-600">
                  {railwayStatus === "running" ? (
                    <>
                      <span className="w-8 h-8 border-2 border-violet-500 border-t-transparent rounded-full animate-spin" />
                      <p className="text-xs">Waiting for first screenshot…</p>
                    </>
                  ) : (
                    <p className="text-xs">No screenshot available</p>
                  )}
                </div>
              )}
              {/* Timestamp overlay */}
              {liveScreenshot && (
                <div className="absolute bottom-2 right-2 bg-black/60 text-xs text-slate-400 px-2 py-0.5 rounded">
                  Live
                </div>
              )}
            </div>

            {/* Logs panel */}
            <div style={{ minHeight: "280px", maxHeight: "320px" }}>
              <LogPanel
                logs={
                  taskLogs.length > 0
                    ? taskLogs
                    : railwayLogs.map((l) => ({
                        ts: l.ts ?? new Date().toISOString(),
                        level: (l.level ?? "info") as LogEntry["level"],
                        category: "system" as const,
                        msg: l.message,
                        meta: {},
                      }))
                }
                isRunning={
                  taskStatus === "RUNNING" ||
                  taskStatus === "WAITING_APPROVAL" ||
                  railwayStatus === "running"
                }
              />
            </div>
          </div>
        </div>
      )}

      {/* Header */}
      <div className="mb-10">
        <h1 className="text-3xl font-display font-bold text-white flex items-center gap-3">
          <span className="w-10 h-10 bg-amber-400/10 rounded-lg flex items-center justify-center text-xl">🤖</span>
          Desktop Agent
        </h1>
        <p className="text-slate-400 mt-2 max-w-xl">
          The VantaHire agent runs on your computer and automates job applications. Download it, connect with your API key, and let it work for you.
        </p>
      </div>

      {/* Status card */}
      <div className={`card mb-8 flex items-center gap-4 ${keyInfo ? "border-emerald-500/20" : "border-amber-400/20"}`}>
        <div className={`w-3 h-3 rounded-full ${keyInfo ? "bg-emerald-400 animate-pulse" : "bg-slate-600"}`} />
        <div className="flex-1">
          <p className="text-white font-semibold">
            {keyInfo ? "Agent Connected" : "Agent Not Connected"}
          </p>
          <p className="text-sm text-slate-400">
            {keyInfo
              ? `Key: ${keyInfo.key_prefix}•••• · Created ${new Date(keyInfo.created_at).toLocaleDateString()}`
              : "Generate an API key and download the agent to get started."}
          </p>
        </div>
        {keyInfo && (
          <span className="px-3 py-1 bg-emerald-500/10 text-emerald-400 text-xs rounded-full font-medium">Active</span>
        )}
      </div>

      {/* Steps */}
      <div className="space-y-4">
        {STEPS.map((s, i) => {
          const num = i + 1;
          const isOpen = step === num;
          const isDone = num < step || (num === 2 && !!keyInfo);

          return (
            <div
              key={s.title}
              className={`card transition-all ${isOpen ? "border-amber-400/30 bg-slate-900/60" : ""}`}
            >
              <button
                onClick={() => setStep(isOpen ? 0 : num)}
                className="w-full flex items-center gap-4 text-left"
              >
                <span className={`w-8 h-8 rounded-full flex items-center justify-center text-sm font-bold shrink-0 ${
                  isDone
                    ? "bg-emerald-500/10 text-emerald-400"
                    : isOpen
                    ? "bg-amber-400/10 text-amber-400"
                    : "bg-slate-800 text-slate-500"
                }`}>
                  {isDone ? "✓" : num}
                </span>
                <div className="flex-1">
                  <p className={`font-semibold ${isOpen ? "text-white" : "text-slate-300"}`}>
                    {s.icon} {s.title}
                  </p>
                </div>
                <span className={`text-slate-600 transition-transform ${isOpen ? "rotate-180" : ""}`}>
                  ▼
                </span>
              </button>

              {isOpen && (
                <div className="mt-4 pl-12">
                  {s.content}
                </div>
              )}
            </div>
          );
        })}
      </div>

      {/* FAQ */}
      <div className="mt-12">
        <h2 className="text-lg font-display font-bold text-white mb-4">Frequently Asked Questions</h2>
        <div className="space-y-3">
          {[
            {
              q: "Is my data safe?",
              a: "Your API key is hashed (SHA-256) before storage — we never store the plaintext. Platform credentials you provide are only used locally by the agent and never sent to our servers.",
            },
            {
              q: "Can I run the agent on multiple machines?",
              a: "Yes, use the same API key on any machine. However, only one agent instance should run tasks at a time to avoid conflicts.",
            },
            {
              q: "Does it work on Linux?",
              a: "Currently Windows and macOS are supported. Linux support is coming soon. You can also run the agent from source if you're technical.",
            },
            {
              q: "Will the agent open a browser window?",
              a: "Yes — the agent uses a visible Chromium browser so you can watch, pause, or intervene. It needs a display to run.",
            },
            {
              q: "What if I lose my API key?",
              a: "Generate a new one from this page. The old key is automatically revoked.",
            },
            {
              q: "Does the agent use my quota?",
              a: "Yes — each task counts against your daily plan limits. Super admin accounts have unlimited access.",
            },
            {
              q: "Why do I need to run 'playwright install chromium'?",
              a: "The agent automates a real Chrome browser to interact with LinkedIn and Naukri. Playwright is the tool that controls it — and it requires you to download the browser engine (Chromium, ~130 MB) once per machine. This is a one-time step and won't affect your existing Chrome browser.",
            },
            {
              q: "What is Semi-Auto Mode?",
              a: "In Semi-Auto Mode, the agent fills in all job application fields but pauses before each final submit — so you can review and click Apply yourself. In full Auto mode, it submits without pausing.",
            },
            {
              q: "What's the difference between 'Auto Apply' and 'Tailor & Apply'?",
              a: "Auto Apply submits your existing resume as-is to matching jobs. Tailor & Apply uses AI to rewrite your resume specifically for each job description before applying — it takes longer but gives much better ATS scores.",
            },
          ].map((faq) => (
            <details key={faq.q} className="card group">
              <summary className="cursor-pointer text-sm text-white font-medium flex items-center justify-between">
                {faq.q}
                <span className="text-slate-600 group-open:rotate-180 transition-transform">▼</span>
              </summary>
              <p className="text-sm text-slate-400 mt-2">{faq.a}</p>
            </details>
          ))}
        </div>
      </div>

      {/* Standalone log panel for own-machine tasks (shown when Railway panel is idle) */}
      {taskLogs.length > 0 && railwayStatus === "idle" && (
        <div className="mt-6 h-96">
          <LogPanel
            logs={taskLogs}
            isRunning={taskStatus === "RUNNING" || taskStatus === "WAITING_APPROVAL"}
          />
        </div>
      )}

      {/* Approval modal overlay */}
      {approvalPayload && (
        <ApprovalPanel
          taskId={approvalPayload.task_id}
          payload={approvalPayload}
          onDecision={(decision) => {
            setApprovalPayload(null);
            setTaskLogs((prev) => [
              ...prev,
              {
                ts: new Date().toISOString(),
                level: decision === "approved" ? ("success" as const) : ("skip" as const),
                category: "approval" as const,
                msg:
                  decision === "approved"
                    ? "✅ You approved — bot is submitting…"
                    : "⏭ You skipped this job",
                meta: {},
              },
            ]);
          }}
        />
      )}
    </div>
  );
}
