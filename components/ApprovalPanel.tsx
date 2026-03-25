'use client'
import { useState, useEffect } from 'react'
import { useAuth } from '@/context/AuthContext'

interface ApprovalPayload {
  job_title: string
  company: string
  url: string
  screenshot_b64: string | null
  waiting_since: string
}

interface Props {
  taskId: string
  payload: ApprovalPayload
  onDecision: (decision: 'approved' | 'skipped') => void
}

export default function ApprovalPanel({ taskId, payload, onDecision }: Props) {
  const { session } = useAuth()
  const [submitting, setSubmitting] = useState(false)
  const [timeLeft, setTimeLeft] = useState(300)

  // Countdown from 5 minutes
  useEffect(() => {
    const tick = () => {
      const elapsed = Math.floor((Date.now() - new Date(payload.waiting_since).getTime()) / 1000)
      const remaining = Math.max(0, 300 - elapsed)
      setTimeLeft(remaining)
      if (remaining === 0) clearInterval(interval)
    }
    tick()
    const interval = setInterval(tick, 1000)
    return () => clearInterval(interval)
  }, [payload.waiting_since])

  const fmt = (s: number) => {
    const m = Math.floor(s / 60).toString().padStart(2, '0')
    const sec = (s % 60).toString().padStart(2, '0')
    return `${m}:${sec}`
  }

  async function decide(decision: 'approved' | 'skipped') {
    setSubmitting(true)
    try {
      await fetch('/api/tasks/approve', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          Authorization: `Bearer ${session?.access_token}`,
        },
        body: JSON.stringify({ task_id: taskId, decision }),
      })
      onDecision(decision)
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <div className="fixed inset-0 bg-black/60 z-50 flex items-center justify-center p-4">
      <div className="bg-white rounded-2xl shadow-2xl w-full max-w-2xl overflow-hidden">

        {/* Header */}
        <div className="bg-amber-50 border-b border-amber-200 px-6 py-4 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <span className="w-3 h-3 rounded-full bg-amber-400 animate-pulse block" />
            <div>
              <p className="font-bold text-amber-900">Waiting for your approval</p>
              <p className="text-sm text-amber-700">{payload.company} — {payload.job_title}</p>
            </div>
          </div>
          <div className="text-right">
            <p className="text-xs text-amber-600">Auto-skips in</p>
            <p className={`text-2xl font-mono font-bold ${timeLeft < 60 ? 'text-red-600' : 'text-amber-700'}`}>
              {fmt(timeLeft)}
            </p>
          </div>
        </div>

        {/* Screenshot */}
        <div className="p-4 bg-gray-50 border-b">
          {payload.screenshot_b64 ? (
            // eslint-disable-next-line @next/next/no-img-element
            <img
              src={`data:image/jpeg;base64,${payload.screenshot_b64}`}
              alt="Filled application form preview"
              className="w-full rounded-lg border border-gray-200 shadow-sm max-h-72 object-top object-cover"
            />
          ) : (
            <div className="h-32 flex items-center justify-center text-gray-400 text-sm rounded-lg border border-dashed border-gray-300">
              Screenshot unavailable — form is filled and ready to submit
            </div>
          )}
        </div>

        {/* Job info row */}
        <div className="px-6 py-4 border-b bg-white">
          <div className="flex items-center gap-4 text-sm text-gray-600 flex-wrap">
            <span>🏢 <strong>{payload.company}</strong></span>
            <span>💼 {payload.job_title}</span>
            {payload.url && (
              <a
                href={payload.url}
                target="_blank"
                rel="noopener noreferrer"
                className="text-blue-600 hover:underline ml-auto"
              >
                View Job →
              </a>
            )}
          </div>
        </div>

        {/* Action buttons */}
        <div className="px-6 py-5 flex gap-3 bg-white">
          <button
            onClick={() => decide('skipped')}
            disabled={submitting}
            className="flex-1 px-5 py-3 border-2 border-gray-300 text-gray-700 rounded-xl font-medium hover:bg-gray-50 hover:border-gray-400 transition-all disabled:opacity-50"
          >
            ⏭ Skip This Job
          </button>
          <button
            onClick={() => decide('approved')}
            disabled={submitting}
            className="flex-1 px-5 py-3 bg-emerald-600 text-white rounded-xl font-bold hover:bg-emerald-700 transition-all disabled:opacity-50 shadow-md shadow-emerald-200"
          >
            {submitting ? 'Submitting…' : '✅ Approve & Submit'}
          </button>
        </div>

      </div>
    </div>
  )
}
