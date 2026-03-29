"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { useAuth } from "@/context/AuthContext";
import { signOut, supabase } from "@/lib/supabase";

const SUPER_ADMINS = [
  "kaviyasaravanan01@gmail.com",
  "anandanathurelangovan94@gmail.com",
];

const JOB_SEEKER_LINKS = [
  { href: "/dashboard",       label: "Dashboard" },
  { href: "/agent",           label: "Agent" },
  { href: "/job-search",      label: "Job Search" },
  { href: "/resume-studio",   label: "Studio" },
  { href: "/interview-prep",  label: "Interview" },
  { href: "/applications",    label: "Applications" },
  { href: "/analytics",       label: "Analytics" },
  { href: "/notifications",   label: "Notifications" },
  { href: "/upload-resume",   label: "Resume" },
  { href: "/billing",         label: "Billing" },
  { href: "/docs",            label: "Docs" },
];

const STUDENT_LINKS = [
  { href: "/career-copilot",  label: "🎯 Career Copilot" },
  { href: "/billing",         label: "Billing" },
];

export default function NavBar() {
  const pathname = usePathname();
  const router   = useRouter();
  const { user } = useAuth();
  const [unread, setUnread] = useState(0);
  const [menuOpen, setMenuOpen] = useState(false);
  const [appMode, setAppMode] = useState<"job_seeker" | "student">("job_seeker");
  const [modeMenuOpen, setModeMenuOpen] = useState(false);

  // Load saved mode on mount
  useEffect(() => {
    const saved = localStorage.getItem("vantahire_app_mode") as "job_seeker" | "student" | null;
    if (saved) setAppMode(saved);
  }, []);

  const switchMode = async (mode: "job_seeker" | "student") => {
    setAppMode(mode);
    setModeMenuOpen(false);
    localStorage.setItem("vantahire_app_mode", mode);
    // Persist to DB best-effort
    if (user) {
      supabase.from("user_profiles").update({ app_mode: mode }).eq("user_id", user.id).then(() => {});
    }
    router.push(mode === "student" ? "/career-copilot" : "/dashboard");
  };

  useEffect(() => {
    if (!user) return;
    supabase
      .from("notifications")
      .select("id", { count: "exact", head: true })
      .eq("user_id", user.id)
      .eq("read", false)
      .then(({ count }) => setUnread(count ?? 0));
  }, [user]);

  const handleSignOut = async () => {
    await signOut();
    router.replace("/login");
  };

  return (
    <header className="sticky top-0 z-50 border-b border-slate-800 bg-slate-950/80 backdrop-blur-md">
      <div className="max-w-7xl mx-auto px-6 h-16 flex items-center justify-between">
        {/* Logo */}
        <Link href={appMode === "student" ? "/career-copilot" : "/dashboard"} className="flex items-center gap-2 group shrink-0">
          <span className="w-6 h-6 bg-amber-400 rounded-sm flex items-center justify-center">
            <svg width="14" height="14" viewBox="0 0 14 14" fill="none">
              <path d="M2 2h4v4H2zM8 2h4v4H8zM2 8h4v4H2zM8 8h4v4H8z" fill="#0a0e1a" />
            </svg>
          </span>
          <span className="font-display font-bold text-white text-lg tracking-tight">
            Vanta<span className="text-amber-400">Hire</span>
          </span>
        </Link>

        {/* Nav Links — desktop */}
        <nav className="hidden lg:flex items-center gap-1">
          {(appMode === "student" ? STUDENT_LINKS : JOB_SEEKER_LINKS).map(({ href, label }) => {
            const active = pathname === href;
            return (
              <Link
                key={href}
                href={href}
                className={`px-3 py-1.5 rounded font-body text-sm font-medium transition-all duration-150 ${
                  active
                    ? "bg-amber-400/10 text-amber-400 border border-amber-400/30"
                    : "text-slate-400 hover:text-white hover:bg-slate-800"
                }`}
              >
                {label}
              </Link>
            );
          })}
          {SUPER_ADMINS.includes(user?.email ?? "") && (
            <Link
              href="/admin"
              className={`px-3 py-1.5 rounded font-body text-sm font-medium transition-all duration-150 ${
                pathname === "/admin"
                  ? "bg-red-500/10 text-red-400 border border-red-400/30"
                  : "text-red-400/60 hover:text-red-400 hover:bg-slate-800"
              }`}
            >
              Admin
            </Link>
          )}
        </nav>

        {/* Right side */}
        <div className="flex items-center gap-2">
          {/* Notification bell */}
          <Link href="/notifications" className="relative p-2 text-slate-400 hover:text-white">
            🔔
            {unread > 0 && (
              <span className="absolute top-1 right-1 w-4 h-4 bg-amber-400 text-slate-950 text-[10px] font-bold rounded-full flex items-center justify-center leading-none">
                {unread > 9 ? "9+" : unread}
              </span>
            )}
          </Link>

          {/* Mode switcher */}
          <div className="relative">
            <button
              onClick={() => setModeMenuOpen((v) => !v)}
              className={`hidden md:flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-semibold border transition-all ${
                appMode === "student"
                  ? "bg-purple-500/10 border-purple-500/30 text-purple-400 hover:bg-purple-500/20"
                  : "bg-slate-800 border-slate-700 text-slate-400 hover:text-white"
              }`}
            >
              {appMode === "student" ? "🎓 Student" : "💼 Job Seeker"}
              <span className="opacity-60">▾</span>
            </button>
            {modeMenuOpen && (
              <div className="absolute right-0 top-full mt-1 w-44 bg-slate-900 border border-slate-700 rounded-lg shadow-xl z-50 overflow-hidden">
                <button
                  onClick={() => switchMode("job_seeker")}
                  className={`w-full text-left px-3 py-2.5 text-sm flex items-center gap-2 transition-colors ${
                    appMode === "job_seeker" ? "bg-amber-400/10 text-amber-400" : "text-slate-300 hover:bg-slate-800"
                  }`}
                >
                  💼 Job Seeker{appMode === "job_seeker" && " ✓"}
                </button>
                <button
                  onClick={() => switchMode("student")}
                  className={`w-full text-left px-3 py-2.5 text-sm flex items-center gap-2 transition-colors ${
                    appMode === "student" ? "bg-purple-500/10 text-purple-400" : "text-slate-300 hover:bg-slate-800"
                  }`}
                >
                  🎓 Student{appMode === "student" && " ✓"}
                </button>
              </div>
            )}
          </div>

          {/* Settings */}
          <Link href="/settings" className="p-2 text-slate-400 hover:text-white">
            ⚙️
          </Link>

          <span className="font-mono text-xs text-slate-500 hidden md:block truncate max-w-[140px]">
            {user?.email}
          </span>
          <button
            onClick={handleSignOut}
            className="px-3 py-1.5 rounded border border-slate-700 text-slate-400 hover:text-white hover:border-slate-500 text-sm font-body transition-all duration-150"
          >
            Sign out
          </button>

          {/* Mobile hamburger */}
          <button
            onClick={() => setMenuOpen((o) => !o)}
            className="lg:hidden p-2 text-slate-400 hover:text-white"
          >
            {menuOpen ? "✕" : "☰"}
          </button>
        </div>
      </div>

      {/* Mobile menu */}
      {menuOpen && (
        <div className="lg:hidden border-t border-slate-800 bg-slate-950 px-6 py-3 space-y-1">
          {/* Mobile mode switcher */}
          <div className="flex gap-2 mb-2 pt-1">
            <button
              onClick={() => switchMode("job_seeker")}
              className={`flex-1 py-2 rounded text-xs font-semibold border transition-all ${
                appMode === "job_seeker"
                  ? "bg-amber-400/10 border-amber-400/30 text-amber-400"
                  : "border-slate-700 text-slate-500 hover:text-white"
              }`}
            >💼 Job Seeker</button>
            <button
              onClick={() => switchMode("student")}
              className={`flex-1 py-2 rounded text-xs font-semibold border transition-all ${
                appMode === "student"
                  ? "bg-purple-500/10 border-purple-500/30 text-purple-400"
                  : "border-slate-700 text-slate-500 hover:text-white"
              }`}
            >🎓 Student</button>
          </div>
          {(appMode === "student" ? STUDENT_LINKS : JOB_SEEKER_LINKS).map(({ href, label }) => (
            <Link
              key={href}
              href={href}
              onClick={() => setMenuOpen(false)}
              className={`block px-3 py-2 rounded text-sm font-body transition-colors ${
                pathname === href
                  ? "bg-amber-400/10 text-amber-400"
                  : "text-slate-400 hover:text-white hover:bg-slate-800"
              }`}
            >
              {label}
            </Link>
          ))}
        </div>
      )}
    </header>
  );
}
