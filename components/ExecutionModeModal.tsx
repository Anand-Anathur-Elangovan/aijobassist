'use client'

import { useState } from 'react'
import Link from 'next/link'

// ─────────────────────────────────────────────────────────────
// Types
// ─────────────────────────────────────────────────────────────

export type ExecutionMode = 'own_machine' | 'railway'

export interface RailwayQuotaInfo {
  used:      number
  limit:     number
  remaining: number
}

interface Props {
  isOpen:             boolean
  onClose:            () => void
  onConfirm:          (mode: ExecutionMode, remember: boolean) => void
  railwayConfigured:  boolean
  quota:              RailwayQuotaInfo
  taskType:           'AUTO_APPLY' | 'TAILOR_AND_APPLY'
  defaultMode:        ExecutionMode
}

// ─────────────────────────────────────────────────────────────
// Helpers
// ─────────────────────────────────────────────────────────────

const TASK_LABELS: Record<string, string> = {
  AUTO_APPLY:       'Auto Apply',
  TAILOR_AND_APPLY: 'Tailor & Apply',
}

function QuotaBar({ used, limit }: { used: number; limit: number }) {
  const pct = limit > 0 ? Math.min(100, (used / limit) * 100) : 0
  const color =
    pct >= 90 ? 'bg-red-500' :
    pct >= 70 ? 'bg-amber-500' :
    'bg-emerald-500'

  return (
    <div className="space-y-1">
      <div className="flex justify-between text-xs text-slate-400">
        <span>{used.toFixed(1)} / {limit} min used today</span>
        <span>{Math.max(0, limit - used).toFixed(1)} min left</span>
      </div>
      <div className="h-1.5 bg-slate-700 rounded-full overflow-hidden">
        <div
          className={`h-full rounded-full transition-all ${color}`}
          style={{ width: `${pct}%` }}
        />
      </div>
    </div>
  )
}

// ─────────────────────────────────────────────────────────────
// Component
// ─────────────────────────────────────────────────────────────

export default function ExecutionModeModal({
  isOpen,
  onClose,
  onConfirm,
  railwayConfigured,
  quota,
  taskType,
  defaultMode,
}: Props) {
  const [selected, setSelected] = useState<ExecutionMode>(defaultMode)
  const [remember, setRemember]  = useState(false)

  if (!isOpen) return null

  const railwayExhausted = quota.remaining <= 0
  const railwayDisabled  = !railwayConfigured || railwayExhausted

  function handleConfirm() {
    onConfirm(selected, remember)
    onClose()
  }

  return (
    // Backdrop
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm"
      onClick={(e) => { if (e.target === e.currentTarget) onClose() }}
    >
      <div className="w-full max-w-lg mx-4 bg-slate-900 border border-slate-700 rounded-2xl shadow-2xl overflow-hidden">

        {/* Header */}
        <div className="px-6 pt-6 pb-4 border-b border-slate-800 flex items-start justify-between">
          <div>
            <h2 className="text-lg font-bold text-white">
              Where should this run?
            </h2>
            <p className="text-sm text-slate-400 mt-0.5">
              Starting: <span className="text-amber-400 font-medium">{TASK_LABELS[taskType] ?? taskType}</span>
            </p>
          </div>
          <button
            onClick={onClose}
            className="text-slate-500 hover:text-slate-300 text-xl leading-none ml-4"
          >
            ×
          </button>
        </div>

        {/* Mode cards */}
        <div className="p-6 space-y-3">

          {/* ── Own Machine ─────────────────────────────────── */}
          <button
            onClick={() => setSelected('own_machine')}
            className={`w-full text-left rounded-xl border p-4 transition-all ${
              selected === 'own_machine'
                ? 'border-amber-400/60 bg-amber-400/5'
                : 'border-slate-700 bg-slate-800/40 hover:border-slate-600'
            }`}
          >
            <div className="flex items-start gap-3">
              <span className="text-2xl mt-0.5">💻</span>
              <div className="flex-1 min-w-0">
                <div className="flex items-center gap-2">
                  <p className="font-semibold text-white">Own Machine</p>
                  {selected === 'own_machine' && (
                    <span className="text-xs px-2 py-0.5 bg-amber-400/10 text-amber-400 rounded-full">Selected</span>
                  )}
                </div>
                <p className="text-sm text-slate-400 mt-1">
                  The desktop agent (.exe) runs on your computer with a visible browser window. You can watch, pause, or intervene at any time.
                </p>
                <p className="text-xs text-slate-500 mt-2">
                  Requires: VantaHire.exe running + Playwright installed
                </p>
              </div>
            </div>
          </button>

          {/* ── Railway Cloud ─────────────────────────────── */}
          <button
            onClick={() => { if (!railwayDisabled) setSelected('railway') }}
            disabled={railwayDisabled}
            className={`w-full text-left rounded-xl border p-4 transition-all ${
              railwayDisabled
                ? 'border-slate-800 bg-slate-800/20 opacity-60 cursor-not-allowed'
                : selected === 'railway'
                ? 'border-violet-400/60 bg-violet-400/5'
                : 'border-slate-700 bg-slate-800/40 hover:border-violet-500/40'
            }`}
          >
            <div className="flex items-start gap-3">
              <span className="text-2xl mt-0.5">☁️</span>
              <div className="flex-1 min-w-0">
                <div className="flex items-center gap-2 flex-wrap">
                  <p className="font-semibold text-white">Railway Cloud</p>

                  {/* Recommended badge */}
                  {!railwayDisabled && (
                    <span className="text-xs px-2 py-0.5 bg-violet-500/15 text-violet-300 rounded-full border border-violet-500/30">
                      ✨ Recommended
                    </span>
                  )}

                  {/* Setup Required badge */}
                  {!railwayConfigured && (
                    <span className="text-xs px-2 py-0.5 bg-amber-400/10 text-amber-400 rounded-full">
                      Setup Required
                    </span>
                  )}

                  {/* Quota exhausted badge */}
                  {railwayConfigured && railwayExhausted && (
                    <span className="text-xs px-2 py-0.5 bg-red-500/10 text-red-400 rounded-full">
                      Daily limit reached
                    </span>
                  )}

                  {/* Selected badge */}
                  {selected === 'railway' && !railwayDisabled && (
                    <span className="text-xs px-2 py-0.5 bg-violet-400/10 text-violet-400 rounded-full">Selected</span>
                  )}
                </div>

                <p className="text-sm text-slate-400 mt-1">
                  Automation runs on VantaHire&apos;s cloud servers. No install needed — watch a live screenshot feed from your browser.
                </p>

                {/* Quota bar */}
                {railwayConfigured && (
                  <div className="mt-3">
                    <QuotaBar used={quota.used} limit={quota.limit} />
                  </div>
                )}

                {/* Setup link */}
                {!railwayConfigured && (
                  <Link
                    href="/agent/setup"
                    onClick={(e) => e.stopPropagation()}
                    className="inline-block mt-2 text-xs text-violet-400 hover:text-violet-300 underline"
                  >
                    Set up Railway →
                  </Link>
                )}
              </div>
            </div>
          </button>

          {/* ── Remember choice ────────────────────────────── */}
          <label className="flex items-center gap-2 cursor-pointer select-none px-1">
            <input
              type="checkbox"
              checked={remember}
              onChange={(e) => setRemember(e.target.checked)}
              className="w-4 h-4 rounded accent-amber-400"
            />
            <span className="text-sm text-slate-400">Remember my choice</span>
          </label>
        </div>

        {/* Footer */}
        <div className="px-6 pb-6 flex justify-end gap-3">
          <button
            onClick={onClose}
            className="px-4 py-2 text-sm text-slate-400 hover:text-white transition-colors"
          >
            Cancel
          </button>
          <button
            onClick={handleConfirm}
            className={`px-5 py-2 text-sm font-semibold rounded-lg transition-all ${
              selected === 'railway'
                ? 'bg-violet-600 hover:bg-violet-500 text-white'
                : 'bg-amber-400 hover:bg-amber-300 text-slate-950'
            }`}
          >
            Start {TASK_LABELS[taskType] ?? taskType}
          </button>
        </div>
      </div>
    </div>
  )
}
