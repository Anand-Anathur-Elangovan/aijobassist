"use client";

import { useState } from "react";
import Link from "next/link";

// ── Data ─────────────────────────────────────────────────────────────────
const STEPS = [
  {
    id: "overview",
    title: "How It Works",
    icon: "🏗️",
  },
  {
    id: "prerequisites",
    title: "Prerequisites",
    icon: "📋",
  },
  {
    id: "env-setup",
    title: "Environment Setup",
    icon: "⚙️",
  },
  {
    id: "database",
    title: "Database Setup",
    icon: "🗄️",
  },
  {
    id: "web-app",
    title: "Run Web App",
    icon: "🌐",
  },
  {
    id: "task-runner",
    title: "Run Task Runner",
    icon: "🤖",
  },
  {
    id: "platforms",
    title: "Platform Setup",
    icon: "🔗",
  },
  {
    id: "troubleshooting",
    title: "Troubleshooting",
    icon: "🔧",
  },
];

function CodeBlock({ children, title }: { children: string; title?: string }) {
  const [copied, setCopied] = useState(false);
  return (
    <div className="relative group">
      {title && <p className="text-xs text-slate-500 font-mono mb-1">{title}</p>}
      <pre className="bg-slate-900 border border-slate-800 rounded-lg p-4 overflow-x-auto text-sm text-emerald-400 font-mono">
        {children}
      </pre>
      <button
        onClick={() => { navigator.clipboard.writeText(children); setCopied(true); setTimeout(() => setCopied(false), 1500); }}
        className="absolute top-2 right-2 px-2 py-1 text-xs bg-slate-800 text-slate-400 hover:text-white rounded opacity-0 group-hover:opacity-100 transition-opacity"
      >
        {copied ? "✓ Copied" : "Copy"}
      </button>
    </div>
  );
}

function InfoBox({ type, children }: { type: "info" | "warning" | "success"; children: React.ReactNode }) {
  const styles = {
    info: "bg-blue-500/5 border-blue-500/20 text-blue-300",
    warning: "bg-amber-400/5 border-amber-400/20 text-amber-300",
    success: "bg-emerald-500/5 border-emerald-500/20 text-emerald-300",
  };
  const icons = { info: "ℹ️", warning: "⚠️", success: "✅" };
  return (
    <div className={`border rounded-lg p-4 text-sm ${styles[type]} my-4`}>
      <span className="mr-2">{icons[type]}</span>
      {children}
    </div>
  );
}

export default function SetupGuidePage() {
  const [activeSection, setActiveSection] = useState("overview");

  return (
    <div className="max-w-7xl mx-auto px-6 py-10">
      {/* Header */}
      <div className="mb-10">
        <Link href="/admin" className="text-slate-500 hover:text-white text-sm mb-4 inline-block">
          ← Back to Admin
        </Link>
        <h1 className="text-3xl font-display font-bold text-white">
          Agent Setup Guide
        </h1>
        <p className="text-slate-400 mt-2 max-w-2xl">
          Complete guide to setting up and connecting the VantaHire automation agent.
          Follow these steps to get the task runner, browser automation, and AI pipeline working.
        </p>
      </div>

      <div className="flex gap-8">
        {/* Sidebar nav */}
        <nav className="hidden md:block w-56 shrink-0 space-y-1 sticky top-24 self-start">
          {STEPS.map((s) => (
            <button
              key={s.id}
              onClick={() => { setActiveSection(s.id); document.getElementById(s.id)?.scrollIntoView({ behavior: "smooth" }); }}
              className={`w-full text-left px-3 py-2 rounded-lg text-sm flex items-center gap-2 transition-all ${
                activeSection === s.id
                  ? "bg-amber-400/10 text-amber-400 border border-amber-400/30"
                  : "text-slate-400 hover:text-white hover:bg-slate-800"
              }`}
            >
              <span>{s.icon}</span> {s.title}
            </button>
          ))}
        </nav>

        {/* Content */}
        <div className="flex-1 max-w-3xl space-y-16">
          {/* ═══ OVERVIEW ═══ */}
          <section id="overview">
            <h2 className="text-xl font-display font-bold text-white mb-4 flex items-center gap-2">
              <span className="text-2xl">🏗️</span> How It Works
            </h2>
            <p className="text-slate-300 mb-4">
              VantaHire uses a <strong>three-component architecture</strong> to automate your job search:
            </p>

            <div className="bg-slate-900/50 border border-slate-800 rounded-lg p-6 mb-6">
              <pre className="text-sm text-slate-300 font-mono whitespace-pre leading-relaxed">
{`┌──────────────────────┐     ┌──────────────────┐     ┌────────────────────┐
│  Next.js Web App     │────▶│  Supabase        │◀────│  Python Agent      │
│  (Your Browser)      │     │  (Cloud DB)      │     │  (Task Runner)     │
│  localhost:3000      │     │  Auth · Storage   │     │  taskrunner/       │
└──────────────────────┘     └──────────────────┘     └────────┬───────────┘
                                                               │
                                                    ┌──────────▼───────────┐
                                                    │   Automation Layer   │
                                                    │  linkedin.py         │
                                                    │  naukri.py           │
                                                    │  gmail_client.py     │
                                                    │  resume_tailor.py    │
                                                    │  ai_client.py        │
                                                    └──────────────────────┘`}
              </pre>
            </div>

            <div className="grid grid-cols-1 md:grid-cols-2 gap-4 mb-6">
              <div className="card">
                <h3 className="text-white font-semibold mb-2">End-to-End Flow</h3>
                <ol className="text-sm text-slate-400 space-y-2 list-decimal list-inside">
                  <li>You upload a resume &amp; configure preferences in the web app</li>
                  <li>Click &quot;Auto Apply&quot; — creates a task in Supabase</li>
                  <li>Python task runner picks it up (polls every 10s)</li>
                  <li>Launches a Chromium browser, logs into the platform</li>
                  <li>Searches for jobs, applies to each automatically</li>
                  <li>Optionally tailors your resume per JD using Claude AI</li>
                  <li>Records each application back in Supabase</li>
                  <li>Live progress, logs &amp; controls sync back to your dashboard</li>
                </ol>
              </div>
              <div className="card">
                <h3 className="text-white font-semibold mb-2">Supported Task Types</h3>
                <div className="space-y-2 text-sm">
                  <div className="flex items-center gap-2">
                    <span className="px-2 py-0.5 bg-blue-500/10 text-blue-400 rounded text-xs font-mono">AUTO_APPLY</span>
                    <span className="text-slate-400">Full auto apply on LinkedIn/Naukri</span>
                  </div>
                  <div className="flex items-center gap-2">
                    <span className="px-2 py-0.5 bg-violet-500/10 text-violet-400 rounded text-xs font-mono">TAILOR_AND_APPLY</span>
                    <span className="text-slate-400">Tailor resume per JD then apply</span>
                  </div>
                  <div className="flex items-center gap-2">
                    <span className="px-2 py-0.5 bg-emerald-500/10 text-emerald-400 rounded text-xs font-mono">TAILOR_RESUME</span>
                    <span className="text-slate-400">AI-tailor resume to a job desc</span>
                  </div>
                  <div className="flex items-center gap-2">
                    <span className="px-2 py-0.5 bg-amber-400/10 text-amber-400 rounded text-xs font-mono">GMAIL_DAILY_CHECK</span>
                    <span className="text-slate-400">Scan inbox, classify &amp; auto-reply</span>
                  </div>
                </div>
              </div>
            </div>
          </section>

          {/* ═══ PREREQUISITES ═══ */}
          <section id="prerequisites">
            <h2 className="text-xl font-display font-bold text-white mb-4 flex items-center gap-2">
              <span className="text-2xl">📋</span> Prerequisites
            </h2>

            <div className="overflow-x-auto">
              <table className="w-full text-sm mb-6">
                <thead>
                  <tr className="text-left text-slate-500 border-b border-slate-800">
                    <th className="pb-2 font-medium">Requirement</th>
                    <th className="pb-2 font-medium">Version</th>
                    <th className="pb-2 font-medium">Purpose</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-800 text-slate-300">
                  <tr><td className="py-2 font-medium">Python</td><td className="py-2 font-mono text-xs">3.10+</td><td className="py-2 text-slate-400">Task runner &amp; automation</td></tr>
                  <tr><td className="py-2 font-medium">Node.js</td><td className="py-2 font-mono text-xs">18+</td><td className="py-2 text-slate-400">Next.js web app</td></tr>
                  <tr><td className="py-2 font-medium">npm</td><td className="py-2 font-mono text-xs">8+</td><td className="py-2 text-slate-400">Package management</td></tr>
                  <tr><td className="py-2 font-medium">Chromium</td><td className="py-2 font-mono text-xs">via Playwright</td><td className="py-2 text-slate-400">Browser automation</td></tr>
                  <tr><td className="py-2 font-medium">Supabase</td><td className="py-2 font-mono text-xs">Cloud</td><td className="py-2 text-slate-400">Database, Auth, Storage</td></tr>
                  <tr><td className="py-2 font-medium">Anthropic API</td><td className="py-2 font-mono text-xs">Claude Sonnet</td><td className="py-2 text-slate-400">AI resume tailoring</td></tr>
                </tbody>
              </table>
            </div>

            <h3 className="text-white font-semibold mb-2">Python Packages</h3>
            <CodeBlock title="Install all Python dependencies">{`pip install python-dotenv requests anthropic pdfplumber python-docx reportlab playwright PyPDF2`}</CodeBlock>

            <div className="mt-4">
              <h3 className="text-white font-semibold mb-2">Install Playwright Browser</h3>
              <CodeBlock>{`python -m playwright install chromium`}</CodeBlock>
            </div>

            <h3 className="text-white font-semibold mt-6 mb-2">Node.js Dependencies</h3>
            <CodeBlock>{`npm install`}</CodeBlock>
          </section>

          {/* ═══ ENVIRONMENT SETUP ═══ */}
          <section id="env-setup">
            <h2 className="text-xl font-display font-bold text-white mb-4 flex items-center gap-2">
              <span className="text-2xl">⚙️</span> Environment Setup
            </h2>

            <p className="text-slate-300 mb-4">
              Create a <code className="text-amber-400 bg-slate-800 px-1.5 py-0.5 rounded text-sm">.env</code> file in the project root with these values:
            </p>

            <CodeBlock title=".env">{`# ── Supabase ─────────────────────────────────────────────
NEXT_PUBLIC_SUPABASE_URL=https://your-project.supabase.co
NEXT_PUBLIC_SUPABASE_ANON_KEY=your-anon-key
SUPABASE_SERVICE_ROLE_KEY=your-service-role-key

# ── Anthropic (Claude AI) ────────────────────────────────
ANTHROPIC_API_KEY=sk-ant-...

# ── Razorpay Billing ─────────────────────────────────────
RAZORPAY_KEY_ID=rzp_test_...
RAZORPAY_KEY_SECRET=your-razorpay-secret
RAZORPAY_WEBHOOK_SECRET=your-webhook-secret

# ── App Settings ─────────────────────────────────────────
NEXT_PUBLIC_APP_URL=http://localhost:3000`}</CodeBlock>

            <InfoBox type="warning">
              The <strong>Supabase Service Role Key</strong> bypasses Row Level Security. Never expose it in the frontend — it&apos;s only used by the Python task runner and server-side API routes.
            </InfoBox>

            <h3 className="text-white font-semibold mt-6 mb-2">Where to find these values</h3>
            <div className="space-y-3 text-sm text-slate-300">
              <div className="flex gap-3">
                <span className="text-amber-400 font-mono w-48 shrink-0">Supabase URL &amp; Keys</span>
                <span>Dashboard → Project Settings → API → Project URL &amp; anon key / service_role key</span>
              </div>
              <div className="flex gap-3">
                <span className="text-amber-400 font-mono w-48 shrink-0">Anthropic API Key</span>
                <span>console.anthropic.com → API Keys → Create key</span>
              </div>
              <div className="flex gap-3">
                <span className="text-amber-400 font-mono w-48 shrink-0">Razorpay Keys</span>
                <span>Razorpay Dashboard → Settings → API Keys → Generate Key</span>
              </div>
            </div>
          </section>

          {/* ═══ DATABASE SETUP ═══ */}
          <section id="database">
            <h2 className="text-xl font-display font-bold text-white mb-4 flex items-center gap-2">
              <span className="text-2xl">🗄️</span> Database Setup
            </h2>

            <p className="text-slate-300 mb-4">
              Run these SQL files <strong>in order</strong> in the Supabase SQL Editor:
            </p>

            <div className="space-y-3 mb-6">
              {[
                { file: "schema.sql", desc: "Core tables — resumes, jobs, applications, tasks with RLS policies" },
                { file: "schema_additions.sql", desc: "Extensions — resume_versions, cover_letters, jd_analyses, company_watchlist, notifications, gmail_settings, task monitoring columns, append_task_log RPC" },
                { file: "schema_billing.sql", desc: "Billing — plans, plan_limits, subscriptions, usage_events, daily_usage, payments, user_profiles, quota RPCs, auto-trial trigger" },
              ].map((s, i) => (
                <div key={s.file} className="flex items-start gap-3 bg-slate-900/50 border border-slate-800 rounded-lg p-4">
                  <span className="w-7 h-7 bg-amber-400/10 text-amber-400 rounded-full flex items-center justify-center text-sm font-bold shrink-0">{i + 1}</span>
                  <div>
                    <p className="text-white font-mono text-sm font-medium">{s.file}</p>
                    <p className="text-slate-400 text-sm mt-0.5">{s.desc}</p>
                  </div>
                </div>
              ))}
            </div>

            <InfoBox type="info">
              After running schema_billing.sql, 4 plans are automatically seeded: Trial (10 days), Free (₹0), Pro (₹999/mo), and Premium (₹1,999/mo). A trigger auto-creates a trial subscription when a new user signs up.
            </InfoBox>

            <h3 className="text-white font-semibold mt-6 mb-2">Supabase Storage Bucket</h3>
            <p className="text-slate-300 text-sm mb-3">Create a storage bucket for resume uploads:</p>
            <ol className="text-sm text-slate-400 space-y-1 list-decimal list-inside">
              <li>Go to Supabase Dashboard → Storage</li>
              <li>Click &quot;New bucket&quot; → name it <code className="text-amber-400 bg-slate-800 px-1 rounded">resumes</code></li>
              <li>Set it as <strong>public</strong> and allow upload for authenticated users</li>
            </ol>
          </section>

          {/* ═══ RUN WEB APP ═══ */}
          <section id="web-app">
            <h2 className="text-xl font-display font-bold text-white mb-4 flex items-center gap-2">
              <span className="text-2xl">🌐</span> Run the Web App
            </h2>

            <CodeBlock title="Start the Next.js dev server">{`npm run dev`}</CodeBlock>

            <p className="text-slate-300 text-sm mt-3">
              Open <code className="text-amber-400 bg-slate-800 px-1.5 py-0.5 rounded">http://localhost:3000</code> in your browser. Sign up with email/password — Supabase Auth handles everything.
            </p>

            <InfoBox type="success">
              New users automatically get a 10-day trial with full access. After trial, they drop to the free plan with limited quotas.
            </InfoBox>

            <h3 className="text-white font-semibold mt-6 mb-2">Key Pages</h3>
            <div className="grid grid-cols-2 gap-3 text-sm">
              {[
                { path: "/dashboard", desc: "Automation controls, task launcher" },
                { path: "/resume-studio", desc: "AI resume tailoring + cover letter" },
                { path: "/job-search", desc: "JD analyzer, job tracker" },
                { path: "/applications", desc: "Application pipeline tracker" },
                { path: "/upload-resume", desc: "Upload resume PDF/DOCX" },
                { path: "/settings", desc: "Gmail config, profile, preferences" },
                { path: "/billing", desc: "Subscription management" },
                { path: "/admin", desc: "Super admin dashboard" },
              ].map((p) => (
                <div key={p.path} className="flex items-center gap-2 bg-slate-800/40 rounded-lg px-3 py-2">
                  <code className="text-amber-400 text-xs font-mono">{p.path}</code>
                  <span className="text-slate-400 text-xs">— {p.desc}</span>
                </div>
              ))}
            </div>
          </section>

          {/* ═══ RUN TASK RUNNER ═══ */}
          <section id="task-runner">
            <h2 className="text-xl font-display font-bold text-white mb-4 flex items-center gap-2">
              <span className="text-2xl">🤖</span> Run the Task Runner (Agent)
            </h2>

            <p className="text-slate-300 mb-4">
              The task runner is the <strong>Python background agent</strong> that executes automation tasks. It polls Supabase for new tasks and launches browser automation.
            </p>

            <CodeBlock title="Start the agent">{`cd taskrunner
python main.py`}</CodeBlock>

            <div className="mt-4 bg-slate-900/50 border border-slate-800 rounded-lg p-4">
              <p className="text-emerald-400 font-mono text-sm mb-2">Expected output:</p>
              <pre className="text-xs text-slate-400 font-mono">{`==================================================
  VantaHire Task Runner — Started
==================================================

[POLL] Checking for pending tasks...
[IDLE]  No pending tasks. Sleeping...`}</pre>
            </div>

            <h3 className="text-white font-semibold mt-6 mb-2">How the Agent Works</h3>
            <div className="space-y-3 text-sm text-slate-300">
              <div className="flex items-start gap-3">
                <span className="w-6 h-6 bg-blue-500/10 text-blue-400 rounded-full flex items-center justify-center text-xs font-bold shrink-0">1</span>
                <p>Polls <code className="text-amber-400 bg-slate-800 px-1 rounded text-xs">tasks</code> table every 10 seconds for <code className="text-amber-400 bg-slate-800 px-1 rounded text-xs">status = PENDING</code></p>
              </div>
              <div className="flex items-start gap-3">
                <span className="w-6 h-6 bg-blue-500/10 text-blue-400 rounded-full flex items-center justify-center text-xs font-bold shrink-0">2</span>
                <p>Picks the oldest pending task, updates to <code className="text-amber-400 bg-slate-800 px-1 rounded text-xs">RUNNING</code></p>
              </div>
              <div className="flex items-start gap-3">
                <span className="w-6 h-6 bg-blue-500/10 text-blue-400 rounded-full flex items-center justify-center text-xs font-bold shrink-0">3</span>
                <p>Checks daily quota before executing — rejects if limit exceeded</p>
              </div>
              <div className="flex items-start gap-3">
                <span className="w-6 h-6 bg-blue-500/10 text-blue-400 rounded-full flex items-center justify-center text-xs font-bold shrink-0">4</span>
                <p>Routes to the correct handler (LinkedIn, Naukri, Gmail, or Tailor)</p>
              </div>
              <div className="flex items-start gap-3">
                <span className="w-6 h-6 bg-blue-500/10 text-blue-400 rounded-full flex items-center justify-center text-xs font-bold shrink-0">5</span>
                <p>Launches a <strong>visible Chromium browser</strong> — you can watch and intervene</p>
              </div>
              <div className="flex items-start gap-3">
                <span className="w-6 h-6 bg-blue-500/10 text-blue-400 rounded-full flex items-center justify-center text-xs font-bold shrink-0">6</span>
                <p>Progress, logs &amp; applied jobs sync to Supabase in real time</p>
              </div>
              <div className="flex items-start gap-3">
                <span className="w-6 h-6 bg-blue-500/10 text-blue-400 rounded-full flex items-center justify-center text-xs font-bold shrink-0">7</span>
                <p>Sets task to <code className="text-emerald-400 bg-slate-800 px-1 rounded text-xs">DONE</code> or <code className="text-red-400 bg-slate-800 px-1 rounded text-xs">FAILED</code></p>
              </div>
            </div>

            <h3 className="text-white font-semibold mt-6 mb-2">Live Controls</h3>
            <p className="text-slate-300 text-sm mb-3">
              While a task is running, you can control it from the web dashboard:
            </p>
            <div className="grid grid-cols-3 gap-3 text-sm">
              <div className="bg-slate-800/40 rounded-lg p-3 text-center">
                <p className="text-amber-400 font-bold mb-1">⏸ Pause</p>
                <p className="text-slate-400 text-xs">Pauses before the next application</p>
              </div>
              <div className="bg-slate-800/40 rounded-lg p-3 text-center">
                <p className="text-red-400 font-bold mb-1">⏹ Stop</p>
                <p className="text-slate-400 text-xs">Stops the task gracefully</p>
              </div>
              <div className="bg-slate-800/40 rounded-lg p-3 text-center">
                <p className="text-blue-400 font-bold mb-1">✏️ Prompt</p>
                <p className="text-slate-400 text-xs">Override the AI tailor prompt</p>
              </div>
            </div>

            <InfoBox type="warning">
              The task runner must be kept running on a machine with a display (or virtual display) — Playwright needs a browser window. Run it on your local machine or a VPS with a desktop environment.
            </InfoBox>
          </section>

          {/* ═══ PLATFORM SETUP ═══ */}
          <section id="platforms">
            <h2 className="text-xl font-display font-bold text-white mb-4 flex items-center gap-2">
              <span className="text-2xl">🔗</span> Platform-Specific Setup
            </h2>

            {/* LinkedIn */}
            <div className="card mb-6">
              <h3 className="text-white font-semibold text-lg mb-3">
                <span className="text-blue-400">LinkedIn</span> — Easy Apply Automation
              </h3>
              <div className="space-y-3 text-sm text-slate-300">
                <p><strong>Login options</strong> (choose one):</p>
                <ul className="list-disc list-inside space-y-1 text-slate-400 ml-2">
                  <li><strong>Auto login</strong> — Enter your LinkedIn email &amp; password in the dashboard. The bot fills them in automatically.</li>
                  <li><strong>Semi-auto</strong> — Bot opens LinkedIn, you type your password manually.</li>
                  <li><strong>Manual login</strong> — Bot opens LinkedIn login page, you have 3 minutes to log in yourself (handles CAPTCHA, 2FA).</li>
                </ul>
                <p><strong>What it automates:</strong></p>
                <ul className="list-disc list-inside space-y-1 text-slate-400 ml-2">
                  <li>Searches for Easy Apply jobs with your keywords &amp; location</li>
                  <li>Fills multi-step application forms (phone, experience, skills, resume)</li>
                  <li>Uploads your resume (or a tailored version per JD)</li>
                  <li>Handles radio buttons, dropdowns, and text fields smartly</li>
                  <li>Records each application to your tracker</li>
                </ul>
                <p><strong>Configuration</strong> (set in Dashboard → Automation):</p>
                <ul className="list-disc list-inside space-y-1 text-slate-400 ml-2">
                  <li><code className="text-amber-400 bg-slate-800 px-1 rounded">Phone</code> — your phone number for applications</li>
                  <li><code className="text-amber-400 bg-slate-800 px-1 rounded">Keywords</code> — job titles to search (e.g. &quot;Software Engineer&quot;)</li>
                  <li><code className="text-amber-400 bg-slate-800 px-1 rounded">Location</code> — &quot;Remote&quot;, city name, or &quot;India&quot;</li>
                  <li><code className="text-amber-400 bg-slate-800 px-1 rounded">Max Apply</code> — stop after this many applications</li>
                  <li><code className="text-amber-400 bg-slate-800 px-1 rounded">Years Experience</code> — auto-filled in forms</li>
                  <li><code className="text-amber-400 bg-slate-800 px-1 rounded">Favourite Companies</code> — prioritize these companies</li>
                </ul>
              </div>
            </div>

            {/* Naukri */}
            <div className="card mb-6">
              <h3 className="text-white font-semibold text-lg mb-3">
                <span className="text-emerald-400">Naukri</span> — Job Application Bot
              </h3>
              <div className="space-y-3 text-sm text-slate-300">
                <p><strong>Login</strong>: Manual only — the bot opens the Naukri login page and waits up to 3 minutes for you to log in.</p>
                <p><strong>Semi-auto mode</strong>: When enabled, the bot fills all form fields but pauses for 5 minutes to let you review &amp; click Submit manually.</p>
                <p><strong>What it fills</strong>: Experience, notice period, salary expectation, cover note, resume upload.</p>
              </div>
            </div>

            {/* Gmail */}
            <div className="card">
              <h3 className="text-white font-semibold text-lg mb-3">
                <span className="text-red-400">Gmail</span> — Email Monitoring &amp; Auto-Reply
              </h3>
              <div className="space-y-3 text-sm text-slate-300">
                <p><strong>Setup steps:</strong></p>
                <ol className="list-decimal list-inside space-y-2 text-slate-400 ml-2">
                  <li>Enable <strong>2-Step Verification</strong> on your Google account</li>
                  <li>Go to <code className="text-amber-400 bg-slate-800 px-1 rounded">myaccount.google.com/apppasswords</code></li>
                  <li>Generate an <strong>App Password</strong> (select &quot;Mail&quot; as the app)</li>
                  <li>In VantaHire: go to <strong>Settings → Gmail</strong> tab</li>
                  <li>Enter your Gmail address and the App Password</li>
                  <li>Set follow-up days (how many days before sending a follow-up)</li>
                </ol>
                <InfoBox type="info">
                  App Passwords are different from your regular Google password. They bypass 2FA for programmatic access. <strong>Do NOT use your regular Gmail password.</strong>
                </InfoBox>
                <p><strong>What it does daily:</strong></p>
                <ul className="list-disc list-inside space-y-1 text-slate-400 ml-2">
                  <li>Scans your inbox for job-related emails (last 14 days)</li>
                  <li>Classifies each: Acknowledgment, Interview Invite, Rejection, Schedule Request, Offer</li>
                  <li>Matches emails to your tracked applications by company name</li>
                  <li>Generates and sends AI-powered replies for actionable emails</li>
                  <li>Sends follow-up emails for overdue applications</li>
                  <li>Updates application stages in your tracker</li>
                  <li>Creates in-app notifications</li>
                </ul>
              </div>
            </div>
          </section>

          {/* ═══ TROUBLESHOOTING ═══ */}
          <section id="troubleshooting">
            <h2 className="text-xl font-display font-bold text-white mb-4 flex items-center gap-2">
              <span className="text-2xl">🔧</span> Troubleshooting
            </h2>

            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="text-left text-slate-500 border-b border-slate-800">
                    <th className="pb-2 font-medium">Issue</th>
                    <th className="pb-2 font-medium">Solution</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-800 text-slate-300">
                  <tr>
                    <td className="py-3 font-medium text-red-400">&quot;pdfplumber not installed&quot;</td>
                    <td className="py-3"><code className="text-amber-400 bg-slate-800 px-1 rounded text-xs">pip install pdfplumber</code></td>
                  </tr>
                  <tr>
                    <td className="py-3 font-medium text-red-400">&quot;anthropic not installed&quot;</td>
                    <td className="py-3"><code className="text-amber-400 bg-slate-800 px-1 rounded text-xs">pip install anthropic</code></td>
                  </tr>
                  <tr>
                    <td className="py-3 font-medium text-red-400">&quot;reportlab not installed&quot;</td>
                    <td className="py-3"><code className="text-amber-400 bg-slate-800 px-1 rounded text-xs">pip install reportlab</code> — PDF generation falls back to .txt without it</td>
                  </tr>
                  <tr>
                    <td className="py-3 font-medium text-red-400">Playwright browser not found</td>
                    <td className="py-3"><code className="text-amber-400 bg-slate-800 px-1 rounded text-xs">python -m playwright install chromium</code></td>
                  </tr>
                  <tr>
                    <td className="py-3 font-medium text-red-400">Task stuck in RUNNING</td>
                    <td className="py-3">Manually update <code className="text-amber-400 bg-slate-800 px-1 rounded text-xs">status</code> to FAILED in Supabase tasks table, or use Admin → Tasks → Cancel</td>
                  </tr>
                  <tr>
                    <td className="py-3 font-medium text-red-400">Quota exceeded</td>
                    <td className="py-3">Check daily_usage and plan_limits tables. Upgrade plan or wait for next day (resets at midnight UTC)</td>
                  </tr>
                  <tr>
                    <td className="py-3 font-medium text-red-400">Gmail IMAP error</td>
                    <td className="py-3">Verify App Password is correct. Enable 2-Step Verification. Re-generate App Password if needed.</td>
                  </tr>
                  <tr>
                    <td className="py-3 font-medium text-red-400">LinkedIn login timeout</td>
                    <td className="py-3">Log in manually within 3 minutes. CAPTCHA/2FA may need manual intervention.</td>
                  </tr>
                  <tr>
                    <td className="py-3 font-medium text-red-400">&quot;No resume found&quot;</td>
                    <td className="py-3">Upload a resume via the web app first (Upload Resume page)</td>
                  </tr>
                  <tr>
                    <td className="py-3 font-medium text-red-400">RPC function not found</td>
                    <td className="py-3">Run all 3 SQL schema files in Supabase SQL Editor in order</td>
                  </tr>
                  <tr>
                    <td className="py-3 font-medium text-red-400">.env not loading</td>
                    <td className="py-3"><code className="text-amber-400 bg-slate-800 px-1 rounded text-xs">pip install python-dotenv</code> and ensure .env is in the project root</td>
                  </tr>
                  <tr>
                    <td className="py-3 font-medium text-red-400">Credit balance too low (Anthropic)</td>
                    <td className="py-3">Purchase credits at console.anthropic.com. AI features use mock fallback without credits.</td>
                  </tr>
                </tbody>
              </table>
            </div>

            <InfoBox type="success">
              Even without an Anthropic API key, the system works — AI functions use keyword-based mock fallbacks. The mock tailor still injects missing keywords and improves your resume, just not as sophisticatedly as Claude.
            </InfoBox>
          </section>

          {/* Bottom nav */}
          <div className="border-t border-slate-800 pt-8 flex justify-between">
            <Link href="/admin" className="text-slate-400 hover:text-white text-sm">
              ← Back to Admin Dashboard
            </Link>
            <Link href="/dashboard" className="text-amber-400 hover:text-amber-300 text-sm">
              Go to Dashboard →
            </Link>
          </div>
        </div>
      </div>
    </div>
  );
}
