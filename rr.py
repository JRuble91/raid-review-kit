#!/usr/bin/env python3
"""raid-review-kit: build raid review pages from Warcraft Logs (+ Wipefest) for any guild and boss.

  python3 rr.py extract MARKER OUT.json [--from FILE]   save a collector payload (RR.dump('MARKER')) from the saved browser output
  python3 rr.py site SITE_DIR --guild "Name"           build every page from SITE_DIR/data/*.wcl.json (+ matching .wf.json)
  python3 rr.py summary SITE_DIR                        print what the site holds (bosses, nights, pulls) for a quick check

Raw files are named <report>-<encounter>-<difficulty>.wcl.json / .wf.json and live in SITE_DIR/data, so a published
site carries its own data and the next run only needs to collect the new nights.
"""
import argparse, collections, datetime, glob, json, os, re, sys

KIT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, KIT)
from rrlib import build as B, render as R  # noqa: E402
from rrlib.extract import extract  # noqa: E402

MONTHS = {m: i for i, m in enumerate(['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'], 1)}


def night_date(n):
    y = datetime.datetime.fromtimestamp((n.get('start') or 0) / 1000, datetime.timezone.utc).year if n.get('start') else datetime.date.today().year
    m = re.search(r'([A-Z][a-z]{2})\s+(\d{1,2})', n.get('date') or '')
    if not m: return None
    return datetime.date(y, MONTHS.get(m.group(1), 1), int(m.group(2)))


def best_txt(pulls_or_rows):
    k = [p for p in pulls_or_rows if p.get('kill')]
    if k: return f"Killed it ({len(k)} {'kill' if len(k) == 1 else 'kills'})."
    b = min(pulls_or_rows, key=lambda p: p['boss_pct'])
    return f"Best pull {b['boss_pct']:.1f}%."


def cmd_site(a):
    site = a.site; data_dir = os.path.join(site, 'data')
    files = sorted(glob.glob(os.path.join(data_dir, '*.wcl.json')))
    if not files: raise SystemExit(f'no *.wcl.json files in {data_dir}')
    groups = collections.defaultdict(list)
    for f in files:
        m = re.match(r'(.+)-(\d+)-(\d+)\.wcl\.json$', os.path.basename(f))
        if not m: continue
        code, enc, diff = m.group(1), int(m.group(2)), int(m.group(3))
        wf = f.replace('.wcl.json', '.wf.json')
        groups[(enc, diff)].append(B.load_night(f, wf if os.path.exists(wf) else None))
    series = []
    for (enc, diff), nights in sorted(groups.items(), key=lambda kv: -max((n.get('start') or 0) for n in kv[1])):
        prof = B.load_profile(enc, a.kit or KIT)
        nights.sort(key=lambda n: (n.get('start') or 0, n['code']))
        boss = nights[-1]['boss']; dname = B.DIFF.get(diff, str(diff))
        base = f'{B.slug(boss)}-{B.slug(dname)}'
        entry = dict(title=f'{boss} · {dname}', nights=[], all=None)
        used = set()
        for n in nights:
            d = night_date(n)
            fn = f"{base}-{d.isoformat() if d else n['code']}.html"
            if fn in used: fn = fn.replace('.html', f"-{n['code']}.html")
            used.add(fn)
            data = B.page_data([n], prof, guild=a.guild, kit_dir=a.kit or KIT)
            best = min(data['wcl_pulls'], key=lambda p: p['boss_pct'])
            open(os.path.join(site, fn), 'w', encoding='utf-8').write(R.page(a.kit or KIT, data, f"{a.guild} · {boss} {dname} · {n['label']}", best['pull']))
            entry['nights'].append(dict(file=fn, label=f"{d.strftime('%a, %b %-d') if d else n['label']}", n_pulls=len(n['pulls']), best=best_txt(data['wcl_pulls'])))
            print(f"{fn}: {len(n['pulls'])} pulls, {len(n['deaths'])} deaths, {best_txt(data['wcl_pulls'])} problems: {[c['title'] for c in data['issues']['cards']][:4]}")
        if len(nights) > 1:
            fn = f'{base}-all.html'
            data = B.page_data(nights, prof, guild=a.guild, kit_dir=a.kit or KIT)
            best = min(data['wcl_pulls'], key=lambda p: p['boss_pct'])
            open(os.path.join(site, fn), 'w', encoding='utf-8').write(R.page(a.kit or KIT, data, f"{a.guild} · {boss} {dname} · every pull", best['pull']))
            entry['all'] = dict(file=fn, n_pulls=len(data['wcl_pulls']), nights=data['meta']['nights'], best=best_txt(data['wcl_pulls']))
            print(f"{fn}: {len(data['wcl_pulls'])} pulls over {len(nights)} nights. problems: {[c['title'] for c in data['issues']['cards']][:5]}")
        entry['nights'].reverse()
        series.append(entry)
    if a.keep_index and os.path.exists(os.path.join(site, 'index.html')):
        print('kept the existing index.html: add cards for', ', '.join(n['file'] for s in series for n in ([s['all']] if s['all'] else []) + s['nights']))
    else:
        open(os.path.join(site, 'index.html'), 'w', encoding='utf-8').write(R.landing(a.kit or KIT, a.guild, series))
        print('index.html:', ', '.join(f"{s['title']} ({len(s['nights'])} nights)" for s in series))


def cmd_summary(a):
    for f in sorted(glob.glob(os.path.join(a.site, 'data', '*.wcl.json'))):
        W = json.load(open(f)); wf = os.path.exists(f.replace('.wcl.json', '.wf.json'))
        print(os.path.basename(f), '|', W['boss'], B.DIFF.get(W['difficulty']), '|', len(W['fights']), 'pulls |', (W['fights'][0].get('date') if W['fights'] else ''), '| wipefest' if wf else '| no wipefest')


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sp = ap.add_subparsers(dest='cmd', required=True)
    e = sp.add_parser('extract'); e.add_argument('marker'); e.add_argument('out'); e.add_argument('--from', dest='src', nargs='*')
    s = sp.add_parser('site'); s.add_argument('site'); s.add_argument('--guild', default=''); s.add_argument('--kit', default=None)
    s.add_argument('--keep-index', action='store_true', help="don't overwrite an index.html the site already has")
    m = sp.add_parser('summary'); m.add_argument('site')
    a = ap.parse_args()
    if a.cmd == 'extract':
        p = extract(a.marker, a.out, a.src); print(f'saved {a.out} (from {p})')
    elif a.cmd == 'site': cmd_site(a)
    elif a.cmd == 'summary': cmd_summary(a)


if __name__ == '__main__':
    main()
