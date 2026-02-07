import hashlib
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import List, Tuple, Optional


class ICSValidationError(Exception):
    """Raised when required ICS fields are missing or invalid."""
    pass


def stable_uid(seed: str, domain: str = "powerdashhr.com") -> str:
    """
    Create a deterministic UID suitable for ICS invites.
    This prevents duplicate meeting creation if the same interview is processed twice.
    """
    if not seed:
        raise ICSValidationError("stable_uid requires a non-empty seed")

    digest = hashlib.md5(seed.encode("utf-8")).hexdigest()
    return f"{digest}@{domain}"


def _format_dt(dt: datetime) -> str:
    """Return UTC datetime in ICS format."""
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    dt = dt.astimezone(timezone.utc)
    return dt.strftime("%Y%m%dT%H%M%SZ")


def _escape_ics(text: str) -> str:
    """Escape special characters for ICS format."""
    if not text:
        return ""
    return (
        text.replace("\\", "\\\\")
            .replace(";", r"\;")
            .replace(",", r"\,")
            .replace("\n", r"\n")
    )


def build_ics_invite(
    organizer_email: str,
    organizer_name: str,
    required_attendees: List[Tuple[str, str]],
    optional_attendees: List[Tuple[str, str]],
    summary: str,
    description: str,
    dtstart_utc: datetime,
    dtend_utc: datetime,
    location: str = "",
    url: str = "",
    uid: Optional[str] = None,
) -> bytes:
    """
    Generate a proper RFC 5545 ICS meeting invite.

    required_attendees: list of (email, display_name)
    optional_attendees: list of (email, display_name)
    """

    if not organizer_email:
        raise ICSValidationError("Organizer email is required")

    if not summary:
        raise ICSValidationError("Summary is required")

    if dtstart_utc is None or dtend_utc is None:
        raise ICSValidationError("Start and end times are required")

    if uid is None:
        uid = f"{uuid.uuid4()}@powerdashhr.com"

    dtstamp = _format_dt(datetime.now(timezone.utc))
    dtstart = _format_dt(dtstart_utc)
    dtend = _format_dt(dtend_utc)

    summary = _escape_ics(summary)
    description = _escape_ics(description or "")
    location = _escape_ics(location or "")
    url = _escape_ics(url or "")

    if url:
        description = f"{description}\\n\\nJoin link: {url}".strip()

    lines = [
        "BEGIN:VCALENDAR",
        "PRODID:-//PowerDash HR//Interview Scheduler//EN",
        "VERSION:2.0",
        "CALSCALE:GREGORIAN",
        "METHOD:REQUEST",
        "BEGIN:VEVENT",
        f"UID:{uid}",
        f"DTSTAMP:{dtstamp}",
        f"DTSTART:{dtstart}",
        f"DTEND:{dtend}",
        f"SUMMARY:{summary}",
        f"DESCRIPTION:{description}",
        f"LOCATION:{location}",
        "STATUS:CONFIRMED",
        "TRANSP:OPAQUE",
        f"ORGANIZER;CN={_escape_ics(organizer_name)}:mailto:{organizer_email}",
    ]

    # Required attendees
    for email, name in required_attendees or []:
        email = (email or "").strip()
        if not email:
            continue
        name = _escape_ics(name or email)
        lines.append(
            f"ATTENDEE;CN={name};ROLE=REQ-PARTICIPANT;"
            f"PARTSTAT=NEEDS-ACTION;RSVP=TRUE:mailto:{email}"
        )

    # Optional attendees
    for email, name in optional_attendees or []:
        email = (email or "").strip()
        if not email:
            continue
        name = _escape_ics(name or email)
        lines.append(
            f"ATTENDEE;CN={name};ROLE=OPT-PARTICIPANT;"
            f"PARTSTAT=NEEDS-ACTION;RSVP=TRUE:mailto:{email}"
        )

    if url:
        lines.append(f"URL:{url}")

    # Reminder alarm
    lines.extend([
        "BEGIN:VALARM",
        "TRIGGER:-PT15M",
        "ACTION:DISPLAY",
        "DESCRIPTION:Interview Reminder",
        "END:VALARM",
    ])

    lines.append("END:VEVENT")
    lines.append("END:VCALENDAR")

    ics_text = "\r\n".join(lines) + "\r\n"
    return ics_text.encode("utf-8")


@dataclass
class ICSInvite:
    """
    Backwards compatible wrapper class so existing app.py code still works.
    """

    organizer_email: str
    organizer_name: str
    attendee_emails: List[str]
    summary: str
    description: str
    dtstart_utc: datetime
    dtend_utc: datetime
    location: str = ""
    url: str = ""
    uid: Optional[str] = None

    def to_bytes(self) -> bytes:
        required_attendees = [(e, e) for e in self.attendee_emails or []]
        optional_attendees = []

        return build_ics_invite(
            organizer_email=self.organizer_email,
            organizer_name=self.organizer_name,
            required_attendees=required_attendees,
            optional_attendees=optional_attendees,
            summary=self.summary,
            description=self.description,
            dtstart_utc=self.dtstart_utc,
            dtend_utc=self.dtend_utc,
            location=self.location,
            url=self.url,
            uid=self.uid,
        )


def create_ics_from_interview(
    organizer_email: str,
    organizer_name: str,
    attendees: List[Tuple[str, str]],
    optional_attendees: List[Tuple[str, str]],
    summary: str,
    description: str,
    start_utc: datetime,
    end_utc: datetime,
    location: str = "",
    join_url: str = "",
    uid_seed: Optional[str] = None,
) -> bytes:
    """
    This matches what app.py expects.

    Returns: ICS bytes suitable for attaching to an email via Graph API.
    """

    uid = None
    if uid_seed:
        uid = stable_uid(uid_seed)

    return build_ics_invite(
        organizer_email=organizer_email,
        organizer_name=organizer_name,
        required_attendees=attendees,
        optional_attendees=optional_attendees,
        summary=summary,
        description=description,
        dtstart_utc=start_utc,
        dtend_utc=end_utc,
        location=location,
        url=join_url,
        uid=uid,
def generate_cancellation_ics(
    organizer_email: str,
    organizer_name: str,
    attendees: List[Tuple[str, str]],
    optional_attendees: List[Tuple[str, str]],
    summary: str,
    description: str,
    start_utc: datetime,
    end_utc: datetime,
    uid: str,
    sequence: int = 1,
    location: str = "",
    url: str = "",
) -> bytes:
    """
    Generates an ICS cancellation invite (METHOD:CANCEL).
    Outlook requires UID + SEQUENCE to match the original invite.
    """

    if not uid:
        raise ICSValidationError("UID is required to cancel an invite")

    dtstamp = _format_dt(datetime.now(timezone.utc))
    dtstart = _format_dt(start_utc)
    dtend = _format_dt(end_utc)

    summary = _escape_ics(summary)
    description = _escape_ics(description or "")
    location = _escape_ics(location or "")
    url = _escape_ics(url or "")

    if url:
        description = f"{description}\\n\\nJoin link: {url}".strip()

    lines = [
        "BEGIN:VCALENDAR",
        "PRODID:-//PowerDash HR//Interview Scheduler//EN",
        "VERSION:2.0",
        "CALSCALE:GREGORIAN",
        "METHOD:CANCEL",
        "BEGIN:VEVENT",
        f"UID:{uid}",
        f"SEQUENCE:{sequence}",
        f"DTSTAMP:{dtstamp}",
        f"DTSTART:{dtstart}",
        f"DTEND:{dtend}",
        f"SUMMARY:{summary}",
        f"DESCRIPTION:{description}",
        f"LOCATION:{location}",
        "STATUS:CANCELLED",
        f"ORGANIZER;CN={_escape_ics(organizer_name)}:mailto:{organizer_email}",
    ]

    for email, name in attendees or []:
        email = (email or "").strip()
        if not email:
            continue
        name = _escape_ics(name or email)
        lines.append(
            f"ATTENDEE;CN={name};ROLE=REQ-PARTICIPANT:mailto:{email}"
        )

    for email, name in optional_attendees or []:
        email = (email or "").strip()
        if not email:
            continue
        name = _escape_ics(name or email)
        lines.append(
            f"ATTENDEE;CN={name};ROLE=OPT-PARTICIPANT:mailto:{email}"
        )

    if url:
        lines.append(f"URL:{url}")

    lines.append("END:VEVENT")
    lines.append("END:VCALENDAR")

    ics_text = "\r\n".join(lines) + "\r\n"
    return ics_text.encode("utf-8")    
)
