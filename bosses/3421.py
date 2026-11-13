"""The Twin Fangs (encounter 3421) plugin: Broodling kicks, unsoaked Globules, Feast soaks, Stone Breaker smashes and waves.

Reads the raw log next to each night's data (n['src']) for per-event stacks, and `<code>-3421-<diff>.kicks.json`
(interrupts and Visceral Burst casts per Broodling) when it was collected.
"""
import collections, json, os

RAID_UP = 15            # "the raid was still up" = at least this many alive
SOAK_MIN = 4            # Ravenous Feast needs 4 per hit on Mythic


def raw_pulls(ctx):
    """[(pull, raw fight, abilities, names, kicks or None)] in pull order."""
    out = []
    for n in ctx['nights']:
        src = n.get('src')
        if not src or not os.path.exists(src): continue
        W = json.load(open(src))
        kp = src.replace('.wcl.', '.kicks.')
        K = json.load(open(kp)) if os.path.exists(kp) else None
        for np_, f in enumerate(sorted(W['fights'], key=lambda f: f['id']), 1):
            pull = ctx['gmap'].get((n['code'], np_))
            if pull: out.append((pull, f, W['abilities'], [p['name'] for p in W['players']], (K or {}).get(str(f['id'])) if K is not None else None))
    return out


def alive_at(ctx, pull, t):
    p = ctx['P_by'][pull]
    return len(p['roster']) - sum(1 for d in ctx['D_by'][pull] if d['t'] < t)


def deaths_between(ctx, pull, a, b):
    return [d for d in ctx['D_by'][pull] if a <= d['t'] <= b]


def ordinal(k):
    return {1: '1st', 2: '2nd', 3: '3rd'}.get(k, f'{k}th')


def issues(ctx, H):
    pulls, P = ctx['pulls'], ctx['P_by']
    N = len(pulls)
    R = raw_pulls(ctx)
    if not R: return []
    guide = ctx['profile'].get('guide', {})
    cls = {p['player']: p['cls'] for p in ctx['players4']}
    f2 = H['f2']
    cards = []

    # ------------------------------------------------------------ 1. Broodling kicks
    have_kicks = any(k is not None for *_, k in R)
    if have_kicks:
        broods, slots, kicks, brood_alive = [], collections.Counter(), collections.Counter(), collections.Counter()
        slot_seen = collections.Counter()
        for pull, f, AB, names, K in R:
            if not K: continue
            A = {a: i for i, a in enumerate(AB)}
            rtb = sorted(c[0] for c in f['casts'] if AB[c[1]] == 'Rouse the Brood' and c[4] == 0)
            begin, done = {}, {}
            for t, b, inst, _ in K['vb']:
                (begin if b else done).setdefault(inst, t)
            kicked_at = {}
            for t, who, abil, what, tgt, inst in K['ints']:
                kicked_at.setdefault(inst, t); kicks[who] += 1
            for w, t0 in enumerate(rtb, 1):
                lo, hi = (w - 1) * 10 + 1, w * 10
                insts = sorted((i for i in begin if lo <= i <= hi), key=lambda i: begin[i])
                if not insts: continue
                alive0 = alive_at(ctx, pull, t0 + 1)
                if alive0 < RAID_UP: continue          # the raid was already gone when this Brood came
                for nm in P[pull]['roster']:
                    dead = next((d['t'] for d in ctx['D_by'][pull] if d['player'] == nm), 1e9)
                    if dead > t0 + 12: brood_alive[nm] += 1
                through = []
                for k, i in enumerate(insts, 1):
                    slot_seen[k] += 1
                    if i in done and done[i] < kicked_at.get(i, 1e9):
                        al = alive_at(ctx, pull, done[i])
                        if al >= RAID_UP:
                            through.append(dict(slot=k, t=done[i], alive=al)); slots[k] += 1
                t1 = through[0]['t'] if through else None
                died = len(deaths_between(ctx, pull, t1, t1 + 15)) if through else 0
                broods.append(dict(pull=pull, wave=w, t0=t0, n=len(insts), through=through, t=t1 or t0, died=died))
        bad = [b for b in broods if b['through']]
        if broods and bad:
            n_burst = sum(len(b['through']) for b in bad)
            wiped = [b for b in bad if b['died'] >= 5]
            rows = []
            for w in sorted({b['wave'] for b in broods}):
                bw = [b for b in broods if b['wave'] == w]; xw = [b for b in bw if b['through']]
                big = max(xw, key=lambda b: (b['died'], len(b['through'])), default=None)
                rows.append(dict(label=f"{ordinal(w)} Brood (about {f2(st_med([b['t0'] for b in bw]))})",
                                 desc=f"{sum(len(b['through']) for b in xw)} bursts got off · {sum(1 for b in xw if b['died'] >= 5)} wipes followed",
                                 value=len(xw), max=len(bw), num=f'{len(xw)} of {len(bw)} Broods',
                                 go=dict(pull=big['pull'], t=max(0, big['t'] - 5)) if big else None))
            slot_rows = [dict(label=f'{ordinal(k)} Broodling up', value=slots[k], max=max(slots.values()),
                              num=f"{slots[k]} of {slot_seen[k]}") for k in sorted(slot_seen) if slots[k]]
            late = sum(slots[k] for k in slots if k >= 7)
            per_brood = sorted(((nm, kicks[nm], brood_alive[nm]) for nm in kicks if brood_alive[nm] >= 5), key=lambda r: -r[1] / r[2])
            tr = H['trend'](ctx, lambda p: any(b['pull'] == p['pull'] for b in bad), 'Pulls where a Broodling got a burst off')
            summary = (f"Every Broodling has to be kicked, and the guides call this the main wipe on Mythic. Across {len(broods)} Broods with the raid still up, "
                       f"{len(bad)} let at least one Visceral Burst through ({n_burst} bursts in all), and {'every one' if len(wiped) == len(bad) else len(wiped)} of those turned into a wipe "
                       f"(5 or more dead within 15 s).")
            wr = [(w, [b for b in broods if b['wave'] == w]) for w in sorted({b['wave'] for b in broods})]
            wr = [(w, bw, sum(1 for b in bw if b['through'])) for w, bw in wr if len(bw) >= 5]
            if wr:
                w, bw, x = max(wr, key=lambda r: r[2] / len(r[1]))
                summary += f" The {ordinal(w)} Brood is the leakiest: {x} of {len(bw)} let a burst through."

            ex_rows = sorted(bad, key=lambda b: (-b['died'], -len(b['through'])))[:4]
            cards.append(dict(
                key='kicks', replaces=['cause-Visceral Burst', 'holder-Visceral Burst', 'holder-Coiling Ichor', 'holder-Feasted', 'holder-Blood Torrent'], cause='Visceral Burst',
                title='Broodlings are getting their Visceral Burst off', big=f'{len(bad)} of {len(broods)}', big_lbl='Broods with a burst through',
                summary=summary,
                main=[dict(type='rows', title='Which Brood (with 15+ still alive)', rows=rows),
                      dict(type='rows', title='Which Broodling got through, by the order they came up', rows=slot_rows)],
                side=[tr, dict(type='who', label='Kicks landed per Brood they were alive for',
                               items=[dict(player=nm, cls=cls.get(nm, ''), txt=f'{k / a:.1f} ({k} kicks, {a} Broods)') for nm, k, a in per_brood[:8]])],
                fixes=guide.get('Visceral Burst', {}).get('fixes', []),
                examples=[dict(pull=b['pull'], t=max(0, round(b['t'] - 5, 1)),
                               label=f"{P[b['pull']]['label']} · {f2(b['t'])} · {ordinal(b['wave'])} Brood, {len(b['through'])} through, {b['died']} died")
                          for b in ex_rows],
                status=H['status'](tr), impact=len(wiped) + 0.6))

    # ------------------------------------------------------------ 2. Globules nobody soaked
    blows = []
    for pull, f, AB, names, K in R:
        A = {a: i for i, a in enumerate(AB)}
        if 'Eternal Venom' not in A: continue
        EV = A['Eternal Venom']
        rtb = [c[0] for c in f['casts'] if AB[c[1]] == 'Rouse the Brood' and c[4] == 0]
        deluge = sorted({round(c[0]) for c in f['casts'] if AB[c[1]] == 'Caustic Deluge' and c[4] == 1})
        ev = sorted((t, p) for t, a, p, ty, s in f['debuffs'] if a == EV and ty in (0, 2))
        cl = []
        for t, p in ev:
            if cl and t - cl[-1][0] <= 0.3: cl[-1][1].add(p)
            else: cl.append([t, {p}])
        last = -99
        for t, ps in cl:
            al = alive_at(ctx, pull, t)
            if len(ps) < max(6, 0.6 * al) or any(abs(t - r) < 1.5 for r in rtb): continue
            if t - last < 1.5: continue          # one pop seen twice
            last = t
            d0 = max((d for d in deluge if d <= t), default=None)
            k = deluge.index(d0) + 1 if d0 is not None else 0
            when = f'set{k}' if d0 is not None and t - d0 <= 30 else 'late'
            died = deaths_between(ctx, pull, t - 0.2, t + 3)
            blows.append(dict(pull=pull, t=t, when=when, set=k, alive=al, died=len(died)))
    if blows:
        pulls_with = {b['pull'] for b in blows}
        ended = [p for p in pulls if (ctx['bursts'].get(p['pull']) or {}).get('cause') == 'Caustic Globule']
        cg_deaths = sum(1 for d in ctx['deaths'] if d['cause'] == 'Caustic Globule')
        rows = []
        labels = {'set1': 'Globules from the 1st Deluge', 'set2': 'Globules from the 2nd Deluge', 'set3': 'Globules from the 3rd Deluge',
                  'set4': 'Globules from the 4th Deluge', 'late': 'Long after a Deluge (most likely Globules dropped by deaths)'}
        for key in ['set1', 'set2', 'set3', 'set4', 'late']:
            bs = [b for b in blows if b['when'] == key]
            if not bs: continue
            big = max(bs, key=lambda b: b['died'])
            rows.append(dict(label=labels[key], desc=f"{len({b['pull'] for b in bs})} pulls · {sum(b['died'] for b in bs)} died within 3 s",
                             value=len(bs), max=len(blows), num=f'{len(bs)} went off', go=dict(pull=big['pull'], t=max(0, round(big['t'] - 6, 1)))))
        died3 = len({(b['pull'], d['t'], d['player']) for b in blows for d in deaths_between(ctx, b['pull'], b['t'] - 0.2, b['t'] + 3)})
        tr = H['trend'](ctx, lambda p: p['pull'] in pulls_with, 'Pulls where a Globule went off unsoaked')
        top = max(rows, key=lambda r: r['value'])
        summary = (f"A Globule nobody soaks explodes, gives the whole raid an Eternal Venom stack and hits hard. We had {len(blows)} of them go off "
                   f"in {len(pulls_with)} of {N} pulls, and {died3} people died within 3 seconds of one. Caustic Globule caused {cg_deaths} of the "
                   f"{len(ctx['deaths'])} deaths ({H['pct'](cg_deaths, len(ctx['deaths']))}%) and ended {len(ended)} pulls. "
                   f"The most came from {top['label'].replace('Globules from the ', 'the ').replace('Long after a Deluge', 'long after a Deluge')} ({top['value']}).")
        cards.append(dict(
            key='globules', replaces=['cause-Caustic Globule', 'holder-Eternal Venom', 'holder-Caustic Globule'], cause='Caustic Globule',
            title='Globules are going off unsoaked', big=str(len(blows)), big_lbl=f'Globules exploded, in {len(pulls_with)} of {N} pulls',
            summary=summary,
            main=[dict(type='rows', title='When they went off (the whole raid got a stack at once)', rows=rows),
                  dict(type='note', text='Spotted from the logs as the whole raid gaining an Eternal Venom stack in the same instant, outside Rouse the Brood. '
                                         'The logs don\'t say whose Globule it was.')],
            side=[tr, H['who'](ctx, collections.Counter(d['player'] for d in ctx['deaths'] if d['cause'] == 'Caustic Globule'),
                               'Died to Caustic Globule most (per 10 pulls)', lambda nm, c, n: f'{10 * c / n:.1f}')],
            fixes=guide.get('Caustic Globule', {}).get('fixes', []),
            examples=[dict(pull=b['pull'], t=max(0, round(b['t'] - 6, 1)), label=f"{P[b['pull']]['label']} · {f2(b['t'])} · {b['died']} died within 3 s")
                      for b in sorted(blows, key=lambda b: -b['died'])[:4]],
            status=H['status'](tr), impact=len(ended) + 0.5))

    # ------------------------------------------------------------ 3. Ravenous Feast soaks
    feasts = []
    for pull, f, AB, names, K in R:
        rf = sorted(c[0] for c in f['casts'] if AB[c[1]] == 'Ravenous Feast' and c[4] == 0)
        fe = sorted(t for t, a, p, ty, s in f['debuffs'] if AB[a] == 'Feasted' and ty == 0)
        dur = P[pull]['duration_s']
        for k, t0 in enumerate(rf, 1):
            if alive_at(ctx, pull, t0) < RAID_UP: continue
            hits = []
            for h in range(3):
                a, b = t0 - 0.5 + 2 * h, t0 + 1.5 + 2 * h
                if a > dur: break
                hits.append(sum(1 for t in fe if a <= t < b))
            died = [d for d in ctx['D_by'][pull] if t0 - 0.5 <= d['t'] <= t0 + 7 and d['cause'] == 'Ravenous Feast']
            feasts.append(dict(pull=pull, k=k, t=t0, hits=hits, died=len(died)))
    short = [f for f in feasts if min(f['hits']) < SOAK_MIN]
    if feasts and short:
        rows = []
        for k in sorted({f['k'] for f in feasts}):
            fk = [f for f in feasts if f['k'] == k]; sk = [f for f in fk if min(f['hits']) < SOAK_MIN]
            big = max(sk, key=lambda f: f['died'], default=None)
            rows.append(dict(label=f"{ordinal(k)} Feast (about {f2(st_med([f['t'] for f in fk]))})", desc=f"{sum(f['died'] for f in sk)} died to the Feast",
                             value=len(sk), max=len(fk), num=f'{len(sk)} of {len(fk)} short', go=dict(pull=big['pull'], t=max(0, round(big['t'] - 3, 1))) if big else None))
        hit_rows = []
        for h, who_ in enumerate(['right side', 'left side', 'melee']):
            fh = [f for f in feasts if len(f['hits']) > h]
            n_ = sum(1 for f in fh if f['hits'][h] < SOAK_MIN)
            hit_rows.append(dict(label=f'Hit {h + 1} ({who_} in the guide plan)', value=n_, max=len(fh), num=f'{n_} of {len(fh)} under {SOAK_MIN}'))
        rf_deaths = sum(1 for d in ctx['deaths'] if d['cause'] == 'Ravenous Feast')
        tr = H['trend'](ctx, lambda p: any(f['pull'] == p['pull'] for f in short), 'Pulls with a Feast hit under 4 soakers')
        summary = (f"Each Feast hit needs at least {SOAK_MIN} people in it or it lands on the whole raid. {len(short)} of {len(feasts)} Feasts had a hit "
                   f"with fewer than {SOAK_MIN} soaking, and those killed {sum(f['died'] for f in short)} people. When all three hits had {SOAK_MIN}+, "
                   f"the Feast killed {sum(f['died'] for f in feasts if f not in short)}. Ravenous Feast caused {rf_deaths} deaths in all.")
        cards.append(dict(
            key='feast', replaces=['cause-Ravenous Feast', 'holder-Ravenous Feast'], cause='Ravenous Feast',
            title='Feast hits with fewer than 4 soakers', big=f'{len(short)} of {len(feasts)}', big_lbl='Feasts with a short hit',
            summary=summary,
            main=[dict(type='rows', title='Which Feast', rows=rows), dict(type='rows', title='Which hit was short', rows=hit_rows)],
            side=[tr], fixes=guide.get('Ravenous Feast', {}).get('fixes', []),
            examples=[dict(pull=f['pull'], t=max(0, round(f['t'] - 3, 1)), label=f"{P[f['pull']]['label']} · {f2(f['t'])} · soakers {'/'.join(map(str, f['hits']))}, {f['died']} died")
                      for f in sorted(short, key=lambda f: -f['died'])[:4]],
            status=H['status'](tr), impact=sum(1 for p in pulls if (ctx['bursts'].get(p['pull']) or {}).get('cause') == 'Ravenous Feast') + 0.4))

    # ------------------------------------------------------------ 4. Stone Breaker smashes the tank didn't take
    misses, smashes, by_tank = [], 0, collections.Counter()
    for pull, f, AB, names, K in R:
        sm = sorted(c[0] for c in f['casts'] if AB[c[1]] == 'Stone Breaker' and c[4] == 0)
        hit = sorted((t, names[p]) for t, a, p, ty, s in f['debuffs'] if AB[a] == 'Stone Breaker' and ty in (0, 2))
        sets = []
        for t in sm:
            if sets and t - sets[-1][-1] < 10: sets[-1].append(t)
            else: sets.append([t])
        for s_ in sets:
            got = {t: [n for tt, n in hit if t - 0.3 <= tt <= t + 1.5] for t in s_}
            tanks = collections.Counter(n for v in got.values() for n in v)
            tank = tanks.most_common(1)[0][0] if tanks else ''
            for t in s_:
                if alive_at(ctx, pull, t) < RAID_UP: continue
                smashes += 1
                if not got[t]:
                    died = [d for d in ctx['D_by'][pull] if t - 0.2 <= d['t'] <= t + 2 and d['cause'] == 'Stone Breaker']
                    misses.append(dict(pull=pull, t=t, tank=tank, died=len(died)))
                    if tank: by_tank[tank] += 1
    if misses and sum(m['died'] for m in misses) >= 3:
        sb_deaths = sum(1 for d in ctx['deaths'] if d['cause'] == 'Stone Breaker')
        tr = H['trend'](ctx, lambda p: any(m['pull'] == p['pull'] for m in misses), 'Pulls with a smash no tank took')
        summary = (f"The tank has to take all three Stone Breaker smashes, or the smash hits the raid. With the raid still up, {len(misses)} of {smashes} smashes "
                   f"didn't land on anyone (nobody got the Stone Breaker debuff), and Stone Breaker killed {sum(m['died'] for m in misses)} people within 2 seconds of those. "
                   f"Stone Breaker caused {sb_deaths} deaths in all.")
        cards.append(dict(
            key='stone', replaces=['cause-Stone Breaker', 'holder-Stone Breaker'], cause='Stone Breaker',
            title="Stone Breaker smashes the tank didn't take", big=str(len(misses)), big_lbl=f'missed smashes, {sum(m["died"] for m in misses)} deaths',
            summary=summary,
            main=[dict(type='rows', title='Missed smashes', rows=[
                dict(label=f"{P[m['pull']]['label']} · {f2(m['t'])}", desc=f"tank on that Stone Breaker: {m['tank'] or 'none took any smash'}",
                     value=m['died'], max=max(1, max(x['died'] for x in misses)), num=f"{m['died']} died", go=dict(pull=m['pull'], t=max(0, round(m['t'] - 4, 1))))
                for m in sorted(misses, key=lambda m: m['pull'])[:10]])],
            side=[tr, dict(type='who', label='Tank on the Stone Breaker when a smash was missed',
                           items=[dict(player=nm, cls=cls.get(nm, ''), txt=f'{c} {"time" if c == 1 else "times"}') for nm, c in by_tank.most_common(4)])],
            fixes=guide.get('Stone Breaker', {}).get('fixes', []),
            examples=[dict(pull=m['pull'], t=max(0, round(m['t'] - 4, 1)), label=f"{P[m['pull']]['label']} · {f2(m['t'])} · {m['died']} died")
                      for m in sorted(misses, key=lambda m: -m['died'])[:4]],
            status=H['status'](tr), impact=sum(1 for p in pulls if (ctx['bursts'].get(p['pull']) or {}).get('cause') == 'Stone Breaker') + 0.3))

    # ------------------------------------------------------------ 5. Stir the Depths: the easiest stacks to avoid
    waves = collections.Counter(); wave_pulls = collections.Counter()
    for pull, f, AB, names, K in R:
        c = collections.Counter(names[p] for t, a, p, ty, s in f['debuffs'] if AB[a] == 'Stir the Depths' and ty == 0)
        waves.update(c)
        wave_pulls[pull] = sum(c.values())
    if sum(waves.values()) >= N:
        pin = {p['player']: p['pulls'] for p in ctx['players4']}
        role = {p['player']: p['role'] for p in ctx['players4']}
        long_pulls = [p for p in pulls if p['duration_s'] >= 90]
        rate = sorted(((nm, c, pin.get(nm, 0)) for nm, c in waves.items() if pin.get(nm, 0) >= 5 and role.get(nm) != 'Tank'), key=lambda r: -r[1] / r[2])
        tot = sum(waves.values()); tank_hits = sum(c for nm, c in waves.items() if role.get(nm) == 'Tank')
        per_long = sum(wave_pulls[p['pull']] for p in long_pulls) / max(1, len(long_pulls))
        tr = H['trend'](ctx, lambda p: wave_pulls[p['pull']] >= 10, 'Pulls with 10+ wave hits')
        cards.append(dict(
            key='waves', cause='Stir the Depths', title='Stir the Depths waves: free stacks we keep taking', big=str(tot), big_lbl='wave hits, each one an extra stack',
            summary=(f"Every Stir the Depths wave that hits you adds an Eternal Venom stack, and the guides call them the easiest stacks to avoid. "
                     f"The raid took {tot} wave hits in {N} pulls, about {per_long:.0f} a pull in the {len(long_pulls)} pulls that lasted 1:30 or more "
                     f"({tank_hits} of them on tanks, who are tied to the bosses). Each one is a stack you carry into the next soak."),
            main=[dict(type='rows', title='Wave hits per 10 pulls (tanks left out)', rows=[
                dict(label=nm, value=round(10 * c / n, 1), max=round(10 * rate[0][1] / rate[0][2], 1), num=f'{10 * c / n:.1f} ({c} in {n} pulls)') for nm, c, n in rate[:10]])],
            side=[tr], fixes=[guide.get('Stir the Depths', {}).get('todo', 'Dodge every wave.'),
                              'Treat every wave as lethal later in the fight: your stacks only go down in a Feast.',
                              'If a wave caught you, say so before the next soak so the raid leader can swap you off it.'],
            examples=[], status=H['status'](tr), impact=1.0))
    return cards


def st_med(xs):
    xs = sorted(xs)
    return xs[len(xs) // 2] if xs else 0
