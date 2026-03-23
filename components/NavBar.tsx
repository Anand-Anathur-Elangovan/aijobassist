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

const NAV_LINKS = [
  { href: "/dashboard",      label: "Dashboard" },
  { href: "/agent",          label: "Agent" },
  { href: "/job-search",     label: "Job Search" },
  { href: "/resume-studio",  label: "Studio" },
  { href: "/interview-prep", label: "Interview" },
  { href: "/applications",   label: "Applications" },
  { href: "/analytics",      label: "Analytics" },
  { href: "/upload-resume",  label: "Resume" },
  { href: "/billing",        label: "Billing" },
];

export default function NavBar() {
  const pathname = usePathname();
  const router   = useRouter();
  const { user } = useAuth();
  const [unread, setUnread] = useState(0);
  const [menuOpen, setMenuOpen] = useState(false);

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
        <Link href="/dashboard" className="flex items-center gap-2 group shrink-0">
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
          {NAV_LINKS.map(({ href, label }) => {
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
          {NAV_LINKS.map(({ href, label }) => (
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
