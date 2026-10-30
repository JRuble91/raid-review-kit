"""Pull a collector payload (RR.dump) out of saved browser-tool results and write it as JSON.

The browser tool saves big results to a file shaped like [{"type": "text", "text": "<JSON of the returned value>"}].
RR.dump('MARKER', part) returns MARKERBEGIN[part/total]<slice of the JSON>MARKEREND plus padding. Big payloads come in
several parts (the link to the user's computer cuts single results off around 260K characters), one file per part.
"""
import glob, json, os, re

PART = re.compile(r'BEGIN\[(\d+)/(\d+)\]')


def candidates(paths=None):
    if paths:
        for p in paths:
            yield from sorted(glob.glob(p), key=os.path.getmtime, reverse=True)
        return
    roots = [os.path.expanduser('~/.claude/projects'), '/root/.claude/projects', '/tmp']
    files = []
    for r in roots:
        files += glob.glob(os.path.join(r, '**', 'tool-results', '*'), recursive=True)
    yield from sorted(set(files), key=os.path.getmtime, reverse=True)


def returned_strings(path):
    """The string values the browser tool returned, decoded from the saved file."""
    raw = open(path, encoding='utf-8', errors='replace').read()
    try:
        arr = json.loads(raw)
    except Exception:
        return [raw]
    out = []
    for item in arr if isinstance(arr, list) else [arr]:
        t = item.get('text', '') if isinstance(item, dict) else ''
        try:
            t = json.JSONDecoder().raw_decode(t.lstrip())[0]     # the value, ignoring any note appended after it
        except Exception:
            pass
        if isinstance(t, str): out.append(t)
    return out


def find_parts(marker, files=None):
    parts, total = {}, None
    for p in candidates(files):
        try:
            if marker + 'BEGIN' not in open(p, encoding='utf-8', errors='replace').read(400): continue
        except Exception:
            continue
        for s in returned_strings(p):
            a = s.find(marker + 'BEGIN')
            if a < 0: continue
            if 'truncated: content too large' in s: raise ValueError(f'{p} was cut off by the device bridge: dump smaller parts')
            m = PART.match(s, a + len(marker))
            if m:
                i, n = int(m.group(1)), int(m.group(2)); body_start = m.end()
            else:
                i, n = 0, 1; body_start = a + len(marker) + 5
            b = s.find(marker + 'END', body_start)
            if b < 0: raise ValueError(f'{marker} part {i} in {p} has no end marker: it was cut off')
            if total is not None and n != total: continue          # an older dump with a different part count
            total = n
            parts.setdefault(i, (s[body_start:b], p))
        if total is not None and len(parts) == total: break
    return parts, total


def extract(marker, out, files=None):
    parts, total = find_parts(marker, files)
    if not total: raise SystemExit(f'no saved tool result with {marker}BEGIN found')
    missing = [i for i in range(total) if i not in parts]
    if missing: raise SystemExit(f'{marker}: missing parts {missing} of {total}. Run RR.dump(\'{marker}\', i) for each.')
    v = json.loads(''.join(parts[i][0] for i in range(total)))
    os.makedirs(os.path.dirname(os.path.abspath(out)), exist_ok=True)
    json.dump(v, open(out, 'w'), ensure_ascii=False, separators=(',', ':'))
    return f'{total} part(s)'
