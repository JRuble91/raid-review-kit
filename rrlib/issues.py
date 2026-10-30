"""Generic 'Biggest problems' detectors. Every card is plain data that issues.js renders.

Card: {key, cause, color, title, big, big_lbl, summary, status{text,tone}, main[sections], side[sections], fixes[], examples[], impact}
  main sections: {type:'rows', title, rows:[{label, desc, value, max, dark, num, go:{pull,t}}]} | {type:'note', text}
  side sections: {type:'trend', label, unit ('%'|'rank'|''), higher_is_better, items:[{night, value, txt}]} | {type:'who', label, items:[{player, cls, txt}]}
"""
import collections, importlib.util, statistics as st

f2 = lambda s: f'{int(max(0, s) // 60)}:{int(max(0, s) % 60):02d}'
pct = lambda a, b: round(100 * a / b) if b else 0


def num(v):
    """Short number: 2.78M, 209K, 16.2."""
    v = float(v)
    for floor, div, unit in ((1e9, 1e9, 'B'), (1e6, 1e6, 'M'), (1e4, 1e3, 'K')):
        if abs(v) >= floor: return f'{v / div:.3g}{unit}'
    return str(int(v)) if v == int(v) else f'{v:.3g}'


def buckets(ctx):
    """Trend buckets: nights when there are several, else thirds of the night."""
    pulls = ctx['pulls']
    if len(ctx['labels']) > 1:
        return [(lab, [p for p in pulls if p['night'] == lab]) for lab in ctx['labels']]
    n = len(pulls)
    if n < 6: return [(f'Pulls 1–{n}', pulls)]
    k = [0, round(n / 3), round(2 * n / 3), n]
    return [(f'Pulls {k[i] + 1}–{k[i + 1]}', pulls[k[i]:k[i + 1]]) for i in range(3)]


def trend(ctx, fn, label, unit='%', hib=False):
    items = []
    for lab, ps in buckets(ctx):
        hit = sum(1 for p in ps if fn(p))
        items.append(dict(night=lab, value=pct(hit, len(ps)) if unit == '%' else hit, txt=f'{hit} of {len(ps)}'))
    return dict(type='trend', label=label, unit=unit, higher_is_better=hib, items=items)


def status(tr, what='last raid'):
    it = tr['items']
    if len(it) < 2: return dict(text='Only one stretch of pulls so far', tone='bad')
    last = it[-1]['value']; prev = [x['value'] for x in it[:-1] if x['value'] is not None]
    base = sum(prev) / len(prev) if prev else last
    lab = it[-1]['night']
    better = (last > base + 8) if tr.get('higher_is_better') else (last < base - 8)
    worse = (last < base - 8) if tr.get('higher_is_better') else (last > base + 8)
    u = '%' if tr['unit'] == '%' else ''
    if better: return dict(text=f'Better in {lab} ({last}{u} vs {round(base)}{u} before)', tone='ok')
    if worse: return dict(text=f'Worse in {lab} ({last}{u} vs {round(base)}{u} before)', tone='bad')
    return dict(text=f'About the same in {lab}', tone='bad')


def who(ctx, counter, label, rate_of=None, n=6, min_pulls=3):
    pin = {p['player']: p['pulls'] for p in ctx['players4']}
    cls = {p['player']: p['cls'] for p in ctx['players4']}
    rows = []
    for nm, c in counter.most_common():
        if pin.get(nm, 0) < min_pulls: continue
        rows.append(dict(player=nm, cls=cls.get(nm, ''), txt=rate_of(nm, c, pin[nm]) if rate_of else f'{c} {"time" if c == 1 else "times"}'))
        if len(rows) >= n: break
    return dict(type='who', label=label, items=rows)


def ex(ctx, rows, what):
    P = ctx['P_by']
    return [dict(pull=r['pull'], t=max(0, round(r['t'] - 4, 1)), label=f"{P[r['pull']]['label']} · {f2(r['t'])} · {what(r)}") for r in rows]


def guide_fixes(ctx, cause, fallback):
    g = ctx['profile'].get('guide', {}).get(cause, {})
    if g.get('fixes'): return g['fixes']
    if g.get('todo'): return [g['todo']] + fallback[1:]
    return fallback


def build(ctx):
    pulls, deaths, D_by, E_by, P = ctx['pulls'], ctx['deaths'], ctx['D_by'], ctx['E_by'], ctx['P_by']
    canon, meta, bursts = ctx['canon'], ctx['meta'], ctx['bursts']
    N = len(pulls); total = len(deaths)
    cards = []

    # ---------------- what ended each pull
    top = [c for c, _ in collections.Counter(b['cause'] for b in bursts.values() if b['kind'] == 'cause').most_common(4)]
    order = top + ['Enrage', 'Kill', 'Something else']
    def ending(p):
        if p['kill']: return 'Kill'
        b = bursts.get(p['pull'])
        if not b: return 'Something else'
        return 'Enrage' if b['kind'] == 'enrage' else b['cause'] if b['cause'] in top else 'Something else'
    endings = []
    for lab, ps in (buckets(ctx) if len(ctx['labels']) > 1 else [('This night', pulls)]):
        c = collections.Counter(ending(p) for p in ps)
        endings.append(dict(night=lab, pulls=len(ps), **{k: c.get(k, 0) for k in order}))
    end_all = collections.Counter(ending(p) for p in pulls)
    order = [k for k in order if end_all.get(k)]

    # ---------------- A. the causes that end pulls
    for cause in top[:3]:
        bs = [dict(b, pull=pn) for pn, b in bursts.items() if b['kind'] == 'cause' and b['cause'] == cause]
        if len(bs) < max(2, 0.1 * N): continue
        cd = [d for d in deaths if canon(d['cause']) == cause]
        before = collections.Counter(); ex_by = {}
        for b in bs:
            evs = {e['event'] for e in E_by[b['pull']] if b['t'] - 12 <= e['t'] <= b['t'] + 0.5 and not e['enrage'] and e['event'] != cause}
            for e in evs:
                before[e] += 1
                if e not in ex_by or len(b['deaths']) > len(ex_by[e]['deaths']): ex_by[e] = b
        firsts = collections.Counter(b['deaths'][0]['player'] for b in bs if b['deaths'])
        died = collections.Counter(d['player'] for d in cd)
        tmed = st.median(b['t'] for b in bs)
        ev, evn = before.most_common(1)[0] if before else (None, 0)
        summ = (f"{cause} caused {len(cd):,} of the {total:,} deaths ({pct(len(cd), total)}%) and ended {len(bs)} of {N} pulls. "
                f"Those wipes started around {f2(tmed)}")
        summ += f", and {evn} of them came within 12 seconds of {ev}." if ev and evn >= 0.4 * len(bs) else '.'
        tr = trend(ctx, lambda p, c=cause: bursts.get(p['pull'], {}).get('cause') == c and bursts[p['pull']]['kind'] == 'cause', f'Pulls ended by {cause}')
        main = []
        if before:
            main.append(dict(type='rows', title='What happened in the 12 seconds before', rows=[
                dict(label=e, value=c, max=len(bs), num=f'{c} of {len(bs)} wipes', go=dict(pull=ex_by[e]['pull'], t=max(0, ex_by[e]['t'] - 4)))
                for e, c in before.most_common(4)]))
        walls = [w for w in ctx['walls'] if w.get('cause') == cause]
        if len(walls) > 1:
            rows = []
            for w in walls:
                inw = [b for b in bs if w['lo'] <= b['t'] <= w['hi']]
                if not inw: continue
                big = max(inw, key=lambda b: len(b['deaths']))
                rows.append(dict(label=w['when'], value=len(inw), max=len(bs), num=f"{len(inw)} wipes · {sum(len(b['deaths']) for b in inw)} deaths", go=dict(pull=big['pull'], t=max(0, big['t'] - 4))))
            main.append(dict(type='rows', title='When', rows=rows))
        cards.append(dict(key='cause-' + cause, cause=cause, title=f'{cause} is ending pulls', big=f'{len(bs)} of {N}', big_lbl=f'pulls ended by {cause}',
                          summary=summ, main=main, side=[tr, who(ctx, firsts, f'First to die in these wipes'),
                                                         who(ctx, died, f'Died to {cause} most (per 10 pulls)', lambda nm, c, n: f'{10 * c / n:.1f}')],
                          fixes=guide_fixes(ctx, cause, [f'Watch the worst pulls below and find who {cause} hits first, and where they were standing.',
                                                         f'Write one sentence for the raid on how to handle {cause}, and call it out the moment it starts.']),
                          examples=ex(ctx, sorted(bs, key=lambda b: -len(b['deaths']))[:4], lambda r: f"{len(r['deaths'])} died"),
                          status=status(tr), impact=len(bs)))

    # ---------------- B. enrage
    enr = []
    for p in pulls:
        t = next((e['t'] for e in E_by[p['pull']] if e['enrage']), None)
        if t is None: continue
        alive = len(p['roster']) - sum(1 for d in D_by[p['pull']] if d['t'] < t - 0.5)
        enr.append(dict(pull=p['pull'], t=t, alive=alive))
    if len(enr) >= 2:
        enough = ctx['profile'].get('enrage_enough_alive') or meta['checkpoint']['alive']
        hi_alive = [e for e in enr if e['alive'] >= enough]
        ts = sorted(e['t'] for e in enr)
        clusters, cur = [], [ts[0]]
        for t in ts[1:]:
            if t - cur[-1] > 25: clusters.append(cur); cur = [t]
            else: cur.append(t)
        clusters.append(cur)
        rows = []
        for c in clusters:
            inw = [e for e in enr if c[0] - 0.1 <= e['t'] <= c[-1] + 0.1]
            big = max(inw, key=lambda e: e['alive'])
            rows.append(dict(label=f'{f2(c[0])} to {f2(c[-1])}' if c[0] != c[-1] else f2(c[0]), value=len(inw), dark=sum(1 for e in inw if e in hi_alive), max=len(enr),
                             num=f"{len(inw)} · {sum(1 for e in inw if e in hi_alive)} with {enough}+ alive", go=dict(pull=big['pull'], t=max(0, big['t'] - 4))))
        tr = trend(ctx, lambda p: any(e['pull'] == p['pull'] for e in enr), 'Pulls that hit the enrage')
        cards.append(dict(key='enrage', cause='', color='bad', title='The boss enrages', big=f'{len(enr)} of {N}', big_lbl='pulls hit the enrage',
                          summary=(f"{len(enr)} pulls hit the enrage. " + (
                              f"{len(hi_alive)} of them still had {enough} or more people alive, enough to have done the mechanic, so it was missed rather than the raid already being dead."
                              if hi_alive else f"In every one fewer than {enough} people were alive, so the pull was already going down when it happened.")),
                          main=[dict(type='rows', title=f"When (darker: {enough}+ alive)", rows=rows)],
                          side=[tr], fixes=guide_fixes(ctx, 'Enrage', ['Find what triggers the enrage on this boss and assign someone to call it.',
                                                                       'Watch the pulls below: the enrage came with most of the raid alive.']),
                          examples=ex(ctx, sorted(enr, key=lambda e: -e['alive'])[:4], lambda r: f"{r['alive']} alive"), status=status(tr), impact=len(enr)))

    # ---------------- C. the first deaths decide the pull
    cp = meta['checkpoint']
    alive_cp = {p['pull']: len(p['roster']) - sum(1 for d in D_by[p['pull']] if d['t'] < cp['t']) for p in pulls}
    hi = [p for p in pulls if alive_cp[p['pull']] >= cp['alive'] and p['duration_s'] >= cp['t']]
    lo = [p for p in pulls if p not in hi]
    if N >= 3 and hi and lo:
        firstc = collections.Counter(canon(D_by[p['pull']][0]['cause']) for p in pulls if D_by[p['pull']])
        f4 = collections.Counter(canon(d['cause']) for p in pulls for d in D_by[p['pull']][:4]); f4n = sum(f4.values())
        firstp = collections.Counter(D_by[p['pull']][0]['player'] for p in pulls if D_by[p['pull']])
        far = lambda ps: pct(sum(1 for p in ps if p['stage'] >= 1 or p['kill']), len(ps))
        top1, n1 = firstc.most_common(1)[0]
        summ = (f"With {cp['alive']} or more alive at {f2(cp['t'])}, the boss ended at {st.mean(p['boss_pct'] for p in hi):.1f}% on average, "
                f"vs {st.mean(p['boss_pct'] for p in lo):.1f}% with fewer.")
        if len(meta['stages']) > 1:
            summ += f" {far(hi)}% of those pulls got past the first phase, vs {far(lo)}%."
        summ += f" {top1} was the first death in {n1} of {N} pulls and {f4[top1]} of the {f4n} first-four deaths."
        tr = trend(ctx, lambda p: p in hi, f"Pulls with {cp['alive']}+ alive at {f2(cp['t'])}", hib=True)
        ex_rows = []
        for c, k in firstc.most_common(4):
            p0 = next(p for p in pulls if D_by[p['pull']] and canon(D_by[p['pull']][0]['cause']) == c)
            ex_rows.append(dict(label=c, value=k, max=N, num=f'{k} of {N} pulls', go=dict(pull=p0['pull'], t=max(0, D_by[p0['pull']][0]['t'] - 4))))
        pin = {p['player']: p['pulls'] for p in ctx['players4']}
        cards.append(dict(key='early', cause=top1, title='The first deaths decide the pull', big=f'{len(lo)} of {N}',
                          big_lbl=f"pulls with fewer than {cp['alive']} alive at {f2(cp['t'])}", summary=summ,
                          main=[dict(type='rows', title='What killed the first person', rows=ex_rows)],
                          side=[tr, who(ctx, firstp, 'First to die most often', lambda nm, c, n: f'{c} of {n} ({pct(c, n)}%)', min_pulls=max(3, N // 4))],
                          fixes=guide_fixes(ctx, top1, [f'{top1} takes the first death most often: plan a defensive or healthstone for it.',
                                                        f"Healers: the first {f2(cp['t'])} is about keeping everyone up, not throughput."]),
                          examples=ex(ctx, [dict(pull=p['pull'], t=D_by[p['pull']][0]['t']) for p in sorted(lo, key=lambda p: D_by[p['pull']][0]['t'] if D_by[p['pull']] else 999)[:4] if D_by[p['pull']]],
                                      lambda r: 'first death'),
                          status=status(tr), impact=len(lo) * 0.8))

    # ---------------- D. someone dies holding a debuff and the raid follows
    for r in [r for r in meta['rings'] if r['style'] == 'ring']:
        ab = r['ability']; chains = []; held = 0
        for d in ctx['debuffs']:
            if d['ability'] != ab: continue
            dd = next((x for x in D_by[d['pull']] if x['player'] == d['player'] and d['s'] <= x['t'] <= d['e'] + 0.5), None)
            if not dd or canon(dd['cause']) == ab: continue          # dying to the debuff itself is the chain, not what set it off
            alive_then = len(P[d['pull']]['roster']) - sum(1 for x in D_by[d['pull']] if x['t'] < dd['t'] - 0.5)
            if alive_then < ctx['roster_size'] - 3: continue          # the pull was already going down
            held += 1
            after = [x for x in D_by[d['pull']] if dd['t'] < x['t'] <= dd['t'] + 6]
            if len(after) >= 3: chains.append(dict(pull=d['pull'], t=dd['t'], who=dd['player'], cause=canon(dd['cause']), n=len(after)))
        if len(chains) >= 3 and len(chains) >= 0.3 * held:
            causes_ = collections.Counter(c['cause'] for c in chains)
            tr = trend(ctx, lambda p: any(c['pull'] == p['pull'] for c in chains), f'Pulls where it happened')
            cards.append(dict(key='holder-' + ab, cause=ab, title=f'Someone dies with {ab} and the raid follows', big=str(len(chains)),
                              big_lbl=f'times 3+ people died within 6 s of a {ab} holder dying',
                              summary=(f"{held} players died to something else while holding {ab}, with the raid still healthy. {len(chains)} of those were followed by 3 or more deaths within 6 seconds. "
                                       f"What killed the holder: {', '.join(f'{c} {n}' for c, n in causes_.most_common(3))}."),
                              main=[], side=[tr, who(ctx, collections.Counter(c['who'] for c in chains), f'Died holding {ab} right before a chain')],
                              fixes=guide_fixes(ctx, ab, [f'Come into {ab} healthy: defensive or healthstone first if you are low.',
                                                          f'Healers: {ab} holders come first.']),
                              examples=ex(ctx, sorted(chains, key=lambda c: -c['n'])[:4], lambda c: f"{c['n']} died after {c['who']}"),
                              status=status(tr), impact=len(chains)))

    # ---------------- E/F. Wipefest: weak mechanics and consumables
    M = ctx['mechanics4']
    if M:
        weak = [m for m in M if m['group'] == 'boss' and m['score'] is not None and m['score'] < 35 and m['pulls'] >= 3]
        if weak:
            weak.sort(key=lambda m: m['score'])
            worst = weak[0]
            mp = collections.Counter({r['player']: r['count'] for r in ctx['mechanic_players4'] if r['mechanic'] == worst['mechanic']})
            cards.append(dict(key='wipefest-weak', cause='', title='Mechanics we take more of than other raids', big=str(worst['score']),
                              big_lbl=f"Wipefest rank for {worst['label']} (100 is best)",
                              summary=(f"Wipefest compares each mechanic with other raids on this boss. These rank in the bottom third: "
                                       + ', '.join(f"{m['label']} ({m['score']})" for m in weak[:5]) + '.'),
                              main=[dict(type='rows', title='Rank vs other raids (lower is worse)', rows=[dict(label=m['label'], value=100 - m['score'], max=100, num=f"rank {m['score']}") for m in weak[:6]])],
                              side=[who(ctx, mp, f"Most {worst['label'].lower()} per 10 pulls", lambda nm, c, n: num(c))],
                              fixes=[f"Start with {worst['label']}: watch your own deaths and hits in the replay.", 'Each player can see their own numbers on the Your report tab.'],
                              examples=[], status=dict(text='From Wipefest', tone='bad'), impact=N * 0.15))
        cons = [m for m in M if m['group'] == 'raid' and m['mechanic'] in ('raid:0', 'raid:1') and m['score'] is not None and m['score'] < 40]
        if cons:
            side = []
            for m in cons:
                side.append(dict(type='trend', label=f"Wipefest rank, {m['label'].lower()} (100 is best)", unit='rank', higher_is_better=True,
                                 items=[dict(night=lab, value=v or 0, txt='—' if v is None else str(v)) for lab, v in zip(ctx['labels'], m['by_night'])]))
                low = collections.Counter({r['player']: -r['count'] for r in ctx['mechanic_players4'] if r['mechanic'] == m['mechanic']})
                side.append(dict(type='who', label=f"Fewest {m['label'].lower()} per 10 pulls", items=[
                    dict(player=nm, cls=next((p['cls'] for p in ctx['players4'] if p['player'] == nm), ''), txt=num(-c)) for nm, c in low.most_common(6)]))
            cards.append(dict(key='consumables', cause='', title='Potions and healthstones are barely used', big=str(min(m['score'] for m in cons)),
                              big_lbl='lowest Wipefest rank vs other raids (100 is best)',
                              summary=' '.join(f"{m['label']}: rank {m['score']} vs other raids" + (f", {num(m['per_pull'])} a pull for the whole raid." if m['per_pull'] is not None else '.') for m in cons),
                              main=[], side=side,
                              fixes=['Pre-pot and use a combat potion every pull.', 'Press a healthstone the first time you drop low. Do not save it.',
                                     'Raid leader: call potions on the pull.'], examples=[], status=dict(text='From Wipefest', tone='bad'), impact=N * 0.12))

    # ---------------- G. boss plugin
    plug = ctx['profile'].get('_plugin')
    if plug:
        spec = importlib.util.spec_from_file_location('boss_plugin', plug)
        mod = importlib.util.module_from_spec(spec); spec.loader.exec_module(mod)
        helpers = dict(trend=trend, status=status, who=who, ex=ex, f2=f2, pct=pct, num=num)
        extra = mod.issues(ctx, helpers) or []
        gone = {c.get('replaces') for c in extra if c.get('replaces')}
        cards = [c for c in cards if c['key'] not in gone] + extra

    cards.sort(key=lambda c: -c.get('impact', 0))
    best = min(pulls, key=lambda p: p['boss_pct'])
    return dict(n_pulls=N, n_deaths=total, n_nights=len(ctx['labels']), nights=ctx['labels'],
                best=dict(pull=best['pull'], label=best['label'], pct=best['boss_pct'], kill=best['kill']),
                endings=endings, end_order=order, end_all={k: end_all.get(k, 0) for k in order}, cards=cards)
