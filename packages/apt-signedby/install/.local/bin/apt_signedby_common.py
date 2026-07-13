"""Shared APT source parsers and Signed-By validation helpers."""
import os
import re
import stat
from typing import Iterable, List, Tuple

# Opcje, które omijają weryfikację podpisu (złe praktyki)
INSECURE_OPTS = ("trusted=yes", "trusted=1", "allow-insecure=yes", "allow-insecure=true")
INSECURE_BOOL_VALUES = ("yes", "true", "1")
INSECURE_OPT_KEYS = ("trusted", "allow-insecure", "allow-weak", "allow-downgrade-to-insecure")

DEB_LINE_RE = re.compile(
    r"^(deb|deb-src)\s+(?:\[(?P<opts>[^\]]+)\]\s+)?(?P<uri>\S+)\s+(?P<suite>\S+)(?:\s+(?P<comps>.+))?$",
    re.I,
)
DEB_PREFIX_RE = re.compile(r"^(?:deb|deb-src)\s", re.I)
SIGNEDBY_OPT_RE = re.compile(r"\bsigned-by\s*=\s*([^\s\]]+)", re.I)
OPTION_RE = re.compile(r"(?P<key>[A-Za-z0-9-]+)\s*=\s*(?P<value>[^\s\]]+)")

Issue = Tuple[str, str, object, str]
Entry = dict


def read_text(path) -> str:
    with open(path, "r", errors="ignore") as f:
        return f.read()


def _parents_traversable(start_dir: str) -> bool:
    d = start_dir
    while True:
        if not (os.stat(d).st_mode & stat.S_IXOTH):
            return False
        parent = os.path.dirname(d)
        if parent == d:
            return True
        d = parent


def is_world_readable(path: str) -> bool:
    """True only if an 'other' user (e.g. _apt) can actually open the file: the file
    itself must be world-readable (o+r) AND every parent directory up to '/' must be
    world-traversable (o+x). A 0644 key under a 0700 dir (e.g. /root) is unreachable by
    _apt despite its own mode bits."""
    try:
        real = os.path.realpath(path)
        st = os.stat(real)
        if not (st.st_mode & stat.S_IROTH):
            return False
        if not _parents_traversable(os.path.dirname(real)):
            return False
        # APT opens the literal path it was given, not the resolved target;
        # if a symlink component leading to that literal path sits under a
        # non-traversable directory (e.g. /root), _apt can't reach it even
        # though the resolved target is world-readable.
        return _parents_traversable(os.path.dirname(os.path.abspath(path)))
    except (FileNotFoundError, PermissionError):
        return False


def parse_options_blob(opts: str) -> dict:
    parsed = {}
    for m in OPTION_RE.finditer(opts or ""):
        parsed[m.group("key").strip().lower()] = m.group("value").strip().lower()
    return parsed


def insecure_options_from_list_opts(opts: str) -> List[str]:
    parsed = parse_options_blob(opts)
    found = []
    for key in INSECURE_OPT_KEYS:
        value = parsed.get(key)
        if value in INSECURE_BOOL_VALUES:
            found.append(f"{key}={value}")
    return found


def validate_signed_by(value: str, path: str, loc, label: str, target: str) -> List[Issue]:
    issues: List[Issue] = []
    if not value:
        issues.append(("MISSING_SIGNED_BY", path, loc, f"brak {label}  ->  {target}"))
        return issues

    # Signed-By może być listą wartości (ścieżki / fingerprinty). Dla tej polityki oczekujemy ścieżki.
    parts = [p.strip() for p in re.split(r"[,\s]+", value) if p.strip()]
    path_like = [p for p in parts if "/" in p]
    if not path_like:
        issues.append(("SIGNED_BY_NOT_PATH", path, loc, f"{label.rstrip(':=')}='{value}' (brak ścieżki)  ->  {target}"))
        return issues

    for p in path_like:
        if not os.path.exists(p):
            issues.append(("SIGNED_BY_MISSING_FILE", path, loc, f"{p} (nie istnieje)  ->  {target}"))
        elif not is_world_readable(p):
            issues.append(("SIGNED_BY_NOT_READABLE", path, loc, f"{p} (niedostępny dla _apt: wymaga world-readable pliku i przechodnich katalogów nadrzędnych)  ->  {target}"))
    return issues


def parse_list_file(path) -> List[Issue]:
    _entries, issues = parse_list_file_with_entries(path)
    return issues


def parse_list_file_with_entries(path) -> Tuple[List[Entry], List[Issue]]:
    entries: List[Entry] = []
    issues: List[Issue] = []
    path_str = str(path)
    text = read_text(path)

    for idx, raw in enumerate(text.splitlines(), 1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if not DEB_PREFIX_RE.match(line):
            continue

        m = DEB_LINE_RE.match(line)
        if not m:
            issues.append(("MALFORMED_DEB_LINE", path_str, idx, "za krótka lub niepoprawna linia deb"))
            continue

        deb_type = m.group(1)
        opts = m.group("opts") or ""
        uri = m.group("uri")
        suite = m.group("suite")
        comps_str = m.group("comps")
        if comps_str is None and not suite.endswith("/"):
            issues.append(("MALFORMED_DEB_LINE", path_str, idx, "brak komponentów dla suite bez końcowego /"))
            continue
        comps = (comps_str or "").split()
        target = f"{uri} {suite}"

        for bad in insecure_options_from_list_opts(opts):
            issues.append(("INSECURE_OPTION", path_str, idx, f"{bad}  ->  {target}"))

        sb_match = SIGNEDBY_OPT_RE.search(opts)
        signed_by = sb_match.group(1).strip() if sb_match else ""
        label = "signed-by=" if opts else "[signed-by=...]"
        issues.extend(validate_signed_by(signed_by, path_str, idx, label, target))

        entries.append({
            "file": path_str,
            "line": idx,
            "type": deb_type,
            "uri": uri,
            "suite": suite,
            "components": set(comps),
            "signed_by": signed_by,
            "enabled": True,
        })

    return entries, issues


def split_deb822_stanzas(text: str) -> List[List[str]]:
    stanzas = []
    cur = []
    for raw in text.splitlines():
        if raw.strip() == "":
            if cur:
                stanzas.append(cur)
                cur = []
        else:
            cur.append(raw)
    if cur:
        stanzas.append(cur)
    return stanzas


def parse_deb822_stanza(lines: Iterable[str]) -> dict:
    d = {}
    key = None
    for raw in lines:
        if raw.lstrip().startswith("#"):
            continue
        if re.match(r"^\s", raw) and key:
            d[key] += "\n" + raw.strip()
            continue
        if ":" not in raw:
            continue
        k, v = raw.split(":", 1)
        key = k.strip().lower()
        d[key] = v.strip()
    return d


def parse_deb822_sources(path) -> List[Issue]:
    _entries, issues = parse_sources_file_with_entries(path)
    return issues


def parse_sources_file_with_entries(path) -> Tuple[List[Entry], List[Issue]]:
    entries: List[Entry] = []
    issues: List[Issue] = []
    path_str = str(path)
    text = read_text(path)

    for si, stanza_lines in enumerate(split_deb822_stanzas(text), 1):
        d = parse_deb822_stanza(stanza_lines)
        if not d:
            continue

        enabled = d.get("enabled", "yes").strip().lower()
        is_enabled = enabled not in ("no", "false", "0")

        uris = d.get("uris") or d.get("uri", "")
        suites = d.get("suites", "")
        types = set(d.get("types", "deb").lower().split())

        # Jeśli to nie wygląda jak repo stanza albo nie dotyczy obsługiwanego typu APT, pomiń.
        # Deb-src-only repozytoria też audytujemy, ale nie dodajemy ich jako binarnych wpisów deb.
        has_binary_deb = "deb" in types
        has_source_deb = "deb-src" in types
        if not uris or not suites or not (has_binary_deb or has_source_deb):
            continue

        uris_list = uris.split()
        suites_list = suites.split()
        comps = d.get("components", "").split()
        signed_by = d.get("signed-by", "").strip()
        target = f"{uris} {suites}"
        loc = f"stanza#{si}"

        if is_enabled:
            for key in INSECURE_OPT_KEYS:
                value = d.get(key, "").strip().lower()
                if value in INSECURE_BOOL_VALUES:
                    issues.append(("INSECURE_OPTION", path_str, loc, f"{key.title()}: {value}  ->  {target}"))

            issues.extend(validate_signed_by(signed_by, path_str, loc, "Signed-By:", target))

        if has_binary_deb:
            for uri in uris_list or [""]:
                for suite in suites_list or [""]:
                    entries.append({
                        "file": path_str,
                        "line": 0,
                        "type": "deb",
                        "uri": uri,
                        "suite": suite,
                        "components": set(comps),
                        "signed_by": signed_by,
                        "enabled": is_enabled,
                    })

    active_entries = [e for e in entries if e.get("enabled", True)]
    return active_entries, issues


def issue_to_violation(issue: Issue):
    kind, path, loc, msg = issue
    line_no = loc if isinstance(loc, int) else 0
    return (path, line_no, f"{kind}: {msg}", "")
