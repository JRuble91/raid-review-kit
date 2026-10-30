"""Turn collector payloads (any boss) into the data a review page needs.

load_night(wcl, wf) normalizes one report + boss. page_data(nights, profile) builds the DATA object for one page
(one night, or every night merged).
"""
import base64, collections, json, math, os, re, statistics as st, struct

f2 = lambda s: f'{int(max(0, s) // 60)}:{int(max(0, s) % 60):02d}'
pct = lambda a, b: round(100 * a / b) if b else 0

TANK = {('Death Knight', 'Blood'), ('Demon Hunter', 'Vengeance'), ('Druid', 'Guardian'), ('Monk', 'Brewmaster'), ('Paladin', 'Protection'), ('Warrior', 'Protection')}
HEAL = {('Druid', 'Restoration'), ('Evoker', 'Preservation'), ('Monk', 'Mistweaver'), ('Paladin', 'Holy'), ('Priest', 'Discipline'), ('Priest', 'Holy'), ('Shaman', 'Restoration')}
MELEE_CLASS = {'Death Knight', 'Demon Hunter', 'Rogue', 'Warrior', 'Paladin', 'Monk'}
MELEE_SPEC = {('Druid', 'Feral'), ('Shaman', 'Enhancement'), ('Hunter', 'Survival')}
CLS_FIX = {'DeathKnight': 'Death Knight', 'DemonHunter': 'Demon Hunter'}
DIFF = {1: 'LFR', 3: 'Normal', 4: 'Heroic', 5: 'Mythic'}


def role_of(cls, spec):
    if (cls, spec) in TANK: return 'Tank'
    if (cls, spec) in HEAL: return 'Healer'
    if cls in MELEE_CLASS or (cls, spec) in MELEE_SPEC: return 'Melee'
    return 'Ranged'


def slug(s):
    return re.sub(r'[^a-z0-9]+', '-', str(s).lower()).strip('-')


# ---------------------------------------------------------------- one night
def load_night(wcl_path, wf_path=None):
    W = json.load(open(wcl_path))
    WF = json.load(open(wf_path)) if wf_path and os.path.exists(wf_path) else None
    A = W['abilities']
    names = [p['name'] for p in W['players']]
    wf_players = {}
    if WF:
        for aid, p in WF.get('players', {}).items():
            wf_players[int(aid)] = p
    roster = []
    for p in W['players']:
        w = wf_players.get(p['id'], {})
        cls = CLS_FIX.get(w.get('cls') or p['cls'], w.get('cls') or p['cls'])
        spec = w.get('spec') or p['spec']
        roster.append(dict(player=p['name'], cls=cls, spec=spec, role=w.get('role') or role_of(cls, spec), ilvl=w.get('ilvl'), wcl_id=p['id']))
    fights = sorted(W['fights'], key=lambda f: f['id'])
    pulls, deaths, casts, debuffs, buffs, phases = [], [], [], [], [], []
    no_kb_cause = last_hit_resolver(W, names)
    for i, f in enumerate(fights, 1):
        dur = round((f['end'] - f['start']) / 1000, 1)
        seq = [ph[0] for ph in f.get('phases', [])]
        pulls.append(dict(np=i, fight_id=f['id'], clock=f.get('clock', ''), date=f.get('date', ''), local_start=f.get('local_start'),
                          duration_s=dur, boss_pct=0.0 if f['kill'] else (f['pct'] if f['pct'] is not None else 100.0), kill=f['kill'],
                          phase_seq=seq, phase_times=[ph[1] for ph in f.get('phases', [])], roster=[names[k] for k in f['players']]))
        lh = collections.defaultdict(list)
        for r in f.get('lasthits') or []: lh[r[0]].append(r)
        for t, p, a, killer in sorted(f['deaths'], key=lambda r: r[0]):
            row = lh[names[p]].pop(0) if lh[names[p]] else None
            cause, nokb = A[a], 0
            if not cause:
                nokb = 1; cause = no_kb_cause(row[2] if row else [])
            deaths.append(dict(np=i, t=t, player=names[p], cause=cause, killer=killer, no_kb=nokb))
        # boss casts: keep 'cast' events for abilities that have them, else begincast
        has_cast = {a for t, a, s, tg, b in f['casts'] if b == 0}
        lastc = {}
        for t, a, s, tg, b in sorted(f['casts'], key=lambda r: r[0]):
            if s in ('', 'Environment') or s in names: continue
            if (b == 1) == (a in has_cast): continue
            if t - lastc.get(a, -99) < 2 and tg < 0: continue          # the same cast from several adds at once
            lastc[a] = t
            casts.append(dict(np=i, t=t, ability=A[a], source=s, target=names[tg] if tg >= 0 else ''))
        # debuff windows on players
        open_ = {}
        for t, a, p, ty, stk in sorted(f['debuffs'], key=lambda r: r[0]):
            k = (a, p)
            if ty in (0, 2, 3) and k not in open_:
                open_[k] = [t, max(stk, 1)]
            elif ty in (2, 3) and k in open_:
                open_[k][1] = max(open_[k][1], stk)
            elif ty == 1 and k in open_:
                s0, mx = open_.pop(k)
                debuffs.append(dict(np=i, player=names[p], ability=A[a], s=s0, e=t, stacks=mx))
        for (a, p), (s0, mx) in open_.items():
            debuffs.append(dict(np=i, player=names[p], ability=A[a], s=s0, e=dur, stacks=mx))
        last = {}
        for t, a, tg, ty in f['buffs']:
            if ty != 0: continue
            if t - last.get(a, -99) < 2: continue
            last[a] = t
            buffs.append(dict(np=i, t=t, ability=A[a], target=tg))
        for k, (pid, t) in enumerate(f.get('phases', [])):
            if k == 0: continue
            nm = W['phase_names'][pid - 1] if 0 < pid <= len(W['phase_names']) else f'Phase {pid}'
            phases.append(dict(np=i, t=t, phase=pid, name=nm))
    date = (fights[0].get('date') or '').strip()
    night = dict(code=W['code'], title=W.get('title', ''), start=W.get('start'), encounter=W['encounter'], difficulty=W['difficulty'],
                 boss=W['boss'], zone=W.get('zone', ''), boss_units=W.get('boss_units', []), phase_names=W.get('phase_names', []),
                 date=date, label=short_date(date), roster=roster, pulls=pulls, deaths=deaths, casts=casts, debuffs=debuffs, buffs=buffs, phases=phases,
                 replay=W.get('replay'), wf=normalize_wf(WF, {r['wcl_id']: r['player'] for r in roster}, len(pulls), [p['fight_id'] for p in pulls]) if WF else None)
    return night


def last_hit_resolver(W, names):
    """Pick a cause for deaths with no logged killing blow (knocked off the map, fall damage) from their last hits:
    the newest hit from a boss ability, skipping background damage that shows up in most deaths' last hits."""
    A = W['abilities']
    hostile = set()
    for f in W['fights']:
        hostile |= {A[a] for t, p, a, k in f['deaths'] if A[a]}
        hostile |= {A[r[1]] for r in f['casts']} | {A[r[1]] for r in f['debuffs']} | {A[r[1]] for r in f['buffs']}
    rows = [r for f in W['fights'] for r in (f.get('lasthits') or [])]
    seen = collections.Counter(n for r in rows for n in set(r[2]))
    ambient = {n for n, c in seen.items() if rows and c >= 0.35 * len(rows)}

    def pick(last):
        for test in (lambda n: n in hostile and n not in ambient, lambda n: n not in ambient, lambda n: n in hostile):
            for n in last:
                if test(n): return n
        return last[0] if last else 'No killing blow logged'
    return pick


def short_date(d):
    # 'Tue, Oct 6' -> 'Oct 6'
    m = re.search(r'([A-Z][a-z]{2})\s+(\d{1,2})', d or '')
    return f'{m.group(1)} {m.group(2)}' if m else (d or '')


def normalize_wf(WF, id2name, n_pulls, fight_ids):
    cfg = WF.get('configs', {})
    fid_np = {fid: i + 1 for i, fid in enumerate(fight_ids)}
    mech = {}
    pv = collections.defaultdict(list)
    for f in WF.get('fights', []):
        np_ = fid_np.get(f['id'])
        if np_ is None: continue
        for k, rank, value, perc, unscaled, players in f['insights']:
            c = cfg.get(k, {})
            if k == 'raid:3': continue                       # deaths: we have our own
            m = mech.setdefault(k, dict(key=k, name=c.get('name', k), group=c.get('group', 'boss'), stat=c.get('stat', ''), hib=c.get('higher_is_better', False),
                                        pulls=0, total=0.0, perc=[], per_player=collections.defaultdict(float), perc_player=collections.defaultdict(list)))
            m['pulls'] += 1; m['total'] += unscaled or 0
            if perc is not None: m['perc'].append(perc)
            for pid, u, pp in players:
                nm = id2name.get(pid)
                if not nm: continue
                m['per_player'][nm] += u or 0
                if pp is not None: m['perc_player'][nm].append(pp)
        for pid, tv, tb in f.get('player_values', []):
            nm = id2name.get(pid)
            if nm: pv[nm].append(tv)
    return dict(mech=mech, player_score={k: sum(v) / len(v) for k, v in pv.items()}, fights=len(WF.get('fights', [])), errors=WF.get('errors', []))


# ---------------------------------------------------------------- profile
def load_profile(encounter, kit_dir):
    p = os.path.join(kit_dir, 'bosses', f'{encounter}.json')
    prof = json.load(open(p)) if os.path.exists(p) else {}
    plug = os.path.join(kit_dir, 'bosses', f'{encounter}.py')
    prof['_plugin'] = plug if os.path.exists(plug) else None
    return prof


# ---------------------------------------------------------------- one page (one night or many)
def page_data(nights, profile, guild='', kit_dir='.'):
    nights = sorted(nights, key=lambda n: (n.get('start') or 0, n['code']))
    multi = len(nights) > 1
    labels = []
    for n in nights:
        lab = n['label'] or n['code']
        while lab in labels: lab += '*'
        labels.append(lab)
    # ---- merge pulls
    pulls, deaths, casts, debuffs, buffs, phases = [], [], [], [], [], []
    g = 0; gmap = {}
    for n, lab in zip(nights, labels):
        for p in n['pulls']:
            g += 1; gmap[(n['code'], p['np'])] = g
            pulls.append(dict(p, pull=g, night=lab, code=n['code'], label=f"{lab} pull {p['np']}" if multi else f"Pull {p['np']}"))
        for src, dst in ((n['deaths'], deaths), (n['casts'], casts), (n['debuffs'], debuffs), (n['buffs'], buffs), (n['phases'], phases)):
            for r in src: dst.append(dict(r, pull=gmap[(n['code'], r['np'])], night=lab))
    P_by = {p['pull']: p for p in pulls}
    D_by = collections.defaultdict(list)
    for d in sorted(deaths, key=lambda d: (d['pull'], d['t'])): D_by[d['pull']].append(d)
    N = len(pulls)
    boss = nights[-1]['boss']; diff = DIFF.get(nights[-1]['difficulty'], str(nights[-1]['difficulty']))
    # ---- roster
    roster = {}
    for n in nights:
        for r in n['roster']: roster[r['player']] = dict(r)        # latest night wins
    pulls_in = collections.Counter(nm for p in pulls for nm in p['roster'])
    score = collections.defaultdict(list)
    for n in nights:
        if n['wf']:
            for nm, v in n['wf']['player_score'].items(): score[nm].append((v, sum(1 for p in n['pulls'] if nm in p['roster'])))
    players4 = []
    for nm, r in roster.items():
        sc = score.get(nm)
        players4.append(dict(player=nm, role=r['role'], cls=r['cls'], spec=r['spec'], ilvl=r.get('ilvl'), pulls=pulls_in[nm],
                             score=round(sum(v * w for v, w in sc) / max(1, sum(w for v, w in sc))) if sc else None))
    players4.sort(key=lambda p: ({'Tank': 0, 'Healer': 1, 'Ranged': 2, 'Melee': 3}.get(p['role'], 4), p['player']))
    roster_size = int(st.median([len(p['roster']) for p in pulls])) if pulls else 20

    # ---- causes
    cause_alias = dict({'Melee': 'Boss melee'}, **profile.get('cause_alias', {}))
    canon = lambda c: cause_alias.get(c, c)
    cc = collections.Counter(canon(d['cause']) for d in deaths)
    causes = [c for c, _ in cc.most_common() if c != 'No killing blow logged'][:8]

    # ---- stages (phases reached)
    stage_names = stage_labels(pulls, nights[-1]['phase_names'], profile)
    for p in pulls:
        p['stage'] = max(0, len(p['phase_seq']) - 1)
        p['phase_reached'] = 'Kill' if p['kill'] else stage_names[min(p['stage'], len(stage_names) - 1)]

    # ---- major boss abilities (for the timeline, feed and jumps)
    tot_s = sum(p['duration_s'] for p in pulls) or 1
    by_ab = collections.defaultdict(list)
    for c in casts: by_ab[c['ability']].append(c)
    assoc = collections.Counter()
    for c in casts:
        for d in D_by[c['pull']]:
            if c['t'] <= d['t'] <= c['t'] + 8 and canon(d['cause']) == c['ability']: assoc[c['ability']] += 1
    major = []
    for ab, rows in by_ab.items():
        rate = len(rows) / tot_s
        cover = len({r['pull'] for r in rows}) / N
        if rate <= 1 / 8 and cover >= 0.4: major.append(ab)
    major.sort(key=lambda a: (-assoc[a], -len(by_ab[a])))
    major = profile.get('events', {}).get('major', major)[:12]
    # debuffs worth drawing in the replay: profile, else auto
    rings = profile.get('rings') or auto_rings(debuffs, deaths, canon, N)
    enrage_names = set(profile.get('enrage', [])) or {b['ability'] for b in buffs if re.search(r'enrage|berserk', b['ability'], re.I)} | \
        {c['ability'] for c in casts if re.search(r'enrage|berserk', c['ability'], re.I)}

    # ---- boss events (feed, strip, jumps, wipe map bands)
    events = []
    ring_names = {r['ability'] for r in rings}
    for c in casts:
        if c['ability'] in ring_names and c['ability'] not in enrage_names: continue
        if c['ability'] in major or c['ability'] in enrage_names:
            events.append(dict(pull=c['pull'], t=c['t'], event=c['ability'], kind='cast', player=c['target'], enrage=c['ability'] in enrage_names))
    for b in buffs:
        if b['ability'] in enrage_names:
            events.append(dict(pull=b['pull'], t=b['t'], event=b['ability'], kind='buff', player='', enrage=True))
    ring_names = {r['ability'] for r in rings}
    grp = {}
    for d in sorted(debuffs, key=lambda d: (d['pull'], d['s'])):
        if d['ability'] not in ring_names: continue
        k = (d['pull'], d['ability']); last = grp.get(k)
        if last and d['s'] - last['t'] < 1.5:
            last['n'] += 1; continue
        e = dict(pull=d['pull'], t=d['s'], event=d['ability'], kind='debuff', player=d['player'], n=1, enrage=False)
        grp[k] = e; events.append(e)
    for ph in phases:
        events.append(dict(pull=ph['pull'], t=ph['t'], event=ph['name'], kind='phase', player='', enrage=False))
    for e in events:
        if e.get('n', 1) > 1: e['player'] = f"{e['player']} +{e['n'] - 1}"
        e.pop('n', None)
    events.sort(key=lambda e: (e['pull'], e['t']))
    E_by = collections.defaultdict(list)
    for e in events: E_by[e['pull']].append(e)

    # ---- checkpoint: alive at time T decides the pull
    cp = profile.get('checkpoint') or {}
    fourth = [D_by[p['pull']][3]['t'] for p in pulls if len(D_by[p['pull']]) >= 4]
    cp_t = cp.get('t') or (max(30, min(180, round(st.median(fourth) / 15) * 15)) if fourth else 60)
    cp_alive = cp.get('alive') or max(1, roster_size - 3)

    # ---- timeline bands
    timeline = timeline_bands(pulls, casts, phases, major[:6], causes, canon)

    # ---- wipe bursts and walls
    bursts = {}
    for p in pulls:
        ds = D_by[p['pull']]; best = None
        for x in ds:
            w = [y for y in ds if x['t'] <= y['t'] < x['t'] + 6]
            if best is None or len(w) > len(best[1]): best = (x['t'], w)
        en = next((e['t'] for e in E_by[p['pull']] if e['enrage']), None)
        if en is not None and (not best or en <= best[0] + 6):
            bursts[p['pull']] = dict(t=en, kind='enrage', cause='Enrage', deaths=[y for y in ds if en <= y['t'] <= en + 5])
        elif best and len(best[1]) >= 3:
            c = collections.Counter(canon(y['cause']) for y in best[1]).most_common(1)[0][0]
            bursts[p['pull']] = dict(t=best[0], kind='cause', cause=c, deaths=best[1])
    walls = make_walls(bursts, E_by, P_by, profile, canon, major)

    # ---- replay
    replay, arena = build_replay(nights, gmap, rings, profile)

    # ---- Wipefest mechanics
    mechanics4, mechanic_players4 = wipefest_tables(nights, labels, players4)

    meta = dict(guild=guild, boss=boss, difficulty=diff, zone=nights[-1]['zone'], nights=labels, codes=[n['code'] for n in nights],
                titles=[n['title'] for n in nights], multi=multi, n_pulls=N, roster_size=roster_size, kills=sum(1 for p in pulls if p['kill']),
                checkpoint=dict(t=cp_t, alive=cp_alive), stages=stage_names, causes=causes, cause_alias=cause_alias,
                stage_tile=profile.get('stage_tile'), has_wipefest=bool(mechanics4), rings=rings, major=major,
                encounter=nights[-1]['encounter'])
    data = dict(
        meta=meta,
        wcl_pulls=[dict(pull=p['pull'], fight_id=p['fight_id'], start_time=p['clock'], duration_s=p['duration_s'], boss_pct=p['boss_pct'], kill=p['kill'],
                        phase_reached=p['phase_reached'], stage=p['stage'], players=len(p['roster']), night=p['night'], np=p['np'], label=p['label'], code=p['code'],
                        replay_url=f"https://www.warcraftlogs.com/reports/{p['code']}?fight={p['fight_id']}&type=summary&view=replay") for p in pulls],
        wcl_deaths=[dict(pull=d['pull'], t=d['t'], player=d['player'], cause=canon(d['cause']), one_shot=0, no_kb=d.get('no_kb', 0)) for d in sorted(deaths, key=lambda d: (d['pull'], d['t']))],
        boss_events=events, fight_timeline=timeline, players4=players4, mechanics4=mechanics4, mechanic_players4=mechanic_players4,
        replay=replay, arena=arena, walls_def=walls,
        mechanic_guide=guide_cards(causes, profile, deaths, D_by, pulls, canon),
    )
    ctx = dict(pulls=pulls, deaths=deaths, casts=casts, debuffs=debuffs, buffs=buffs, phases=phases, events=events, D_by=D_by, E_by=E_by, P_by=P_by,
               bursts=bursts, walls=walls, meta=meta, labels=labels, nights=nights, gmap=gmap, canon=canon, players4=players4, profile=profile,
               mechanics4=mechanics4, mechanic_players4=mechanic_players4, replay_raw={n['code']: n['replay'] for n in nights}, roster_size=roster_size)
    from . import issues as ISS
    data['issues'] = ISS.build(ctx)
    return data


def stage_labels(pulls, phase_names, profile):
    if profile.get('stages'): return profile['stages']
    longest = max((p['phase_seq'] for p in pulls), key=len, default=[])
    nm = lambda pid: phase_names[pid - 1] if 0 < pid <= len(phase_names) else f'Phase {pid}'
    if len(longest) <= 1:
        return ['Wipe']
    out = [f'Wiped in {nm(longest[0])}']
    seen = collections.Counter([longest[0]])
    for pid in longest[1:]:
        seen[pid] += 1
        out.append(f'Reached {nm(pid)}' + (f' ({seen[pid]}{"nd" if seen[pid] == 2 else "rd" if seen[pid] == 3 else "th"} time)' if seen[pid] > 1 else ''))
    return out


def auto_rings(debuffs, deaths, canon, N):
    """Debuffs worth showing on the replay: the ones whose holders die most, plus single-target marks."""
    by = collections.defaultdict(list)
    for d in debuffs: by[d['ability']].append(d)
    dpull = collections.defaultdict(list)
    for d in deaths: dpull[(d['pull'], d['player'])].append(d['t'])
    scored = []
    for ab, ws in by.items():
        if len({w['pull'] for w in ws}) < max(2, N * 0.3): continue
        held_deaths = sum(1 for w in ws for t in dpull.get((w['pull'], w['player']), []) if w['s'] <= t <= w['e'] + 0.5)
        per_pull_apps = len(ws) / N
        mean_len = st.mean(w['e'] - w['s'] for w in ws)
        conc = collections.Counter((w['pull'], round(w['s'])) for w in ws)
        single = max(conc.values()) == 1 and mean_len >= 5 and per_pull_apps <= 12
        scored.append((ab, held_deaths, single, per_pull_apps, mean_len))
    rings = []
    for ab, hd, single, ppa, ml in sorted(scored, key=lambda r: -r[1]):
        if single and not any(r['style'] == 'dash' for r in rings):
            rings.append(dict(ability=ab, style='dash'))
        elif not single and hd >= 3 and ppa <= 60 and sum(1 for r in rings if r['style'] == 'ring') < 2:
            rings.append(dict(ability=ab, style='ring'))
    return rings[:3]


def timeline_bands(pulls, casts, phases, major, causes, canon):
    if not pulls: return []
    by = collections.defaultdict(lambda: collections.defaultdict(list))
    for c in sorted(casts, key=lambda c: (c['pull'], c['t'])):
        if c['ability'] not in major: continue
        by[c['ability']][c['pull']].append(c['t'])
    out = []
    dur = {p['pull']: p['duration_s'] for p in pulls}
    for lane, ab in enumerate(major):
        seqs = by.get(ab, {})
        k = 0
        while True:
            ts = [s[k] for s in seqs.values() if len(s) > k]
            if not ts: break
            med = st.median(ts)
            alive = sum(1 for d in dur.values() if d >= med)
            if alive < 2 or len(ts) < 0.4 * alive: break
            label = ab if max(len(s) for s in seqs.values()) == 1 else f'{ab} {k + 1}'
            keys = [ab] if ab in causes else []
            out.append(dict(start_s=round(med - 0.5, 1), end_s=round(med + 2, 1), label=label, keys='|'.join(keys), lane=lane, ability=ab))
            k += 1
            if k > 60: break
    # phase bands
    byk = collections.defaultdict(list)
    for p in pulls:
        for k, t in enumerate(p['phase_times'][1:], 1): byk[k].append((t, p['phase_seq'][k]))
    seen = collections.Counter()
    for k in sorted(byk):
        rows = byk[k]
        if len(rows) < max(2, 0.2 * len(pulls)): continue
        t0 = st.median(r[0] for r in rows)
        nxt = byk.get(k + 1)
        t1 = st.median(r[0] for r in nxt) if nxt and len(nxt) >= 2 else t0 + 20
        pid = collections.Counter(r[1] for r in rows).most_common(1)[0][0]
        seen[pid] += 1
        out.append(dict(start_s=round(t0, 1), end_s=round(t1, 1), label=next((ph['name'] for ph in phases if ph['phase'] == pid), f'Phase {pid}'),
                        keys='', lane=len(major), ability='phase', phase=True))
    return out


def make_walls(bursts, E_by, P_by, profile, canon, major):
    if profile.get('walls'):
        return profile['walls']
    groups = collections.defaultdict(list)
    for pn, b in bursts.items(): groups[b['cause']].append((b['t'], pn))
    clusters = []
    for cause, rows in groups.items():
        rows.sort(); cur = [rows[0]]
        for r in rows[1:]:
            if r[0] - cur[-1][0] > 25: clusters.append((cause, cur)); cur = [r]
            else: cur.append(r)
        clusters.append((cause, cur))
    clusters = [c for c in clusters if len(c[1]) >= 2] or clusters
    clusters.sort(key=lambda c: -len(c[1]))
    walls = []
    guide = profile.get('guide', {})
    for cause, rows in clusters[:4]:
        ts = sorted(t for t, _ in rows)
        lo = max(0, ts[max(0, int(len(ts) * 0.1))] - 6); hi = ts[min(len(ts) - 1, int(len(ts) * 0.9))] + 6
        before = collections.Counter()
        for t, pn in rows:
            seen = {e['event'] for e in E_by[pn] if t - 12 <= e['t'] <= t + 0.5 and not e['enrage'] and e['kind'] != 'phase' or (e['kind'] == 'phase' and t - 12 <= e['t'] <= t + 0.5)}
            for ev in seen: before[ev] += 1
        ev, n = before.most_common(1)[0] if before else (None, 0)
        after = ev if ev and n >= max(2, 0.5 * len(rows)) and ev != cause else None
        key = slug(cause) + '-' + str(int(lo))
        if cause == 'Enrage':
            walls.append(dict(key=key, kind='enrage', cause='', causes=[], lo=lo, hi=hi, title=profile.get('enrage_title', 'The boss enraged'),
                              when=f'{f2(lo)} to {f2(hi)}' + (f', after {after}' if after else ''),
                              todo=guide.get('Enrage', {}).get('todo') or 'Watch the pulls below to see why the enrage mechanic was missed.'))
        else:
            g = guide.get(cause, {})
            walls.append(dict(key=key, kind='cause', cause=cause, causes=[cause], lo=lo, hi=hi,
                              title=f'{cause} after {after}' if after else f'{cause} wipes the raid',
                              when=f'{f2(lo)} to {f2(hi)}', todo=g.get('todo') or f'Watch the worst pulls below and find who {cause} hit first, and what they were doing.'))
    seen = collections.Counter(w['title'] for w in walls)
    for w in walls:
        if seen[w['title']] > 1: w['title'] += f" ({w['when'].split(',')[0]})"
    return walls


def guide_cards(causes, profile, deaths, D_by, pulls, canon):
    guide = profile.get('guide', {})
    out = []
    first = collections.Counter(canon(D_by[p['pull']][0]['cause']) for p in pulls if D_by[p['pull']])
    for c in causes:
        g = guide.get(c, {})
        ds = [d for d in deaths if canon(d['cause']) == c]
        med = st.median(d['t'] for d in ds) if ds else 0
        what = g.get('what') or (f"{len(ds)} deaths, most around {f2(med)}" + (f", and the first death of {first[c]} pulls." if first[c] else '.'))
        out.append(dict(key=c, name=g.get('name', c), group=g.get('group', 'Boss ability'), who=g.get('who', 'Everyone'), what=what,
                        todo=g.get('todo', ''), clip=g.get('clip', ''), clip2=g.get('clip2', '')))
    return out


def build_replay(nights, gmap, rings, profile):
    """Re-center every night's positions on the fight, turn them if the profile says so, and pack as int8 per second."""
    rot = math.radians(profile.get('arena', {}).get('rotate', 0))
    cr, sr = math.cos(rot), math.sin(rot)
    rows, allpts, markers = [], [], collections.Counter()
    decoded = []
    for n in nights:
        R = n.get('replay')
        if not R or not R.get('pulls'): continue
        u = R['unit_cm'] / 100.0
        nb = R.get('boss_actors', 0); NA = len(R['actors'])
        players = R['actors'][:NA - nb]
        # centre: median position of everyone over the whole night
        xs, ys = [], []
        dec = {}
        for fid, pr in R['pulls'].items():
            raw = base64.b64decode(pr['pos'])
            vals = struct.unpack('<%dh' % (len(raw) // 2), raw)
            dec[int(fid)] = (pr['n'], vals)
            for i in range(0, len(vals), 2 * 7):
                if vals[i] != -32768: xs.append(vals[i] * u); ys.append(vals[i + 1] * u)
        cx = st.median(xs) if xs else 0; cy = st.median(ys) if ys else 0
        decoded.append((n, R, u, NA, players, dec, cx, cy))
        for ic, mx, my in R.get('markers', []):
            X, Y = (mx - R['center'][0]) / 100.0 - cx, (my - R['center'][1]) / 100.0 - cy
            markers[(n['code'], ic, round(X * cr - Y * sr, 1), round(X * sr + Y * cr, 1))] += 1
    # view size from the spread of positions
    dist = []
    for n, R, u, NA, players, dec, cx, cy in decoded:
        for fid, (secs, vals) in dec.items():
            for i in range(0, len(vals), 2 * 3):
                if vals[i] != -32768:
                    dist.append(max(abs(vals[i] * u - cx), abs(vals[i + 1] * u - cy)))
    dist.sort()
    view = profile.get('arena', {}).get('view') or max(20.0, (dist[int(len(dist) * 0.985)] if dist else 50) * 1.08)
    unit = math.ceil(view / 120 * 4) / 4
    edge = dist[int(len(dist) * 0.97)] if dist else 40
    rot_to = profile.get('arena', {}).get('rotate_to')
    for n, R, u, NA, players, dec, cx, cy in decoded:
        if rot_to:
            # turn so where the first holder of this debuff stood when it ended points up
            angs = []
            for p in n['pulls']:
                ws = sorted([d for d in n['debuffs'] if d['np'] == p['np'] and d['ability'] == rot_to and d['s'] < 45], key=lambda d: d['s'])
                if not ws or p['fight_id'] not in dec: continue
                secs, vals = dec[p['fight_id']]; a = R['actors'].index(ws[0]['player']) if ws[0]['player'] in R['actors'] else -1
                sec = min(secs - 1, int(ws[0]['e']))
                if a < 0: continue
                i = (sec * NA + a) * 2
                if vals[i] == -32768: continue
                angs.append(math.atan2(vals[i + 1] * u - cy, vals[i] * u - cx))
            if angs:
                ang = math.atan2(sum(math.sin(x) for x in angs), sum(math.cos(x) for x in angs))
                rot_n = math.pi / 2 - ang; cr, sr = math.cos(rot_n), math.sin(rot_n)
        for fid, (secs, vals) in dec.items():
            pull = gmap.get((n['code'], next((p['np'] for p in n['pulls'] if p['fight_id'] == fid), None)))
            if pull is None: continue
            buf = bytearray()
            for s_ in range(secs):
                for a in range(NA):
                    i = (s_ * NA + a) * 2
                    vx, vy = vals[i], vals[i + 1]
                    if vx == -32768: buf += bytes([128, 128]); continue
                    X, Y = vx * u - cx, vy * u - cy
                    X, Y = X * cr - Y * sr, X * sr + Y * cr
                    buf += bytes([max(-127, min(127, round(X / unit))) & 255, max(-127, min(127, round(Y / unit))) & 255])
            np_ = next(p['np'] for p in n['pulls'] if p['fight_id'] == fid)
            rg = []
            for ri, r in enumerate(rings):
                for d in n['debuffs']:
                    if d['np'] == np_ and d['ability'] == r['ability']: rg.append([d['player'], ri, d['s'], d['e']])
            rows.append(dict(pull=pull, seconds=secs, actors='|'.join(R['actors']), boss_actors=R.get('boss_actors', 0), unit=unit,
                             pos=base64.b64encode(bytes(buf)).decode(), rings=json.dumps(rg, ensure_ascii=False)))
    rows.sort(key=lambda r: r['pull'])
    MN = {1: 'Star', 2: 'Circle', 3: 'Diamond', 4: 'Triangle', 5: 'Moon', 6: 'Square', 7: 'Cross', 8: 'Skull'}
    arena_cfg = profile.get('arena', {})
    arena = [dict(kind='edge', name='Edge', icon=0, x=0, y=0, r=arena_cfg.get('r', round(edge, 1)), shape=arena_cfg.get('shape', 'circle'), view=round(arena_cfg.get('view', view), 1))]
    for (code, ic, x, y), c in markers.items():
        if ic in MN and abs(x) <= view and abs(y) <= view:
            arena.append(dict(kind='marker', name=MN[ic], icon=ic, x=x, y=y, r=0, code=code))
    return rows, arena


def wipefest_tables(nights, labels, players4):
    keys = {}
    for n in nights:
        if not n['wf']: continue
        for k, m in n['wf']['mech'].items(): keys.setdefault(k, m)
    if not keys: return [], []
    pulls_in = {p['player']: p['pulls'] for p in players4}
    mechanics4, mp = [], []
    for k, m0 in keys.items():
        tot, n_p, percs, by_night = 0.0, 0, [], []
        per_player = collections.defaultdict(float)
        for n in nights:
            m = n['wf']['mech'].get(k) if n['wf'] else None
            if not m: by_night.append(None); continue
            tot += m['total']; n_p += m['pulls']; percs += m['perc']
            by_night.append(round(st.mean(m['perc'])) if m['perc'] else None)
            for nm, v in m['per_player'].items(): per_player[nm] += v
        label = f"{m0['name']} (healing done)" if m0['stat'] == 'Healing' else 'Potions used' if m0['name'] == 'Potions' else m0['name']
        summable = not (m0['stat'].startswith('Average') or m0['stat'] in ('Score', ''))
        mechanics4.append(dict(mechanic=k, label=label, group=m0['group'], stat=m0['stat'], higher_is_better=m0['hib'], score=round(st.mean(percs)) if percs else None,
                               count=round(tot) if summable else None, per_pull=round(tot / n_p, 2) if n_p and summable else None, pulls=n_p, by_night=by_night))
        if not summable: continue
        for nm, v in per_player.items():
            if pulls_in.get(nm):
                mp.append(dict(mechanic=k, player=nm, count=round(10 * v / pulls_in[nm], 1)))
    mechanics4.sort(key=lambda r: (r['group'] != 'raid', r['score'] if r['score'] is not None else 101))
    return mechanics4, mp
