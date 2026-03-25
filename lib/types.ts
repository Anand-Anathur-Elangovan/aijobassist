// ── Log types shared between Python bot and the web UI ──────────

export type LogLevel =
  | 'info'
  | 'success'
  | 'warning'
  | 'error'
  | 'skip'
  | 'ai'
  | 'fill'

export type LogCategory =
  | 'navigation'
  | 'search'
  | 'form_fill'
  | 'ai_decision'
  | 'submit'
  | 'skip'
  | 'tailor'
  | 'system'
  | 'approval'

export interface LogMeta {
  job_title?: string
  company?: string
  score?: number
  threshold?: number
  skip_reason?: string
  field_name?: string
  field_value?: string
  url?: string
  decision?: string
  count?: number
  applied?: number
  skipped?: number
  error?: string
  [key: string]: unknown
}

export interface LogEntry {
  /** ISO timestamp e.g. "2026-03-25T10:30:00.000Z" */
  ts: string
  level: LogLevel
  category: LogCategory
  msg: string
  meta?: LogMeta
}
