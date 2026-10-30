"""Sszorak (encounter 3420) plugin: why the Viscous Cysts go off.

Example of a boss plugin. issues(ctx, H) returns extra cards in the generic card format (see rrlib/issues.py).
A card with "replaces" removes the generic card with that key.
"""
import base64, collections, math, struct

CYST, XW, SURGE = 'Viscous Cyst', 'Raging Crosswinds', 'Venomous Surge'
THROWN_YD = 30          # a marked player who moves this far in the 3 s around the knock got launched


def position_reader(ctx, pull):
    p = ctx['P_by'][pull]; R = (ctx['replay_raw'] or {}).get(p['code'])
    pr = R and R['pulls'].get(str(p['fight_id']))
    if not pr: return None
    raw = base64.b64decode(pr['pos']); vals = struct.unpack('<%dh' % (len(raw) // 2), raw)
    N = len(R['actors']); u = R['unit_cm'] / 100.0; idx = {n: i for i, n in enumerate(R['actors'])}

    def at(name, sec):
        i = idx.get(name)
        if i is None or sec < 0 or sec >= pr['n']: return None
        k = (sec * N + i) * 2
        return None if vals[k] == -32768 else (vals[k] * u, vals[k + 1] * u)
    return at


# the Cyst fixes in the profile, in this order: Crosswinds knock, Cyst drop, old Cysts, the winds
FIX_FOR = ['knock', 'drop', 'later', 'winds']


def ordered_fixes(fixes, waves):
    """Lead with the advice for the moment that cost the most Cyst deaths."""
    if len(fixes) != len(FIX_FOR): return fixes
    cost = {k: sum(w['deaths'] for w in waves if w['when'] == k) for k in FIX_FOR}
    return [f for f, k in sorted(zip(fixes, FIX_FOR), key=lambda fk: -cost[fk[1]])]


def issues(ctx, H):
    pulls, D_by, P = ctx['pulls'], ctx['D_by'], ctx['P_by']
    N = len(pulls)
    if not any(d['cause'] == CYST for d in ctx['deaths']): return []
    knocks = collections.defaultdict(lambda: collections.defaultdict(list))
    drops = collections.defaultdict(list)
    for d in ctx['debuffs']:
        if d['ability'] == XW: knocks[d['pull']][round(d['e'])].append(d['player'])
        if d['ability'] == SURGE: drops[d['pull']].append(d['e'])
    winds = collections.defaultdict(list)                       # (start, end) of the intermission
    for p in pulls:
        seq = list(zip(p['phase_seq'], p['phase_times']))
        for k, (pid, t) in enumerate(seq):
            if pid == 2: winds[p['pull']].append((t, seq[k + 1][1] if k + 1 < len(seq) else p['duration_s']))

    # bursts of Cyst deaths (3+ less than 6 s apart) and what set them off
    waves = []
    for p in pulls:
        cd = [d for d in D_by[p['pull']] if d['cause'] == CYST]; i = 0
        while i < len(cd):
            j = i
            while j + 1 < len(cd) and cd[j + 1]['t'] - cd[i]['t'] < 6: j += 1
            t0 = cd[i]['t']; n = j - i + 1
            if n >= 3:
                kn = [k for k in knocks[p['pull']] if -1 <= t0 - k <= 10]
                dr = [t for t in drops[p['pull']] if 0 <= t0 - t <= 8]
                when = 'winds' if any(s <= t0 <= e + 3 for s, e in winds[p['pull']]) else 'knock' if kn else 'drop' if dr else 'later'
                b = ctx['bursts'].get(p['pull'])
                waves.append(dict(pull=p['pull'], t=t0, deaths=n, when=when, ended=bool(b and b['cause'] == CYST and abs(b['t'] - t0) < 6)))
            i = j + 1
    if len(waves) < 2: return []

    # Crosswinds: who got launched, and did a Cyst wave follow
    thrown, marked = collections.Counter(), collections.Counter()
    rows = []
    for p in pulls:
        at = position_reader(ctx, p['pull'])
        if not at: continue
        dead = {}
        for d in D_by[p['pull']]: dead.setdefault(d['player'], d['t'])
        for k, names in knocks[p['pull']].items():
            th = 0
            for nm in names:
                if dead.get(nm, 1e9) < k: continue
                a, b = at(nm, k - 1), at(nm, k + 2)
                if not a or not b: continue
                marked[nm] += 1
                if math.dist(a, b) >= THROWN_YD: thrown[nm] += 1; th += 1
            wave = next((w for w in waves if w['pull'] == p['pull'] and -1 <= w['t'] - k <= 10), None)
            rows.append(dict(pull=p['pull'], t=k, thrown=th, wave=wave))
    def bucket(lo, hi, label):
        rs = [r for r in rows if lo <= r['thrown'] <= hi]
        w = sum(1 for r in rs if r['wave'])
        return dict(label=label, value=round(100 * w / len(rs)) if rs else 0, max=100, num=f'{w} of {len(rs)} knocks')
    buckets = [bucket(0, 0, 'Nobody thrown'), bucket(1, 1, '1 thrown'), bucket(2, 2, '2 thrown'), bucket(3, 99, '3 or more thrown')]
    min_marks = max(5, round(0.15 * N))
    cls = {p['player']: p['cls'] for p in ctx['players4']}
    who_thrown = sorted([(nm, thrown[nm], marked[nm]) for nm in marked if marked[nm] >= min_marks], key=lambda r: -r[1] / r[2])[:6]

    ended = [p for p in pulls if (ctx['bursts'].get(p['pull']) or {}).get('cause') == CYST]
    cyst_deaths = sum(1 for d in ctx['deaths'] if d['cause'] == CYST)
    big3 = [r for r in rows if r['thrown'] >= 3]; none = [r for r in rows if r['thrown'] == 0]
    WHEN = [('knock', 'At the Crosswinds knock', 'Within 10 s of the knock, as marked players get thrown across the room'),
            ('drop', 'Right after the Cysts drop', 'In the 8 s after Surge lands and drops the Cysts'),
            ('winds', 'In the winds', 'During a wind push, when Cysts are supposed to be popped on purpose'),
            ('later', 'Walking into an old Cyst', 'Later, while moving for the next combo or Fury stack')]
    when_rows = []
    for k, label, desc in WHEN:
        ws = [w for w in waves if w['when'] == k]
        if not ws: continue
        big = max(ws, key=lambda w: w['deaths'])
        when_rows.append(dict(label=label, desc=desc, value=sum(w['deaths'] for w in ws), num=f"{len(ws)} times · {sum(w['deaths'] for w in ws)} deaths",
                              go=dict(pull=big['pull'], t=max(0, big['t'] - 4))))
    tr = H['trend'](ctx, lambda p: p in ended, 'Pulls ended by a Cyst pop')
    summary = (f"Touching a Cyst pops it and knocks back the whole raid. Viscous Cyst caused {cyst_deaths:,} of the {len(ctx['deaths']):,} deaths "
               f"({H['pct'](cyst_deaths, len(ctx['deaths']))}%), almost all of them in {len(waves)} mass knockbacks of 3 or more deaths.")
    r3 = sum(1 for r in big3 if r['wave']) / len(big3) if big3 else 0
    r0 = sum(1 for r in none if r['wave']) / len(none) if none else 0
    if len(big3) >= 5 and r3 >= 0.4 and r3 >= 3 * max(r0, 0.01):
        summary += (f" The biggest trigger is the Crosswinds knock: when 3 or more of the marked players got thrown, a Cyst wipe followed "
                    f"{sum(1 for r in big3 if r['wave'])} of {len(big3)} times. When nobody got thrown, it was {sum(1 for r in none if r['wave'])} of {len(none)}.")
    else:
        top = max(WHEN, key=lambda w: sum(x['deaths'] for x in waves if x['when'] == w[0]))
        tw = [x for x in waves if x['when'] == top[0]]
        summary += f" The most deaths came {top[1].lower()}: {len(tw)} times, {sum(x['deaths'] for x in tw)} deaths."
        if big3: summary += (f" Players getting thrown by Crosswinds wasn't the trigger here: when 3 or more were thrown, a Cyst wipe followed "
                             f"{sum(1 for r in big3 if r['wave'])} of {len(big3)} times.")
    guide = ctx['profile'].get('guide', {}).get(CYST, {})
    ex_rows = sorted([r for r in rows if r['thrown'] >= 3 and r['wave']], key=lambda r: -r['wave']['deaths'])[:3]
    return [dict(
        key='cyst', replaces='cause-' + CYST, cause=CYST, title='Cyst pops are knocking the raid off the platform',
        big=f'{len(ended)} of {N}', big_lbl='pulls ended by a Cyst pop', summary=summary,
        main=[dict(type='rows', title='When the Cyst went off (bursts of 3+ Cyst deaths)', rows=when_rows),
              dict(type='rows', title='Crosswinds-marked players thrown 30+ yards, and how often a Cyst wipe followed', rows=buckets)],
        side=[tr, dict(type='who', label=f'Thrown 30+ yards by their own Crosswinds (share of their marks, {min_marks}+ marks)',
                       items=[dict(player=nm, cls=cls.get(nm, ''), txt=f'{t} of {m} ({round(100 * t / m)}%)') for nm, t, m in who_thrown])],
        fixes=ordered_fixes(guide.get('fixes', []), waves),
        examples=[dict(pull=r['pull'], t=max(0, r['t'] - 4), label=f"{P[r['pull']]['label']} · {H['f2'](r['t'])} · {r['thrown']} thrown, {r['wave']['deaths']} died") for r in ex_rows]
                 + [dict(pull=w['pull'], t=max(0, w['t'] - 4), label=f"{P[w['pull']]['label']} · {H['f2'](w['t'])} · {w['deaths']} died, {(lambda l: l[0].lower() + l[1:])(dict((k, l) for k, l, d in WHEN)[w['when']])}")
                    for w in sorted(waves, key=lambda w: -w['deaths'])[:5 - len(ex_rows)]],
        status=H['status'](tr), impact=len(ended) + 0.5)]
