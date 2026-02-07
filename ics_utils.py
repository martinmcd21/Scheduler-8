import uuid
from datetime import datetime, timezone


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
    required_attendees: list,
    optional_attendees: list,
    summary: str,
    description: str,
    dtstart_utc: datetime,
    dtend_utc: datetime,
    location: str = "",
    url: str = "",
    uid: str = None,
) -> bytes:
    """
    Generate a proper RFC 5545 ICS meeting invite.

    required_attendees: list of (email, display_name)
    optional_attendees: list of (email, display_name)
    """

    if uid is None:
        uid = f"{uuid.uuid4()}@powerdashhr.com"

    dtstamp = _format_dt(datetime.now(timezone.utc))
    dtstart = _format_dt(dtstart_utc)
    dtend = _format_dt(dtend_utc)

    summary = _escape_ics(summary)
    description = _escape_ics(description or "")
    location = _escape_ics(location or "")
    url = _escape_ics(url or "")

    # Append URL to description for maximum compatibility
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
    for email, name in required_attendees:
        email = email.strip()
        name = _escape_ics(name or email)
        lines.append(
            f"ATTENDEE;CN={name};ROLE=REQ-PARTICIPANT;"
            f"PARTSTAT=NEEDS-ACTION;RSVP=TRUE:mailto:{email}"
        )

    # Optional attendees
    for email, name in optional_attendees:
        email = email.strip()
        name = _escape_ics(name or email)
        lines.append(
            f"ATTENDEE;CN={name};ROLE=OPT-PARTICIPANT;"
            f"PARTSTAT=NEEDS-ACTION;RSVP=TRUE:mailto:{email}"
        )

    # URL field (some clients display this prominently)
    if url:
        lines.append(f"URL:{url}")

    # Alarm (optional but nice)
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


# --------------------------------------------------------------------
# Backwards-compatible API expected by app.py
# --------------------------------------------------------------------

class ICSValidationError(ValueError):
    """Raised when an ICS invite cannot be generated due to invalid inputs."""
    pass


def stable_uid(seed: str) -> str:
    """Generate a deterministic UID for calendar invites."""
    import hashlib
    if not seed:
        seed = str(uuid.uuid4())
    h = hashlib.md5(seed.encode("utf-8")).hexdigest()
    return f"{h}@powerdashhr.com"


class ICSInvite:
    """Compatibility wrapper that exposes the legacy interface used by app.py."""

    def __init__(
        self,
        organizer_email: str,
        organizer_name: str,
        attendee_emails: list,
        summary: str,
        description: str,
        dtstart_utc: datetime,
        dtend_utc: datetime,
        location: str = "",
        url: str = "",
        uid: str | None = None,
        optional_attendee_emails: list | None = None,
    ):
        self.organizer_email = organizer_email
        self.organizer_name = organizer_name
        self.attendee_emails = attendee_emails or []
        self.optional_attendee_emails = optional_attendee_emails or []
        self.summary = summary
        self.description = description
        self.dtstart_utc = dtstart_utc
        self.dtend_utc = dtend_utc
        self.location = location
        self.url = url
        self.uid = uid or stable_uid(f"{summary}|{organizer_email}|{dtstart_utc.isoformat()}")

    def to_bytes(self) -> bytes:
        required = [(e, e) for e in self.attendee_emails]
        optional = [(e, e) for e in self.optional_attendee_emails]

        return build_ics_invite(
            organizer_email=self.organizer_email,
            organizer_name=self.organizer_name,
            required_attendees=required,
            optional_attendees=optional,
            summary=self.summary,
            description=self.description,
            dtstart_utc=self.dtstart_utc,
            dtend_utc=self.dtend_utc,
            location=self.location,
            url=self.url,
            uid=self.uid,
        )
