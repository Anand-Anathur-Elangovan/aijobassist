"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { useAuth } from "@/context/AuthContext";
import { updateUserProfile, getUserProfile } from "@/lib/billing";

const STEPS = [
  { key: "welcome", title: "Welcome to VantaHire" },
  { key: "profile", title: "Tell us about you" },
  { key: "preferences", title: "Job Preferences" },
  { key: "resume", title: "Upload Resume" },
  { key: "done", title: "You're all set!" },
];

export default function OnboardingPage() {
  const { user } = useAuth();
  const router = useRouter();
  const [step, setStep] = useState(0);
  const [loading, setLoading] = useState(true);

  // Profile fields
  const [fullName, setFullName] = useState("");
  const [phone, setPhone] = useState("");
  const [country, setCountry] = useState("India");

  // Job preferences
  const [roles, setRoles] = useState("");
  const [locations, setLocations] = useState("");
  const [experience, setExperience] = useState("0-2");
  const [jobType, setJobType] = useState("full-time");
  const [platforms, setPlatforms] = useState<string[]>(["linkedin"]);

  useEffect(() => {
    if (user) checkOnboarding();
  }, [user]);

  async function checkOnboarding() {
    if (!user) return;
    const profile = await getUserProfile(user.id);
    if (profile?.onboarding_done) {
      router.replace("/dashboard");
      return;
    }
    if (profile) {
      setFullName(profile.full_name || "");
      setPhone(profile.phone || "");
    }
    setLoading(false);
  }

  async function completeOnboarding() {
    if (!user) return;
    await updateUserProfile(user.id, {
      full_name: fullName,
      phone,
      country,
      onboarding_done: true,
    });
    router.replace("/dashboard");
  }

  function togglePlatform(p: string) {
    setPlatforms((prev) =>
      prev.includes(p) ? prev.filter((x) => x !== p) : [...prev, p]
    );
  }

  if (loading) {
    return (
      <main className="min-h-screen bg-slate-950 flex items-center justify-center">
        <div className="w-8 h-8 border-2 border-amber-400 border-t-transparent rounded-full animate-spin" />
      </main>
    );
  }

  return (
    <main className="min-h-screen bg-slate-950 flex items-center justify-center p-6">
      <div className="w-full max-w-lg">
        {/* Progress */}
        <div className="flex items-center gap-2 mb-8">
          {STEPS.map((s, i) => (
            <div
              key={s.key}
              className={`flex-1 h-1.5 rounded-full transition-all ${
                i <= step ? "bg-amber-400" : "bg-slate-800"
              }`}
            />
          ))}
        </div>

        <div className="card animate-fadeUp">
          {/* Step 0: Welcome */}
          {step === 0 && (
            <div className="text-center py-8">
              <div className="text-5xl mb-4">🚀</div>
              <h1 className="text-2xl font-display font-bold text-white mb-3">
                Welcome to Vanta<span className="text-amber-400">Hire</span>
              </h1>
              <p className="text-slate-400 mb-8 max-w-sm mx-auto">
                Let&apos;s set up your account in 2 minutes. AI-powered job search automation awaits!
              </p>
              <div className="space-y-3 text-left max-w-xs mx-auto mb-8">
                {[
                  "📝 10-day free trial — full access",
                  "🤖 AI resume tailoring & auto-apply",
                  "📧 Gmail interview detection",
                  "📊 Analytics & tracking",
                ].map((f) => (
                  <div key={f} className="flex items-center gap-2 text-sm text-slate-300">{f}</div>
                ))}
              </div>
              <button onClick={() => setStep(1)} className="btn-primary w-full">
                Let&apos;s Get Started →
              </button>
            </div>
          )}

          {/* Step 1: Profile */}
          {step === 1 && (
            <div>
              <h2 className="text-xl font-display font-bold text-white mb-1">{STEPS[1].title}</h2>
              <p className="text-slate-400 text-sm mb-6">Basic info for your applications</p>
              <div className="space-y-4">
                <div>
                  <label className="block text-sm text-slate-400 mb-1">Full Name *</label>
                  <input
                    type="text"
                    value={fullName}
                    onChange={(e) => setFullName(e.target.value)}
                    className="input-base"
                    placeholder="John Doe"
                  />
                </div>
                <div>
                  <label className="block text-sm text-slate-400 mb-1">Phone</label>
                  <input
                    type="tel"
                    value={phone}
                    onChange={(e) => setPhone(e.target.value)}
                    className="input-base"
                    placeholder="+91 98765 43210"
                  />
                </div>
                <div>
                  <label className="block text-sm text-slate-400 mb-1">Country</label>
                  <select value={country} onChange={(e) => setCountry(e.target.value)} className="input-base">
                    <option value="India">India</option>
                    <option value="United States">United States</option>
                    <option value="United Kingdom">United Kingdom</option>
                    <option value="Canada">Canada</option>
                    <option value="Australia">Australia</option>
                    <option value="Other">Other</option>
                  </select>
                </div>
              </div>
              <div className="flex gap-3 mt-6">
                <button onClick={() => setStep(0)} className="px-4 py-2 border border-slate-700 text-slate-400 rounded-lg text-sm">
                  Back
                </button>
                <button
                  onClick={() => setStep(2)}
                  disabled={!fullName.trim()}
                  className="btn-primary flex-1"
                >
                  Continue →
                </button>
              </div>
            </div>
          )}

          {/* Step 2: Job Preferences */}
          {step === 2 && (
            <div>
              <h2 className="text-xl font-display font-bold text-white mb-1">{STEPS[2].title}</h2>
              <p className="text-slate-400 text-sm mb-6">Help us find the right jobs for you</p>
              <div className="space-y-4">
                <div>
                  <label className="block text-sm text-slate-400 mb-1">Desired Roles (comma-separated)</label>
                  <input
                    type="text"
                    value={roles}
                    onChange={(e) => setRoles(e.target.value)}
                    className="input-base"
                    placeholder="Software Engineer, Full-Stack Developer, Backend Developer"
                  />
                </div>
                <div>
                  <label className="block text-sm text-slate-400 mb-1">Preferred Locations</label>
                  <input
                    type="text"
                    value={locations}
                    onChange={(e) => setLocations(e.target.value)}
                    className="input-base"
                    placeholder="Bangalore, Remote, Hyderabad"
                  />
                </div>
                <div className="grid grid-cols-2 gap-4">
                  <div>
                    <label className="block text-sm text-slate-400 mb-1">Experience</label>
                    <select value={experience} onChange={(e) => setExperience(e.target.value)} className="input-base">
                      <option value="0-2">0-2 years</option>
                      <option value="2-5">2-5 years</option>
                      <option value="5-8">5-8 years</option>
                      <option value="8+">8+ years</option>
                    </select>
                  </div>
                  <div>
                    <label className="block text-sm text-slate-400 mb-1">Job Type</label>
                    <select value={jobType} onChange={(e) => setJobType(e.target.value)} className="input-base">
                      <option value="full-time">Full-time</option>
                      <option value="part-time">Part-time</option>
                      <option value="contract">Contract</option>
                      <option value="internship">Internship</option>
                    </select>
                  </div>
                </div>
                <div>
                  <label className="block text-sm text-slate-400 mb-2">Platforms</label>
                  <div className="flex gap-3">
                    {["linkedin", "naukri"].map((p) => (
                      <button
                        key={p}
                        onClick={() => togglePlatform(p)}
                        className={`px-4 py-2 rounded-lg text-sm font-medium transition-all border ${
                          platforms.includes(p)
                            ? "bg-amber-400/10 text-amber-400 border-amber-400/30"
                            : "text-slate-400 border-slate-700 hover:border-slate-500"
                        }`}
                      >
                        {p === "linkedin" ? "LinkedIn" : "Naukri"}
                      </button>
                    ))}
                  </div>
                </div>
              </div>
              <div className="flex gap-3 mt-6">
                <button onClick={() => setStep(1)} className="px-4 py-2 border border-slate-700 text-slate-400 rounded-lg text-sm">
                  Back
                </button>
                <button onClick={() => setStep(3)} className="btn-primary flex-1">
                  Continue →
                </button>
              </div>
            </div>
          )}

          {/* Step 3: Resume upload */}
          {step === 3 && (
            <div>
              <h2 className="text-xl font-display font-bold text-white mb-1">{STEPS[3].title}</h2>
              <p className="text-slate-400 text-sm mb-6">Upload your resume to get started (you can do this later too)</p>
              <div className="border-2 border-dashed border-slate-700 rounded-xl p-12 text-center hover:border-amber-400/50 transition-colors">
                <div className="text-4xl mb-3">📄</div>
                <p className="text-slate-400 text-sm mb-2">
                  Drag and drop your resume PDF here
                </p>
                <p className="text-slate-500 text-xs">or</p>
                <button
                  onClick={() => setStep(4)}
                  className="mt-3 px-4 py-2 bg-slate-800 text-slate-300 rounded-lg text-sm hover:bg-slate-700"
                >
                  Skip for Now
                </button>
              </div>
              <div className="flex gap-3 mt-6">
                <button onClick={() => setStep(2)} className="px-4 py-2 border border-slate-700 text-slate-400 rounded-lg text-sm">
                  Back
                </button>
                <button onClick={() => setStep(4)} className="btn-primary flex-1">
                  Continue →
                </button>
              </div>
            </div>
          )}

          {/* Step 4: Done */}
          {step === 4 && (
            <div className="text-center py-8">
              <div className="text-5xl mb-4">🎉</div>
              <h2 className="text-2xl font-display font-bold text-white mb-3">You&apos;re All Set!</h2>
              <p className="text-slate-400 mb-8">
                Your 10-day free trial is active. Start applying to jobs with AI!
              </p>
              <div className="space-y-3 text-left max-w-xs mx-auto mb-8">
                <div className="flex items-center gap-2 text-sm text-emerald-400">✓ Account created</div>
                <div className="flex items-center gap-2 text-sm text-emerald-400">✓ Profile set up</div>
                <div className="flex items-center gap-2 text-sm text-emerald-400">✓ Job preferences saved</div>
                <div className="flex items-center gap-2 text-sm text-emerald-400">✓ Free trial activated (10 days)</div>
              </div>
              <button onClick={completeOnboarding} className="btn-primary w-full">
                Go to Dashboard →
              </button>
            </div>
          )}
        </div>
      </div>
    </main>
  );
}
