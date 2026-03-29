"use client";

import { useState } from "react";

type Section = "overview" | "dashboard" | "agent" | "applications" | "analytics" | "studio" | "workflow" | "pricing" | "support";

const SECTIONS: { id: Section; label: string; icon: string }[] = [
  { id: "overview",      label: "Overview",        icon: "🚀" },
  { id: "dashboard",     label: "Dashboard",       icon: "⚙️" },
  { id: "agent",         label: "Agent",           icon: "🤖" },
  { id: "applications",  label: "Applications",    icon: "📋" },
  { id: "analytics",     label: "Analytics",       icon: "📊" },
  { id: "studio",        label: "Resume Studio",   icon: "✏️" },
  { id: "workflow",      label: "How It Works",    icon: "🔄" },
  { id: "pricing",       label: "Pricing",         icon: "💳" },
  { id: "support",       label: "Support",         icon: "💬" },
];

export default function DocsPage() {
  const [active, setActive] = useState<Section>("overview");

  return (
    <div className="min-h-screen bg-slate-950 text-white">
      <div className="max-w-6xl mx-auto px-4 py-10">
        {/* Header */}
        <div className="mb-8">
          <h1 className="font-display text-3xl font-bold text-white mb-2">
            VantaHire <span className="text-amber-400">Documentation</span>
          </h1>
          <p className="font-body text-slate-400">
            Everything you need to know about using VantaHire to automate your job search.
          </p>
        </div>

        <div className="flex flex-col lg:flex-row gap-6">
          {/* Sidebar */}
          <aside className="lg:w-52 shrink-0">
            <nav className="space-y-0.5 sticky top-20">
              {SECTIONS.map(({ id, label, icon }) => (
                <button
                  key={id}
                  onClick={() => setActive(id)}
                  className={`w-full text-left flex items-center gap-2.5 px-3 py-2 rounded-lg text-sm font-body transition-all ${
                    active === id
                      ? "bg-amber-400/10 text-amber-400 border border-amber-400/20"
                      : "text-slate-400 hover:text-white hover:bg-slate-800"
                  }`}
                >
                  <span>{icon}</span>
                  <span>{label}</span>
                </button>
              ))}
            </nav>
          </aside>

          {/* Content */}
          <main className="flex-1 min-w-0">
            {active === "overview" && <OverviewSection />}
            {active === "dashboard" && <DashboardSection />}
            {active === "agent" && <AgentSection />}
            {active === "applications" && <ApplicationsSection />}
            {active === "analytics" && <AnalyticsSection />}
            {active === "studio" && <StudioSection />}
            {active === "workflow" && <WorkflowSection />}
            {active === "pricing" && <PricingSection />}
            {active === "support" && <SupportSection />}
          </main>
        </div>
      </div>
    </div>
  );
}

/* ── Shared components ────────────────────────────────────────────────────── */

function H2({ children }: { children: React.ReactNode }) {
  return <h2 className="font-display text-xl font-bold text-white mb-4">{children}</h2>;
}

function H3({ children }: { children: React.ReactNode }) {
  return <h3 className="font-mono text-sm font-semibold text-amber-400 mb-2 mt-5">{children}</h3>;
}

function P({ children }: { children: React.ReactNode }) {
  return <p className="font-body text-sm text-slate-300 leading-relaxed mb-3">{children}</p>;
}

function Card({ children }: { children: React.ReactNode }) {
  return (
    <div className="p-4 rounded-xl border border-slate-800 bg-slate-900/50 mb-4">{children}</div>
  );
}

function Badge({ color, children }: { color: "amber" | "green" | "blue" | "violet" | "red"; children: React.ReactNode }) {
  const cls: Record<string, string> = {
    amber:  "bg-amber-400/10 text-amber-400 border-amber-400/30",
    green:  "bg-emerald-400/10 text-emerald-400 border-emerald-400/30",
    blue:   "bg-blue-400/10 text-blue-400 border-blue-400/30",
    violet: "bg-violet-400/10 text-violet-400 border-violet-400/30",
    red:    "bg-red-400/10 text-red-400 border-red-400/30",
  };
  return (
    <span className={`inline-flex items-center px-2 py-0.5 rounded text-xs font-mono border ${cls[color]}`}>
      {children}
    </span>
  );
}

function StepList({ steps }: { steps: { n: number; title: string; desc: string }[] }) {
  return (
    <ol className="space-y-3 mb-4">
      {steps.map(({ n, title, desc }) => (
        <li key={n} className="flex gap-3">
          <span className="shrink-0 w-6 h-6 rounded-full bg-amber-400/10 border border-amber-400/30 text-amber-400 text-xs font-bold flex items-center justify-center mt-0.5">
            {n}
          </span>
          <div>
            <p className="font-mono text-sm text-white">{title}</p>
            <p className="font-body text-xs text-slate-400 mt-0.5">{desc}</p>
          </div>
        </li>
      ))}
    </ol>
  );
}

/* ── Sections ─────────────────────────────────────────────────────────────── */

function OverviewSection() {
  return (
    <div>
      <H2>What is VantaHire?</H2>
      <P>
        VantaHire is an AI-powered job application automation platform. It searches for jobs on
        LinkedIn and Naukri, scores them against your resume, tailors your resume for each
        application, and applies — all without manual effort.
      </P>

      <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 mb-6">
        {[
          { icon: "🔍", title: "Smart Search", desc: "Searches LinkedIn & Naukri using your keywords and filters." },
          { icon: "🧠", title: "AI Match Score", desc: "Scores each job against your resume before applying." },
          { icon: "📄", title: "Resume Tailoring", desc: "Rewrites your resume to hit a target ATS score for each role." },
          { icon: "🤖", title: "Auto Apply", desc: "Fills and submits applications end-to-end." },
          { icon: "📊", title: "Analytics", desc: "Tracks applications, responses, and success rates." },
          { icon: "📬", title: "Notifications", desc: "Telegram and Gmail alerts after every session." },
        ].map(({ icon, title, desc }) => (
          <Card key={title}>
            <p className="text-lg mb-1">{icon}</p>
            <p className="font-mono text-sm text-white font-semibold">{title}</p>
            <p className="font-body text-xs text-slate-400 mt-1">{desc}</p>
          </Card>
        ))}
      </div>

      <H3>Quick Start</H3>
      <StepList steps={[
        { n: 1, title: "Upload your resume", desc: "Go to Resume → Upload. The system extracts and stores your resume text." },
        { n: 2, title: "Fill in your profile", desc: "Dashboard → fill your personal details, experience, preferences, and job keywords." },
        { n: 3, title: "Set job preferences", desc: "Choose platforms (LinkedIn / Naukri), salary range, locations, and apply count." },
        { n: 4, title: "Run the agent", desc: "Click Auto Apply or Tailor & Apply. The bot handles everything." },
        { n: 5, title: "Review results", desc: "Check Applications tab for history, Analytics for stats, and your inbox for reports." },
      ]} />
    </div>
  );
}

function DashboardSection() {
  return (
    <div>
      <H2>Dashboard</H2>
      <P>The Dashboard is your control panel. Configure every setting before running the bot.</P>

      <H3>Personal Details</H3>
      <P>Fill in your name, phone, LinkedIn URL, location, years of experience, and skill rating. These are used to auto-fill application forms.</P>

      <H3>Keywords (1, 2, 3)</H3>
      <P>
        Enter up to 3 job-title keywords. The bot searches each keyword independently and applies to the
        best-matching results. Use <Badge color="violet">✨ AI Suggest Keywords</Badge> to auto-generate
        10 role ideas based on your uploaded resume — click any chip to fill a keyword slot.
      </P>

      <H3>Target Companies</H3>
      <P>
        Enter up to 5 company names. The bot will specifically search for openings at those companies
        matching your keywords, giving them priority over general results.
      </P>

      <H3>Smart Match</H3>
      <P>
        Set a minimum match score (e.g. 70%). The bot calculates an AI score for each job against your
        resume. Jobs below the threshold are automatically skipped, keeping your application quality high.
      </P>

      <H3>Auto Apply</H3>
      <P>Applies to jobs directly using your existing resume. Set apply count, platforms (LinkedIn / Naukri), and other filters.</P>

      <H3>Tailor & Apply</H3>
      <P>
        Before each application, the AI rewrites your resume to match the job description. Set a Target
        ATS Score (e.g. 90%) — the bot will keep refining the resume until that score is hit or the
        maximum attempts are reached. Each tailored resume is saved with the format{" "}
        <Badge color="amber">Company — Role.pdf</Badge> and can be downloaded from Applications.
      </P>

      <H3>URL Apply</H3>
      <P>
        Paste one or more job page URLs (LinkedIn / Naukri). The bot opens each URL, extracts the JD,
        and applies. Works with both Easy Apply and external company site forms.
      </P>

      <H3>Smart Apply Scheduler</H3>
      <P>
        Schedule the bot to run automatically during certain hours each day (e.g. 9 AM – 6 PM). Tasks
        created outside the window are queued and executed when the window opens.
      </P>

      <H3>Cover Letter</H3>
      <P>Enable AI-generated cover letters. The bot writes a personalized letter for each job before applying.</P>

      <H3>Run in Progress (Live Logs)</H3>
      <P>
        Once a task starts, live logs appear at the bottom of the Dashboard. Each log line shows timestamp,
        level (info / warn / error / success), and message. The Agent page has a more detailed view
        with live screenshots.
      </P>
    </div>
  );
}

function AgentSection() {
  return (
    <div>
      <H2>Agent</H2>
      <P>
        The Agent page is the advanced control centre for running and monitoring automation tasks.
      </P>

      <H3>Execution Modes</H3>
      <div className="space-y-2 mb-4">
        <Card>
          <p className="font-mono text-sm text-white font-semibold mb-1">Local Machine</p>
          <p className="font-body text-xs text-slate-400">
            Run the Python task runner on your own computer. Download and start the runner with your
            API key. Best for development and testing — uses your local browser session.
          </p>
        </Card>
        <Card>
          <p className="font-mono text-sm text-white font-semibold mb-1">Railway Cloud</p>
          <p className="font-body text-xs text-slate-400">
            Run the automation on a cloud server (Railway). No local setup required. See live
            screenshots streamed from the cloud browser. Quota applies per billing plan.
          </p>
        </Card>
      </div>

      <H3>Live Screenshot Feed</H3>
      <P>During cloud runs, a real-time screenshot of the browser is shown. Use Hide/Show Feed to toggle it. Auto-scroll can be enabled/disabled for the log panel.</P>

      <H3>Approval Flow</H3>
      <P>
        If a job requires manual input (e.g. complex form, captcha, or payment), the bot pauses and
        sends an approval request. You will see a prompt in the Agent page and receive a Telegram/Gmail
        notification with details and any tailored resume link.
      </P>

      <H3>Local Agent Logs</H3>
      <P>
        The log panel shows structured logs from the running task: timestamps, levels, and messages.
        Filters allow you to show only errors, warnings, or success events. Auto-scroll follows the
        latest log when enabled.
      </P>
    </div>
  );
}

function ApplicationsSection() {
  return (
    <div>
      <H2>Applications</H2>
      <P>Track every job the bot has applied to.</P>

      <H3>What you see</H3>
      <div className="space-y-2 mb-4">
        {[
          ["Job title & company", "Extracted from the job listing."],
          ["Status badge", "Applied, Viewed, Interview, Offer, Rejected."],
          ["Match score", "AI score at the time of application."],
          ["Tailored resume", "Download link if Tailor & Apply was used."],
          ["Applied date", "When the bot submitted the application."],
          ["Platform", "LinkedIn or Naukri."],
        ].map(([title, desc]) => (
          <div key={title as string} className="flex gap-3">
            <span className="text-amber-400 text-xs mt-0.5 shrink-0">▸</span>
            <div>
              <span className="font-mono text-xs text-white">{title}</span>
              <span className="font-body text-xs text-slate-400"> — {desc}</span>
            </div>
          </div>
        ))}
      </div>

      <H3>Filtering & Search</H3>
      <P>Filter by status, platform, or date range. Search by company or job title.</P>

      <H3>Email Thread Tracking</H3>
      <P>
        If Gmail automation is enabled, the system parses your inbox daily for offer and rejection
        emails and links them to the corresponding application automatically.
      </P>
    </div>
  );
}

function AnalyticsSection() {
  return (
    <div>
      <H2>Analytics</H2>
      <P>Visualise your job search performance with 7 real-time charts powered by your application data.</P>

      <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 mb-4">
        {[
          { title: "Applications Over Time", desc: "Daily count of applications submitted." },
          { title: "Status Breakdown", desc: "Pie chart of Applied / Interview / Offer / Rejected." },
          { title: "Platform Split", desc: "LinkedIn vs Naukri application share." },
          { title: "Match Score Distribution", desc: "Histogram of AI match scores across all applications." },
          { title: "Response Rate", desc: "Percentage of applications that received a reply." },
          { title: "Top Companies", desc: "Companies you have applied to most." },
          { title: "Weekly Heatmap", desc: "Activity heatmap by day of week and hour." },
        ].map(({ title, desc }) => (
          <Card key={title}>
            <p className="font-mono text-sm text-white font-semibold">{title}</p>
            <p className="font-body text-xs text-slate-400 mt-1">{desc}</p>
          </Card>
        ))}
      </div>
    </div>
  );
}

function StudioSection() {
  return (
    <div>
      <H2>Resume Studio</H2>
      <P>A full AI-powered resume editor and analyser.</P>

      <H3>Resume Analysis</H3>
      <P>Paste a job description alongside your resume. The AI scores the match (0–100) and returns missing skills, recommended improvements, and keywords to add.</P>

      <H3>Resume Tailoring</H3>
      <P>The studio rewrites your resume specifically for the pasted JD, targeting a high ATS score. You can download the tailored version as a PDF.</P>

      <H3>Cover Letter Generator</H3>
      <P>Generate a personalised cover letter from your resume + JD in one click.</P>

      <H3>Skill Gap Analysis</H3>
      <P>Identifies which skills you are missing for a target role and suggests learning resources for each gap.</P>

      <H3>Interview Prep</H3>
      <P>Generate likely interview questions and model answers tailored to the specific job and your background.</P>
    </div>
  );
}

function WorkflowSection() {
  return (
    <div>
      <H2>How It Works — Full Workflow</H2>

      <div className="overflow-x-auto mb-6">
        <div className="min-w-[480px] space-y-2">
          {[
            { label: "User configures profile + preferences", color: "blue" as const },
            { label: "User clicks Auto Apply / Tailor & Apply", color: "amber" as const },
            { label: "Frontend creates a task row in Supabase", color: "amber" as const },
            { label: "Python Task Runner polls DB and picks up the task", color: "green" as const },
            { label: "Runner scrapes LinkedIn / Naukri for matching jobs", color: "green" as const },
            { label: "AI scores each job against resume (Smart Match)", color: "violet" as const },
            { label: "Jobs below threshold are skipped", color: "red" as const },
            { label: "For Tailor & Apply: AI rewrites resume until target ATS score is met", color: "violet" as const },
            { label: "Tailored PDF saved to DB with Company — Role filename", color: "violet" as const },
            { label: "Bot fills and submits the application form (Easy Apply or External)", color: "green" as const },
            { label: "If stuck: sends Telegram/Gmail alert and awaits manual action", color: "amber" as const },
            { label: "After all jobs: sends batch summary report", color: "green" as const },
            { label: "Application records saved to DB for Applications + Analytics", color: "blue" as const },
          ].map(({ label, color }, i) => (
            <div key={i} className="flex items-start gap-3">
              <span className={`shrink-0 w-6 h-6 rounded-full flex items-center justify-center text-xs font-bold border ${
                color === "blue"   ? "bg-blue-400/10 border-blue-400/30 text-blue-400" :
                color === "amber"  ? "bg-amber-400/10 border-amber-400/30 text-amber-400" :
                color === "green"  ? "bg-emerald-400/10 border-emerald-400/30 text-emerald-400" :
                color === "violet" ? "bg-violet-400/10 border-violet-400/30 text-violet-400" :
                                     "bg-red-400/10 border-red-400/30 text-red-400"
              }`}>{i + 1}</span>
              <p className="font-body text-sm text-slate-300 pt-0.5">{label}</p>
            </div>
          ))}
        </div>
      </div>

      <H3>Key Technology</H3>
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
        {[
          { name: "Next.js 14", role: "Frontend + API routes" },
          { name: "Supabase", role: "Database, Auth, Storage, Real-time" },
          { name: "Playwright", role: "Browser automation (LinkedIn, Naukri)" },
          { name: "Claude AI", role: "Scoring, tailoring, form-filling, cover letters" },
          { name: "Railway", role: "Cloud execution environment" },
          { name: "Razorpay", role: "Subscription billing" },
          { name: "Telegram Bot", role: "Real-time notifications" },
          { name: "Gmail SMTP", role: "Email notifications + inbox parsing" },
        ].map(({ name, role }) => (
          <div key={name} className="flex items-center gap-2 p-2.5 rounded-lg border border-slate-800 bg-slate-900/40">
            <span className="font-mono text-xs text-amber-400 font-semibold min-w-[110px]">{name}</span>
            <span className="font-body text-xs text-slate-400">{role}</span>
          </div>
        ))}
      </div>
    </div>
  );
}

function PricingSection() {
  return (
    <div>
      <H2>Pricing</H2>
      <P>VantaHire offers flexible plans to match your job search intensity. All plans include access to the full feature set — limits apply per day.</P>

      <div className="grid grid-cols-1 sm:grid-cols-3 gap-4 mb-6">
        {[
          {
            name: "Free Trial",
            price: "Free",
            color: "blue" as const,
            features: [
              "5 auto-apply / day",
              "3 resume tailoring / day",
              "5 AI analyses / day",
              "LinkedIn + Naukri",
              "Smart Match scoring",
            ],
          },
          {
            name: "Pro",
            price: "₹999 / month",
            color: "amber" as const,
            features: [
              "50 auto-apply / day",
              "20 resume tailoring / day",
              "Unlimited AI analyses",
              "Cloud execution",
              "Telegram notifications",
              "Gmail inbox parsing",
              "Priority support",
            ],
          },
          {
            name: "Elite",
            price: "₹1,999 / month",
            color: "violet" as const,
            features: [
              "Unlimited auto-apply",
              "Unlimited tailoring",
              "All Pro features",
              "Dedicated cloud session",
              "Early access to new features",
            ],
          },
        ].map(({ name, price, color, features }) => (
          <Card key={name}>
            <Badge color={color}>{name}</Badge>
            <p className="font-display text-xl font-bold text-white mt-2 mb-3">{price}</p>
            <ul className="space-y-1.5">
              {features.map((f) => (
                <li key={f} className="flex items-start gap-2 font-body text-xs text-slate-300">
                  <span className="text-emerald-400 mt-0.5 shrink-0">✓</span>
                  {f}
                </li>
              ))}
            </ul>
          </Card>
        ))}
      </div>

      <P>
        Weekly plans are also available at a reduced rate. Upgrade or change plans anytime from the{" "}
        <span className="font-mono text-amber-400">Billing</span> tab.
      </P>
    </div>
  );
}

function SupportSection() {
  return (
    <div>
      <H2>Support</H2>
      <P>Need help? We are here for you.</P>

      <Card>
        <p className="font-mono text-sm text-white font-semibold mb-1">Email Support</p>
        <a
          href="mailto:anandanathurelangovan94@gmail.com"
          className="font-mono text-sm text-amber-400 hover:underline"
        >
          anandanathurelangovan94@gmail.com
        </a>
        <p className="font-body text-xs text-slate-400 mt-2">
          Response within 24 hours on business days. Include your account email and a description of the issue.
        </p>
      </Card>

      <H3>Common Issues</H3>
      <div className="space-y-3 mb-4">
        {[
          {
            q: "The bot is not picking up my task.",
            a: "Make sure the Python task runner is running (local mode) or Railway is configured (cloud mode). Check the Agent page for connection status.",
          },
          {
            q: "Smart Match is rejecting all jobs.",
            a: "Lower the Smart Match threshold in the Dashboard, or upload an updated resume that better reflects your target roles.",
          },
          {
            q: "Tailoring never reaches the target score.",
            a: "The AI makes up to 3 refinement attempts. If the JD has very niche requirements not in your resume, the target may not be reachable — consider lowering the target score or updating your resume.",
          },
          {
            q: "LinkedIn / Naukri login is failing.",
            a: "Re-enter your credentials in the Dashboard. For LinkedIn, make sure 2FA is not blocking the session. The bot uses a persistent browser profile to maintain login.",
          },
          {
            q: "I am not receiving Telegram notifications.",
            a: "Ensure your Telegram Chat ID is set in Settings → Notifications. Start a conversation with the bot first so it can send messages to you.",
          },
          {
            q: "Where are my tailored resumes?",
            a: "Go to Applications and look for the download icon on applications that used Tailor & Apply. Each PDF is named Company — Role.pdf.",
          },
        ].map(({ q, a }) => (
          <details key={q} className="group border border-slate-800 rounded-lg overflow-hidden">
            <summary className="px-4 py-3 font-mono text-sm text-slate-300 cursor-pointer hover:text-white list-none flex items-center justify-between">
              {q}
              <span className="text-slate-500 group-open:rotate-180 transition-transform">▾</span>
            </summary>
            <div className="px-4 pb-3">
              <p className="font-body text-sm text-slate-400">{a}</p>
            </div>
          </details>
        ))}
      </div>
    </div>
  );
}
