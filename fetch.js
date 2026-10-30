/* raid-review-kit browser collector, v1.
 *
 * Paste this whole file into the browser's JavaScript tool:
 *   - in a https://www.warcraftlogs.com tab for report data (RR.reports, RR.report, RR.collect)
 *   - in a https://www.wipefest.gg tab for Wipefest data (RR.collectWipefest)
 * Long jobs run in the background: start one, poll RR.status(), then RR.dump('MARKER', i) for i < RR.parts() once it's done.
 * RR.dump pads its output so the result is saved to a file, which `rr.py extract MARKER out.json` stitches back together.
 * Uses Warcraft Logs' own site endpoints (no API key), so public reports work without signing in.
 */
(() => {
  const RR = (window.RR = window.RR || {});
  RR.version = 1;
  const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

  async function get(url, kind = 'json', tries = 5) {
    let last = null;
    for (let i = 0; i < tries; i++) {
      try {
        const cross = /^https?:/.test(url) && !url.includes(location.host);
        const r = await fetch(url, { credentials: cross ? 'omit' : 'include' });
        if (r.status === 429 || r.status >= 500) { last = new Error(`HTTP ${r.status}`); last.status = r.status; await sleep(2500 * (i + 1)); continue; }
        if (!r.ok) { const e = new Error(`HTTP ${r.status} ${url}`); e.status = r.status; throw e; }
        return kind === 'json' ? await r.json() : kind === 'buf' ? await r.arrayBuffer() : await r.text();
      } catch (e) { last = e; if (e.status && e.status < 500 && e.status !== 429) throw e; await sleep(1500 * (i + 1)); }
    }
    throw last || new Error('failed ' + url);
  }

  async function paged(mk, start, end) {
    const out = []; let s = start;
    for (let guard = 0; guard < 400; guard++) {
      const j = await get(mk(s, end));
      out.push(...(j.events || []));
      const nx = j.nextPageTimestamp;
      if (!nx || nx <= s || nx >= end) break;
      s = nx;
    }
    return out;
  }

  const job = (name, fn) => {
    RR.job = { name, status: 'running', done: 0, total: 0, log: [], result: null, error: null, started: Date.now() };
    fn(RR.job).then((res) => { RR.job.result = res; RR.job.status = 'done'; })
      .catch((e) => { RR.job.status = 'error'; RR.job.error = String(e && e.stack ? e.stack : e); });
    return `started ${name}`;
  };
  RR.status = () => {
    const j = RR.job; if (!j) return 'no job';
    return { name: j.name, status: j.status, done: j.done, total: j.total, seconds: Math.round((Date.now() - j.started) / 1000), log: j.log.slice(-6), error: j.error };
  };
  // RR.dump('MARKER', part): one slice of the finished job's JSON. Results over ~250K characters get cut off on the way
  // back from the browser, so big payloads come in parts: call RR.parts() for the count, then RR.dump('MARKER', i) for each i.
  RR.parts = (what, size = 180000) => Math.max(1, Math.ceil(JSON.stringify(what !== undefined ? what : RR.job && RR.job.result).length / size));
  RR.dump = (marker = 'RR', part = 0, what, size = 180000) => {
    const v = what !== undefined ? what : RR.job && RR.job.result;
    const s = JSON.stringify(v); const n = Math.max(1, Math.ceil(s.length / size));
    if (part >= n) return `only ${n} parts`;
    const out = `${marker}BEGIN[${part}/${n}]` + s.slice(part * size, (part + 1) * size) + `${marker}END`;
    return out + ' '.repeat(Math.max(0, 130000 - out.length));   // big enough that the tool saves it to a file
  };

  /* ---------------- Warcraft Logs: find reports ---------------- */
  // A guild's report list. `guild` is the numeric reports-list id (from warcraftlogs.com/guild/reports-list/<id>) or any guild page path.
  RR.reports = async (guild) => {
    let path = /^\d+$/.test(String(guild)) ? `/guild/reports-list/${guild}` : String(guild).replace(/^https?:\/\/[^/]+/, '');
    let h = await get(path, 'text');
    if (!/reports-list/.test(path)) {
      const m = h.match(/\/guild\/reports-list\/(\d+)/);
      if (m) { path = `/guild/reports-list/${m[1]}`; h = await get(path, 'text'); }
    }
    const d = new DOMParser().parseFromString(h, 'text/html');
    const rows = [];
    for (const tr of d.querySelectorAll('tr')) {
      const a = tr.querySelector('a[href*="/reports/"]'); if (!a) continue;
      const code = (a.getAttribute('href').match(/\/reports\/([A-Za-z0-9]+)/) || [])[1]; if (!code) continue;
      const txt = tr.innerText || tr.textContent || '';
      const st = (txt.match(/(\d{10,13})\$/) || [])[1];
      const ms = st ? Number(st.length === 10 ? st + '000' : st) : null;
      rows.push({ code, title: a.textContent.trim(), start: ms, date: ms ? new Date(ms).toLocaleString() : null });
    }
    return { list: path, reports: rows };
  };

  // What bosses are in a report: encounter id, name, difficulty, pulls, kills, best %.
  RR.report = async (code) => {
    const r = await get(`/reports/fights-and-participants/${code}/0`);
    const enc = {};
    for (const f of r.fights.filter((f) => f.boss)) {
      const k = f.boss + ':' + f.difficulty;
      const e = (enc[k] = enc[k] || { encounter: f.boss, name: f.name, difficulty: f.difficulty, zone: f.zoneName, pulls: 0, kills: 0, best: 100 });
      e.pulls++; if (f.kill) e.kills++; e.best = Math.min(e.best, f.kill ? 0 : (f.fightPercentage || 10000) / 100);
    }
    return { code, encounters: Object.values(enc).sort((a, b) => b.pulls - a.pulls) };
  };

  // Fight ids for one boss and difficulty (what RR.collectWipefest needs).
  RR.fightIds = async (code, encounter, difficulty) => {
    const r = await get(`/reports/fights-and-participants/${code}/0`);
    return r.fights.filter((f) => f.boss === encounter && f.difficulty === difficulty).map((f) => f.id);
  };

  /* ---------------- Warcraft Logs: collect one boss from one report ---------------- */
  // RR.collect(code, encounterId, difficulty, {replay: true, fights: [ids]}) -> background job. Difficulty: 3 Normal, 4 Heroic, 5 Mythic.
  RR.collect = (code, encounter, difficulty, opts = {}) => job(`collect ${code} ${encounter}/${difficulty}`, async (J) => {
    const rep = await get(`/reports/fights-and-participants/${code}/0`);
    const html = await get(`/reports/${code}`, 'text');
    const startMs = Number((html.match(/reportStartDate\s*=\s*new Date\((\d+)\)/) || [])[1] || 0);
    const title = ((html.match(/<title>([^<]*)/) || [])[1] || '').replace(/^.*Report:\s*/, '').replace(/\s*\|\s*Warcraft Logs.*$/, '');
    const guildPath = ((html.match(/\/guild\/(?:calendar|reports-list|id)\/(\d+)/) || [])[1]) || null;
    let fights = rep.fights.filter((f) => f.boss === encounter && f.difficulty === difficulty);
    if (opts.fights) fights = fights.filter((f) => opts.fights.includes(f.id));
    if (!fights.length) throw new Error('no fights for that encounter and difficulty');
    const inFight = (p, f) => String(p.fights || '').includes('.' + f.id + '.');
    const players = rep.friendlies.filter((p) => !['Pet', 'NPC'].includes(p.type) && fights.some((f) => inFight(p, f)));
    const pIdx = new Map(players.map((p, i) => [p.id, i]));
    const actorName = new Map([...rep.friendlies, ...rep.enemies, ...(rep.enemyPets || []), ...(rep.friendlyPets || [])].map((a) => [a.id, a.name]));
    const encEnemies = rep.enemies.filter((e) => String(e.bosses || '').includes('.' + encounter + '.'));
    const lc = (s) => String(s || '').toLowerCase();
    let boss = encEnemies.filter((e) => e.type === 'Boss');
    if (!boss.length) boss = encEnemies.filter((e) => lc(fights[0].name).includes(lc(e.name)) || lc(e.name).includes(lc(fights[0].name)));
    if (!boss.length) boss = encEnemies.slice(0, 1);
    const bossIds = new Set(boss.map((e) => e.id));
    const phaseNames = ((rep.phases || []).find((p) => p.boss === encounter) || {}).phases || [];
    const AB = [], abIdx = new Map();
    const ab = (n) => { n = n || ''; if (!abIdx.has(n)) { abIdx.set(n, AB.length); AB.push(n); } return abIdx.get(n); };
    const srcName = (e) => (e.source && e.source.name) || actorName.get(e.sourceID) || '';
    const tgtName = (e) => (e.target && e.target.name) || actorName.get(e.targetID) || '';
    const out = {
      kit: 1, source: 'warcraftlogs', code, title, start: startMs, guild_id: guildPath, encounter, difficulty, boss: fights[0].name, zone: fights[0].zoneName,
      phase_names: phaseNames, boss_units: boss.map((e) => e.name),
      players: players.map((p) => ({ name: p.name, cls: p.type, spec: String(p.icon || '').split('-').slice(1).join('-'), server: p.server || '', region: p.region || '', id: p.id })),
      abilities: AB, fights: [], replay: null,
    };
    J.total = fights.length * (opts.replay === false ? 1 : 2);
    for (const f of fights) {
      const a = f.start_time, b = f.end_time, T = (ts) => Math.round((ts - a) / 100) / 10;
      J.log.push(`fight ${f.id}: events`);
      const deaths = await paged((s, e) => `/reports/events/deaths/${code}/${f.id}/${s}/${e}/source/0/0/0/0/0/0/-1.0.-1.-1/0/Any/Any/2`, a, b);
      const casts = await paged((s, e) => `/reports/casts-events/${code}/${f.id}/${s}/${e}/0/0/Any/0/0/Any/0/1/-1.0.-1.-1/0/2`, a, b);
      const debuffs = await paged((s, e) => `/reports/auras-events/${code}/${f.id}/${s}/${e}/debuffs/0/0/0/0/0/source/0/-1.0.-1.-1/0/Any/Any/0`, a, b);
      const buffs = await paged((s, e) => `/reports/auras-events/${code}/${f.id}/${s}/${e}/buffs/0/0/0/0/0/source/1/-1.0.-1.-1/0/Any/Any/0`, a, b);
      let lasthits = null; try { lasthits = await lastHits(code, f); } catch (e) { J.log.push(`fight ${f.id}: no last hits`); }
      const AT = { applydebuff: 0, removedebuff: 1, applydebuffstack: 2, refreshdebuff: 3, removedebuffstack: 4 };
      out.fights.push({
        id: f.id, start: a, end: b, local_start: startMs ? new Date(startMs + a).toISOString() : null,
        clock: startMs ? new Date(startMs + a).toLocaleTimeString([], { hour: 'numeric', minute: '2-digit' }) : '',
        date: startMs ? new Date(startMs + a).toLocaleDateString([], { weekday: 'short', month: 'short', day: 'numeric' }) : '',
        kill: !!f.kill, pct: f.kill ? 0 : (f.fightPercentage != null ? f.fightPercentage / 100 : null), boss_pct: f.bossPercentage != null ? f.bossPercentage / 100 : null,
        last_phase: f.lastPhaseForPercentageDisplay || null, phases: (f.phases || []).map((p) => [p.id, T(p.startTime)]),
        players: players.filter((p) => inFight(p, f)).map((p) => pIdx.get(p.id)), lasthits,
        // [t, player, killing ability, killer]
        deaths: deaths.filter((e) => e.type === 'death' && pIdx.has(e.targetID))
          .map((e) => [T(e.timestamp), pIdx.get(e.targetID), ab(e.killingAbility ? e.killingAbility.name : ''), e.killerID != null ? actorName.get(e.killerID) || '' : '']),
        // [t, ability, source, target player or -1, 1 if begincast]
        casts: casts.filter((e) => !e.sourceIsFriendly && (e.type === 'cast' || e.type === 'begincast') && e.ability && e.ability.name !== 'Melee')
          .map((e) => [T(e.timestamp), ab(e.ability.name), srcName(e), pIdx.has(e.targetID) ? pIdx.get(e.targetID) : -1, e.type === 'begincast' ? 1 : 0]),
        // [t, ability, player, type (0 apply, 1 remove, 2 stack, 3 refresh, 4 stack down), stack]
        debuffs: debuffs.filter((e) => !e.sourceIsFriendly && pIdx.has(e.targetID) && e.type in AT)
          .map((e) => [T(e.timestamp), ab(e.ability.name), pIdx.get(e.targetID), AT[e.type], e.stack || 0]),
        // boss buffs: [t, ability, target name, 0 apply / 1 remove]
        buffs: buffs.filter((e) => !e.targetIsFriendly && (e.type === 'applybuff' || e.type === 'removebuff'))
          .map((e) => [T(e.timestamp), ab(e.ability.name), tgtName(e), e.type === 'applybuff' ? 0 : 1]),
      });
      J.done++;
    }
    if (opts.replay !== false) out.replay = await replay(code, encounter, fights, players, pIdx, bossIds, actorName, J);
    J.log.push('done');
    return out;
  });

  // Replay positions once a second per player (and the boss), from the replay segments Warcraft Logs' replay view uses.
  async function replay(code, encounter, fights, players, pIdx, bossIds, actorName, J) {
    const bossList = [...bossIds];
    const actors = [...players.map((p) => p.id), ...bossList];
    const aIdx = new Map(actors.map((id, i) => [id, i]));
    const R = { unit_cm: 25, center: null, markers: [], bounds: null, actors: [...players.map((p) => p.name), ...bossList.map((id) => actorName.get(id) || 'Boss')], boss_actors: bossList.length, pulls: {} };
    const step = 60000;
    for (const f of fights) {
      J.log.push(`fight ${f.id}: replay`);
      const n = Math.ceil((f.end_time - f.start_time) / 1000) + 1, N = actors.length;
      const xs = new Float64Array(n * N).fill(NaN), ys = new Float64Array(n * N).fill(NaN);
      const segs = [];
      for (let s = f.start_time; s < f.end_time; s += step) segs.push([s, Math.min(f.end_time, s + step)]);
      while (segs.length) {
        const [s, e] = segs.shift(); let j;
        try { j = await get(`/reports/replaysegment/${code}/${encounter}/${s}/${e}`); }
        catch (err) { if (e - s > 15000) { const m = Math.floor((s + e) / 2); segs.unshift([s, m], [m, e]); continue; } J.log.push(`replay gap ${s}-${e}`); continue; }
        if (!R.center && j.minX != null) {
          R.bounds = [j.minX, j.minY, j.maxX, j.maxY];
          R.center = [Math.round((j.minX + j.maxX) / 2), Math.round((j.minY + j.maxY) / 2)];
          R.markers = (j.worldMarkers || []).map((m) => [m.icon, m.x, m.y]);
        }
        for (const ev of j.events || []) {
          if (ev.x == null) continue;
          const id = ev.resourceActor === 2 ? ev.targetID : ev.sourceID;
          const ai = aIdx.get(id); if (ai == null) continue;
          const sec = Math.floor((ev.timestamp - f.start_time) / 1000); if (sec < 0 || sec >= n) continue;
          xs[sec * N + ai] = ev.x; ys[sec * N + ai] = ev.y;
        }
      }
      const C = R.center || [0, 0];
      const buf = new Int16Array(n * N * 2);
      for (let i = 0; i < n * N; i++) {
        if (Number.isNaN(xs[i])) { buf[2 * i] = -32768; buf[2 * i + 1] = -32768; continue; }
        buf[2 * i] = Math.max(-32767, Math.min(32767, Math.round((xs[i] - C[0]) / R.unit_cm)));
        buf[2 * i + 1] = Math.max(-32767, Math.min(32767, Math.round((ys[i] - C[1]) / R.unit_cm)));
      }
      const bytes = new Uint8Array(buf.buffer); let bin = '';
      for (let i = 0; i < bytes.length; i += 0x8000) bin += String.fromCharCode.apply(null, bytes.subarray(i, i + 0x8000));
      R.pulls[f.id] = { n, pos: btoa(bin) };
      J.done++;
    }
    return R;
  }

  // Per death: [player, killing blow shown by Warcraft Logs, last three hits (newest first)] from the Deaths view.
  // Deaths with no logged killing blow (knocked off a platform, fall damage) get their cause from these.
  async function lastHits(code, f) {
    const h = await get(`/reports/deaths/${code}/${f.id}/${f.start_time}/${f.end_time}/0/0/0/-1.0.-1.-1/0/Any/0/${f.start_time}`, 'text');
    const doc = new DOMParser().parseFromString(h, 'text/html');
    return [...doc.querySelectorAll('tr[onclick*="setFilterDeath"]')].map((tr) => {
      const td = tr.querySelectorAll('td');
      const name = td[1] ? td[1].textContent.trim() : '';
      const kb = td[2] ? td[2].textContent.trim() : '';
      const last = td[4] ? [...td[4].querySelectorAll('span[class^="school"]')].map((s) => s.textContent.trim().replace(/\s*\(x\d+\)$/, '')) : [];
      return [name, kb === '-' ? '' : kb, last];
    });
  }
  // Add last hits to every fight of an encounter (for payloads collected without them): RR.collectLastHits(code, encounter, difficulty)
  RR.collectLastHits = (code, encounter, difficulty) => job(`lasthits ${code} ${encounter}/${difficulty}`, async (J) => {
    const rep = await get(`/reports/fights-and-participants/${code}/0`);
    const fights = rep.fights.filter((f) => f.boss === encounter && f.difficulty === difficulty);
    J.total = fights.length; const out = { kit: 1, source: 'lasthits', code, encounter, difficulty, fights: {} };
    for (const f of fights) { out.fights[f.id] = await lastHits(code, f); J.done++; }
    return out;
  });

  /* ---------------- Wipefest (run in a wipefest.gg tab) ---------------- */
  // RR.collectWipefest(code, encounterId, [fightIds], {cutoff: 4}) -> background job. Uses each insight's "first N deaths" interval when it has one.
  RR.collectWipefest = (code, encounter, fightIds, opts = {}) => job(`wipefest ${code} ${encounter}`, async (J) => {
    const cutoff = opts.cutoff || 4;
    const out = { kit: 1, source: 'wipefest', code, encounter, cutoff, configs: {}, players: {}, fights: [], errors: [] };
    J.total = fightIds.length;
    for (const fid of fightIds) {
      J.log.push(`fight ${fid}`);
      let f;
      try { f = await get(`https://api.wipefest.gg/report/${code}/fight/${fid}?markupFormat=Markup&group=${encounter}&&insightsOnly=false`); }
      catch (e) { out.errors.push([fid, String(e)]); J.done++; continue; }
      for (const c of f.insightConfigs || []) {
        const k = c.group + ':' + c.id;
        if (!out.configs[k]) {
          const st = (c.statistics || []).find((s) => s.name === c.mainStatistic) || (c.statistics || [])[0] || {};
          out.configs[k] = { name: c.name, type: c.type, group: c.group === 'raid' ? 'raid' : 'boss', stat: c.mainStatistic || st.name || '', higher_is_better: !!st.higherIsBetter };
        }
      }
      for (const p of (f.raid && f.raid.players) || []) {
        out.players[p.actorId] = { name: p.name, cls: (p.specialization && p.specialization.className) || p.className, spec: (p.specialization && p.specialization.name) || '', role: (p.specialization && p.specialization.role) || '', ilvl: p.itemLevel };
      }
      const byKey = {};
      for (const i of f.insights || []) {
        const k = i.group + ':' + i.id; const iv = i.interval || {};
        const rank = iv.unit === 'Death' ? (iv.endUnit === cutoff ? 0 : 9) : iv.unit === 'WipeCalled' ? 1 : iv.unit === 'EntireFight' ? 2 : 9;
        if (rank < 9 && (!byKey[k] || rank < byKey[k].rank)) byKey[k] = { rank, i };
      }
      const rows = [];
      for (const [k, { i, rank }] of Object.entries(byKey)) {
        const cfg = out.configs[k] || {}; const pick = (arr) => (arr || []).find((s) => s.name === cfg.stat) || (arr || [])[0];
        const rs = pick(i.statistics);
        if (!rs) continue;
        rows.push([k, rank, rs.value, rs.percentile, rs.unscaledValue,
          (i.statisticsForPlayers || []).map((p) => { const s = pick(p.statistics); return s ? [p.playerId, s.unscaledValue, s.percentile] : null; }).filter(Boolean)]);
      }
      out.fights.push({ id: fid, percentile: f.percentile, insights: rows, player_values: (f.playerValues || []).map((p) => [p.playerId, p.totalValue, p.totalBonus]) });
      J.done++;
    }
    return out;
  });

  Object.assign(RR, { _get: get, _paged: paged, _job: job, _replay: replay, _lastHits: lastHits });
  return `raid-review-kit collector v${RR.version} ready on ${location.host}`;
})();
