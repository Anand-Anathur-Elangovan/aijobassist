"""
Job Bot Notifier — sends actionable alerts to user via:
  • Telegram Bot (primary)   — free, instant, works on mobile
  • Gmail SMTP   (fallback)  — HTML email with full details

Notification types:
  notify_manual_required  — bot stuck on external apply; user needs to complete it
  notify_session_summary  — end-of-session stats (applied / stuck / skipped)

Config keys (read from task_input dict first, then os.environ fallback):
  telegram_bot_token   — Telegram bot token from @BotFather
  telegram_chat_id     — Your personal chat ID (send /start to @userinfobot)
  gmail_address        — Gmail address used for SMTP (needs App Password)
  gmail_app_password   — Gmail App Password (NOT your regular password)
                         Get one: https://myaccount.google.com/apppasswords
  notification_email   — Where to send email alerts (defaults to gmail_address)

Setup (one-time, 5 min):
  1. Open Telegram → search @BotFather → /newbot → copy token
  2. Search @userinfobot → /start → copy your Id number
  3. Paste both into your .env or the task config

Never raises — all errors are caught and printed as warnings.
"""

import os
import smtplib
import textwrap
from datetime import datetime
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Optional

try:
    import requests as _requests
    _HAS_REQUESTS = True
except ImportError:
    _HAS_REQUESTS = False


# ── Config helper ──────────────────────────────────────────────────────────────

def _cfg(task_input: dict, key: str, env_key: str = "") -> str:
    """Read config from task_input first, then os.environ fallback."""
    val = (task_input or {}).get(key, "")
    if not val and env_key:
        val = os.environ.get(env_key, "")
    return val.strip() if isinstance(val, str) else str(val or "").strip()


def _now_str() -> str:
    return datetime.now().strftime("%d %b %Y, %I:%M %p")


# ── Telegram sender ────────────────────────────────────────────────────────────

def _tg_send(bot_token: str, chat_id: str, html_text: str) -> bool:
    """
    Send a Telegram HTML message (up to 4096 chars).
    Splits into multiple messages if longer.
    Returns True if at least one message sent successfully.
    """
    if not _HAS_REQUESTS:
        print("  [NOTIFY] 'requests' not installed — Telegram unavailable")
        return False
    if not bot_token or not chat_id:
        return False

    # Telegram max message length is 4096 chars
    chunks = [html_text[i:i+4000] for i in range(0, len(html_text), 4000)]
    success = False
    for chunk in chunks:
        try:
            resp = _requests.post(
                f"https://api.telegram.org/bot{bot_token}/sendMessage",
                json={
                    "chat_id":                  chat_id,
                    "text":                     chunk,
                    "parse_mode":               "HTML",
                    "disable_web_page_preview": False,
                },
                timeout=15,
            )
            data = resp.json()
            if resp.status_code == 200 and data.get("ok"):
                success = True
            else:
                err = data.get("description", resp.text[:200])
                print(f"  [NOTIFY] Telegram API error: {err}")
        except Exception as e:
            print(f"  [NOTIFY] Telegram send failed: {e}")
    return success


# ── Gmail sender ───────────────────────────────────────────────────────────────

def _gmail_send(gmail_address: str, app_password: str,
                to: str, subject: str,
                plain_body: str, html_body: str = "") -> bool:
    """Send HTML+plain email via Gmail SMTP. Returns True on success."""
    try:
        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"]    = f"AI Job Bot <{gmail_address}>"
        msg["To"]      = to
        msg.attach(MIMEText(plain_body, "plain", "utf-8"))
        if html_body:
            msg.attach(MIMEText(html_body, "html", "utf-8"))

        with smtplib.SMTP("smtp.gmail.com", 587) as srv:
            srv.ehlo()
            srv.starttls()
            srv.login(gmail_address, app_password)
            srv.sendmail(gmail_address, to, msg.as_string())

        print(f"  [NOTIFY] Email sent to {to}: {subject}")
        return True
    except smtplib.SMTPAuthenticationError:
        print("  [NOTIFY] Gmail auth failed — check App Password (not regular password)")
        return False
    except Exception as e:
        print(f"  [NOTIFY] Gmail send failed: {e}")
        return False


# ── Answer formatter ───────────────────────────────────────────────────────────

def _fmt_answers_plain(answers: dict) -> str:
    """Format answers dict into a readable copy-paste block (plain text)."""
    if not answers:
        return "(no answers captured)"
    lines = []
    for label, value in answers.items():
        label_clean = str(label).replace("_", " ").title()
        value_str   = str(value).strip()
        if len(value_str) > 100:
            # Long text (cover letter / summary) — indent under label
            wrapped = textwrap.indent(textwrap.fill(value_str, 80), "  ")
            lines.append(f"{label_clean}:\n{wrapped}")
        else:
            lines.append(f"{label_clean:<32}: {value_str}")
    return "\n".join(lines)


def _fmt_answers_html(answers: dict) -> str:
    """Format answers dict as HTML table rows."""
    if not answers:
        return "<tr><td colspan='2'>(no answers captured)</td></tr>"
    rows = []
    for label, value in answers.items():
        label_clean = str(label).replace("_", " ").title()
        value_str   = str(value).strip().replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        style = "white-space:pre-wrap;word-break:break-word;" if len(value_str) > 80 else ""
        rows.append(
            f"<tr>"
            f"<td style='padding:6px 10px;font-weight:bold;white-space:nowrap;vertical-align:top;background:#f8f9fa;border:1px solid #dee2e6'>{label_clean}</td>"
            f"<td style='padding:6px 10px;border:1px solid #dee2e6;{style}'>{value_str}</td>"
            f"</tr>"
        )
    return "\n".join(rows)


def _esc_tg(text: str) -> str:
    """Escape special HTML chars for Telegram HTML mode."""
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


# ── Message builders: Manual Required ─────────────────────────────────────────

def _build_manual_tg(company: str, job_title: str, apply_url: str,
                     linkedin_url: str, stuck_reason: str,
                     answers: dict, applied_today: int) -> str:
    company   = _esc_tg(company   or "Unknown Company")
    job_title = _esc_tg(job_title or "Unknown Position")
    reason    = _esc_tg(stuck_reason or "Could not complete submission")
    answer_block = _esc_tg(_fmt_answers_plain(answers))

    parts = [
        "🔔 <b>Action Required — External Application</b>",
        "",
        f"🏢 <b>Company :</b>  {company}",
        f"💼 <b>Job     :</b>  {job_title}",
        f"⚠️ <b>Stuck at:</b>  {reason}",
        f"🕐 <b>Time    :</b>  {_now_str()}",
        "",
        f'🔗 <b>Apply here →</b>  <a href="{apply_url}">{apply_url[:70]}</a>',
    ]
    if linkedin_url and linkedin_url != apply_url:
        parts.append(f'🔍 <a href="{linkedin_url}">View LinkedIn job post →</a>')

    parts += [
        "",
        "📋 <b>Answers to copy-paste into the form:</b>",
        "<pre>" + answer_block + "</pre>",
        "",
        "─────────────────────────────────",
        f"🤖 AI Bot applied <b>{applied_today}</b> job(s) this session",
        "⏱ <i>This one takes ~3–5 minutes to complete manually</i>",
    ]
    return "\n".join(parts)


def _build_manual_email(company: str, job_title: str, apply_url: str,
                        linkedin_url: str, stuck_reason: str,
                        answers: dict, applied_today: int) -> tuple[str, str, str]:
    """Returns (subject, plain_text, html_body)."""
    co  = company   or "Unknown Company"
    jt  = job_title or "Unknown Position"
    subject     = f"[AI Job Bot] Action Required: {co} — {jt}"
    answer_plain = _fmt_answers_plain(answers)
    answer_html  = _fmt_answers_html(answers)

    li_line_plain = f"LinkedIn post : {linkedin_url}" if linkedin_url else ""
    li_line_html  = f'<p><a href="{linkedin_url}">View LinkedIn Job Post →</a></p>' if linkedin_url else ""

    plain = f"""
ACTION REQUIRED — External Application
=======================================
Company   : {co}
Job       : {jt}
Stuck at  : {stuck_reason or "Could not complete submission"}
Time      : {_now_str()}

APPLY HERE:
{apply_url}
{li_line_plain}

ANSWERS TO COPY-PASTE INTO THE FORM:
{answer_plain}

---------------------------------------
AI Bot applied {applied_today} jobs via Easy Apply today.
This one needs ~3–5 minutes to complete manually.
    """.strip()

    html = f"""
<!DOCTYPE html>
<html>
<body style="font-family:Arial,sans-serif;max-width:660px;margin:0 auto;color:#333">

  <div style="background:#e74c3c;color:white;padding:16px 20px;border-radius:6px 6px 0 0">
    <h2 style="margin:0;font-size:18px">🔔 Action Required — External Application</h2>
  </div>

  <div style="border:1px solid #ddd;border-top:none;padding:20px;border-radius:0 0 6px 6px">

    <table style="border-collapse:collapse;width:100%;margin-bottom:16px">
      <tr style="background:#fef9f0">
        <td style="padding:8px 12px;font-weight:bold;width:120px;border:1px solid #fce4b3">Company</td>
        <td style="padding:8px 12px;border:1px solid #fce4b3">{_esc_tg(co)}</td>
      </tr>
      <tr>
        <td style="padding:8px 12px;font-weight:bold;border:1px solid #e9ecef">Job Title</td>
        <td style="padding:8px 12px;border:1px solid #e9ecef">{_esc_tg(jt)}</td>
      </tr>
      <tr style="background:#fef9f0">
        <td style="padding:8px 12px;font-weight:bold;border:1px solid #fce4b3;color:#e74c3c">Stuck At</td>
        <td style="padding:8px 12px;border:1px solid #fce4b3;color:#e74c3c">{_esc_tg(stuck_reason or "Could not complete submission")}</td>
      </tr>
      <tr>
        <td style="padding:8px 12px;font-weight:bold;border:1px solid #e9ecef">Time</td>
        <td style="padding:8px 12px;border:1px solid #e9ecef">{_now_str()}</td>
      </tr>
    </table>

    <a href="{apply_url}"
       style="display:inline-block;background:#2980b9;color:white;padding:12px 24px;
              text-decoration:none;border-radius:5px;font-size:15px;font-weight:bold;margin-bottom:8px">
      🔗 Open Application Form →
    </a>
    {li_line_html}

    <h3 style="margin-top:24px;margin-bottom:8px">📋 Answers to Copy-Paste</h3>
    <p style="color:#666;font-size:13px;margin-bottom:10px">
      Use these answers when filling the form. Each row = one field.
    </p>
    <table style="border-collapse:collapse;width:100%;font-size:13px">
      {answer_html}
    </table>

    <hr style="margin:24px 0;border:none;border-top:1px solid #eee">
    <p style="color:#888;font-size:12px;margin:0">
      🤖 AI Bot applied <strong>{applied_today}</strong> jobs via Easy Apply today.
      This one needs ~3–5 minutes to complete manually.
    </p>
  </div>

</body>
</html>
    """.strip()

    return subject, plain, html


# ── Message builders: Session Summary ─────────────────────────────────────────

def _build_summary_tg(stats: dict) -> str:
    applied       = stats.get("applied", 0)
    easy_applied  = stats.get("easy_applied", -1)    # -1 means not tracked separately
    ext_applied   = stats.get("external_applied", 0)
    manual        = stats.get("manual_needed", 0)
    skipped       = stats.get("skipped", 0)
    errors        = stats.get("errors", 0)
    duration      = stats.get("duration_minutes", 0)
    manual_jobs   = stats.get("manual_jobs", [])     # list of {company, title, url}
    jobs          = stats.get("jobs", [])             # per-job report list
    resume_url    = stats.get("resume_url", "")
    resume_name   = stats.get("resume_filename", "resume.pdf")

    parts = [
        "📊 <b>AI Job Bot — Session Complete</b>",
        "",
    ]

    # Show apply type breakdown when tracked separately
    if easy_applied >= 0 and ext_applied > 0:
        parts.append(f"✅ Easy Apply submitted  : <b>{easy_applied}</b>")
        parts.append(f"🌐 External Apply submitted: <b>{ext_applied}</b>")
    elif easy_applied >= 0:
        parts.append(f"✅ Easy Apply submitted  : <b>{easy_applied}</b>")
    else:
        parts.append(f"✅ Applied               : <b>{applied}</b>")

    parts += [
        f"📋 Manual action needed  : <b>{manual}</b>",
        f"⏭️  Skipped (low match)  : <b>{skipped}</b>",
    ]
    if errors:
        parts.append(f"❌ Errors                 : <b>{errors}</b>")
    if duration:
        parts.append(f"⏱  Duration              : <b>{duration} min</b>")
    parts.append(f"🕐 Completed             : {_now_str()}")

    # Per-job details (score + link + status)
    if jobs:
        applied_jobs = [j for j in jobs if j.get("status") == "applied"]
        skipped_jobs = [j for j in jobs if j.get("status") == "skipped"]

        if applied_jobs:
            parts += ["", "✅ <b>Applied Jobs:</b>"]
            for j in applied_jobs[:12]:
                co    = _esc_tg(j.get("company",   "?") or "?")
                jt    = _esc_tg(j.get("job_title", "?") or "?")
                url   = j.get("url", "")
                score = j.get("score")
                atype = j.get("apply_type", "easy_apply")
                icon  = "🌐" if atype == "external" else "✅"
                score_str = f" | <b>{score}%</b>" if score is not None else ""
                if url:
                    parts.append(f'{icon} <a href="{url}">{co} — {jt}</a>{score_str}')
                else:
                    parts.append(f'{icon} {co} — {jt}{score_str}')
                # Per-job resume link: tailored takes priority over original
                _job_resume = j.get("tailored_resume_url") or j.get("resume_url") or ""
                _job_fname  = j.get("resume_filename", "resume.pdf")
                _label      = "Tailored resume" if j.get("tailored_resume_url") else "Resume used"
                if _job_resume:
                    parts.append(f'   📄 <a href="{_job_resume}">{_label}: {_esc_tg(_job_fname)}</a>')
            if len(applied_jobs) > 12:
                parts.append(f"   … and {len(applied_jobs) - 12} more (see email)")

        if skipped_jobs:
            parts += ["", "⏭️ <b>Skipped Jobs:</b>"]
            for j in skipped_jobs[:8]:
                co     = _esc_tg(j.get("company",   "?") or "?")
                jt     = _esc_tg(j.get("job_title", "?") or "?")
                score  = j.get("score")
                reason = _esc_tg(j.get("skip_reason", "") or "")
                score_str  = f" | {score}%" if score is not None else ""
                reason_str = f" ({reason})" if reason else ""
                parts.append(f"⏭ {co} — {jt}{score_str}{reason_str}")

    if manual_jobs:
        parts += ["", "📌 <b>Tap a link to open &amp; complete:</b>"]
        for i, j in enumerate(manual_jobs[:15], 1):
            co  = _esc_tg(j.get("company", "?"))
            jt  = _esc_tg(j.get("title",   "?"))
            url = j.get("url", "")
            parts.append(f'{i}. <a href="{url}">{co} — {jt}</a>')
        if len(manual_jobs) > 15:
            parts.append(f"   … and {len(manual_jobs) - 15} more (see email)")

    if applied == 0 and manual == 0:
        parts += ["", "ℹ️ <i>No jobs processed this session.</i>"]
    elif manual > 0:
        parts += ["", "⚠️ <i>Tap each link above, paste the answers from earlier alerts, and submit!</i>"]

    return "\n".join(parts)


def _build_summary_email(stats: dict) -> tuple[str, str, str]:
    applied       = stats.get("applied", 0)
    easy_applied  = stats.get("easy_applied", -1)
    ext_applied   = stats.get("external_applied", 0)
    manual        = stats.get("manual_needed", 0)
    skipped       = stats.get("skipped", 0)
    errors        = stats.get("errors", 0)
    duration      = stats.get("duration_minutes", 0)
    manual_jobs   = stats.get("manual_jobs", [])
    jobs          = stats.get("jobs", [])  # per-job report

    subject = (
        f"[AI Job Bot] Session Done — {applied} submitted"
        + (f", {manual} need your action" if manual else "")
    )

    # Per-job rows
    applied_jobs = [j for j in jobs if j.get("status") == "applied"]
    skipped_jobs = [j for j in jobs if j.get("status") == "skipped"]

    def _job_row_plain(i, j):
        co     = j.get("company", "?") or "?"
        jt     = j.get("job_title", "?") or "?"
        url    = j.get("url", "")
        score  = j.get("score")
        atype  = j.get("apply_type", "easy_apply")
        status = j.get("status", "")
        reason = j.get("skip_reason", "")
        score_str  = f" | {score}%" if score is not None else ""
        reason_str = f" ({reason})" if reason else ""
        atype_str  = " [External]" if atype == "external" else ""
        return f"  {i}. {co} — {jt}{score_str}{atype_str}{reason_str}\n     {url}"

    def _job_row_html(i, j):
        co     = _esc_tg(j.get("company",   "?") or "?")
        jt     = _esc_tg(j.get("job_title", "?") or "?")
        url    = j.get("url", "")
        score  = j.get("score")
        atype  = j.get("apply_type", "easy_apply")
        status = j.get("status", "")
        reason = _esc_tg(j.get("skip_reason", "") or "")
        score_str = f"{score}%" if score is not None else "—"
        atype_icon = "🌐" if atype == "external" else "✅"
        status_color = "#27ae60" if status == "applied" else "#95a5a6"
        link = f"<a href='{url}' style='color:#2980b9'>Open →</a>" if url else "—"
        return (
            f"<tr>"
            f"<td style='padding:6px 8px;border:1px solid #dee2e6'>{i}</td>"
            f"<td style='padding:6px 8px;border:1px solid #dee2e6;font-weight:bold'>{co}</td>"
            f"<td style='padding:6px 8px;border:1px solid #dee2e6'>{jt}</td>"
            f"<td style='padding:6px 8px;border:1px solid #dee2e6;text-align:center'>{score_str}</td>"
            f"<td style='padding:6px 8px;border:1px solid #dee2e6;text-align:center'>{atype_icon}</td>"
            f"<td style='padding:6px 8px;border:1px solid #dee2e6;color:{status_color}'>{reason or status.title()}</td>"
            f"<td style='padding:6px 8px;border:1px solid #dee2e6'>{link}</td>"
            f"</tr>"
        )

    applied_rows_plain = "\n".join(_job_row_plain(i, j) for i, j in enumerate(applied_jobs, 1)) if applied_jobs else "  None"
    skipped_rows_plain = "\n".join(_job_row_plain(i, j) for i, j in enumerate(skipped_jobs, 1)) if skipped_jobs else "  None"
    applied_rows_html  = "\n".join(_job_row_html(i, j) for i, j in enumerate(applied_jobs, 1)) if applied_jobs else "<tr><td colspan='7' style='padding:8px;text-align:center;color:#888'>None</td></tr>"
    skipped_rows_html  = "\n".join(_job_row_html(i, j) for i, j in enumerate(skipped_jobs, 1)) if skipped_jobs else ""

    manual_rows_plain = "\n".join(
        f"  {i}. {j.get('company','?')} — {j.get('title','?')}\n     {j.get('url','')}"
        for i, j in enumerate(manual_jobs, 1)
    ) if manual_jobs else "  None"

    manual_rows_html = "\n".join(
        f"<tr>"
        f"<td style='padding:8px;border:1px solid #dee2e6'>{i}</td>"
        f"<td style='padding:8px;border:1px solid #dee2e6;font-weight:bold'>{_esc_tg(j.get('company','?'))}</td>"
        f"<td style='padding:8px;border:1px solid #dee2e6'>{_esc_tg(j.get('title','?'))}</td>"
        f"<td style='padding:8px;border:1px solid #dee2e6'><a href='{j.get('url','')}' style='color:#2980b9'>Open →</a></td>"
        f"</tr>"
        for i, j in enumerate(manual_jobs, 1)
    ) if manual_jobs else "<tr><td colspan='4' style='padding:8px;text-align:center;color:#888'>None</td></tr>"

    apply_label = "Applied" if easy_applied < 0 else "Easy Apply Submitted"
    plain = f"""
AI JOB BOT — SESSION SUMMARY
=======================================
{apply_label}        : {applied if easy_applied < 0 else easy_applied}
{("External Apply Submitted : " + str(ext_applied)) if ext_applied > 0 else ""}
Manual action needed : {manual}
Skipped (low match)  : {skipped}
Errors               : {errors}
Duration             : {duration} minutes
Completed at         : {_now_str()}

APPLIED JOBS:
{applied_rows_plain}

SKIPPED JOBS:
{skipped_rows_plain}

MANUAL APPLICATIONS:
{manual_rows_plain}
    """.strip()

    _easy_label  = "✅ Easy Apply Submitted" if easy_applied >= 0 else "✅ Applied"
    _easy_count  = easy_applied if easy_applied >= 0 else applied
    _ext_row_html = (
        f"<tr><td style='padding:10px 14px;font-size:15px;border:1px solid #a9dfbf'>🌐 External Apply Submitted</td>"
        f"<td style='padding:10px 14px;font-size:22px;font-weight:bold;color:#1a6b3c;border:1px solid #a9dfbf'>{ext_applied}</td></tr>"
        if ext_applied > 0 else ""
    )

    _jobs_table_html = ""
    if applied_jobs:
        _rows = "\n".join(_job_row_html(i, j) for i, j in enumerate(applied_jobs, 1))
        _jobs_table_html += (
            "<h3 style='margin-top:24px;margin-bottom:8px'>✅ Applied Jobs</h3>"
            "<table style='border-collapse:collapse;width:100%;font-size:12px'>"
            "<thead><tr style='background:#27ae60;color:white'>"
            "<th style='padding:6px 8px'>#</th>"
            "<th style='padding:6px 8px;text-align:left'>Company</th>"
            "<th style='padding:6px 8px;text-align:left'>Position</th>"
            "<th style='padding:6px 8px'>Score</th>"
            "<th style='padding:6px 8px'>Type</th>"
            "<th style='padding:6px 8px;text-align:left'>Status</th>"
            "<th style='padding:6px 8px'>Link</th>"
            "</tr></thead><tbody>" + _rows + "</tbody></table>"
        )
    if skipped_jobs:
        _rows = "\n".join(_job_row_html(i, j) for i, j in enumerate(skipped_jobs, 1))
        _jobs_table_html += (
            "<h3 style='margin-top:20px;margin-bottom:8px'>⏭️ Skipped Jobs</h3>"
            "<table style='border-collapse:collapse;width:100%;font-size:12px'>"
            "<thead><tr style='background:#95a5a6;color:white'>"
            "<th style='padding:6px 8px'>#</th>"
            "<th style='padding:6px 8px;text-align:left'>Company</th>"
            "<th style='padding:6px 8px;text-align:left'>Position</th>"
            "<th style='padding:6px 8px'>Score</th>"
            "<th style='padding:6px 8px'>Type</th>"
            "<th style='padding:6px 8px;text-align:left'>Reason</th>"
            "<th style='padding:6px 8px'>Link</th>"
            "</tr></thead><tbody>" + _rows + "</tbody></table>"
        )

    html = f"""
<!DOCTYPE html>
<html>
<body style="font-family:Arial,sans-serif;max-width:700px;margin:0 auto;color:#333">

  <div style="background:#27ae60;color:white;padding:16px 20px;border-radius:6px 6px 0 0">
    <h2 style="margin:0;font-size:18px">📊 AI Job Bot — Session Complete</h2>
    <p style="margin:4px 0 0;font-size:13px;opacity:0.85">Completed at {_now_str()}</p>
  </div>

  <div style="border:1px solid #ddd;border-top:none;padding:20px;border-radius:0 0 6px 6px">

    <table style="border-collapse:collapse;width:100%;margin-bottom:24px">
      <tr style="background:#eafaf1">
        <td style="padding:10px 14px;font-size:15px;border:1px solid #a9dfbf">{_easy_label}</td>
        <td style="padding:10px 14px;font-size:22px;font-weight:bold;color:#27ae60;border:1px solid #a9dfbf">{_easy_count}</td>
      </tr>
      {_ext_row_html}
      <tr>
        <td style="padding:10px 14px;font-size:15px;border:1px solid #fce4b3">📋 Manual Action Needed</td>
        <td style="padding:10px 14px;font-size:22px;font-weight:bold;color:#e67e22;border:1px solid #fce4b3">{manual}</td>
      </tr>
      <tr style="background:#f8f9fa">
        <td style="padding:10px 14px;font-size:15px;border:1px solid #dee2e6">⏭️ Skipped (Low Match)</td>
        <td style="padding:10px 14px;font-size:22px;font-weight:bold;color:#95a5a6;border:1px solid #dee2e6">{skipped}</td>
      </tr>
      {"<tr><td style='padding:10px 14px;font-size:15px;border:1px solid #f5c6cb'>❌ Errors</td><td style='padding:10px 14px;font-size:22px;font-weight:bold;color:#e74c3c;border:1px solid #f5c6cb'>" + str(errors) + "</td></tr>" if errors else ""}
      <tr style="background:#f8f9fa">
        <td style="padding:10px 14px;border:1px solid #dee2e6">⏱ Duration</td>
        <td style="padding:10px 14px;border:1px solid #dee2e6">{duration} minutes</td>
      </tr>
    </table>

    {_jobs_table_html}

    {"<h3 style='margin-top:24px;margin-bottom:10px'>📌 Manual Applications — Open and Complete</h3><p style='color:#888;font-size:13px;margin-bottom:12px'>Click each link, use the answers from the earlier alert emails.</p><table style='border-collapse:collapse;width:100%;font-size:13px'><thead><tr style='background:#3498db;color:white'><th style='padding:8px;text-align:left'>#</th><th style='padding:8px;text-align:left'>Company</th><th style='padding:8px;text-align:left'>Job</th><th style='padding:8px;text-align:left'>Link</th></tr></thead><tbody>" + manual_rows_html + "</tbody></table>" if manual_jobs else ""}

    <hr style="margin:24px 0;border:none;border-top:1px solid #eee">
    <p style="color:#aaa;font-size:11px;margin:0">
      2 channels used: Telegram (instant) + Email (this message). Configure in your task settings.
    </p>
  </div>
</body>
</html>
    """.strip()

    return subject, plain, html


# ── Public API ─────────────────────────────────────────────────────────────────

def notify_manual_required(
    task_input:    dict,
    company:       str,
    job_title:     str,
    apply_url:     str,
    stuck_reason:  str,
    answers:       dict        = None,
    linkedin_url:  str         = "",
    applied_today: int         = 0,
) -> None:
    """
    Notify user that an external application needs manual completion.

    Sends via Telegram first. If Telegram not configured or fails, sends via Gmail.
    If both are configured, sends on both (Telegram for speed, email for record).
    Never raises.
    """
    answers = answers or {}

    tg_token  = _cfg(task_input, "telegram_bot_token",  "TELEGRAM_BOT_TOKEN")
    tg_chat   = _cfg(task_input, "telegram_chat_id",    "TELEGRAM_CHAT_ID")
    gmail     = _cfg(task_input, "gmail_address",        "GMAIL_ADDRESS")
    gmail_pwd = _cfg(task_input, "gmail_app_password",   "GMAIL_APP_PASSWORD")
    notif_to  = _cfg(task_input, "notification_email",   "NOTIFICATION_EMAIL") or gmail

    co = company   or "Unknown Company"
    jt = job_title or "Unknown Position"

    tg_sent    = False
    email_sent = False

    # ── Telegram (primary) ──
    if tg_token and tg_chat:
        msg    = _build_manual_tg(co, jt, apply_url, linkedin_url,
                                  stuck_reason, answers, applied_today)
        tg_sent = _tg_send(tg_token, tg_chat, msg)
        if tg_sent:
            print(f"  [NOTIFY] ✅ Telegram manual-required → {co} — {jt}")
        else:
            print(f"  [NOTIFY] ⚠ Telegram failed — will try Gmail")

    # ── Gmail (fallback OR always if both configured) ──
    if gmail and gmail_pwd and notif_to:
        subj, plain, html = _build_manual_email(co, jt, apply_url, linkedin_url,
                                                stuck_reason, answers, applied_today)
        email_sent = _gmail_send(gmail, gmail_pwd, notif_to, subj, plain, html)
        if email_sent:
            print(f"  [NOTIFY] ✅ Email manual-required → {notif_to}")

    if not tg_sent and not email_sent:
        print(
            f"  [NOTIFY] ⚠ No notification channels configured — "
            f"add TELEGRAM_BOT_TOKEN + TELEGRAM_CHAT_ID to .env"
        )


def notify_session_summary(task_input: dict, stats: dict) -> None:
    """
    Send end-of-session summary via Telegram + Gmail.

    stats dict expected keys:
      applied         int   — jobs submitted via Easy Apply
      manual_needed   int   — external jobs that need manual completion
      skipped         int   — jobs skipped (low match / already applied)
      errors          int   — jobs that errored
      duration_minutes int  — total run time
      manual_jobs     list  — [{"company": str, "title": str, "url": str}]

    Never raises.
    """
    tg_token  = _cfg(task_input, "telegram_bot_token",  "TELEGRAM_BOT_TOKEN")
    tg_chat   = _cfg(task_input, "telegram_chat_id",    "TELEGRAM_CHAT_ID")
    gmail     = _cfg(task_input, "gmail_address",        "GMAIL_ADDRESS")
    gmail_pwd = _cfg(task_input, "gmail_app_password",   "GMAIL_APP_PASSWORD")
    notif_to  = _cfg(task_input, "notification_email",   "NOTIFICATION_EMAIL") or gmail

    if tg_token and tg_chat:
        msg = _build_summary_tg(stats)
        ok  = _tg_send(tg_token, tg_chat, msg)
        if ok:
            print("  [NOTIFY] ✅ Telegram session summary sent")
        else:
            print("  [NOTIFY] ⚠ Telegram summary failed")

    if gmail and gmail_pwd and notif_to:
        subj, plain, html = _build_summary_email(stats)
        ok = _gmail_send(gmail, gmail_pwd, notif_to, subj, plain, html)
        if ok:
            print("  [NOTIFY] ✅ Email session summary sent")
