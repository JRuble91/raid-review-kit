"""The Twin Fangs (encounter 3421) plugin: Broodling kicks, unsoaked Globules, Feast soaks, Stone Breaker smashes and waves.

Reads the raw log next to each night's data (n['src']) for per-event stacks, and `<code>-3421-<diff>.kicks.json`
(interrupts and Visceral Burst casts per Broodling) when it was collected.
"""
import collections, json, math, os

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



# ---------------------------------------------------------------- Globules
# Needs <code>-3421-<diff>.globules.json next to the log: per fight, every "Caustic Globule" hit (who, where),
# and every Barbed Bulwark (one per shielded Globule: where it spawned, when the shield came off).
# Caustic Deluge logs one cast per Globule it drops, so the casts are the spawns. A Globule nobody takes
# explodes 10.1 s after it spawns and hits everyone at once; any other hit is somebody taking one.

FUSE = 10.1

def ev_stacks(f, A, P):
    """per player list of (t, stacks) changes of Eternal Venom"""
    EV = A.get('Eternal Venom'); out = collections.defaultdict(list)
    if EV is None: return out
    for t, a, p, ty, s in sorted(f['debuffs'], key=lambda r: r[0]):
        if a != EV: continue
        v = 0 if ty == 1 else max(1, s) if ty in (0, 3) and s == 0 else s
        if ty == 3 and s == 0: continue
        out[P[p]].append((t, v))
    return out

def stack_at(series, t):
    v = 0
    for tt, s in series:
        if tt > t: break
        v = s
    return v

def model(f, AB, P, g):
    A = {a: i for i, a in enumerate(AB)}
    spawns = sorted(c[0] for c in f['casts'] if c[1] == A.get('Caustic Deluge') and c[4] == 0 and c[3] < 0)
    dur = (f['end'] - f['start']) / 1000
    # sets: chains of spawns 0.6 s apart
    groups = []
    for t in spawns:
        if groups and t - groups[-1][-1] <= 0.6: groups[-1].append(t)
        else: groups.append([t])
    hits = sorted(g['soaks'], key=lambda r: r[0])
    # explosions: hit clusters landing FUSE after a spawn, with 4+ targets
    cl = []
    for r in hits:
        if cl and r[0] - cl[-1][0][0] <= 0.35: cl[-1].append(r)
        else: cl.append([r])
    spawn_left = list(spawns)
    blasts, soaks = [], []
    for c in cl:
        t = c[0][0]
        cand = [s for s in spawn_left if abs(t - s - FUSE) <= 0.35]
        if len(c) >= 4 and cand:
            s = min(cand, key=lambda s: abs(t - s - FUSE)); spawn_left.remove(s)
            blasts.append(dict(t=t, spawn=s, n=len(c), victims=[r[1] for r in c]))
        else:
            soaks += c
    soaks = [dict(t=r[0], who=r[1], x=r[2], y=r[3]) for r in soaks]
    # Bulwarks: one per shielded Globule, spawned 0-0.3 s after its Globule
    bws = sorted((v for v in g['bw'].values() if v.get('x') is not None), key=lambda v: v['first'])
    glob = [dict(spawn=s, x=None, y=None, shield_end=None, soaked=None, blast=None) for s in spawns]
    used = set()
    for b in bws:
        k = min((i for i, gl in enumerate(glob) if i not in used and 0 <= b['first'] - gl['spawn'] <= 0.4), key=lambda i: b['first'] - glob[i]['spawn'], default=None)
        if k is None: continue
        used.add(k); glob[k].update(x=b['x'], y=b['y'], shield_end=b['rm'] if b['rm'] is not None else b['last'])
    for bl in blasts:
        k = next((i for i, gl in enumerate(glob) if gl['spawn'] == bl['spawn'] and gl['blast'] is None), None)
        if k is not None: glob[k]['blast'] = bl['t']; bl['g'] = k
    # soaks -> Globules: by position to a shielded one when close, else the oldest open one
    for s in soaks:
        live = [i for i, gl in enumerate(glob) if gl['soaked'] is None and gl['blast'] is None and gl['spawn'] <= s['t'] + 0.2 and s['t'] <= gl['spawn'] + FUSE + 0.2]
        if not live: s['g'] = None; continue
        near = [i for i in live if glob[i]['x'] is not None and s['x'] is not None and math.hypot(glob[i]['x'] - s['x'], glob[i]['y'] - s['y']) <= 600]
        k = min(near, key=lambda i: math.hypot(glob[i]['x'] - s['x'], glob[i]['y'] - s['y'])) if near else min(live, key=lambda i: glob[i]['spawn'])
        glob[k]['soaked'] = s; s['g'] = k
    # sets
    sets = []
    for grp in groups:
        idx = [i for i, gl in enumerate(glob) if grp[0] <= gl['spawn'] <= grp[-1]]
        kind = 'deluge' if len(grp) >= 8 else 'deaths'
        end = grp[-1] + FUSE + 0.3
        sets.append(dict(kind=kind, t0=grp[0], t1=grp[-1], end=end, idx=idx,
                         soakers=[glob[i]['soaked']['who'] for i in idx if glob[i]['soaked']],
                         blasts=[glob[i]['blast'] for i in idx if glob[i]['blast'] is not None],
                         open_at_end=[i for i in idx if glob[i]['soaked'] is None and glob[i]['blast'] is None and end <= dur]))
    return dict(spawns=spawns, glob=glob, soaks=soaks, blasts=blasts, sets=sets, dur=dur, bwhits=g.get('bwHits', []))


def globule_pulls(ctx_nights, gmap):
    """[(code, np, pull, raw fight, abilities, names, model)] for nights that have globules.json."""
    out = []
    for n in ctx_nights:
        src = n.get('src')
        gp = src and src.replace('.wcl.', '.globules.')
        if not gp or not os.path.exists(gp): continue
        W = json.load(open(src)); G = json.load(open(gp))
        P = [p['name'] for p in W['players']]
        for np_, f in enumerate(sorted(W['fights'], key=lambda f: f['id']), 1):
            g = G.get(str(f['id']))
            if g is None: continue
            out.append((n['code'], np_, gmap.get((n['code'], np_)), f, W['abilities'], P, model(f, W['abilities'], P, g)))
    return out


def set_report(f, AB, P, m, raid_up=RAID_UP):
    """Per Deluge set with the raid up: who took one, who sat out, what blew up."""
    deaths = {}
    for d in sorted(f['deaths']): deaths.setdefault(P[d[1]], d[0])
    roster = [P[k] for k in f['players']]
    A = {a: i for i, a in enumerate(AB)}
    stacks = ev_stacks(f, A, P)
    out = []
    for k, S in enumerate([s for s in m['sets'] if s['kind'] == 'deluge'], 1):
        alive0 = [n for n in roster if deaths.get(n, 1e9) > S['t0']]
        if len(alive0) < raid_up: continue
        took = collections.Counter(S['soakers'])
        stayed = [n for n in alive0 if deaths.get(n, 1e9) >= S['t1'] + FUSE - 1]      # alive for the whole set
        out.append(dict(k=k, t0=S['t0'], t1=S['t1'], end=S['end'], n=len(S['idx']), took=took, blasts=S['blasts'],
                        sat=[n for n in stayed if not took[n]], stayed=stayed,
                        stack=lambda n, t=S['t0']: stack_at(stacks[n], t)))
    return out


def replay_extras(nights, gmap, profile):
    """Globules on the floor (with a 10 s fuse), who grabbed each one, and a red ring on everyone who hadn't grabbed one when one blew up."""
    debuffs, objects, notes = collections.defaultdict(list), collections.defaultdict(list), collections.defaultdict(list)
    for code, np_, pull, f, AB, P, m in globule_pulls(nights, gmap):
        key = (code, np_)
        for gl in m['glob']:
            s0 = gl['spawn']; fuse = s0 + FUSE
            end = gl['soaked']['t'] if gl['soaked'] else gl['blast'] if gl['blast'] is not None else min(m['dur'], fuse)
            x, y = gl['x'], gl['y']
            if x is None and gl['soaked'] and gl['soaked']['x'] is not None: x, y = gl['soaked']['x'], gl['soaked']['y']
            if x is None: continue          # unshielded and nobody grabbed it: the log has no spot for it
            se = gl['shield_end']
            who = gl['soaked']['who'] if gl['soaked'] else None
            if se is not None and se > s0:
                objects[key].append([0, x, y, s0, min(se, end), 'Globule with a shield: break it with a stun or fear first', fuse, s0])
            objects[key].append([1, x, y, min(se, end) if se is not None and se > s0 else s0, end,
                                 f"Globule: {who} grabbed it at {int(end // 60)}:{int(end % 60):02d}" if who else 'Globule: nobody grabbed it', fuse, s0])
            if who:
                objects[key].append([3, x, y, end, end + 1.8, f"{who} grabbed it"])
            if gl['blast'] is not None:
                objects[key].append([2, x, y, gl['blast'], gl['blast'] + 2.5, 'Blew up!'])
        for s in m['soaks']:
            debuffs[code].append(dict(np=np_, player=s['who'], ability='Took a Globule', s=s['t'], e=s['t'] + 1.5, stacks=1))
        for S in set_report(f, AB, P, m, raid_up=1):
            if not S['blasts']: continue
            b0, b1 = min(S['blasts']), max(S['blasts'])
            for n in S['sat']:
                debuffs[code].append(dict(np=np_, player=n, ability='No Globule this set', s=b0 - 3, e=b1 + 2, stacks=1))
        bl = sorted(m['blasts'], key=lambda b: b['t']); i = 0
        while i < len(bl):
            j = i
            while j + 1 < len(bl) and bl[j + 1]['t'] - bl[i]['t'] < 1.5: j += 1
            n_ = j - i + 1
            notes[key].append([bl[i]['t'], f"{'A Globule' if n_ == 1 else str(n_) + ' Globules'} blew up: nobody grabbed {'it' if n_ == 1 else 'them'}", 2])
            i = j + 1
    return dict(debuffs=debuffs, objects=objects, notes=notes)


def globule_stats(ctx, GP):
    """Per player, over rounds (Deluges) with the raid up: rounds alive, Globules grabbed, rounds where one blew up and they hadn't grabbed one."""
    per = collections.defaultdict(collections.Counter)
    moments = collections.defaultdict(list)
    sets_up, blasts = [], []
    for code, np_, pull, f, AB, names, m in GP:
        if not pull: continue
        for b in m['blasts']:
            if alive_at(ctx, pull, b['t']) < RAID_UP: continue
            S = next((S for S in m['sets'] if S['t0'] - 0.1 <= b['spawn'] <= S['t1'] + 0.1), None)
            kind = f"set{[x for x in m['sets'] if x['kind'] == 'deluge'].index(S) + 1}" if S and S['kind'] == 'deluge' else 'deaths'
            blasts.append(dict(pull=pull, t=b['t'], kind=kind, died=len(deaths_between(ctx, pull, b['t'] - 0.2, b['t'] + 3))))
        for R in set_report(f, AB, names, m):
            sets_up.append(dict(pull=pull, **{k: R[k] for k in ('k', 't0', 'n', 'blasts', 'sat')}, took=R['took']))
            for nm in R['stayed']:
                c = per[nm]; c['sets'] += 1; c['took'] += R['took'][nm]
                if R['took'][nm] >= 1: c['rounds'] += 1
                if R['took'][nm] >= 2: c['double'] += 1
                if R['blasts']:
                    c['blown_sets'] += 1
                    if not R['took'][nm]:
                        c['sat_blown'] += 1
                        moments[nm].append(dict(pull=pull, t=min(R['blasts'])))
        for t, nm, *_ in m['bwhits']:
            if alive_at(ctx, pull, t) >= RAID_UP: per[nm]['knocked'] += 1
    return per, moments, sets_up, blasts


def player_notes(ctx):
    """A Globules section for each player's report."""
    GP = globule_pulls(ctx['nights'], ctx['gmap'])
    if not GP: return []
    per, moments, sets_up, blasts = globule_stats(ctx, GP)
    P, f2 = ctx['P_by'], lambda s: f"{int(s // 60)}:{int(s % 60):02d}"
    per_set = round(sum(S['n'] for S in sets_up) / max(1, len(sets_up)))
    rates = sorted(c['rounds'] / c['sets'] for c in per.values() if c['sets'] >= 10)
    med = rates[len(rates) // 2] if rates else 0
    out = []
    for nm, c in per.items():
        if not c['sets']: continue
        rate = c['rounds'] / c['sets']
        stats = [dict(v=c['took'], l=f"Globules you grabbed, in {c['sets']} rounds you were alive for"),
                 dict(v=f"{round(100 * rate)}%", l=f"of rounds you grabbed at least one (raid middle: {round(100 * med)}%)",
                      tone='bad' if rate < 0.6 * med else 'ok' if rate >= med else '')]
        if c['blown_sets']:
            stats.append(dict(v=f"{c['sat_blown']} of {c['blown_sets']}", l='rounds where a Globule blew up and you hadn\'t grabbed one',
                              tone='bad' if c['sat_blown'] / c['blown_sets'] >= 0.5 else 'ok' if not c['sat_blown'] else ''))
        if c['knocked']: stats.append(dict(v=c['knocked'], l='times a shielded Globule knocked you back'))
        if not c['blown_sets']:
            verdict, tone = 'No Globule blew up in any round you were alive for.', 'ok'
        elif not c['sat_blown']:
            verdict, tone = 'Every time a Globule blew up, you had already grabbed one that round. Nice.', 'ok'
        else:
            verdict = (f"{c['sat_blown']} {'time' if c['sat_blown'] == 1 else 'times'} a Globule blew up in a round where you hadn't grabbed one.")
            tone = 'bad' if c['sat_blown'] / c['blown_sets'] >= 0.5 else ''
        if c['double']: verdict += f" You grabbed two in {c['double']} {'round' if c['double'] == 1 else 'rounds'}, covering for someone."
        mo = sorted(moments[nm], key=lambda r: (r['pull'], r['t']))[:8]
        out.append(dict(player=nm, title='Globules', tone=tone, verdict=verdict, stats=stats,
                        lead=f"Each Caustic Deluge drops {per_set} Globules on the floor. Someone has to grab each one within 10 seconds, or it blows up on the whole raid. "
                             f"With about 20 alive, {max(0, 20 - per_set)} people get each round off.",
                        moments_title='Watch the rounds where one blew up and you hadn\'t grabbed one (starts 8 s before it blew up)',
                        moments=[dict(pull=r['pull'], t=max(0, round(r['t'] - 8, 1)), label=f"{P[r['pull']]['label']} · {f2(r['t'])}") for r in mo],
                        tip=("If you had that round off on purpose, ignore these. If not, grab the closest Globule as soon as they land. "
                             "If it has a purple shield, wait for the stun or fear to break it, or it knocks you back.") if mo else None))
    return out


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

    # ------------------------------------------------------------ 2. Globules nobody took
    GP = globule_pulls(ctx['nights'], ctx['gmap'])
    if GP:
        cards += globule_card(ctx, H, GP, guide, cls)
    else:
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


def globule_card(ctx, H, GP, guide, cls):
    P, f2, N = ctx['P_by'], H['f2'], len(ctx['pulls'])
    role = {p['player']: p['role'] for p in ctx['players4']}
    per, moments, sets_up, blasts = globule_stats(ctx, GP)
    if not blasts and not sets_up: return []
    pulls_with = {b['pull'] for b in blasts}
    ended = [p for p in ctx['pulls'] if (ctx['bursts'].get(p['pull']) or {}).get('cause') == 'Caustic Globule']
    cg_deaths = sum(1 for d in ctx['deaths'] if d['cause'] == 'Caustic Globule')
    died3 = len({(b['pull'], d['t'], d['player']) for b in blasts for d in deaths_between(ctx, b['pull'], b['t'] - 0.2, b['t'] + 3)})
    blown_sets = [S for S in sets_up if S['blasts']]
    per_set = round(sum(S['n'] for S in sets_up) / max(1, len(sets_up)))
    labels = {'set1': '1st round of Globules (about 0:11)', 'set2': '2nd round (about 1:12)', 'set3': '3rd round (about 2:46)',
              'set4': '4th round', 'deaths': 'Extra ones dropped when people died'}
    rows = []
    for key in ['set1', 'set2', 'set3', 'set4', 'deaths']:
        bs = [b for b in blasts if b['kind'] == key]
        if not bs: continue
        big = max(bs, key=lambda b: b['died'])
        rows.append(dict(label=labels[key], desc=f"{len({b['pull'] for b in bs})} pulls · {sum(b['died'] for b in bs)} died within 3 s",
                         value=len(bs), max=len(blasts), num=f'{len(bs)} blew up', go=dict(pull=big['pull'], t=max(0, round(big['t'] - 8, 1)))))
    tag = lambda nm: f" ({role[nm].lower()})" if role.get(nm) in ('Tank', 'Healer') else ''
    sat = sorted((nm for nm in per if per[nm]['blown_sets'] >= 3), key=lambda nm: (-per[nm]['sat_blown'] / per[nm]['blown_sets'], -per[nm]['sat_blown']))
    sat_rows = [dict(label=nm + tag(nm), desc=f"grabbed {per[nm]['took']} Globules in {per[nm]['sets']} rounds",
                     value=per[nm]['sat_blown'], max=per[nm]['blown_sets'], num=f"{per[nm]['sat_blown']} of {per[nm]['blown_sets']} times")
                for nm in sat[:10]]
    rate = sorted((nm for nm in per if per[nm]['sets'] >= 10), key=lambda nm: per[nm]['rounds'] / per[nm]['sets'])
    most = sorted((nm for nm in per if per[nm]['sets'] >= 10), key=lambda nm: -per[nm]['took'] / per[nm]['sets'])
    pct_ = lambda nm: f"grabbed one in {round(100 * per[nm]['rounds'] / per[nm]['sets'])}% of rounds"
    tr = H['trend'](ctx, lambda p: p['pull'] in pulls_with, 'Pulls where a Globule blew up with the raid up')
    top = max(rows, key=lambda r: r['value']) if rows else None
    summary = (f"Every Caustic Deluge drops {per_set} Globules on the floor. Someone has to grab each one within 10 seconds, or it blows up, "
               f"hits the whole raid and gives everyone a stack. With about 20 of us alive, only {max(0, 20 - per_set)} people get a round off. "
               f"With the raid still up, {len(blasts)} Globules blew up in {len(pulls_with)} of {N} pulls, and {died3} people died within 3 seconds of one. "
               f"Globules killed {cg_deaths} people in all and ended {len(ended)} pulls."
               + (f" Most of them were in the {top['label'].split(' (')[0].replace('round of Globules', 'round').lower()}: {top['value']}." if top and top['label'][0].isdigit() else ''))
    worst, seen = [], set()
    for b in sorted(blasts, key=lambda b: -b['died']):
        if (b['pull'], b['kind']) in seen: continue
        seen.add((b['pull'], b['kind'])); worst.append(b)
    return [dict(
        key='globules', replaces=['cause-Caustic Globule', 'holder-Eternal Venom', 'holder-Caustic Globule'], cause='Caustic Globule',
        title="Globules nobody grabbed", big=str(len(blasts)), big_lbl=f'Globules blew up because nobody grabbed them ({len(pulls_with)} of {N} pulls)',
        summary=summary,
        main=[dict(type='rows', title='When they blew up', rows=rows),
              dict(type='rows', title="Hadn't grabbed one when a Globule blew up (out of the times it happened while they were alive)", rows=sat_rows),
              dict(type='note', text=f"The log shows exactly who grabbed every Globule. It doesn't know who was supposed to: with {per_set} Globules and about 20 people, "
                                     f"{max(0, 20 - per_set)} people get each round off. Check these names against your soak list before calling anyone out. "
                                     f"Everyone can see their own Globule numbers on the Your report tab. "
                                     f"In the replay, green circles are Globules on the floor (the ring around each one is the time left before it blows up), "
                                     f"purple ones still have a shield, a green ring on a player means they just grabbed one, and a red dashed ring marks "
                                     f"everyone who hadn't grabbed one when a Globule blew up.")],
        side=[tr, dict(type='who', label='Grab the fewest Globules',
                       items=[dict(player=nm, cls=cls.get(nm, ''), txt=pct_(nm)) for nm in rate[:6]]),
              dict(type='who', label='Grab the most (covering for others)',
                   items=[dict(player=nm, cls=cls.get(nm, ''), txt=f"{per[nm]['took']} in {per[nm]['sets']} rounds" + (f", 2 in {per[nm]['double']}" if per[nm]['double'] else '')) for nm in most[:4]])],
        fixes=guide.get('Caustic Globule', {}).get('fixes', []),
        examples=[dict(pull=b['pull'], t=max(0, round(b['t'] - 8, 1)), label=f"{P[b['pull']]['label']} · {f2(b['t'])} · {b['died']} died within 3 s") for b in worst[:4]],
        status=H['status'](tr), impact=len(ended) + 0.5)]
