import re
from dataclasses import dataclass
from typing import List, Optional

# Tries to match common formats:
# 2026-02-20 10:22:11,123 ERROR service.name - Something happened
# 2026-02-20T10:22:11Z WARNING Something happened
LOG_RE = re.compile(
    r"""
    ^\s*
    (?P<timestamp>
        \d{4}-\d{2}-\d{2}            # date
        [T\s]
        \d{2}:\d{2}:\d{2}            # time
        (?:[.,]\d+)?                 # optional millis
        (?:Z|[+-]\d{2}:\d{2})?       # optional tz
    )?
    \s*
    (?P<level>ERROR|WARNING|WARN|INFO|DEBUG|CRITICAL)?
    \s*
    (?P<service>[A-Za-z0-9_.:-]+)?   # optional service/logger
    \s*
    (?:-|\:)?\s*
    (?P<message>.*?)
    \s*$
    """,
    re.VERBOSE | re.IGNORECASE,
)

@dataclass
class LogEntry:
    timestamp: Optional[str]
    level: str
    message: str
    service: Optional[str]
    raw_log: str

def _normalize_level(level: str) -> str:
    lvl = (level or "").upper()
    if lvl == "WARN":
        return "WARNING"
    return lvl

def parse_log_text(log_text: str) -> List[LogEntry]:
    entries: List[LogEntry] = []
    for raw in log_text.splitlines():
        line = raw.strip()
        if not line:
            continue

        m = LOG_RE.match(line)
        if m:
            ts = m.group("timestamp")
            lvl = _normalize_level(m.group("level") or "")
            svc = m.group("service")
            msg = (m.group("message") or "").strip()
        else:
            # fallback: treat as unknown line
            ts, lvl, svc, msg = None, "", None, line

        if "ERROR" in line.upper() or "WARNING" in line.upper() or re.search(r"\bWARN\b", line.upper()):
            if not lvl:
                # infer
                if "ERROR" in line.upper():
                    lvl = "ERROR"
                else:
                    lvl = "WARNING"
            entries.append(LogEntry(ts, lvl, msg or line, svc, raw_log=raw))

    return entries