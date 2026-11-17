"""Secret and PII detection at memory write and telemetry choke points."""
import re

# The store feeds verbatim into every future session's context and into every
# backup: a captured credential is a permanent leak. Hard-block unambiguous
# token shapes; block keyword+value only when the value LOOKS like a credential
# (has a digit, or mixed case at >=8 chars) so prose like "token budget" or
# "Bearer tokens" passes. Email/IPv4 warn only (server inventory is legitimate).
_SECRET_RES = [
    ("aws-access-key", re.compile(r"\bAKIA[0-9A-Z]{16}\b"), None),
    ("github-token", re.compile(r"\bgh[pousr]_[A-Za-z0-9]{20,}\b"), None),
    ("github-pat", re.compile(r"\bgithub_pat_[A-Za-z0-9_]{20,}\b"), None),
    ("openai-key", re.compile(r"\bsk-(?:proj-|live-|test-)?[A-Za-z0-9_-]{20,}\b"), None),
    ("anthropic-key", re.compile(r"\bsk-ant-[A-Za-z0-9_-]{20,}\b"), None),
    ("huggingface-token", re.compile(r"\bhf_[A-Za-z0-9]{20,}\b"), None),
    ("google-api-key", re.compile(r"\bAIza[0-9A-Za-z_-]{35}\b"), None),
    ("jwt", re.compile(r"\beyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\b"), None),
    ("private-key-block", re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"), None),
    ("bearer-token", re.compile(
        r"(?i)\bAuthorization\s*:\s*Bearer\s+(?P<val>\S{6,})"), "val"),
    ("keyword+value", re.compile(
        r"(?i)(?<![A-Za-z])(?:password|passwd|пароль|api[_-]?key|secret"
        r"|access[_-]?key|auth[_-]?token|token)(?![A-Za-z])"
        r"""['"]?\s*[:=]?\s*(?P<val>\S{6,})"""), "val"),
    ("aws-secret-key", re.compile(
        r"(?i)(?<![A-Za-z])(?:aws_)?secret[_-]?access[_-]?key"
        r"""['"]?\s*[:=]?\s*(?P<val>\S{6,})"""), "val"),
    ("curl-u-cred", re.compile(
        r"(?:^|\s)-u\s+\S+:(?P<val>[^\s:]{6,})(?:\s|$)"), "val"),
    ("url-userinfo", re.compile(
        r"[\w.+-]+:(?P<val>[^\s:@/]{6,})@[\w.-]+"), "val"),
]
_PII_RES = [
    re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b"),
    re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}\b"),
]

# Structural shell/code punctuation: a value containing these is a fragment
# (e.g. '-m 1983 ... (9)'), never a credential. Leading '-' is a shell flag.
_STRUCTURAL = "(){}[]<>|;&"
_PATHISH = re.compile(r"^\d{4}-\d{2}-\d{2}|^v?\d+\.\d+")


def _pathish(v: str) -> bool:
    """Doc/path-shaped value: dated/versioned bare value, or a multi-segment
    path (slash OR backslash) whose LAST segment carries a dot."""
    if _PATHISH.search(v):
        return True
    if "/" in v or "\\" in v:
        seg = re.split(r"[/\\]", v)[-1]
        return "." in seg
    return False


def _looks_secret(val: str) -> bool:
    """Credential-shaped value, not prose/code fragment/path."""
    v = val.rstrip(",;")
    if v.endswith(")") and "(" not in v:
        v = v[:-1]
    v = v.strip("'\"")
    v = v.rstrip(",;")
    if not v or not v[0].isalnum():
        return False
    if any(c in v for c in _STRUCTURAL):
        return False
    if _pathish(v):
        return False
    if any(c.isdigit() for c in v):
        return len(v) >= 6
    return len(v) >= 8 and any(c.isupper() for c in v) \
        and any(c.islower() for c in v)


def find_secrets(text: str) -> tuple[list[str], list[str]]:
    """(blocking pattern names, pii values) — descriptors are pattern NAMES
    only, never a slice of the match."""
    secrets, pii = [], []
    for name, rx, val_group in _SECRET_RES:
        for m in rx.finditer(text):
            if val_group and not _looks_secret(m.group(val_group)):
                continue
            secrets.append(name)
    for rx in _PII_RES:
        for m in rx.finditer(text):
            pii.append(m.group(0))
    return secrets, pii


def scrub_text(text: str) -> str:
    """Redaction for telemetry: query strings pass through here before the
    search_log INSERT."""
    secrets, _ = find_secrets(text)
    return "***redacted***" if secrets else text
