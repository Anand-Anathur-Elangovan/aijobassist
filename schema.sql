-- ============================================================
-- ENUM: task status
-- ============================================================
CREATE TYPE task_status AS ENUM ('PENDING', 'RUNNING', 'DONE', 'FAILED');


-- ============================================================
-- RESUMES
-- Users own resumes; content is free-form JSONB
-- ============================================================
CREATE TABLE resumes (
  id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id     UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
  title       TEXT NOT NULL,
  content     JSONB NOT NULL DEFAULT '{}',   -- structured resume data
  created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_resumes_user_id ON resumes(user_id);


-- ============================================================
-- JOBS
-- Job postings a user is interested in tracking
-- ============================================================
CREATE TABLE jobs (
  id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id     UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
  company     TEXT NOT NULL,
  role        TEXT NOT NULL,
  url         TEXT,
  status      TEXT NOT NULL DEFAULT 'SAVED',  -- SAVED, APPLYING, CLOSED, etc.
  metadata    JSONB NOT NULL DEFAULT '{}',    -- salary, location, remote, tags, etc.
  created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_jobs_user_id    ON jobs(user_id);
CREATE INDEX idx_jobs_metadata   ON jobs USING GIN (metadata);


-- ============================================================
-- APPLICATIONS
-- Links a user's resume to a job; tracks the application stage
-- ============================================================
CREATE TABLE applications (
  id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id     UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
  job_id      UUID NOT NULL REFERENCES jobs(id) ON DELETE CASCADE,
  resume_id   UUID REFERENCES resumes(id) ON DELETE SET NULL,
  stage       TEXT NOT NULL DEFAULT 'APPLIED',  -- APPLIED, SCREENING, INTERVIEW, OFFER, REJECTED
  notes       TEXT,
  payload     JSONB NOT NULL DEFAULT '{}',       -- cover letter, custom answers, recruiter info, etc.
  applied_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  UNIQUE (user_id, job_id)
);

CREATE INDEX idx_applications_user_id   ON applications(user_id);
CREATE INDEX idx_applications_job_id    ON applications(job_id);
CREATE INDEX idx_applications_payload   ON applications USING GIN (payload);


-- ============================================================
-- TASKS
-- Background/async work tied to an application (e.g. AI resume
-- tailoring, email draft, interview prep generation)
-- ============================================================
CREATE TABLE tasks (
  id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id         UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
  application_id  UUID REFERENCES applications(id) ON DELETE SET NULL,
  type            TEXT NOT NULL,                 -- e.g. 'TAILOR_RESUME', 'DRAFT_EMAIL'
  status          task_status NOT NULL DEFAULT 'PENDING',
  input           JSONB NOT NULL DEFAULT '{}',   -- task configuration / request payload
  output          JSONB,                         -- task result; NULL until DONE
  error           TEXT,                          -- populated on FAILED
  created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  completed_at    TIMESTAMPTZ                    -- set when status → DONE or FAILED
);

CREATE INDEX idx_tasks_user_id        ON tasks(user_id);
CREATE INDEX idx_tasks_application_id ON tasks(application_id);
CREATE INDEX idx_tasks_status         ON tasks(status);


-- ============================================================
-- AUTO-UPDATE updated_at via trigger
-- ============================================================
CREATE OR REPLACE FUNCTION set_updated_at()
RETURNS TRIGGER LANGUAGE plpgsql AS $$
BEGIN
  NEW.updated_at = NOW();
  RETURN NEW;
END;
$$;

CREATE TRIGGER trg_resumes_updated_at
  BEFORE UPDATE ON resumes
  FOR EACH ROW EXECUTE FUNCTION set_updated_at();

CREATE TRIGGER trg_jobs_updated_at
  BEFORE UPDATE ON jobs
  FOR EACH ROW EXECUTE FUNCTION set_updated_at();

CREATE TRIGGER trg_applications_updated_at
  BEFORE UPDATE ON applications
  FOR EACH ROW EXECUTE FUNCTION set_updated_at();


-- ============================================================
-- ROW LEVEL SECURITY
-- ============================================================
ALTER TABLE resumes      ENABLE ROW LEVEL SECURITY;
ALTER TABLE jobs         ENABLE ROW LEVEL SECURITY;
ALTER TABLE applications ENABLE ROW LEVEL SECURITY;
ALTER TABLE tasks        ENABLE ROW LEVEL SECURITY;

-- Users can only see and modify their own rows
CREATE POLICY "resumes: owner access"
  ON resumes FOR ALL USING (auth.uid() = user_id);

CREATE POLICY "jobs: owner access"
  ON jobs FOR ALL USING (auth.uid() = user_id);

CREATE POLICY "applications: owner access"
  ON applications FOR ALL USING (auth.uid() = user_id);

CREATE POLICY "tasks: owner access"
  ON tasks FOR ALL USING (auth.uid() = user_id);