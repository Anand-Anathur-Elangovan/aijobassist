# VantaHire — Next.js + Supabase App

A full-stack job search platform built with **Next.js 14 App Router** and **Supabase** (Auth + Storage + Database).

---

## Folder Structure

```
nextjs-supabase-app/
├── app/
│   ├── globals.css              # Global styles (fonts, CSS vars, utilities)
│   ├── layout.tsx               # Root layout — wraps app in <AuthProvider>
│   ├── page.tsx                 # "/" — redirects to /dashboard or /login
│   ├── login/
│   │   └── page.tsx             # Sign in / Sign up page
│   └── (protected)/             # Route group — all pages behind AuthGuard
│       ├── layout.tsx           # Protected layout — renders NavBar
│       ├── dashboard/
│       │   └── page.tsx         # Dashboard with stats + resume list
│       ├── upload-resume/
│       │   └── page.tsx         # Drag-and-drop resume upload
│       └── job-preferences/
│           └── page.tsx         # Job prefs form (title, salary, industries)
│
├── components/
│   ├── AuthGuard.tsx            # Redirects unauthenticated users to /login
│   └── NavBar.tsx               # Sticky nav with active links + sign out
│
├── context/
│   └── AuthContext.tsx          # React context — user, session, loading state
│
├── lib/
│   └── supabase.ts              # Supabase client + all API helpers
│
├── supabase/
│   └── schema.sql               # SQL schema (tables, RLS policies, storage)
│
├── next.config.js
├── tailwind.config.ts
├── tsconfig.json
└── package.json
```

---

## Quick Start

### 1. Install dependencies
```bash
npm install
```

### 2. Set your Supabase credentials
Open `lib/supabase.ts` and replace the two hardcoded constants:

```ts
const SUPABASE_URL     = "https://your-project-ref.supabase.co";
const SUPABASE_ANON_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.your-anon-key";
```

Find these in: **Supabase Dashboard → Project Settings → API**

### 3. Run the SQL schema
Copy `supabase/schema.sql` into:
**Supabase Dashboard → SQL Editor → New query → Run**

### 4. Create the storage bucket
- Go to **Storage → New Bucket**
- Name it exactly: `resumes`
- Set **Public** to ON
- Add the two storage policies described at the bottom of `schema.sql`

### 5. Start the dev server
```bash
npm run dev
```

Open http://localhost:3000

---

## How It Works

### Authentication
- `lib/supabase.ts` creates a **singleton Supabase client** with `persistSession: true`
  — JWT is stored in localStorage and refreshed automatically
- `context/AuthContext.tsx` subscribes to `onAuthStateChange` — any component can call `useAuth()` to get `{ user, session, loading }`
- `components/AuthGuard.tsx` wraps all protected routes; unauthenticated users are redirected to `/login`

### Resume Upload Flow
1. User drops/selects a file on `/upload-resume`
2. File is validated (type + 5 MB limit) client-side
3. `uploadResume()` uploads to Supabase Storage: `resumes/{userId}/{timestamp}_{filename}`
4. `saveResumeMeta()` upserts a row in the `resumes` table with the public URL
5. Dashboard fetches the list via `getResumes(userId)`

### Job Preferences Flow
1. On mount, `getJobPreferences(userId)` fetches existing prefs and pre-fills the form
2. On submit, `saveJobPreferences()` calls `supabase.from("job_preferences").upsert(...)`
   — one row per user (unique constraint on `user_id`)

---

## Supabase Tables

| Table             | Key columns                                                                 |
|-------------------|-----------------------------------------------------------------------------|
| `resumes`         | `id`, `user_id`, `file_name`, `file_url`, `updated_at`                     |
| `job_preferences` | `user_id` (unique), `desired_title`, `locations[]`, `min_salary`, `job_type`, `industries[]`, `open_to_relocation` |

All tables have **Row Level Security (RLS)** enabled — users can only access their own rows.

---

## Tech Stack

| Layer      | Tech                                          |
|------------|-----------------------------------------------|
| Framework  | Next.js 14 App Router                         |
| Auth & DB  | Supabase (`@supabase/supabase-js`)            |
| Styling    | Tailwind CSS + CSS variables                  |
| Fonts      | Syne (display) · DM Sans (body) · JetBrains Mono |
| Language   | TypeScript                                    |
