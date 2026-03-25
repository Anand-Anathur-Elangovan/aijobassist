-- ================================================================
-- SCHEMA: Railway Approval Flow + Structured Logs
-- VantaHire — Run in Supabase SQL Editor AFTER all other schema
-- files (schema.sql → schema_additions.sql → schema_billing.sql)
-- ================================================================


-- ──────────────────────────────────────────────────────────────
-- STEP 1 — Extend task_status enum
-- Adds WAITING_APPROVAL so bot can pause for human review
-- ──────────────────────────────────────────────────────────────
ALTER TYPE task_status ADD VALUE IF NOT EXISTS 'WAITING_APPROVAL';


-- ──────────────────────────────────────────────────────────────
-- STEP 2 — Add approval columns to tasks
-- approval_payload  → bot writes before pausing { job_title, company,
--                     url, screenshot_b64, waiting_since }
-- approval_decision → web app writes: NULL | 'approved' | 'skipped'
-- ──────────────────────────────────────────────────────────────
ALTER TABLE tasks
  ADD COLUMN IF NOT EXISTS approval_payload  JSONB,
  ADD COLUMN IF NOT EXISTS approval_decision TEXT;


-- ──────────────────────────────────────────────────────────────
-- STEP 3 — Ensure all bot runtime columns exist on tasks
-- (safe to re-run — IF NOT EXISTS guards prevent duplicates)
-- ──────────────────────────────────────────────────────────────
ALTER TABLE tasks
  ADD COLUMN IF NOT EXISTS logs                   JSONB    NOT NULL DEFAULT '[]',
  ADD COLUMN IF NOT EXISTS progress               INT      NOT NULL DEFAULT 0,
  ADD COLUMN IF NOT EXISTS current_job            TEXT,
  ADD COLUMN IF NOT EXISTS paused                 BOOLEAN  NOT NULL DEFAULT FALSE,
  ADD COLUMN IF NOT EXISTS stop_requested         BOOLEAN  NOT NULL DEFAULT FALSE,
  ADD COLUMN IF NOT EXISTS custom_prompt_override TEXT;


-- ──────────────────────────────────────────────────────────────
-- STEP 4 — Upgrade append_task_log RPC
-- Must DROP first because PostgreSQL won't let us rename parameters
-- via CREATE OR REPLACE (old params were p_task_id / p_entry).
-- New structured entry shape: { ts, level, category, msg, meta }
-- ──────────────────────────────────────────────────────────────
DROP FUNCTION IF EXISTS append_task_log(uuid, jsonb);

CREATE OR REPLACE FUNCTION append_task_log(task_id UUID, entry JSONB)
RETURNS VOID
LANGUAGE plpgsql
SECURITY DEFINER
AS $$
BEGIN
  UPDATE tasks
  SET logs = COALESCE(logs, '[]'::jsonb) || jsonb_build_array(entry)
  WHERE id = task_id;
END;
$$;


-- ──────────────────────────────────────────────────────────────
-- STEP 5 — Add url_apply action type to plan_limits
-- URL Apply is tracked separately from semi_auto so each
-- mode has its own daily counter in the dashboard quota bar
-- ──────────────────────────────────────────────────────────────
INSERT INTO plan_limits (plan_id, action_type, daily_limit)
SELECT p.id, v.action_type, v.daily_limit
FROM plans p
CROSS JOIN (VALUES
  -- plan_slug     action_type   daily_limit
  ('trial',   'url_apply',   10),
  ('free',    'url_apply',    3),
  ('normal',  'url_apply',   30),
  ('premium', 'url_apply',  100)
) AS v(plan_slug, action_type, daily_limit)
WHERE p.slug = v.plan_slug
ON CONFLICT (plan_id, action_type) DO UPDATE
  SET daily_limit = EXCLUDED.daily_limit;


-- ──────────────────────────────────────────────────────────────
-- STEP 6 — Feature flags on plans
-- railway_access → can use Railway cloud execution
-- approval_flow  → semi-auto approval panel is available
-- ──────────────────────────────────────────────────────────────
UPDATE plans
SET features = features
  || '{"railway_access": false, "approval_flow": false}'::jsonb
WHERE slug = 'free';

UPDATE plans
SET features = features
  || '{"railway_access": true, "approval_flow": true}'::jsonb
WHERE slug IN ('trial', 'normal', 'premium');


-- ──────────────────────────────────────────────────────────────
-- STEP 7 — Performance indexes
-- ──────────────────────────────────────────────────────────────

-- Speeds up live log polling by the agent page
CREATE INDEX IF NOT EXISTS idx_tasks_logs
  ON tasks USING GIN (logs);

-- Speeds up poll_approval_decision() — partial index on NULL decisions only
CREATE INDEX IF NOT EXISTS idx_tasks_approval_pending
  ON tasks(id, approval_decision)
  WHERE approval_decision IS NULL;

-- Speeds up the agent page detecting WAITING_APPROVAL status per user
-- NOTE: Cannot use WHERE status = 'WAITING_APPROVAL' here because PostgreSQL
-- requires new enum values to be committed before use in a partial index predicate.
-- A full composite index on (user_id, status) covers the same queries efficiently.
CREATE INDEX IF NOT EXISTS idx_tasks_waiting_approval
  ON tasks(user_id, status);
