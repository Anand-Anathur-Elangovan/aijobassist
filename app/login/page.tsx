"use client";

import { useState, useEffect } from "react";
import { useRouter } from "next/navigation";
import { useAuth } from "@/context/AuthContext";
import { signIn, signUp } from "@/lib/supabase";

type Tab = "signin" | "signup";

export default function LoginPage() {
  const [tab, setTab] = useState<Tab>("signin");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  const { user, loading: authLoading } = useAuth();
  const router = useRouter();

  // Redirect if already authenticated
  useEffect(() => {
    if (!authLoading && user) {
      router.replace("/dashboard");
    }
  }, [user, authLoading, router]);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    setSuccess(null);
    setLoading(true);

    try {
      if (tab === "signup") {
        const { error } = await signUp(email, password);
        if (error) throw error;
        setSuccess("Check your email to confirm your account.");
      } else {
        const { error } = await signIn(email, password);
        if (error) throw error;
        router.replace("/dashboard");
      }
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Something went wrong.");
    } finally {
      setLoading(false);
    }
  };

  return (
    <main className="min-h-screen flex">
      {/* ── Left panel: branding ── */}
      <div className="hidden lg:flex flex-col justify-between w-[480px] flex-shrink-0 p-12 bg-slate-900 border-r border-slate-800 relative overflow-hidden">
        {/* Decorative grid */}
        <div
          className="absolute inset-0 opacity-[0.04]"
          style={{
            backgroundImage:
              "linear-gradient(var(--border) 1px, transparent 1px), linear-gradient(90deg, var(--border) 1px, transparent 1px)",
            backgroundSize: "40px 40px",
          }}
        />
        {/* Glow */}
        <div className="absolute top-1/3 left-1/2 -translate-x-1/2 -translate-y-1/2 w-64 h-64 bg-amber-400/5 rounded-full blur-3xl pointer-events-none" />

        <div className="relative">
          <div className="flex items-center gap-2 mb-16">
            <span className="w-7 h-7 bg-amber-400 rounded-sm flex items-center justify-center">
              <svg width="15" height="15" viewBox="0 0 14 14" fill="none">
                <path d="M2 2h4v4H2zM8 2h4v4H8zM2 8h4v4H2zM8 8h4v4H8z" fill="#0a0e1a" />
              </svg>
            </span>
            <span className="font-display font-bold text-white text-xl tracking-tight">
              Vanta<span className="text-amber-400">Hire</span>
            </span>
          </div>

          <h2 className="font-display font-bold text-4xl text-white leading-tight mb-4">
            Your career,
            <br />
            <span className="gradient-text">engineered.</span>
          </h2>
          <p className="text-slate-400 font-body text-base leading-relaxed">
            Upload your resume, define your dream role, and let intelligent
            matching surface the opportunities you deserve.
          </p>
        </div>

        <div className="relative space-y-5">
          {[
            { icon: "📄", label: "Resume parsing & analysis" },
            { icon: "🎯", label: "Preference-based job matching" },
            { icon: "🔐", label: "Secure session management" },
          ].map(({ icon, label }) => (
            <div key={label} className="flex items-center gap-3">
              <span className="text-lg">{icon}</span>
              <span className="text-slate-300 font-body text-sm">{label}</span>
            </div>
          ))}
        </div>
      </div>

      {/* ── Right panel: form ── */}
      <div className="flex-1 flex items-center justify-center px-6 py-16 bg-slate-950 relative">
        <div
          className="absolute inset-0 opacity-[0.03]"
          style={{
            backgroundImage:
              "radial-gradient(circle, var(--accent) 1px, transparent 1px)",
            backgroundSize: "32px 32px",
          }}
        />

        <div className="relative w-full max-w-[400px] animate-fadeUp">
          {/* Mobile logo */}
          <div className="flex items-center gap-2 mb-10 lg:hidden">
            <span className="w-6 h-6 bg-amber-400 rounded-sm flex items-center justify-center">
              <svg width="13" height="13" viewBox="0 0 14 14" fill="none">
                <path d="M2 2h4v4H2zM8 2h4v4H8zM2 8h4v4H2zM8 8h4v4H8z" fill="#0a0e1a" />
              </svg>
            </span>
            <span className="font-display font-bold text-white text-lg">
              Vanta<span className="text-amber-400">Hire</span>
            </span>
          </div>

          {/* Tabs */}
          <div className="flex rounded-lg bg-slate-900 border border-slate-800 p-1 mb-8">
            {(["signin", "signup"] as Tab[]).map((t) => (
              <button
                key={t}
                onClick={() => { setTab(t); setError(null); setSuccess(null); }}
                className={`flex-1 py-2 rounded-md font-body text-sm font-medium transition-all duration-150 ${
                  tab === t
                    ? "bg-amber-400 text-slate-950"
                    : "text-slate-400 hover:text-white"
                }`}
              >
                {t === "signin" ? "Sign In" : "Create Account"}
              </button>
            ))}
          </div>

          <div className="animate-fadeUp-delay-1">
            <h1 className="font-display font-bold text-2xl text-white mb-1">
              {tab === "signin" ? "Welcome back" : "Get started"}
            </h1>
            <p className="text-slate-500 font-body text-sm mb-8">
              {tab === "signin"
                ? "Sign in to your VantaHire account"
                : "Create your free account today"}
            </p>
          </div>

          <form onSubmit={handleSubmit} className="space-y-4 animate-fadeUp-delay-2">
            <div>
              <label className="block font-body text-xs font-medium text-slate-400 uppercase tracking-widest mb-2">
                Email
              </label>
              <input
                className="input-base"
                type="email"
                placeholder="you@company.com"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                required
                autoComplete="email"
              />
            </div>

            <div>
              <label className="block font-body text-xs font-medium text-slate-400 uppercase tracking-widest mb-2">
                Password
              </label>
              <input
                className="input-base"
                type="password"
                placeholder={tab === "signup" ? "Min. 8 characters" : "••••••••"}
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                required
                minLength={tab === "signup" ? 8 : 1}
                autoComplete={tab === "signin" ? "current-password" : "new-password"}
              />
            </div>

            {error && (
              <div className="rounded-lg bg-red-500/10 border border-red-500/20 px-4 py-3 text-red-400 font-body text-sm">
                {error}
              </div>
            )}

            {success && (
              <div className="rounded-lg bg-emerald-500/10 border border-emerald-500/20 px-4 py-3 text-emerald-400 font-body text-sm">
                {success}
              </div>
            )}

            <button
              type="submit"
              disabled={loading}
              className="btn-primary w-full mt-2"
            >
              {loading
                ? "Please wait…"
                : tab === "signin"
                ? "Sign In →"
                : "Create Account →"}
            </button>
          </form>

          <p className="mt-8 text-center text-slate-600 font-mono text-xs">
            Protected by Supabase Auth
          </p>
        </div>
      </div>
    </main>
  );
}
