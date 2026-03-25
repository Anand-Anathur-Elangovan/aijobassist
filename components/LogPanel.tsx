'use client'
import { useState, useRef, useEffect } from 'react'
import type { LogEntry, LogLevel } from '@/lib/types'

// ── Visual config ──────────────────────────────────────────────
const LEVEL_CONFIG: Record<LogLevel, { icon: string; color: string; bg: string }> = {
  info:    { icon: '🔍', color: 'text-gray-700',   bg: 'bg-gray-50'    },
  success: { icon: '✅', color: 'text-emerald-700', bg: 'bg-emerald-50' },
  warning: { icon: '⚠️', color: 'text-amber-700',  bg: 'bg-amber-50'   },
  error:   { icon: '❌', color: 'text-red-700',     bg: 'bg-red-50'     },
  skip:    { icon: '⏭',  color: 'text-blue-600',   bg: 'bg-blue-50'    },
  ai:      { icon: '🤖', color: 'text-violet-700',  bg: 'bg-violet-50'  },
  fill:    { icon: '✍️', color: 'text-indigo-700',  bg: 'bg-indigo-50'  },
}

const FILTER_TABS: { label: string; value: LogLevel | 'all' }[] = [
  { label: 'All',        value: 'all'     },
  { label: '✅ Applied', value: 'success' },
  { label: '⏭ Skipped', value: 'skip'    },
  { label: '❌ Failed',  value: 'error'   },
  { label: '✍️ Fills',   value: 'fill'    },
  { label: '🤖 AI',      value: 'ai'      },
]

interface Props {
  logs: LogEntry[]
  isRunning: boolean
}

export default function LogPanel({ logs, isRunning }: Props) {
  const [filter,     setFilter]     = useState<LogLevel | 'all'>('all')
  const [expanded,   setExpanded]   = useState<Set<number>>(new Set())
  const [autoScroll, setAutoScroll] = useState(true)
  const bottomRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (autoScroll && isRunning) {
      bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
    }
  }, [logs, autoScroll, isRunning])

  const filtered = filter === 'all' ? logs : logs.filter(l => l.level === filter)

  const fmtTime = (ts: string) => {
    try { return new Date(ts).toLocaleTimeString('en-IN', { hour: '2-digit', minute: '2-digit', second: '2-digit' }) }
    catch { return '' }
  }

  const toggleExpand = (i: number) =>
    setExpanded(prev => { const n = new Set(prev); n.has(i) ? n.delete(i) : n.add(i); return n })

  const hasMeta = (e: LogEntry) =>
    !!e.meta && Object.values(e.meta).some(v => v !== undefined && v !== null && v !== '')

  const counts = logs.reduce((acc, l) => {
    acc[l.level] = (acc[l.level] ?? 0) + 1
    return acc
  }, {} as Record<string, number>)

  return (
    <div className="flex flex-col h-full border border-gray-200 rounded-xl overflow-hidden bg-white">

      {/* Header */}
      <div className="flex items-center justify-between px-4 py-3 border-b bg-gray-50">
        <div className="flex items-center gap-2">
          <h3 className="font-semibold text-gray-800 text-sm">Activity Log</h3>
          {isRunning && (
            <span className="flex items-center gap-1 text-xs text-emerald-600 bg-emerald-100 px-2 py-0.5 rounded-full">
              <span className="w-1.5 h-1.5 rounded-full bg-emerald-500 animate-pulse inline-block" />
              Live
            </span>
          )}
          <span className="text-xs text-gray-400">{logs.length} entries</span>
        </div>
        <label className="flex items-center gap-1.5 text-xs text-gray-500 cursor-pointer select-none">
          <input
            type="checkbox"
            checked={autoScroll}
            onChange={e => setAutoScroll(e.target.checked)}
            className="rounded"
          />
          Auto-scroll
        </label>
      </div>

      {/* Filter tabs */}
      <div className="flex gap-1 px-3 py-2 border-b bg-white overflow-x-auto">
        {FILTER_TABS.map(tab => (
          <button
            key={tab.value}
            onClick={() => setFilter(tab.value)}
            className={`flex-shrink-0 flex items-center gap-1 px-3 py-1 rounded-full text-xs font-medium transition-all ${
              filter === tab.value
                ? 'bg-gray-800 text-white'
                : 'bg-gray-100 text-gray-600 hover:bg-gray-200'
            }`}
          >
            {tab.label}
            {tab.value !== 'all' && counts[tab.value] ? (
              <span className={`text-xs px-1 rounded-full ${filter === tab.value ? 'bg-white/20 text-white' : 'bg-gray-200 text-gray-500'}`}>
                {counts[tab.value]}
              </span>
            ) : null}
          </button>
        ))}
      </div>

      {/* Entries */}
      <div className="flex-1 overflow-y-auto p-3 space-y-1 font-mono text-xs">
        {filtered.length === 0 && (
          <div className="flex items-center justify-center h-32 text-gray-400 text-sm font-sans">
            {isRunning ? 'Waiting for activity…' : 'No logs yet'}
          </div>
        )}

        {filtered.map((entry, i) => {
          const cfg = LEVEL_CONFIG[entry.level] ?? LEVEL_CONFIG.info
          const isOpen   = expanded.has(i)
          const hasDetail = hasMeta(entry)

          return (
            <div key={i} className={`rounded-lg overflow-hidden ${cfg.bg}`}>
              <div
                className={`flex items-start gap-2 px-3 py-2 ${hasDetail ? 'cursor-pointer hover:brightness-95' : ''}`}
                onClick={() => hasDetail && toggleExpand(i)}
              >
                <span className="flex-shrink-0 mt-0.5">{cfg.icon}</span>
                <span className="flex-shrink-0 text-gray-400 tabular-nums w-20">{fmtTime(entry.ts)}</span>
                <span className={`flex-1 leading-relaxed ${cfg.color}`}>{entry.msg}</span>
                {hasDetail && (
                  <span className={`flex-shrink-0 text-gray-400 transition-transform ${isOpen ? 'rotate-90' : ''}`}>›</span>
                )}
              </div>

              {isOpen && hasDetail && (
                <div className="px-10 pb-3 space-y-1 border-t border-black/5">
                  {Object.entries(entry.meta!).map(([k, v]) => {
                    if (v === undefined || v === null || v === '') return null
                    return (
                      <div key={k} className="flex items-start gap-2">
                        <span className="text-gray-400 capitalize w-28 flex-shrink-0">{k.replace(/_/g, ' ')}</span>
                        <span className={`font-sans ${cfg.color} break-all`}>
                          {typeof v === 'object' ? JSON.stringify(v) : String(v)}
                        </span>
                      </div>
                    )
                  })}
                </div>
              )}
            </div>
          )
        })}

        {isRunning && (
          <div className="flex items-center gap-1.5 px-3 py-2 text-gray-400">
            <span className="w-1.5 h-1.5 rounded-full bg-gray-400 animate-bounce" />
            <span className="w-1.5 h-1.5 rounded-full bg-gray-400 animate-bounce [animation-delay:75ms]" />
            <span className="w-1.5 h-1.5 rounded-full bg-gray-400 animate-bounce [animation-delay:150ms]" />
          </div>
        )}

        <div ref={bottomRef} />
      </div>
    </div>
  )
}
