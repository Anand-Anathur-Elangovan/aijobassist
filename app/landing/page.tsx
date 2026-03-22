"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { useAuth } from "@/context/AuthContext";
import { useRouter } from "next/navigation";

const FEATURES = [
  {
    icon: "🤖",
    title: "AI Auto-Apply",
    desc: "Automatically apply to jobs on LinkedIn & Naukri with AI-tailored resumes. Set it and forget it.",
  },
  {
    icon: "📝",
    title: "Resume Studio",
    desc: "AI analyzes job descriptions and rewrites your resume to maximize ATS match score.",
  },
  {
    icon: "📊",
    title: "Match Score Engine",
    desc: "Real-time compatibility scoring between your resume and any job posting.",
  },
  {
    icon: "💌",
    title: "Cover Letter AI",
    desc: "Generate personalized cover letters, LinkedIn intros, and email drafts in seconds.",
  },
  {
    icon: "📧",
    title: "Gmail Monitor",
    desc: "Auto-detect interview invites, rejections, and follow-up reminders from your inbox.",
  },
  {
    icon: "📈",
    title: "Smart Analytics",
    desc: "Track applications, response rates, and optimize your job search strategy.",
  },
];

const STEPS = [
  { num: "01", title: "Upload Resume", desc: "Drop your PDF and we'll parse it instantly." },
  { num: "02", title: "Set Preferences", desc: "Choose roles, locations, salary range, and platforms." },
  { num: "03", title: "Launch Automation", desc: "VantaHire applies to matching jobs 24/7." },
  { num: "04", title: "Track & Optimize", desc: "Monitor applications, tweak settings, land interviews." },
];

const TESTIMONIALS = [
  {
    name: "Priya S.",
    role: "SDE II at Amazon",
    text: "VantaHire applied to 200+ jobs in a week. I got 12 interview calls. The resume tailoring is incredible!",
  },
  {
    name: "Rahul K.",
    role: "Full-Stack Developer",
    text: "The auto-apply saved me hours every day. My ATS score jumped from 45% to 89% with AI tailoring.",
  },
  {
    name: "Anjali M.",
    role: "Product Manager",
    text: "The Gmail monitor caught an interview invite I almost missed. Lifesaver during my job search!",
  },
];

export default function LandingPage() {
  const { user, loading } = useAuth();
  const router = useRouter();
  const [scrolled, setScrolled] = useState(false);

  useEffect(() => {
    const onScroll = () => setScrolled(window.scrollY > 20);
    window.addEventListener("scroll", onScroll);
    return () => window.removeEventListener("scroll", onScroll);
  }, []);

  // If authenticated, redirect to dashboard
  useEffect(() => {
    if (!loading && user) {
      router.replace("/dashboard");
    }
  }, [user, loading, router]);

  if (loading) {
    return (
      <div className="min-h-screen bg-slate-950 flex items-center justify-center">
        <div className="w-8 h-8 border-2 border-amber-400 border-t-transparent rounded-full animate-spin" />
      </div>
    );
  }

  if (user) return null;

  return (
    <div className="min-h-screen bg-slate-950 text-white">
      {/* Navigation */}
      <header
        className={`fixed top-0 inset-x-0 z-50 transition-all duration-300 ${
          scrolled ? "bg-slate-950/90 backdrop-blur-md border-b border-slate-800" : ""
        }`}
      >
        <div className="max-w-7xl mx-auto px-6 h-16 flex items-center justify-between">
          <div className="flex items-center gap-2">
            <span className="w-7 h-7 bg-amber-400 rounded-sm flex items-center justify-center">
              <svg width="14" height="14" viewBox="0 0 14 14" fill="none">
                <path d="M2 2h4v4H2zM8 2h4v4H8zM2 8h4v4H2zM8 8h4v4H8z" fill="#0a0e1a" />
              </svg>
            </span>
            <span className="font-display font-bold text-xl tracking-tight">
              Vanta<span className="text-amber-400">Hire</span>
            </span>
          </div>
          <nav className="hidden md:flex items-center gap-6 text-sm text-slate-400">
            <a href="#features" className="hover:text-white transition-colors">Features</a>
            <a href="#how-it-works" className="hover:text-white transition-colors">How it Works</a>
            <a href="#pricing" className="hover:text-white transition-colors">Pricing</a>
            <a href="#testimonials" className="hover:text-white transition-colors">Testimonials</a>
          </nav>
          <div className="flex items-center gap-3">
            <Link
              href="/login"
              className="px-4 py-2 text-sm text-slate-300 hover:text-white transition-colors"
            >
              Sign In
            </Link>
            <Link
              href="/login"
              className="px-4 py-2 bg-amber-400 text-slate-950 text-sm font-semibold rounded-lg hover:bg-amber-300 transition-colors"
            >
              Start Free Trial
            </Link>
          </div>
        </div>
      </header>

      {/* Hero */}
      <section className="pt-32 pb-20 px-6 relative overflow-hidden">
        {/* Grid background */}
        <div
          className="absolute inset-0 opacity-[0.03]"
          style={{
            backgroundImage:
              "linear-gradient(#1e2d4a 1px, transparent 1px), linear-gradient(90deg, #1e2d4a 1px, transparent 1px)",
            backgroundSize: "48px 48px",
          }}
        />
        <div className="absolute top-1/4 left-1/2 -translate-x-1/2 w-[600px] h-[600px] bg-amber-400/5 rounded-full blur-[120px]" />

        <div className="max-w-4xl mx-auto text-center relative z-10">
          <div className="inline-block px-4 py-1.5 bg-amber-400/10 border border-amber-400/20 rounded-full text-amber-400 text-sm font-medium mb-6">
            🚀 AI-Powered Job Search Automation
          </div>
          <h1 className="text-5xl md:text-7xl font-display font-bold leading-tight mb-6">
            Land Your Dream Job on{" "}
            <span className="gradient-text">Autopilot</span>
          </h1>
          <p className="text-lg md:text-xl text-slate-400 max-w-2xl mx-auto mb-10 leading-relaxed">
            VantaHire tailors your resume with AI, auto-applies to matching jobs on LinkedIn & Naukri,
            and monitors your Gmail for interview invites — all while you sleep.
          </p>
          <div className="flex flex-col sm:flex-row items-center justify-center gap-4">
            <Link
              href="/login"
              className="px-8 py-4 bg-amber-400 text-slate-950 font-bold text-lg rounded-xl hover:bg-amber-300 transition-all shadow-lg shadow-amber-400/20"
            >
              Start 10-Day Free Trial →
            </Link>
            <a
              href="#how-it-works"
              className="px-8 py-4 border border-slate-700 text-slate-300 font-medium rounded-xl hover:border-slate-500 hover:text-white transition-all"
            >
              See How It Works
            </a>
          </div>
          <p className="mt-4 text-sm text-slate-500">No credit card required • 10-day full access</p>
        </div>

        {/* Stats */}
        <div className="max-w-3xl mx-auto mt-16 grid grid-cols-3 gap-8 text-center relative z-10">
          {[
            { value: "10,000+", label: "Jobs Applied" },
            { value: "89%", label: "Avg ATS Score" },
            { value: "3x", label: "More Interviews" },
          ].map(({ value, label }) => (
            <div key={label}>
              <div className="text-3xl md:text-4xl font-display font-bold text-amber-400">{value}</div>
              <div className="text-slate-400 text-sm mt-1">{label}</div>
            </div>
          ))}
        </div>
      </section>

      {/* Features */}
      <section id="features" className="py-20 px-6 bg-slate-900/50">
        <div className="max-w-6xl mx-auto">
          <div className="text-center mb-14">
            <h2 className="text-3xl md:text-4xl font-display font-bold">
              Everything You Need to <span className="text-amber-400">Win</span>
            </h2>
            <p className="text-slate-400 mt-3 max-w-xl mx-auto">
              From AI resume optimization to automated applications — VantaHire handles it all.
            </p>
          </div>
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
            {FEATURES.map(({ icon, title, desc }) => (
              <div
                key={title}
                className="card hover:border-amber-400/30 transition-all group"
              >
                <div className="text-3xl mb-4 group-hover:scale-110 transition-transform">
                  {icon}
                </div>
                <h3 className="text-lg font-display font-bold text-white mb-2">{title}</h3>
                <p className="text-slate-400 text-sm leading-relaxed">{desc}</p>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* How it works */}
      <section id="how-it-works" className="py-20 px-6">
        <div className="max-w-4xl mx-auto">
          <div className="text-center mb-14">
            <h2 className="text-3xl md:text-4xl font-display font-bold">
              How It <span className="text-amber-400">Works</span>
            </h2>
          </div>
          <div className="space-y-8">
            {STEPS.map(({ num, title, desc }, i) => (
              <div key={num} className="flex gap-6 items-start animate-fadeUp" style={{ animationDelay: `${i * 0.1}s` }}>
                <div className="w-12 h-12 shrink-0 rounded-lg bg-amber-400/10 border border-amber-400/20 flex items-center justify-center font-display font-bold text-amber-400">
                  {num}
                </div>
                <div>
                  <h3 className="font-display font-bold text-white text-lg">{title}</h3>
                  <p className="text-slate-400 mt-1">{desc}</p>
                </div>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* Pricing preview */}
      <section id="pricing" className="py-20 px-6 bg-slate-900/50">
        <div className="max-w-4xl mx-auto text-center">
          <h2 className="text-3xl md:text-4xl font-display font-bold mb-4">
            Simple, Transparent <span className="text-amber-400">Pricing</span>
          </h2>
          <p className="text-slate-400 mb-10 max-w-xl mx-auto">
            Start free. Upgrade when you need more power.
          </p>
          <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
            {[
              { name: "Free", price: "₹0", period: "forever", features: ["10 Semi-Auto/day", "1 AI Tailor/day", "3 Gmail scans/day", "Basic analytics"], cta: "Get Started" },
              { name: "Pro", price: "₹999", period: "/month", features: ["25 Auto Apply/day", "75 Semi-Auto/day", "15 AI Tailor/day", "25 Gmail scans/day", "Full analytics"], cta: "Start Trial", popular: true },
              { name: "Premium", price: "₹1,999", period: "/month", features: ["80 Auto Apply/day", "200 Semi-Auto/day", "40 AI Tailor/day", "75 Gmail scans/day", "Priority support"], cta: "Start Trial" },
            ].map(({ name, price, period, features, cta, popular }) => (
              <div
                key={name}
                className={`card text-left relative ${popular ? "border-amber-400/50 shadow-lg shadow-amber-400/5" : ""}`}
              >
                {popular && (
                  <div className="absolute -top-3 left-1/2 -translate-x-1/2 px-3 py-0.5 bg-amber-400 text-slate-950 text-xs font-bold rounded-full">
                    POPULAR
                  </div>
                )}
                <h3 className="font-display font-bold text-xl text-white">{name}</h3>
                <div className="mt-3 mb-4">
                  <span className="text-3xl font-display font-bold text-white">{price}</span>
                  <span className="text-slate-400 text-sm">{period}</span>
                </div>
                <ul className="space-y-2 mb-6">
                  {features.map((f) => (
                    <li key={f} className="flex items-center gap-2 text-sm text-slate-300">
                      <span className="text-emerald-400">✓</span> {f}
                    </li>
                  ))}
                </ul>
                <Link
                  href="/login"
                  className={`block text-center py-2.5 rounded-lg font-semibold text-sm transition-all ${
                    popular
                      ? "bg-amber-400 text-slate-950 hover:bg-amber-300"
                      : "bg-slate-800 text-slate-300 hover:bg-slate-700"
                  }`}
                >
                  {cta}
                </Link>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* Testimonials */}
      <section id="testimonials" className="py-20 px-6">
        <div className="max-w-4xl mx-auto">
          <h2 className="text-3xl md:text-4xl font-display font-bold text-center mb-12">
            Loved by <span className="text-amber-400">Job Seekers</span>
          </h2>
          <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
            {TESTIMONIALS.map(({ name, role, text }) => (
              <div key={name} className="card">
                <p className="text-slate-300 text-sm leading-relaxed mb-4">&ldquo;{text}&rdquo;</p>
                <div>
                  <p className="text-white font-semibold text-sm">{name}</p>
                  <p className="text-slate-500 text-xs">{role}</p>
                </div>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* CTA */}
      <section className="py-20 px-6 bg-slate-900/50">
        <div className="max-w-3xl mx-auto text-center">
          <h2 className="text-3xl md:text-4xl font-display font-bold mb-4">
            Ready to <span className="text-amber-400">Automate</span> Your Job Search?
          </h2>
          <p className="text-slate-400 mb-8">
            Join thousands of job seekers landing interviews on autopilot.
          </p>
          <Link
            href="/login"
            className="inline-block px-8 py-4 bg-amber-400 text-slate-950 font-bold text-lg rounded-xl hover:bg-amber-300 transition-all shadow-lg shadow-amber-400/20"
          >
            Start Your Free Trial →
          </Link>
          <p className="mt-3 text-sm text-slate-500">No credit card required</p>
        </div>
      </section>

      {/* Footer */}
      <footer className="border-t border-slate-800 py-12 px-6">
        <div className="max-w-6xl mx-auto">
          <div className="grid grid-cols-2 md:grid-cols-4 gap-8 mb-8">
            <div>
              <div className="flex items-center gap-2 mb-4">
                <span className="w-6 h-6 bg-amber-400 rounded-sm flex items-center justify-center">
                  <svg width="12" height="12" viewBox="0 0 14 14" fill="none">
                    <path d="M2 2h4v4H2zM8 2h4v4H8zM2 8h4v4H2zM8 8h4v4H8z" fill="#0a0e1a" />
                  </svg>
                </span>
                <span className="font-display font-bold">
                  Vanta<span className="text-amber-400">Hire</span>
                </span>
              </div>
              <p className="text-slate-500 text-sm">AI-powered job search automation.</p>
            </div>
            <div>
              <h4 className="font-semibold text-white text-sm mb-3">Product</h4>
              <ul className="space-y-2 text-sm text-slate-400">
                <li><a href="#features" className="hover:text-white">Features</a></li>
                <li><a href="#pricing" className="hover:text-white">Pricing</a></li>
                <li><a href="#how-it-works" className="hover:text-white">How It Works</a></li>
              </ul>
            </div>
            <div>
              <h4 className="font-semibold text-white text-sm mb-3">Legal</h4>
              <ul className="space-y-2 text-sm text-slate-400">
                <li><Link href="/privacy" className="hover:text-white">Privacy Policy</Link></li>
                <li><Link href="/terms" className="hover:text-white">Terms of Service</Link></li>
                <li><Link href="/refund" className="hover:text-white">Refund Policy</Link></li>
              </ul>
            </div>
            <div>
              <h4 className="font-semibold text-white text-sm mb-3">Support</h4>
              <ul className="space-y-2 text-sm text-slate-400">
                <li><a href="mailto:support@vantahire.com" className="hover:text-white">Email Support</a></li>
                <li><Link href="/contact" className="hover:text-white">Contact Us</Link></li>
              </ul>
            </div>
          </div>
          <div className="border-t border-slate-800 pt-6 text-center text-slate-500 text-sm">
            © {new Date().getFullYear()} VantaHire. All rights reserved.
          </div>
        </div>
      </footer>
    </div>
  );
}
