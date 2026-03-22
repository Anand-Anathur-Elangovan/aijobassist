"""
Gmail client for VantaHire.
Scans the user's inbox for job-related emails and sends follow-up/reply emails.
Uses IMAP (imaplib) for reading and SMTP (smtplib) for sending — no OAuth needed,
just a Gmail App Password.

How to get a Gmail App Password:
  https://myaccount.google.com/apppasswords
  (Requires 2-Step Verification to be enabled on the account)
"""

import imaplib
import smtplib
import email as email_lib
import email.header
import re
import os
import sys
import time
from datetime import datetime, timezone, timedelta
from email.mime.text import MIMEText

IMAP_HOST = "imap.gmail.com"
IMAP_PORT = 993
SMTP_HOST = "smtp.gmail.com"
SMTP_PORT = 587

JOB_SUBJECT_KEYWORDS = [
    "application", "apply", "applied", "position", "role", "job",
    "interview", "offer", "opportunity", "hiring", "recruit", "candidate",
    "shortlisted", "selected", "rejection", "regret", "thank you for applying",
    "we received your", "next steps", "assessment", "schedule",
]

CLASSIFICATION_PROMPT = """You are classifying a job-related email into exactly one of these categories:
ACKNOWLEDGMENT   - company acknowledged receiving the application
INTERVIEW_INVITE - company is inviting for an interview
REJECTION        - application was rejected
SCHEDULE_REQUEST - asking to schedule a call or meeting
OFFER            - job offer extended
GENERAL          - other job-related email

Email subject: {subject}
Email body (first 800 chars): {body}

Reply with ONLY the category name (e.g. ACKNOWLEDGMENT). Nothing else."""

FOLLOWUP_TEMPLATE = """Hi,

I hope this message finds you well. I recently applied for the {role} position at {company} and wanted to follow up on my application status.

I remain very interested in this opportunity and would love to discuss how my background aligns with your team's needs. Please let me know if you need any additional information from my side.

Thank you for your time and consideration.

Best regards,
{applicant_name}"""

REPLY_PROMPT = """You are a professional job applicant writing an email reply.

Original email subject: {subject}
Original email body: {body}
Classification: {classification}
Applicant name: {applicant_name}
Position: {role}
Company: {company}

Write a professional, concise reply (3-5 sentences max) appropriate for the classification.
- ACKNOWLEDGMENT → brief thank-you, express continued interest
- INTERVIEW_INVITE → confirm availability, express enthusiasm  
- REJECTION → gracious acceptance, ask to keep in mind for future
- SCHEDULE_REQUEST → confirm willingness, suggest flexible availability
- OFFER → express gratitude, mention you will review and respond soon
Reply with ONLY the email body text, no subject line, no "Dear X"."""


# ──────────────────────────────────────────────────────────────
# AI helpers (reuse existing ai_client or fall back to mock)
# ──────────────────────────────────────────────────────────────

def _ai_classify(subject: str, body: str) -> str:
    """Classify the email type using Claude (or return GENERAL on failure)."""
    prompt = CLASSIFICATION_PROMPT.format(subject=subject, body=body[:800])
    try:
        sys.path.insert(0, os.path.dirname(__file__))
        from ai_client import call_claude
        result = call_claude(prompt).strip().upper()
        valid = {"ACKNOWLEDGMENT", "INTERVIEW_INVITE", "REJECTION", "SCHEDULE_REQUEST", "OFFER", "GENERAL"}
        return result if result in valid else "GENERAL"
    except Exception as e:
        print(f"  [GMAIL] AI classify failed: {e}")
        # Keyword fallback
        text = (subject + " " + body).lower()
        if any(w in text for w in ["interview", "schedule", "call", "meet"]):
            return "INTERVIEW_INVITE"
        if any(w in text for w in ["reject", "regret", "unfortunately", "not moving forward"]):
            return "REJECTION"
        if any(w in text for w in ["offer", "congratulations", "pleased to offer"]):
            return "OFFER"
        if any(w in text for w in ["received", "acknowledg", "thank you for applying"]):
            return "ACKNOWLEDGMENT"
        return "GENERAL"


def _ai_generate_reply(subject: str, body: str, classification: str,
                        company: str, role: str, applicant_name: str) -> str:
    """Generate an AI reply for the email."""
    prompt = REPLY_PROMPT.format(
        subject=subject, body=body[:600], classification=classification,
        applicant_name=applicant_name, role=role, company=company,
    )
    try:
        from ai_client import call_claude
        return call_claude(prompt).strip()
    except Exception:
        # Soft fallback
        return (
            f"Thank you for your email regarding the {role} position at {company}. "
            "I appreciate you reaching out and will be in touch shortly."
        )


def _ai_summarise(subject: str, body: str) -> str:
    """One-sentence summary of the email."""
    try:
        from ai_client import call_claude
        return call_claude(f"Summarise this email in one sentence:\nSubject: {subject}\n{body[:400]}").strip()
    except Exception:
        return subject


# ──────────────────────────────────────────────────────────────
# IMAP helpers
# ──────────────────────────────────────────────────────────────

def _decode_header(raw: str) -> str:
    parts = email.header.decode_header(raw or "")
    decoded = []
    for part, enc in parts:
        if isinstance(part, bytes):
            decoded.append(part.decode(enc or "utf-8", errors="replace"))
        else:
            decoded.append(part)
    return "".join(decoded)


def _extract_body(msg) -> str:
    """Extract plain-text body from email.Message."""
    body = ""
    if msg.is_multipart():
        for part in msg.walk():
            ct = part.get_content_type()
            cd = str(part.get("Content-Disposition", ""))
            if ct == "text/plain" and "attachment" not in cd:
                try:
                    body = part.get_payload(decode=True).decode(
                        part.get_content_charset("utf-8"), errors="replace"
                    )
                    break
                except Exception:
                    pass
    else:
        try:
            body = msg.get_payload(decode=True).decode(
                msg.get_content_charset("utf-8"), errors="replace"
            )
        except Exception:
            body = str(msg.get_payload())
    return body.strip()


def _is_job_related(subject: str, body: str, known_companies: list[str]) -> bool:
    """Return True if the email is likely job-related."""
    text = (subject + " " + body[:300]).lower()
    # Match by known company name
    for company in known_companies:
        if company.lower() in text:
            return True
    # Match by generic keywords
    return any(kw in text for kw in JOB_SUBJECT_KEYWORDS)


# ──────────────────────────────────────────────────────────────
# Public API
# ──────────────────────────────────────────────────────────────

def scan_job_emails(gmail_address: str, app_password: str,
                     since_days: int = 14,
                     known_companies: list[str] = None) -> list[dict]:
    """
    Connect to Gmail via IMAP, scan recent emails, return list of job-related ones.
    Each result dict has: thread_id, subject, from_address, received_at, body, classification, summary
    """
    known_companies = known_companies or []
    results = []

    try:
        mail = imaplib.IMAP4_SSL(IMAP_HOST, IMAP_PORT)
        mail.login(gmail_address, app_password)
        mail.select("INBOX")

        # Search since N days ago
        since_date = (datetime.now() - timedelta(days=since_days)).strftime("%d-%b-%Y")
        status, msg_ids = mail.search(None, f"SINCE {since_date}")
        if status != "OK":
            mail.logout()
            return []

        ids = msg_ids[0].split()
        print(f"  [GMAIL] Found {len(ids)} emails since {since_date}")

        for uid in reversed(ids[-100:]):  # last 100 emails, newest first
            status, data = mail.fetch(uid, "(RFC822 UID)")
            if status != "OK" or not data or not data[0]:
                continue
            raw = data[0][1]
            msg = email_lib.message_from_bytes(raw)

            subject = _decode_header(msg.get("Subject", ""))
            from_raw = _decode_header(msg.get("From", ""))
            date_raw = msg.get("Date", "")
            body = _extract_body(msg)

            # Extract bare email address from From field
            match = re.search(r"<([^>]+)>", from_raw)
            from_address = match.group(1) if match else from_raw.strip()

            # Parse date
            try:
                received_at = email_lib.utils.parsedate_to_datetime(date_raw).isoformat()
            except Exception:
                received_at = datetime.now(timezone.utc).isoformat()

            if not _is_job_related(subject, body, known_companies):
                continue

            print(f"  [GMAIL] Job email: {subject[:60]} from {from_address}")

            classification = _ai_classify(subject, body)
            summary = _ai_summarise(subject, body)

            results.append({
                "thread_id":    f"{uid.decode()}-{gmail_address}",
                "subject":      subject,
                "from_address": from_address,
                "received_at":  received_at,
                "body":         body[:2000],
                "classification": classification,
                "summary":      summary,
            })

        mail.logout()
    except imaplib.IMAP4.error as e:
        print(f"  [GMAIL] IMAP error: {e}")
    except Exception as e:
        print(f"  [GMAIL] Scan error: {e}")

    return results


def send_email(gmail_address: str, app_password: str,
                to_address: str, subject: str, body: str) -> bool:
    """Send an email via Gmail SMTP. Returns True on success."""
    try:
        msg = MIMEText(body, "plain")
        msg["Subject"] = subject
        msg["From"]    = gmail_address
        msg["To"]      = to_address

        with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as server:
            server.ehlo()
            server.starttls()
            server.login(gmail_address, app_password)
            server.sendmail(gmail_address, to_address, msg.as_string())

        print(f"  [GMAIL] Sent email to {to_address}: {subject}")
        return True
    except Exception as e:
        print(f"  [GMAIL] Send error: {e}")
        return False


def send_followup_email(gmail_address: str, app_password: str,
                         to_address: str, company: str, role: str,
                         applicant_name: str) -> bool:
    """Send a follow-up email to a recruiter."""
    subject = f"Follow-up: {role} Application at {company}"
    body = FOLLOWUP_TEMPLATE.format(
        role=role, company=company, applicant_name=applicant_name
    )
    return send_email(gmail_address, app_password, to_address, subject, body)


def generate_and_send_reply(gmail_address: str, app_password: str,
                              to_address: str, original_subject: str,
                              original_body: str, classification: str,
                              company: str, role: str, applicant_name: str) -> tuple[bool, str]:
    """
    Generate an AI reply to a recruiter email and send it.
    Returns (sent_ok, reply_text).
    """
    reply_body = _ai_generate_reply(
        subject=original_subject,
        body=original_body,
        classification=classification,
        company=company,
        role=role,
        applicant_name=applicant_name,
    )
    subject = f"Re: {original_subject}"
    sent = send_email(gmail_address, app_password, to_address, subject, reply_body)
    return sent, reply_body
