'use client'

import { useState } from 'react'
import { useRouter } from 'next/navigation'
import { useAuth } from '@/context/AuthContext'
import { supabase } from '@/lib/supabase'

type Step = 1 | 2 | 3

interface ConnectionTestResult {
  status: 'idle' | 'testing' | 'success' | 'failed'
  message: string
}

export default function AgentSetupPage() {
  const { user } = useAuth()
  const router   = useRouter()

  const [step,    setStep]    = useState<Step>(1)
  const [connTest, setConnTest] = useState<ConnectionTestResult>({ status: 'idle', message: '' })
  const [saving,  setSaving]  = useState(false)

  // ── Step 2: Test Railway connection ──────────────────────────
  async function testConnection() {
    setConnTest({ status: 'testing', message: 'Testing connection to Railway service…' })

    const session = await supabase.auth.getSession()
    const token   = session.data.session?.access_token
    if (!token) {
      setConnTest({ status: 'failed', message: 'Not authenticated. Please refresh and try again.' })
      return
    }

    try {
      const res = await fetch('/api/railway/status?ping=true', {
        headers: { Authorization: `Bearer ${token}` },
      })
      const data = await res.json()

      if (data.reachable) {
        setConnTest({ status: 'success', message: 'Railway service is reachable!' })
      } else {
        setConnTest({
          status:  'failed',
          message: 'Railway service returned an error. Contact support if this persists.',
        })
      }
    } catch (err) {
      setConnTest({
        status:  'failed',
        message: `Cannot connect to Railway service. ${err instanceof Error ? err.message : ''}`,
      })
    }
  }

  // ── Step 3: Mark railway_configured = true in user_profiles ──
  async function markConfigured() {
    if (!user) return
    setSaving(true)

    await supabase
      .from('user_profiles')
      .update({ railway_configured: true })
      .eq('user_id', user.id)

    setSaving(false)
    router.push('/agent')
  }

  // ─────────────────────────────────────────────────────────────
  // Step content
  // ─────────────────────────────────────────────────────────────

  const STEPS = [
    {
      num:   1 as Step,
      title: 'Cloud Infrastructure',
      icon:  '☁️',
    },
    {
      num:   2 as Step,
      title: 'Test Connection',
      icon:  '🔌',
    },
    {
      num:   3 as Step,
      title: "You're All Set",
      icon:  '✅',
    },
  ]

  return (
    <div className="max-w-2xl mx-auto px-6 py-10">

      {/* Header */}
      <div className="mb-8">
        <button
          onClick={() => router.back()}
          className="text-sm text-slate-500 hover:text-slate-300 mb-4 flex items-center gap-1 transition-colors"
        >
          ← Back
        </button>
        <h1 className="text-3xl font-display font-bold text-white flex items-center gap-3">
          <span className="w-10 h-10 bg-violet-500/10 rounded-lg flex items-center justify-center text-xl">☁️</span>
          Railway Cloud Setup
        </h1>
        <p className="text-slate-400 mt-2">
          Run your job automation in the cloud — no install needed on your machine.
        </p>
      </div>

      {/* Step progress bar */}
      <div className="flex items-center gap-2 mb-8">
        {STEPS.map((s, i) => (
          <div key={s.num} className="flex items-center gap-2 flex-1">
            <div className={`flex items-center gap-2 ${i < STEPS.length - 1 ? 'flex-1' : ''}`}>
              <div className={`w-8 h-8 rounded-full flex items-center justify-center text-sm font-bold shrink-0 transition-all ${
                step > s.num
                  ? 'bg-emerald-500/10 text-emerald-400'
                  : step === s.num
                  ? 'bg-violet-500/10 text-violet-400'
                  : 'bg-slate-800 text-slate-500'
              }`}>
                {step > s.num ? '✓' : s.num}
              </div>
              <span className={`text-sm hidden sm:block ${step === s.num ? 'text-white font-medium' : 'text-slate-500'}`}>
                {s.title}
              </span>
            </div>
            {i < STEPS.length - 1 && (
              <div className={`h-px flex-1 mx-2 ${step > s.num ? 'bg-emerald-500/30' : 'bg-slate-700'}`} />
            )}
          </div>
        ))}
      </div>

      {/* ── Step 1: Informational ──────────────────────────────── */}
      {step === 1 && (
        <div className="card space-y-5">
          <div className="flex items-center gap-3">
            <span className="text-3xl">☁️</span>
            <div>
              <h2 className="text-xl font-bold text-white">We&apos;ve handled Railway for you</h2>
              <p className="text-slate-400 text-sm mt-0.5">
                VantaHire&apos;s cloud automation service is already deployed and ready.
              </p>
            </div>
          </div>

          <div className="bg-violet-500/5 border border-violet-500/20 rounded-lg p-4 space-y-3">
            <p className="text-sm font-medium text-violet-300">What this means for you:</p>
            <ul className="space-y-2 text-sm text-slate-300">
              {[
                '✅ No Railway account needed — VantaHire manages the cloud infrastructure',
                '✅ No software to install — run automation directly from your browser',
                '✅ Watch a live screenshot feed as the bot applies to jobs',
                '✅ Stop at any time with the Stop button',
                '✅ All job history, logs and results are saved to your account as usual',
              ].map((item) => (
                <li key={item} className="flex items-start gap-2">
                  <span className="shrink-0">{item.slice(0, 2)}</span>
                  <span>{item.slice(3)}</span>
                </li>
              ))}
            </ul>
          </div>

          <div className="bg-slate-800/40 border border-slate-700 rounded-lg p-4 space-y-2">
            <p className="text-sm font-medium text-white">Daily cloud usage limits by plan:</p>
            <div className="grid grid-cols-2 sm:grid-cols-4 gap-2 text-center text-xs">
              {[
                { plan: 'Trial / Free', mins: '5 min' },
                { plan: 'Pro',          mins: '15 min' },
                { plan: 'Premium',      mins: '30 min' },
                { plan: 'Admin',        mins: '120 min' },
              ].map((item) => (
                <div key={item.plan} className="bg-slate-900 rounded-lg p-2">
                  <p className="text-slate-400">{item.plan}</p>
                  <p className="text-white font-bold mt-0.5">{item.mins}/day</p>
                </div>
              ))}
            </div>
            <p className="text-xs text-slate-500">
              Upgrade to Pro or Premium for more daily cloud minutes.
            </p>
          </div>

          <button
            onClick={() => setStep(2)}
            className="w-full py-3 bg-violet-600 hover:bg-violet-500 text-white font-semibold rounded-xl transition-all"
          >
            Next: Test Connection →
          </button>
        </div>
      )}

      {/* ── Step 2: Test Connection ────────────────────────────── */}
      {step === 2 && (
        <div className="card space-y-5">
          <div className="flex items-center gap-3">
            <span className="text-3xl">🔌</span>
            <div>
              <h2 className="text-xl font-bold text-white">Test the connection</h2>
              <p className="text-slate-400 text-sm mt-0.5">
                We&apos;ll ping the Railway service to make sure everything is working.
              </p>
            </div>
          </div>

          {/* Test button */}
          <button
            onClick={testConnection}
            disabled={connTest.status === 'testing'}
            className="w-full py-3 bg-slate-800 border border-slate-700 hover:border-violet-500/50 text-white font-semibold rounded-xl transition-all disabled:opacity-50 disabled:cursor-not-allowed flex items-center justify-center gap-2"
          >
            {connTest.status === 'testing' ? (
              <>
                <span className="w-4 h-4 border-2 border-violet-400 border-t-transparent rounded-full animate-spin" />
                Testing…
              </>
            ) : (
              <>🔌 Test Railway Connection</>
            )}
          </button>

          {/* Result */}
          {connTest.status !== 'idle' && connTest.status !== 'testing' && (
            <div className={`rounded-lg p-4 text-sm ${
              connTest.status === 'success'
                ? 'bg-emerald-500/5 border border-emerald-500/20 text-emerald-300'
                : 'bg-red-500/5 border border-red-500/20 text-red-300'
            }`}>
              {connTest.status === 'success' ? '✅' : '❌'} {connTest.message}
            </div>
          )}

          {connTest.status === 'failed' && (
            <div className="text-sm text-slate-400 space-y-1">
              <p>If the connection test fails:</p>
              <ul className="list-disc list-inside text-slate-500 space-y-0.5">
                <li>The Railway service may be cold-starting (can take ~30s). Try again.</li>
                <li>Contact support at <span className="text-white">support@vantahire.com</span></li>
              </ul>
            </div>
          )}

          <div className="flex gap-3">
            <button
              onClick={() => setStep(1)}
              className="flex-1 py-2.5 text-sm text-slate-400 hover:text-white border border-slate-700 rounded-xl transition-colors"
            >
              ← Back
            </button>
            <button
              onClick={() => setStep(3)}
              disabled={connTest.status !== 'success'}
              className="flex-1 py-2.5 bg-violet-600 hover:bg-violet-500 disabled:opacity-40 disabled:cursor-not-allowed text-white font-semibold text-sm rounded-xl transition-all"
            >
              Next →
            </button>
          </div>
        </div>
      )}

      {/* ── Step 3: Done ──────────────────────────────────────── */}
      {step === 3 && (
        <div className="card space-y-5 text-center">
          <div className="flex flex-col items-center gap-3 py-4">
            <div className="w-16 h-16 bg-emerald-500/10 rounded-full flex items-center justify-center text-4xl">
              🎉
            </div>
            <h2 className="text-2xl font-bold text-white">You&apos;re all set!</h2>
            <p className="text-slate-400 max-w-sm">
              Railway Cloud is connected to your VantaHire account. You can now launch automation jobs without installing anything.
            </p>
          </div>

          <div className="bg-slate-800/40 border border-slate-700 rounded-xl p-4 text-left space-y-2 text-sm text-slate-300">
            <p className="font-medium text-white">What&apos;s next?</p>
            <ul className="space-y-1.5">
              <li>☁️ Go to the Agent page and click <strong className="text-white">Start Auto Apply</strong> or <strong className="text-white">Start Tailor &amp; Apply</strong></li>
              <li>🖥️ Choose <strong className="text-white">Railway Cloud</strong> in the popup</li>
              <li>📺 Watch the live screenshot feed as the bot works</li>
              <li>🛑 Hit <strong className="text-white">Stop</strong> at any time to pause</li>
            </ul>
          </div>

          <button
            onClick={markConfigured}
            disabled={saving}
            className="w-full py-3 bg-emerald-600 hover:bg-emerald-500 text-white font-semibold rounded-xl transition-all disabled:opacity-50"
          >
            {saving ? 'Saving…' : 'Go to Agent Page →'}
          </button>
        </div>
      )}
    </div>
  )
}
