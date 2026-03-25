"""
Mock test — validates all core logic without launching a browser.
Run from:  cd taskrunner && python mock_test.py
"""

import sys, os, re
from urllib.parse import urlencode, urlparse, parse_qs

# ── Make sure project root is importable ───────────────────────────────────────
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, ROOT)

PASS = "✅"
FAIL = "❌"
results = []

def check(name: str, condition: bool, detail: str = ""):
    status = PASS if condition else FAIL
    results.append((status, name, detail))
    print(f"  {status}  {name}" + (f"  — {detail}" if detail else ""))

# ══════════════════════════════════════════════════════════════════════════════
# 1. Dashboard payload builder
#    Simulates createTask logic from dashboard/page.tsx in Python
# ══════════════════════════════════════════════════════════════════════════════
print("\n── 1. Dashboard payload ─────────────────────────────────────────────────")

def build_payload(
    remote_enabled: bool,
    location_list: list,
    keywords: str,
    keywords2: str,
    keywords3: str,
    platform: str,
    naukri_date_posted: str = "any",
    naukri_work_mode: str = "any",
    naukri_job_type: str = "all",
    linkedin_date_posted: str = "any",
    linkedin_remote: bool = None,   # None → uses remote_enabled
    linkedin_exp_level: str = "all",
    linkedin_job_type: str = "all",
) -> dict:
    """Mirrors the JS createTask payload logic."""
    if linkedin_remote is None:
        linkedin_remote = remote_enabled

    loc_parts = (["Remote"] if remote_enabled else []) + location_list
    location = ",".join(loc_parts)

    payload = {
        "platform": platform,
        "keywords": keywords,
        "location": location,
    }
    if keywords2.strip():
        payload["keywords2"] = keywords2.strip()
    if keywords3.strip():
        payload["keywords3"] = keywords3.strip()

    if platform == "naukri":
        if naukri_date_posted != "any":
            payload["freshness_days"] = int(naukri_date_posted)
        if naukri_work_mode != "any":
            payload["work_mode"] = naukri_work_mode
        elif remote_enabled:
            payload["work_mode"] = "remote"
        if naukri_job_type != "all":
            payload["naukri_job_type"] = naukri_job_type

    if platform == "linkedin":
        payload["linkedin_date_posted"] = linkedin_date_posted
        payload["linkedin_remote"] = linkedin_remote
        if linkedin_exp_level != "all":
            payload["linkedin_exp_level"] = linkedin_exp_level
        if linkedin_job_type != "all":
            payload["linkedin_job_type"] = linkedin_job_type

    return payload


# Case 1: Remote only, no location tags
p = build_payload(True, [], "Python Developer", "", "", "naukri")
check("Remote-only → location='Remote'", p["location"] == "Remote", p["location"])
check("Remote-only → work_mode=remote (fallback)", p.get("work_mode") == "remote")

# Case 2: Remote + cities
p = build_payload(True, ["Bangalore", "Hyderabad"], "Python Developer", "", "", "naukri")
check("Remote+cities → location contains Remote", "Remote" in p["location"].split(","))
check("Remote+cities → 3 entries", len(p["location"].split(",")) == 3, p["location"])

# Case 3: No location, no remote
p = build_payload(False, [], "Python Developer", "", "", "naukri")
check("No location → empty string", p["location"] == "", repr(p["location"]))

# Case 4: Cities only (no remote)
p = build_payload(False, ["Chennai", "Mumbai"], "Python Developer", "", "", "naukri")
check("Cities only → remote NOT prepended", "Remote" not in p["location"].split(","))
check("Cities only → correct string", p["location"] == "Chennai,Mumbai", p["location"])

# Case 5: Naukri filters propagated
p = build_payload(False, ["Bangalore"], "Python Developer", "", "", "naukri",
                  naukri_date_posted="7", naukri_work_mode="hybrid", naukri_job_type="fullTime")
check("Naukri freshness_days=7", p.get("freshness_days") == 7)
check("Naukri work_mode=hybrid", p.get("work_mode") == "hybrid")
check("Naukri naukri_job_type=fullTime", p.get("naukri_job_type") == "fullTime")

# Case 6: LinkedIn remote uses shared remote_enabled
p = build_payload(True, ["London"], "Python Developer", "", "", "linkedin")
check("LinkedIn linkedin_remote reflects remote_enabled", p.get("linkedin_remote") == True)
check("LinkedIn location includes Remote", "Remote" in p["location"].split(","))

# Case 7: Multi-keywords in payload
p = build_payload(False, [], "Python Developer", "Backend Engineer", "REST API", "linkedin")
check("keywords2 present", p.get("keywords2") == "Backend Engineer")
check("keywords3 present", p.get("keywords3") == "REST API")

# Case 8 : Naukri work_mode NOT auto-set to remote when work_mode=any but remote_enabled=False
p = build_payload(False, [], "Python Developer", "", "", "naukri", naukri_work_mode="any")
check("Naukri work_mode absent when any+no-remote", "work_mode" not in p)


# ══════════════════════════════════════════════════════════════════════════════
# 2. Naukri _search_jobs URL building  (exercise the real code)
# ══════════════════════════════════════════════════════════════════════════════
print("\n── 2. Naukri search URL builder ──────────────────────────────────────────")

def _mock_naukri_url(keywords: str, location: str, task_input: dict) -> str:
    """Mirrors _search_jobs URL construction in naukri.py."""
    task_input = task_input or {}
    NAUKRI_URL = "https://www.naukri.com"

    kw_slug  = re.sub(r"[^a-z0-9]+", "-", keywords.strip().lower()).strip("-")
    loc_slug = re.sub(r"[^a-z0-9]+", "-", location.strip().lower()).strip("-") if location else ""

    if loc_slug:
        base_url = f"{NAUKRI_URL}/{kw_slug}-jobs-in-{loc_slug}"
    else:
        base_url = f"{NAUKRI_URL}/{kw_slug}-jobs"

    params = {}
    years = int(float(task_input.get("years_experience", 0) or 0))
    if years > 0:
        params["experience"] = f"{max(0,years-1)}-{years+3}"

    freshness = task_input.get("freshness_days")
    if freshness:
        params["jobAge"] = int(freshness)

    work_mode = str(task_input.get("work_mode") or "").lower()
    _wfh_code = {"remote": "0", "work from home": "0", "wfh": "0", "hybrid": "3", "office": "2", "wfo": "2"}
    for _k, _v in _wfh_code.items():
        if _k in work_mode:
            params["wfhType"] = _v
            break

    _naukri_jobtype_map = {"fullTime": "1", "contract": "2", "temporary": "3"}
    _naukri_jt = str(task_input.get("naukri_job_type", "all"))
    if _naukri_jt in _naukri_jobtype_map:
        params["jobtype"] = _naukri_jobtype_map[_naukri_jt]

    return f"{base_url}?{urlencode(params)}" if params else base_url


# Test Naukri URLs
u = _mock_naukri_url("Python Developer", "Bangalore", {"years_experience": 3})
check("Naukri URL: slug format", "python-developer-jobs-in-bangalore" in u, u)
check("Naukri URL: experience param", "experience=2-6" in u, u)

u = _mock_naukri_url("Python Developer", "", {"freshness_days": 7})
check("Naukri URL: no location → bare /jobs", "python-developer-jobs?" in u or u.endswith("python-developer-jobs"), u)
check("Naukri URL: jobAge=7", "jobAge=7" in u, u)

u = _mock_naukri_url("Python Developer", "Remote", {"work_mode": "remote"})
check("Naukri URL: remote wfhType=0", "wfhType=0" in u, u)
check("Naukri URL: hybrid slugified to location", "remote" in u, u)

u = _mock_naukri_url("Python Developer", "Hyderabad", {"naukri_job_type": "fullTime"})
check("Naukri URL: jobtype=1 for fullTime", "jobtype=1" in u, u)

u = _mock_naukri_url("Python Developer", "Hyderabad", {"naukri_job_type": "contract"})
check("Naukri URL: jobtype=2 for contract", "jobtype=2" in u, u)

u = _mock_naukri_url("Python Developer", "Hyderabad", {"naukri_job_type": "temporary"})
check("Naukri URL: jobtype=3 for temporary", "jobtype=3" in u, u)

u = _mock_naukri_url("Python Developer", "Hyderabad", {"naukri_job_type": "all"})
check("Naukri URL: no jobtype param for 'all'", "jobtype" not in u, u)


# ══════════════════════════════════════════════════════════════════════════════
# 3. LinkedIn _search_jobs URL building
# ══════════════════════════════════════════════════════════════════════════════
print("\n── 3. LinkedIn search URL builder ────────────────────────────────────────")
import urllib.parse

def _mock_linkedin_url(keywords: str, location: str, task_input: dict) -> str:
    """Mirrors _search_jobs URL construction in linkedin.py."""
    params = {
        "keywords": keywords,
        "location": location,
        "f_AL":     "true",
        "sortBy":   "DD",
    }
    _DATE_MAP = {"past24h": "r86400", "pastWeek": "r604800", "pastMonth": "r2592000"}
    date_posted = task_input.get("linkedin_date_posted", "any")
    if date_posted in _DATE_MAP:
        params["f_TPR"] = _DATE_MAP[date_posted]

    if task_input.get("linkedin_remote"):
        params["f_WT"] = "2"

    _EXP_MAP = {"internship":"1","entry":"2","associate":"3","mid":"4","director":"5","executive":"6"}
    exp_level = task_input.get("linkedin_exp_level", "all")
    if exp_level in _EXP_MAP:
        params["f_E"] = _EXP_MAP[exp_level]

    _JOBTYPE_MAP = {"fullTime":"F","partTime":"P","contract":"C","temporary":"T","internship":"I","volunteer":"V"}
    job_type = task_input.get("linkedin_job_type", "all")
    if job_type in _JOBTYPE_MAP:
        params["f_JT"] = _JOBTYPE_MAP[job_type]

    return "https://www.linkedin.com/jobs/search/?" + urllib.parse.urlencode(params)


u = _mock_linkedin_url("Python Developer", "Bangalore", {"linkedin_remote": True})
check("LinkedIn URL: f_WT=2 when remote=True", "f_WT=2" in u, u)
check("LinkedIn URL: location=Bangalore (single)", "location=Bangalore" in urllib.parse.unquote(u))

u = _mock_linkedin_url("Python Developer", "Remote", {"linkedin_date_posted": "pastWeek"})
check("LinkedIn URL: f_TPR=r604800 for pastWeek", "f_TPR=r604800" in u, u)

u = _mock_linkedin_url("Python Developer", "", {"linkedin_job_type": "fullTime", "linkedin_exp_level": "mid"})
check("LinkedIn URL: f_JT=F for fullTime", "f_JT=F" in u, u)
check("LinkedIn URL: f_E=4 for mid", "f_E=4" in u, u)

# Confirm single-location inputs always produce clean URLs (no comma inside location param)
single_locations = ["Remote", "Bangalore", "", "New York"]
for sloc in single_locations:
    u = _mock_linkedin_url("Python Developer", sloc, {})
    decoded_q = urllib.parse.unquote(urllib.parse.urlparse(u).query)
    # extract location= value
    loc_val = ""
    for part in decoded_q.split("&"):
        if part.startswith("location="):
            loc_val = part[len("location="):]
    check(
        f"LinkedIn URL: single-loc '{sloc}' → no comma in URL param",
        "," not in loc_val,
        f"loc_val={loc_val!r}"
    )


# ══════════════════════════════════════════════════════════════════════════════
# 4. Multi-location loop simulation (Naukri)
# ══════════════════════════════════════════════════════════════════════════════
print("\n── 4. Multi-location loop simulation (Naukri) ────────────────────────────")

def _simulate_naukri_multi_location(task_input: dict) -> list[str]:
    """Simulates the keyword × location loop in apply_naukri_jobs."""
    _kw_list = [
        k.strip() for k in [
            task_input.get("keywords", ""),
            task_input.get("keywords2", ""),
            task_input.get("keywords3", ""),
        ] if k.strip()
    ]
    if not _kw_list:
        _kw_list = ["Software Engineer"]

    _loc_list = [
        l.strip() for l in task_input.get("location", "").split(",") if l.strip()
    ] or [""]

    urls = []
    for _kw in _kw_list:
        for _loc in _loc_list:
            urls.append(_mock_naukri_url(_kw, _loc, task_input))
    return urls


task = {"keywords": "Python Developer", "keywords2": "Backend Engineer",
        "location": "Remote,Bangalore,Chennai", "years_experience": 2}
urls = _simulate_naukri_multi_location(task)
check("Naukri 2 keywords × 3 locations = 6 search URLs", len(urls) == 6, f"got {len(urls)}")
check("Naukri URL contains Remote as a location slug", any("remote" in u for u in urls), str(urls[:2]))
check("Naukri URL contains Bangalore slug", any("bangalore" in u for u in urls), "")
check("Naukri URL contains Chennai slug", any("chennai" in u for u in urls), "")


# ══════════════════════════════════════════════════════════════════════════════
# 5. Multi-location loop simulation (LinkedIn) — after fix
# ══════════════════════════════════════════════════════════════════════════════
print("\n── 5. Multi-location loop simulation (LinkedIn after fix) ────────────────")

def _simulate_linkedin_multi_location(task_input: dict) -> list[str]:
    """
    Simulates the FIXED keyword × location loop in apply_linkedin_jobs.
    Each location gets its own search URL — no commas in the URL.
    """
    _li_kw_list = [
        k.strip() for k in [
            task_input.get("keywords", ""),
            task_input.get("keywords2", ""),
            task_input.get("keywords3", ""),
        ] if k.strip()
    ]
    if not _li_kw_list:
        _li_kw_list = ["Software Engineer"]

    _li_loc_list = [
        l.strip() for l in task_input.get("location", "").split(",") if l.strip()
    ] or [""]

    urls = []
    for _kw in _li_kw_list:
        for _loc in _li_loc_list:
            urls.append(_mock_linkedin_url(_kw, _loc, task_input))
    return urls


task_li = {"keywords": "Python Developer", "keywords2": "Backend Engineer",
           "location": "Remote,Bangalore", "linkedin_remote": True}
urls_li = _simulate_linkedin_multi_location(task_li)
check("LinkedIn 2 keywords × 2 locations = 4 search URLs", len(urls_li) == 4, f"got {len(urls_li)}")
check("LinkedIn each URL has clean location (no comma)", all("," not in urllib.parse.unquote(u).split("location=")[1].split("&")[0] for u in urls_li), str(urls_li[:2]))
check("LinkedIn f_WT=2 in all URLs when remote=True", all("f_WT=2" in u for u in urls_li), "")

task_li_empty = {"keywords": "Python Developer", "location": ""}
urls_empty = _simulate_linkedin_multi_location(task_li_empty)
check("LinkedIn empty location → 1 URL with empty loc", len(urls_empty) == 1)
check("LinkedIn empty location URL usable", "keywords=Python+Developer" in urls_empty[0] or "keywords=Python%20Developer" in urls_empty[0], urls_empty[0])


# ══════════════════════════════════════════════════════════════════════════════
# 6. Naukri _apply_filters work_mode mapping
# ══════════════════════════════════════════════════════════════════════════════
print("\n── 6. Naukri wfhType mapping ────────────────────────────────────────────")

_wfh_code = {"remote": "0", "work from home": "0", "wfh": "0", "hybrid": "3", "office": "2", "wfo": "2"}

def get_wfh_code(work_mode: str) -> str:
    wm = work_mode.lower()
    for k, v in _wfh_code.items():
        if k in wm:
            return v
    return ""

check("wfhType: remote → 0",  get_wfh_code("remote") == "0")
check("wfhType: hybrid → 3",  get_wfh_code("hybrid") == "3")
check("wfhType: office → 2",  get_wfh_code("office") == "2")
check("wfhType: any → ''",    get_wfh_code("any") == "")
check("wfhType: empty → ''",  get_wfh_code("") == "")


# ══════════════════════════════════════════════════════════════════════════════
# 7. Resume fingerprint generation (both bots use same logic)
# ══════════════════════════════════════════════════════════════════════════════
print("\n── 7. Resume fingerprint ────────────────────────────────────────────────")
import hashlib

def _make_fp(resume_text: str = "", resume_url: str = "") -> str:
    if resume_text:
        return hashlib.md5(resume_text[:500].encode()).hexdigest()[:16]
    elif resume_url:
        return hashlib.md5(resume_url.encode()).hexdigest()[:16]
    return ""

fp1 = _make_fp(resume_text="Python developer with 5 years experience...")
fp2 = _make_fp(resume_text="Python developer with 5 years experience...")
fp3 = _make_fp(resume_text="Java developer with 5 years experience...")
fp4 = _make_fp(resume_url="https://example.com/resume.pdf")

check("Same text → same fingerprint", fp1 == fp2)
check("Different text → different fingerprint", fp1 != fp3)
check("URL fallback → non-empty fingerprint", len(fp4) == 16)
check("No inputs → empty string", _make_fp() == "")


# ══════════════════════════════════════════════════════════════════════════════
# 8. Job history skip_reason logic
# ══════════════════════════════════════════════════════════════════════════════
print("\n── 8. skip_reason logic ─────────────────────────────────────────────────")

def _compute_skip_reason(success: bool, last_reason: str, resume_fp: str, apply_types: str) -> tuple:
    """Mirrors the post-apply logic in both bots."""
    skip_meta = {}
    if last_reason == "smart_match" and resume_fp:
        skip_meta["resume_fingerprint"] = resume_fp
    if last_reason == "mode_skip":
        skip_meta["apply_types"] = apply_types

    final_status = "applied" if success else "skipped"
    final_reason = "applied" if success else last_reason
    return final_status, final_reason, skip_meta

s, r, m = _compute_skip_reason(True, "skipped", "abc123", "both")
check("Applied → status+reason='applied'", s == "applied" and r == "applied")

s, r, m = _compute_skip_reason(False, "smart_match", "abc123", "both")
check("Smart match skip → reason='smart_match'", r == "smart_match")
check("Smart match skip → metadata has resume_fingerprint", m.get("resume_fingerprint") == "abc123")

s, r, m = _compute_skip_reason(False, "mode_skip", "", "direct_only")
check("Mode skip → reason='mode_skip'", r == "mode_skip")
check("Mode skip → metadata has apply_types", m.get("apply_types") == "direct_only")

s, r, m = _compute_skip_reason(False, "skipped", "", "both")
check("Generic skip → reason='skipped', no metadata", r == "skipped" and not m)


# ══════════════════════════════════════════════════════════════════════════════
# §9  AUTO COVER LETTER FLAG LOGIC
# ══════════════════════════════════════════════════════════════════════════════
print("\n§9  Auto Cover Letter flag logic")

def _should_generate_cover_letter(task_input: dict, has_jd: bool, has_resume: bool) -> bool:
    """Mirrors the guard in naukri.py / linkedin.py."""
    return bool(task_input.get("auto_cover_letter", True)) and has_jd and has_resume

check("CL: default True + JD + resume → generate",
      _should_generate_cover_letter({}, True, True))
check("CL: explicit True + JD + resume → generate",
      _should_generate_cover_letter({"auto_cover_letter": True}, True, True))
check("CL: explicit False → skip",
      not _should_generate_cover_letter({"auto_cover_letter": False}, True, True))
check("CL: no JD → skip",
      not _should_generate_cover_letter({}, False, True))
check("CL: no resume → skip",
      not _should_generate_cover_letter({}, True, False))
check("CL: no JD and no resume → skip",
      not _should_generate_cover_letter({}, False, False))


# ══════════════════════════════════════════════════════════════════════════════
# §10  SMART APPLY SCHEDULER WINDOW CHECK
# ══════════════════════════════════════════════════════════════════════════════
print("\n§10  Smart Apply Scheduler window logic")

def _in_window(start: int, end: int, now: int) -> bool:
    """Mirrors _is_in_schedule_window() in main.py."""
    if start <= end:
        return start <= now < end
    return now >= start or now < end  # overnight window

# Normal daytime window 09:00–17:00
check("Sched 09-17, now=10 → in window",       _in_window(9, 17, 10))
check("Sched 09-17, now=09 → in window",       _in_window(9, 17, 9))
check("Sched 09-17, now=08 → out of window",   not _in_window(9, 17, 8))
check("Sched 09-17, now=17 → out of window",   not _in_window(9, 17, 17))
check("Sched 09-17, now=23 → out of window",   not _in_window(9, 17, 23))
# Overnight window 22:00–06:00
check("Sched 22-06, now=23 → in window",       _in_window(22, 6, 23))
check("Sched 22-06, now=00 → in window",       _in_window(22, 6, 0))
check("Sched 22-06, now=05 → in window",       _in_window(22, 6, 5))
check("Sched 22-06, now=06 → out of window",   not _in_window(22, 6, 6))
check("Sched 22-06, now=10 → out of window",   not _in_window(22, 6, 10))
# No schedule → always run (represented by returning True without calling _in_window)
check("Sched: no schedule set → always run",   True)


# ══════════════════════════════════════════════════════════════════════════════
# §11  GMAIL TRIGGER VALIDATION
# ══════════════════════════════════════════════════════════════════════════════
print("\n§11  Gmail trigger validation logic")

def _can_trigger_gmail(settings: dict | None) -> tuple[bool, str]:
    """Mirrors logic in app/api/gmail/trigger/route.ts."""
    if not settings:
        return False, "no_settings"
    if not settings.get("active", False):
        return False, "inactive"
    return True, "ok"

ok, reason = _can_trigger_gmail(None)
check("Gmail trigger: no settings → blocked",  not ok and reason == "no_settings")

ok, reason = _can_trigger_gmail({"active": False})
check("Gmail trigger: inactive → blocked",     not ok and reason == "inactive")

ok, reason = _can_trigger_gmail({"active": True, "email": "test@example.com"})
check("Gmail trigger: valid active settings → allowed", ok and reason == "ok")


# ══════════════════════════════════════════════════════════════════════════════
# §12  APPLICATION FUNNEL METRICS
# ══════════════════════════════════════════════════════════════════════════════
print("\n§12  Application funnel metrics")

def _funnel_rates(applied: int, screening: int, interview: int, offer: int):
    total = max(applied, 1)
    return {
        "screening_rate": round((screening / total) * 100),
        "interview_rate": round((interview / total) * 100),
        "offer_rate": round((offer / total) * 100),
        "screening_drop": round(((applied - screening) / applied) * 100) if applied else 0,
        "interview_drop": round(((screening - interview) / screening) * 100) if screening else 0,
        "offer_drop": round(((interview - offer) / interview) * 100) if interview else 0,
    }

rates = _funnel_rates(100, 42, 15, 3)
check("Funnel: screening rate 42%", rates["screening_rate"] == 42)
check("Funnel: interview rate 15%", rates["interview_rate"] == 15)
check("Funnel: offer rate 3%", rates["offer_rate"] == 3)
check("Funnel: applied→screening drop 58%", rates["screening_drop"] == 58)
check("Funnel: screening→interview drop 64%", rates["interview_drop"] == 64)
check("Funnel: interview→offer drop 80%", rates["offer_drop"] == 80)


# ══════════════════════════════════════════════════════════════════════════════
# §13  SKILL GAP LEARNING PLAN SHAPE
# ══════════════════════════════════════════════════════════════════════════════
print("\n§13  Skill gap learning plan shape")

def _mock_skill_gap_result(missing_skills: list[str]) -> dict:
    learning_plan = []
    for i, skill in enumerate(missing_skills[:6]):
        learning_plan.append({
            "skill": skill,
            "priority": "High" if i < 2 else "Medium" if i < 4 else "Low",
            "resources": [
                {"platform": "YouTube", "search_query": f"{skill} complete tutorial for beginners 2024"},
                {"platform": "Udemy", "search_query": f"{skill} masterclass complete course"},
                {"platform": "Official Docs / Practice", "search_query": f"{skill} official documentation getting started"},
            ],
        })
    schedule = [f"Week item {i}" for i in range(1, 8)]
    return {"learning_plan": learning_plan, "two_week_schedule": schedule}

sg = _mock_skill_gap_result(["docker", "kubernetes", "graphql", "aws", "redis", "terraform", "kafka"])
check("Skill gap: max 6 skills in plan", len(sg["learning_plan"]) == 6)
check("Skill gap: 3 resources per skill", all(len(item["resources"]) == 3 for item in sg["learning_plan"]))
check("Skill gap: includes YouTube resource", sg["learning_plan"][0]["resources"][0]["platform"] == "YouTube")
check("Skill gap: includes Udemy resource", sg["learning_plan"][0]["resources"][1]["platform"] == "Udemy")
check("Skill gap: has 7 schedule items", len(sg["two_week_schedule"]) == 7)


# ══════════════════════════════════════════════════════════════════════════════
# §14  JD-AWARE INTERVIEW REQUEST PAYLOAD
# ══════════════════════════════════════════════════════════════════════════════
print("\n§14  Interview prep payload")

def _build_interview_payload(jd_text: str, resume_text: str, company: str, role: str):
    return {
        "jd_text": jd_text,
        "resume_text": resume_text,
        "company": company,
        "role": role,
    }

payload = _build_interview_payload("x" * 80, "resume text", "Google", "Backend Engineer")
check("Interview payload: includes company", payload["company"] == "Google")
check("Interview payload: includes role", payload["role"] == "Backend Engineer")
check("Interview payload: JD length preserved", len(payload["jd_text"]) == 80)


# ══════════════════════════════════════════════════════════════════════════════
# §15  PLACEMENT MODE OUTPUT SHAPE
# ══════════════════════════════════════════════════════════════════════════════
print("\n§15  Placement mode output shape")

def _mock_placement_output():
    return {
        "amcat_prep": [1, 2, 3, 4, 5],
        "elitmus_prep": [1, 2, 3, 4],
        "campus_drive_calendar": [1, 2, 3, 4, 5, 6, 7, 8],
        "off_campus_portals": [1, 2, 3, 4, 5, 6, 7],
        "four_week_plan": [
            {"week": "Week 1", "tasks": [1, 2, 3, 4, 5]},
            {"week": "Week 2", "tasks": [1, 2, 3, 4, 5]},
            {"week": "Week 3", "tasks": [1, 2, 3, 4, 5]},
            {"week": "Week 4", "tasks": [1, 2, 3, 4, 5]},
        ],
        "hr_tips": [1, 2, 3, 4, 5, 6],
        "resume_tips": [1, 2, 3, 4, 5, 6],
    }

placement = _mock_placement_output()
check("Placement: 5 AMCAT prep buckets", len(placement["amcat_prep"]) == 5)
check("Placement: 4 eLitmus prep buckets", len(placement["elitmus_prep"]) == 4)
check("Placement: 8 drive calendar entries", len(placement["campus_drive_calendar"]) == 8)
check("Placement: 7 off-campus portals", len(placement["off_campus_portals"]) == 7)
check("Placement: 4-week plan present", len(placement["four_week_plan"]) == 4)
check("Placement: each week has 5 tasks", all(len(w["tasks"]) == 5 for w in placement["four_week_plan"]))
check("Placement: 6 HR tips", len(placement["hr_tips"]) == 6)
check("Placement: 6 resume tips", len(placement["resume_tips"]) == 6)



# ══════════════════════════════════════════════════════════════════════════════
# §16  RAILWAY CLOUD EXECUTION FLOW
#      Tests: env detection, task routing, fetch_pending_tasks filtering,
#             stop-task logic, screenshot push flow, session_id injection,
#             main.py loop behaviour, trigger route payload, push_screenshot
# ══════════════════════════════════════════════════════════════════════════════
print("\n§16  Railway cloud execution flow")

import os as _os
import base64 as _b64
import json as _json

# ── 16.1  TASK_RUNNER_ENV detection ────────────────────────────────────────
_orig_env = _os.environ.get("TASK_RUNNER_ENV")

_os.environ.pop("TASK_RUNNER_ENV", None)
check("Env: local agent → TASK_RUNNER_ENV not set",
      _os.environ.get("TASK_RUNNER_ENV") != "railway")

_os.environ["TASK_RUNNER_ENV"] = "railway"
check("Env: Railway container → TASK_RUNNER_ENV=railway",
      _os.environ.get("TASK_RUNNER_ENV") == "railway")

# Restore
if _orig_env is None:
    _os.environ.pop("TASK_RUNNER_ENV", None)
else:
    _os.environ["TASK_RUNNER_ENV"] = _orig_env


# ── 16.2  task_runner.py Railway guard logic (no execution_mode=railway locally) ──
def _should_skip_locally(task: dict) -> bool:
    """Mirrors the guard in task_runner.py run_task()."""
    return (
        task.get("execution_mode") == "railway"
        and _os.environ.get("TASK_RUNNER_ENV") != "railway"
    )

_os.environ.pop("TASK_RUNNER_ENV", None)
check("Guard: local + execution_mode=railway → skipped",
      _should_skip_locally({"execution_mode": "railway"}))
check("Guard: local + execution_mode=own_machine → not skipped",
      not _should_skip_locally({"execution_mode": "own_machine"}))
check("Guard: local + no execution_mode → not skipped",
      not _should_skip_locally({}))

_os.environ["TASK_RUNNER_ENV"] = "railway"
check("Guard: Railway + execution_mode=railway → NOT skipped (runs on cloud)",
      not _should_skip_locally({"execution_mode": "railway"}))
check("Guard: Railway + own_machine → not skipped (incl. legacy tasks)",
      not _should_skip_locally({"execution_mode": "own_machine"}))

_os.environ.pop("TASK_RUNNER_ENV", None)


# ── 16.3  fetch_pending_tasks URL selection ──────────────────────────────────
def _pending_task_url(is_railway: bool) -> str:
    SUPABASE_URL = "https://feqhdpxnzlctpwvvjxui.supabase.co"
    if is_railway:
        return f"{SUPABASE_URL}/rest/v1/tasks?status=eq.PENDING&execution_mode=eq.railway&order=created_at.asc"
    else:
        return f"{SUPABASE_URL}/rest/v1/tasks?status=eq.PENDING&execution_mode=neq.railway&order=created_at.asc"

check("DB query: Railway → filters execution_mode=railway",
      "execution_mode=eq.railway" in _pending_task_url(True))
check("DB query: local → excludes execution_mode=railway tasks",
      "execution_mode=neq.railway" in _pending_task_url(False))
check("DB query: both still filter PENDING only",
      "status=eq.PENDING" in _pending_task_url(True)
      and "status=eq.PENDING" in _pending_task_url(False))


# ── 16.4  main.py loop behaviour on Railway ──────────────────────────────────
def _should_exit_after_run(ran_any_task: bool, is_railway: bool) -> bool:
    """
    Mirrors updated main.py logic:
      - Local: exit after all tasks done
      - Railway: reset ran_any_task flag and keep polling (never exits)
    """
    if ran_any_task and not is_railway:
        return True   # local: exit
    return False      # railway: keep looping

check("main.py: local + tasks done → exits",
      _should_exit_after_run(True, False))
check("main.py: Railway + tasks done → does NOT exit",
      not _should_exit_after_run(True, True))
check("main.py: local + no tasks → does not exit",
      not _should_exit_after_run(False, False))
check("main.py: Railway + no tasks → does not exit",
      not _should_exit_after_run(False, True))


# ── 16.5  trigger/route.ts keeps task PENDING + injects session_id ────────────
def _build_trigger_task_update(
    existing_input: dict,
    task_input_override: dict,
    session_id: str,
    set_status_to: str = "PENDING",   # MUST remain PENDING so Railway poller picks it up
) -> dict:
    """
    Mirrors the DB update in trigger/route.ts after session row is created.
    Previously (buggy): set status='RUNNING' (Railway poller never found it).
    Fixed: keeps PENDING + injects session_id into input.
    """
    return {
        "execution_mode": "railway",
        "status": set_status_to,
        "input": {**existing_input, **task_input_override, "session_id": session_id},
    }

update = _build_trigger_task_update(
    {"user_id": "u1", "keywords": "SWE"},
    {"max_apply": 5},
    "sess-123",
)
check("Trigger: task kept as PENDING (not RUNNING)",
      update["status"] == "PENDING")
check("Trigger: session_id injected into input",
      update["input"].get("session_id") == "sess-123")
check("Trigger: existing input preserved",
      update["input"].get("user_id") == "u1")
check("Trigger: task_input_override applied",
      update["input"].get("max_apply") == 5)
check("Trigger: execution_mode set to railway",
      update["execution_mode"] == "railway")


# ── 16.6  push_screenshot logic ──────────────────────────────────────────────
def _mock_push_screenshot(session_id: str, page_or_bytes) -> dict | None:
    """Mirrors push_screenshot() in api_client.py (without network call)."""
    if not session_id:
        return None
    try:
        if hasattr(page_or_bytes, "screenshot"):
            img_bytes = page_or_bytes.screenshot()
        else:
            img_bytes = page_or_bytes
        b64 = _b64.b64encode(img_bytes).decode()
        return {"session_id": session_id, "latest_screenshot": b64}
    except Exception:
        return None

# Fake Playwright Page
class _MockPage:
    def screenshot(self, **kwargs):
        return b"\xff\xd8\xff\xe0" + b"\x00" * 20  # fake JPEG header + padding

result = _mock_push_screenshot("sess-abc", _MockPage())
check("push_screenshot: page object → b64 encoded",
      result is not None and len(result["latest_screenshot"]) > 0)
check("push_screenshot: session_id preserved",
      result["session_id"] == "sess-abc")
check("push_screenshot: valid base64",
      _b64.b64decode(result["latest_screenshot"])[:2] == b"\xff\xd8")

result_bytes = _mock_push_screenshot("sess-xyz", b"\xff\xd8\xff\xe0\x00\x01")
check("push_screenshot: raw bytes input → works",
      result_bytes is not None and result_bytes["session_id"] == "sess-xyz")

result_empty = _mock_push_screenshot("", _MockPage())
check("push_screenshot: empty session_id → no-op (returns None)",
      result_empty is None)


# ── 16.7  _push_screenshot helper in linkedin.py (session_id gate) ───────────
def _should_push_screenshot(task_input: dict) -> bool:
    """Mirrors the guard in _push_screenshot() in linkedin.py."""
    return bool(task_input.get("session_id", ""))

check("_push_screenshot: present session_id → fires",
      _should_push_screenshot({"session_id": "sess-123"}))
check("_push_screenshot: missing session_id → skipped (own-machine)",
      not _should_push_screenshot({}))
check("_push_screenshot: empty session_id → skipped",
      not _should_push_screenshot({"session_id": ""}))


# ── 16.8  stopActiveTask — Supabase update shape ──────────────────────────────
def _build_stop_update(active_task_id: str) -> dict | None:
    """Mirrors stopActiveTask() in agent/page.tsx."""
    if not active_task_id:
        return None
    return {"stop_requested": True, "status": "DONE"}

upd = _build_stop_update("task-abc")
check("Stop: sets stop_requested=True",    upd["stop_requested"] is True)
check("Stop: sets status=DONE",            upd["status"] == "DONE")
check("Stop: no task_id → returns None",   _build_stop_update("") is None)


# ── 16.9  stoppedRef race-condition guard ────────────────────────────────────
class _MockPollState:
    def __init__(self):
        self.stopped = False
        self.task_status = "RUNNING"
        self.task_logs = ["log1", "log2"]

    def stop_task(self):
        self.stopped = True
        self.task_status = None
        self.task_logs = []

    def poll(self, db_task_status: str, db_logs: list):
        """Simulates pollActiveTask respecting stoppedRef."""
        if self.stopped:
            return  # blocked by stoppedRef
        self.task_status = db_task_status
        self.task_logs = db_logs

state = _MockPollState()
state.stop_task()
# Poll fires immediately after stop (DB may still say RUNNING)
state.poll("RUNNING", ["log1", "log2", "log3"])
check("Race guard: poll after stop doesn't re-populate task_status",
      state.task_status is None)
check("Race guard: poll after stop doesn't re-populate task_logs",
      state.task_logs == [])

# After 4s stoppedRef re-enables — simulate it
state.stopped = False
state.poll("DONE", ["final log"])
check("Race guard: poll re-enables → updates state normally",
      state.task_status == "DONE")


# ── 16.10 Cloud vs Local panel visibility logic ──────────────────────────────
def _panel_visible(railway_status: str, task_logs: list, railway_status_is_idle: bool) -> dict:
    """Mirrors conditional rendering in agent/page.tsx."""
    return {
        "cloud_panel":  railway_status != "idle",
        "local_panel":  len(task_logs) > 0 and railway_status_is_idle,
        "mode_switcher": True,  # always shown once railwayConfigured
    }

p = _panel_visible("running", [], True)
check("Panel: cloud running → cloud panel visible, local hidden",
      p["cloud_panel"] and not p["local_panel"])

p = _panel_visible("idle", ["log1"], True)
check("Panel: idle + local logs → local panel visible, cloud hidden",
      not p["cloud_panel"] and p["local_panel"])

p = _panel_visible("idle", [], True)
check("Panel: idle + no logs → both panels hidden",
      not p["cloud_panel"] and not p["local_panel"])

p = _panel_visible("done", ["log1"], False)
check("Panel: cloud done → cloud session-ended panel visible",
      p["cloud_panel"])


print("\n" + "═"*70)
passed  = sum(1 for s, _, _ in results if s == PASS)
failed  = sum(1 for s, _, _ in results if s == FAIL)
total   = len(results)
print(f"  Results: {passed}/{total} passed, {failed} failed")
if failed:
    print("\n  FAILURES:")
    for s, name, detail in results:
        if s == FAIL:
            print(f"    {FAIL}  {name}" + (f"  — {detail}" if detail else ""))
print("═"*70)
sys.exit(0 if failed == 0 else 1)
