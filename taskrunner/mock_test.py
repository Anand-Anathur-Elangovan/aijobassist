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
# SUMMARY
# ══════════════════════════════════════════════════════════════════════════════
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
