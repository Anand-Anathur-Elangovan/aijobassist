"use client";

import { useState, useEffect } from "react";
import { useAuth } from "@/context/AuthContext";
import { supabase } from "@/lib/supabase";

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

  useEffect(() => {
    fetchKey();
  }, [user]);

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
    </div>
  );
}
