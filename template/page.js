/* raid-review-kit page script: everything boss-specific comes from DATA (meta, walls_def, mechanic_guide, issues). */
const f2 = (s) => { s = Math.max(0, Math.floor(s)); return Math.floor(s / 60) + ':' + String(s % 60).padStart(2, '0'); };
const M = () => { const m = dash.data('meta'); return m.status === 'ok' ? m.data : { causes: [], stages: ['Wipe'], checkpoint: { t: 60, alive: 17 }, rings: [], major: [], nights: [], codes: [] }; };

/* ---------------- calcs ---------------- */
dash.calc('ranked', {
  inputs: ['wcl_deaths', 'wcl_pulls'],
  fn: (wcl_deaths, wcl_pulls) => {
    const rows = wcl_deaths.map((d, i) => ({ ...d, id: i }));
    const by = new Map(); for (const d of rows) { if (!by.has(d.pull)) by.set(d.pull, []); by.get(d.pull).push(d); }
    const out = [];
    for (const p of wcl_pulls.map((x) => x.pull)) {
      (by.get(p) || []).sort((a, b) => a.t - b.t || a.id - b.id)
        .forEach((d, k) => out.push({ id: d.id, pull: p, rank: k + 1, t: d.t, t_txt: f2(d.t), player: d.player, cause: d.cause, note: d.no_kb ? 'no killing blow logged; named from the last hit' : '' }));
    }
    return out;
  },
});

dash.calc('cutoff_causes', {
  inputs: ['ranked'],
  fn: (ranked) => {
    const out = [];
    for (const cutoff of [3, 4, 5, 99]) {
      const d = ranked.filter((r) => r.rank <= cutoff); const m = new Map();
      for (const r of d) { const x = m.get(r.cause) || { cutoff, cause: r.cause, deaths: 0, opened: 0 }; x.deaths += 1; if (r.rank === 1) x.opened += 1; m.set(r.cause, x); }
      for (const x of m.values()) out.push({ ...x, total: d.length, share_txt: Math.round((100 * x.deaths) / d.length) + '%' });
    }
    return out.sort((a, b) => a.cutoff - b.cutoff || b.deaths - a.deaths);
  },
});

dash.calc('pull_view', {
  inputs: ['ranked', 'wcl_pulls'],
  fn: (ranked, wcl_pulls) => {
    const cp = M().checkpoint;
    const by = new Map(); for (const r of ranked) { if (!by.has(r.pull)) by.set(r.pull, []); by.get(r.pull).push(r); }
    return wcl_pulls.map((p) => {
      const d = by.get(p.pull) || []; const fourth = d.find((r) => r.rank === 4); const f4 = fourth ? fourth.t : p.duration_s;
      return { pull: p.pull, label: p.label, night: p.night, np: p.np, code: p.code, start_time: p.start_time, boss_pct: p.boss_pct, kill: p.kill,
        boss_txt: p.kill ? 'Kill' : p.boss_pct.toFixed(1) + '%', duration_s: p.duration_s, length_txt: f2(p.duration_s), phase_reached: p.phase_reached, stage: p.stage,
        players: p.players, fourth_s: f4, fourth_txt: f2(f4), deaths: d.length, alive_cp: p.players - d.filter((r) => r.t < cp.t).length, replay_url: p.replay_url };
    });
  },
});

dash.calc('headline', {
  inputs: ['pull_view'],
  fn: (pv) => {
    const cp = M().checkpoint;
    const mean = (a) => a.reduce((s, v) => s + v, 0) / a.length;
    const best = pv.reduce((a, p) => (p.boss_pct < a.boss_pct ? p : a));
    const hi = pv.filter((p) => p.alive_cp >= cp.alive && p.duration_s >= cp.t), lo = pv.filter((p) => !hi.includes(p));
    const x = pv.map((p) => p.fourth_s), y = pv.map((p) => p.boss_pct), mx = mean(x), my = mean(y);
    const den = Math.sqrt(x.reduce((s, v) => s + (v - mx) ** 2, 0) * y.reduce((s, v) => s + (v - my) ** 2, 0));
    const r = den ? x.reduce((s, v, i) => s + (v - mx) * (y[i] - my), 0) / den : 0;
    return [{
      best_pct_txt: best.kill ? 'Kill' : best.boss_pct.toFixed(1) + '%', best_pull: best.pull, best_label: best.label, best_kill: best.kill,
      first_pct_txt: pv[0].kill ? 'a kill' : pv[0].boss_pct.toFixed(1) + '%', n_pulls: pv.length, kills: pv.filter((p) => p.kill).length,
      n_hi: hi.length, n_lo: lo.length, hi_avg_txt: hi.length ? mean(hi.map((p) => p.boss_pct)).toFixed(1) + '%' : '—', lo_avg_txt: lo.length ? mean(lo.map((p) => p.boss_pct)).toFixed(1) + '%' : '—',
      avg4_txt: f2(mean(x)), corr_txt: r.toFixed(2), reached: pv.filter((p) => p.stage >= 1 || p.kill).length, past: pv.filter((p) => p.stage >= 2 || p.kill).length,
      longest: pv.reduce((a, p) => (p.duration_s > a.duration_s ? p : a)),
    }];
  },
});

dash.calc('wall_pulls', {
  inputs: ['wcl_deaths', 'boss_events', 'wcl_pulls', 'walls_def'],
  fn: (wcl_deaths, boss_events, wcl_pulls, walls_def) => {
    const out = [];
    const dby = new Map(); for (const d of wcl_deaths) { if (!dby.has(d.pull)) dby.set(d.pull, []); dby.get(d.pull).push(d); }
    for (const p of wcl_pulls) {
      const d = (dby.get(p.pull) || []).slice().sort((a, b) => a.t - b.t);
      for (const w of walls_def) {
        let ds = [];
        if (w.kind === 'enrage') {
          const en = boss_events.find((x) => x.pull === p.pull && x.enrage);
          if (!en) continue;
          ds = d.filter((x) => x.t >= en.t && x.t <= en.t + 5);
          out.push({ key: w.key + '|' + p.pull, wall: w.key, pull: p.pull, t: en.t, t_txt: f2(en.t), deaths: ds.length, ended: p.duration_s - en.t <= 20 });
          continue;
        }
        ds = d.filter((x) => w.causes.includes(x.cause) && x.t >= w.lo && x.t <= w.hi);
        if (ds.length) out.push({ key: w.key + '|' + p.pull, wall: w.key, pull: p.pull, t: ds[0].t, t_txt: f2(ds[0].t), deaths: ds.length, ended: p.duration_s - ds[0].t <= 20 });
      }
    }
    return out;
  },
});

dash.calc('walls', {
  inputs: ['wall_pulls', 'walls_def'],
  fn: (wall_pulls, walls_def) => walls_def.map((w) => {
    const r = wall_pulls.filter((x) => x.wall === w.key);
    const hit = w.kind === 'enrage' ? r : r.filter((x) => x.deaths > 0);
    const worst = hit.reduce((a, x) => (!a || x.deaths > a.deaths ? x : a), null);
    return { wall: w.key, deaths: r.reduce((s, x) => s + x.deaths, 0), n_pulls: hit.length, n_ended: hit.filter((x) => x.ended).length, worst_pull: worst ? worst.pull : '', worst_deaths: worst ? worst.deaths : 0 };
  }),
});

dash.calc('player_cut', {
  inputs: ['ranked', 'players4'],
  fn: (ranked, players4) => {
    const out = [];
    for (const cutoff of [3, 4, 5, 99]) {
      const rows = players4.map((p) => {
        const d = ranked.filter((r) => r.player === p.player && r.rank <= cutoff);
        return { player: p.player, cutoff, deaths: d.length, opened: d.filter((r) => r.rank === 1).length, avg_txt: d.length ? f2(d.reduce((s, r) => s + r.t, 0) / d.length) : '—' };
      });
      for (const r of rows) out.push({ ...r, key: r.player + '|' + cutoff, rank_txt: '#' + (1 + rows.filter((o) => o.deaths > r.deaths).length) });
    }
    return out;
  },
});

dash.calc('player_causes', {
  inputs: ['ranked'],
  fn: (ranked) => {
    const m = new Map();
    for (const cutoff of [3, 4, 5, 99]) for (const r of ranked.filter((x) => x.rank <= cutoff)) {
      const k = r.player + '|' + cutoff + '|' + r.cause; const x = m.get(k) || { key: k, player: r.player, cutoff, cause: r.cause, deaths: 0 }; x.deaths += 1; m.set(k, x);
    }
    return [...m.values()].sort((a, b) => b.deaths - a.deaths);
  },
});

dash.calc('player_metrics', {
  inputs: ['players4', 'mechanic_players4', 'mechanics4'],
  fn: (players4, mp, mechanics4) => {
    const med = (a) => { const s = [...a].sort((x, y) => x - y); const n = s.length; return n % 2 ? s[(n - 1) / 2] : (s[n / 2 - 1] + s[n / 2]) / 2; };
    const ids = new Set(mp.map((r) => r.mechanic));
    const out = [];
    for (const m of mechanics4.filter((x) => ids.has(x.mechanic))) {
      const dir = m.higher_is_better ? 'down' : 'up';
      const val = (p) => (mp.find((x) => x.mechanic === m.mechanic && x.player === p) || { count: 0 }).count;
      const regulars = players4.filter((p) => p.pulls >= 3);
      const all = regulars.map((p) => val(p.player)); if (!all.length) continue;
      const md = med(all), worst = dir === 'up' ? Math.max(...all) : Math.min(...all);
      for (const p of players4) { const v = val(p.player); out.push({ key: p.player + '|' + m.mechanic, metric_id: m.mechanic, player: p.player, metric: m.label, dir, you: v, raid_median: +md.toFixed(1), worst, worse: dir === 'up' ? v > md : v < md, better: dir === 'up' ? v < md : v > md }); }
    }
    return out;
  },
});

/* ---------------- state ---------------- */
const causeKey = (c) => (M().cause_alias || {})[c] || c;
const causeColor = (c) => { const i = (M().causes || []).indexOf(causeKey(c)); return i >= 0 ? dash.colors[i] : 'var(--cds-chart-muted)'; };
const stageColor = (stage, kill) => (kill ? 'var(--color-ok)' : stage >= 2 ? dash.colors[0] : stage === 1 ? dash.colors[1] : 'var(--cds-chart-muted)');
const CLASS_COLOR = { 'Death Knight': '#C41E3A', 'Demon Hunter': '#A330C9', Druid: '#FF7C0A', Evoker: '#33937F', Hunter: '#AAD372', Mage: '#3FC7EB', Monk: '#00FF98', Paladin: '#F48CBA', Priest: '#F2F2F2', Rogue: '#FFF468', Shaman: '#0070DD', Warlock: '#8788EE', Warrior: '#C69B6D' };
const MARKER = { 1: ['star', '#F2C230'], 2: ['circle', '#F08A24'], 3: ['diamond', '#B05BE0'], 4: ['triangle', '#3CC46A'], 5: ['moon', '#B9C6D3'], 6: ['square', '#3A8FE0'], 7: ['cross', '#E5484D'], 8: ['skull', '#E9EDF0'] };
const ui = { tab: 'issues', focus: null };
const P = () => { const p = dash.params(); return { cutoff: Number(p.cutoff) || 4, player: p.player || '', pull: Number(p.pull) || 1 }; };

/* ---------------- helpers ---------------- */
const $ = (id) => document.getElementById(id);
const el = (tag, cls, text) => { const e = document.createElement(tag); if (cls) e.className = cls; if (text != null) e.textContent = text; return e; };
const fail = (box) => { box.replaceChildren(); box.appendChild(el('div', 'fail', 'Failed to load')); };
const ready = (box, ids) => {
  const st = ids.map((i) => dash.data(i));
  if (st.some((s) => s.status === 'error')) { box.classList.remove('dash-skeleton'); fail(box); return null; }
  if (st.some((s) => s.status !== 'ok')) { box.replaceChildren(); box.classList.add('dash-skeleton'); return null; }
  box.classList.remove('dash-skeleton'); return st.map((s) => s.data);
};
const tipFor = (box) => { let t = box.querySelector(':scope > .tip'); if (!t) { t = el('div', 'tip'); box.appendChild(t); } return t; };
const showTip = (tip, box, ev, head, lines) => {
  tip.replaceChildren(el('div', 'h', head));
  for (const [c, txt] of lines) { const l = el('div'); l.style.display = 'flex'; l.style.alignItems = 'center'; l.style.gap = '6px'; if (c) { const s = el('span', 'sw'); s.style.background = c; l.appendChild(s); } l.appendChild(document.createTextNode(txt)); tip.appendChild(l); }
  tip.style.display = 'block';
  const r = box.getBoundingClientRect(); let x = ev.clientX - r.left + 14; let y = ev.clientY - r.top + 14;
  if (x + tip.offsetWidth > box.clientWidth) x = Math.max(0, ev.clientX - r.left - tip.offsetWidth - 14);
  if (y + tip.offsetHeight > box.clientHeight + 40) y = Math.max(0, ev.clientY - r.top - tip.offsetHeight - 10);
  tip.style.left = x + 'px'; tip.style.top = y + 'px';
};
const hideTip = (tip) => { tip.style.display = 'none'; };
const axisStyle = (g, keepDomain) => { g.attr('font-size', null).attr('font-family', null); if (keepDomain) g.select('.domain').attr('stroke', 'var(--cds-chart-axis)'); else g.select('.domain').remove(); g.selectAll('text').attr('fill', 'var(--color-fg-muted)').style('font-size', 'var(--cds-font-size-caption)'); };
const mark = (node, source, field, where) => { node.dataset.source = source; node.dataset.field = field; if (where) node.dataset.where = where; else delete node.dataset.where; };
const enc = encodeURIComponent;
const pl = (n, w) => (n === 1 ? w : w + 's');
const PL = (n) => { const w = dash.data('wcl_pulls'); const p = w.status === 'ok' ? w.data.find((x) => x.pull === n) : null; return p && p.label ? p.label : 'Pull ' + n; };
const pullCount = () => { const w = dash.data('wcl_pulls'); return w.status === 'ok' ? w.data.length : 1; };
const bestPull = () => { const pv = dash.data('pull_view'); return pv.status === 'ok' ? pv.data.reduce((a, p) => (p.boss_pct < a.boss_pct ? p : a)).pull : P().pull; };
const firstKey = (b) => String(b.keys || '').split('|')[0];
const hasKey = (b, k) => String(b.keys || '').split('|').includes(k);
const cpTxt = () => { const c = M().checkpoint; return `${c.alive}+ alive at ${f2(c.t)}`; };

function bands(svg, x, top, bottom, timeline, opts = {}) {
  const g = svg.append('g');
  for (const b of timeline) {
    const x0 = x(b.start_s), x1 = Math.max(x(b.end_s), x0 + 3);
    g.append('rect').attr('x', x0 - 1).attr('width', x1 - x0 + 2).attr('y', top).attr('height', bottom - top)
      .attr('fill', b.phase ? 'var(--cds-chart-muted)' : firstKey(b) ? causeColor(firstKey(b)) : 'var(--cds-chart-muted)')
      .attr('opacity', ui.focus && !hasKey(b, ui.focus) ? 0.03 : b.phase ? 0.08 : opts.opacity || 0.1);
  }
  return g;
}

/* ---------------- tabs + controls ---------------- */
function setTab(t) { if (t !== 'replay') rpPause(); ui.tab = t; dash.setLink(t); render(); }
document.querySelectorAll('.tabs button').forEach((b) => b.addEventListener('click', () => setTab(b.dataset.tab)));
document.querySelectorAll('#cut-seg button').forEach((b) => b.addEventListener('click', () => dash.setParams({ cutoff: Number(b.dataset.cut) })));
const named = location.hash.slice(1); if (['issues', 'overview', 'fight', 'report', 'replay'].includes(named)) ui.tab = named;
function openReplay(pull, t) { RP.seek = Math.max(0, t || 0); if (pull === RP.pull) RP.pull = -1; dash.setParams({ pull }); setTab('replay'); setTimeout(() => { const c = $('replay-card'); if (c) c.scrollIntoView({ behavior: 'smooth', block: 'start' }); }, 60); }
function openCause(c) { ui.focus = causeKey(c); setTab('fight'); setTimeout(() => { const g = document.querySelector(`.gcard[data-key="${CSS.escape(c)}"]`); if (g) g.scrollIntoView({ behavior: 'smooth', block: 'center' }); }, 60); }

/* ---------------- header ---------------- */
function drawHeader() {
  const m = M();
  const who = [m.guild, `${m.boss} ${m.difficulty}`].filter(Boolean).join(' · ');
  $('h1').textContent = who || 'Raid review';
  const nights = m.nights || [];
  $('sub').textContent = (m.multi ? `Every pull from ${nights.length} nights, ${nights[0]} to ${nights[nights.length - 1]}` : `${nights[0] || ''}`) + ` · ${m.n_pulls} ${pl(m.n_pulls, 'pull')} · from Warcraft Logs (including its replay)` + (m.has_wipefest ? ' and Wipefest' : '');
  $('sources').textContent = `Sources: Warcraft Logs ${pl((m.codes || []).length, 'report')} ${(m.codes || []).map((c, i) => `${c}${m.multi ? ` (${nights[i]})` : ''}`).join(', ')}: boss health, phases, deaths, boss casts, debuffs on players, and positions from the replay.` +
    (m.has_wipefest ? ' Wipefest analysis with a 4-death cutoff: mechanic ranks and per-player counts.' : '') + ' Built with raid-review-kit.';
  document.title = `${who} · ${m.multi ? 'every pull' : nights[0] || 'review'}`;
}

function drawLead() {
  const lead = $('lead'); const h = dash.data('headline');
  if (h.status !== 'ok') { lead.replaceChildren(el('span', 'dash-skeleton', '—')); return; }
  const r = h.data[0]; const m = M(); lead.replaceChildren();
  if (r.kills) lead.append(`${r.kills} ${pl(r.kills, 'kill')} in ${r.n_pulls} pulls (first: ${r.best_label}). `);
  else lead.append(`${m.multi ? `Across all ${r.n_pulls} pulls, our` : 'Our'} best pull got ${m.boss} to ${r.best_pct_txt} (${r.best_label}). `);
  if (r.n_hi && r.n_lo) lead.append(`With ${m.checkpoint.alive} or more of us alive at ${f2(m.checkpoint.t)}, the boss ended at ${r.hi_avg_txt} on average, vs ${r.lo_avg_txt} with fewer. `);
  const go = el('button', 'ilink', 'Biggest problems'); go.addEventListener('click', () => { setTab('issues'); $('top').scrollIntoView({ behavior: 'smooth' }); });
  lead.append('The ', go, ' tab ranks what keeps ending our pulls. The other tabs have every pull, with replays.');
}

/* ---------------- overview ---------------- */
function drawTiles() {
  const h = dash.data('headline'); if (h.status !== 'ok') return; const r = h.data[0]; const m = M();
  const set = (id, lbl, big, ctx) => { if (lbl != null) $(id + '-lbl').textContent = lbl; const b = $(id + '-big'); b.textContent = big; b.classList.remove('dash-skeleton'); $(id + '-ctx').textContent = ctx; };
  set('t1', r.best_kill ? 'First kill' : 'Best pull', r.best_kill ? 'Kill' : r.best_pct_txt, r.best_kill ? `${r.best_label}.` : `Boss health left on ${r.best_label}. The first pull ended at ${r.first_pct_txt}.`);
  set('t2', cpTxt(), r.hi_avg_txt, `avg boss health on those ${r.n_hi} ${pl(r.n_hi, 'pull')}, vs ${r.lo_avg_txt} on the rest`);
  if (r.kills) set('t3', 'Kills', String(r.kills), `of ${r.n_pulls} pulls`);
  else if ((m.stages || []).length > 1) set('t3', m.stage_tile || m.stages[1], String(r.reached), `of ${r.n_pulls} pulls got there` + (m.stages.length > 2 ? `, and ${r.past} got further.` : '.'));
  else set('t3', 'Longest pull', r.longest.length_txt, `${r.longest.label}, ended at ${r.longest.boss_txt}`);
  $('fourth-note').textContent = `Each dot is a pull: when the 4th person died vs where the boss ended (correlation ${r.corr_txt}; the closer to -1, the more the 4th death decides the pull). On average it came at ${r.avg4_txt}. Colored dots had ${cpTxt()}.`;
}

function drawTopKiller() {
  const cc = dash.data('cutoff_causes'); const cut = P().cutoff;
  const top = cc.status === 'ok' ? cc.data.find((r) => r.cutoff === cut) : null;
  const where = top ? `cutoff=${cut}&cause=${enc(top.cause)}` : `cutoff=${cut}`;
  mark($('tile-share'), 'cutoff_causes', 'share_txt', where); mark($('tile-cause'), 'cutoff_causes', 'cause', where);
  mark($('tile-share-n'), 'cutoff_causes', 'deaths', where); mark($('tile-total'), 'cutoff_causes', 'total', where);
}

function drawWalls() {
  const box = $('walls'); const got = ready(box, ['walls', 'wall_pulls', 'walls_def']); if (!got) return;
  const [walls, wp, defs] = got; box.replaceChildren();
  $('walls-wrap').hidden = !defs.length;
  for (const w of walls) {
    const def = defs.find((d) => d.key === w.wall); if (!def) continue;
    const enrage = def.kind === 'enrage';
    const c = el('div', 'card wall');
    const head = el('div', 'win'); const sw = el('span', 'sw'); sw.style.background = enrage ? 'var(--color-bad)' : causeColor(def.cause); head.append(sw, def.when);
    const big = el('div', 'v', `${enrage ? w.n_pulls : w.deaths} ${pl(enrage ? w.n_pulls : w.deaths, enrage ? 'pull' : 'death')}`);
    const p = el('p');
    if (!w.n_pulls) p.append('None in these pulls.');
    else if (enrage) p.append(`${w.n_pulls} ${pl(w.n_pulls, 'pull')} hit it, and ${w.deaths} ${w.deaths === 1 ? 'person' : 'people'} died in the 5 seconds after.`);
    else p.append(`${w.deaths} ${def.cause} ${pl(w.deaths, 'death')} in ${w.n_pulls} ${pl(w.n_pulls, 'pull')} (${w.worst_deaths} in ${PL(w.worst_pull)}). ${w.n_ended} of those wiped within 20 seconds.`);
    const d = el('p', 'do'); if (def.todo) d.append(el('b', null, 'Do: '), def.todo);
    const chips = el('div', 'chips');
    for (const r of wp.filter((x) => x.wall === w.wall && x.deaths > 0).sort((a, b) => b.deaths - a.deaths || a.pull - b.pull).slice(0, 6)) {
      const b = el('button', 'chip-btn'); const tt = el('span', 't', r.t_txt);
      b.append('▶ ', PL(r.pull), ' · ', tt, ` · ${r.deaths} died`); b.setAttribute('aria-label', `Watch ${PL(r.pull)} at ${r.t_txt}`);
      b.addEventListener('click', () => openReplay(r.pull, r.t - 4)); chips.appendChild(b);
    }
    c.append(head, el('h3', null, def.title), big, p, d, chips);
    box.appendChild(c);
  }
}

function drawBoss() {
  const box = $('boss-chart'); const got = ready(box, ['pull_view']); const m = M();
  const st = m.stages || ['Wipe'];
  const keys = [[st.length > 1 ? st[0] : 'Wipe', stageColor(0)]];
  if (st.length > 1) keys.push([st[1], stageColor(1)]);
  if (st.length > 2) keys.push([st.length > 3 ? 'Got further' : st[2], stageColor(2)]);
  if (m.kills) keys.push(['Kill', stageColor(0, true)]);
  $('boss-legend').replaceChildren(...keys.map(([n, c]) => { const s = el('span', 'pill'); s.style.display = 'inline-flex'; s.style.alignItems = 'center'; s.style.gap = '6px'; const w = el('span', 'sw'); w.style.background = c; s.append(w, n); return s; }));
  if (!got) return; const [rows] = got; box.replaceChildren();
  const W = box.clientWidth || 600, H = 300, mg = { t: 24, r: 14, b: 28, l: 44 };
  const svg = d3.select(box).append('svg').attr('width', '100%').attr('viewBox', `0 0 ${W} ${H}`).attr('height', H);
  const x = d3.scalePoint(rows.map((r) => r.pull), [mg.l + 8, W - mg.r - 8]);
  const ext = d3.extent(rows, (r) => r.boss_pct);
  const y = d3.scaleLinear([Math.floor(ext[0] / 5) * 5, Math.max(5, Math.ceil(ext[1] / 5) * 5)], [H - mg.b, mg.t]);
  svg.append('g').selectAll('line').data(y.ticks(5)).join('line').attr('x1', mg.l).attr('x2', W - mg.r).attr('y1', y).attr('y2', y).attr('stroke', 'var(--cds-chart-grid)');
  axisStyle(svg.append('g').attr('transform', `translate(${mg.l},0)`).call(d3.axisLeft(y).ticks(5).tickSize(0).tickFormat((d) => d + '%')));
  if (m.multi) {
    const starts = rows.filter((q) => q.np === 1);
    const roomy = (r) => { const nx = starts.find((q) => q.pull > r.pull); return (nx ? x(nx.pull) : W - mg.r) - x(r.pull) >= 40; };
    const xa = svg.append('g').attr('transform', `translate(0,${H - mg.b})`).call(d3.axisBottom(x).tickSize(0).tickFormat((d) => { const r = starts.find((q) => q.pull === d); return r && roomy(r) ? r.night : ''; }));
    axisStyle(xa, true); xa.selectAll('text').attr('dy', '1em').attr('text-anchor', 'start');
    for (const r of starts.filter((q) => q.pull > 1)) svg.append('line').attr('x1', x(r.pull) - x.step() / 2).attr('x2', x(r.pull) - x.step() / 2).attr('y1', mg.t).attr('y2', H - mg.b).attr('stroke', 'var(--cds-chart-axis)').attr('stroke-dasharray', '2 3');
  } else {
    const every = W / rows.length >= 18 ? 1 : W / rows.length >= 7 ? 5 : 10;
    const xa = svg.append('g').attr('transform', `translate(0,${H - mg.b})`).call(d3.axisBottom(x).tickSize(0).tickFormat((d) => { const r = rows.find((q) => q.pull === d); return r.np === 1 || r.np % every === 0 ? r.np : ''; }));
    axisStyle(xa, true); xa.selectAll('text').attr('dy', '1em');
  }
  svg.append('path').datum(rows).attr('fill', 'none').attr('stroke', 'var(--cds-chart-muted)').attr('stroke-width', 1.5).attr('d', d3.line().x((d) => x(d.pull)).y((d) => y(d.boss_pct)));
  let rb = Infinity; const bl = rows.map((r) => ({ pull: r.pull, v: (rb = Math.min(rb, r.boss_pct)) }));
  svg.append('path').datum(bl).attr('fill', 'none').attr('stroke', 'var(--color-fg)').attr('stroke-width', 1.5).attr('stroke-dasharray', '5 4').attr('d', d3.line().curve(d3.curveStepAfter).x((d) => x(d.pull)).y((d) => y(d.v)));
  const r0 = Math.max(3.5, Math.min(6.5, (W - mg.l - mg.r) / rows.length / 3));
  const cur = P().pull;
  svg.append('g').selectAll('circle').data(rows).join('circle').attr('cx', (d) => x(d.pull)).attr('cy', (d) => y(d.boss_pct)).attr('r', (d) => (d.pull === cur ? r0 + 2 : r0))
    .attr('fill', (d) => stageColor(d.stage, d.kill)).attr('stroke', (d) => (d.pull === cur ? 'var(--color-fg)' : 'var(--color-panel)')).attr('stroke-width', 1.5);
  const best = rows.reduce((a, p) => (p.boss_pct < a.boss_pct ? p : a));
  const lbl = svg.append('text').attr('y', y(best.boss_pct) - 8).attr('fill', 'var(--color-fg)').style('font-size', 'var(--cds-font-size-caption)').text(`${best.label} · ${best.boss_txt}`);
  const lw = lbl.node().getComputedTextLength(); lbl.attr('x', Math.max(mg.l, Math.min(W - mg.r - lw, x(best.pull) - lw / 2)));
  const tip = tipFor(box); const step = (W - mg.l - mg.r) / rows.length;
  svg.append('g').selectAll('rect').data(rows).join('rect').attr('x', (d) => x(d.pull) - step / 2).attr('width', step).attr('y', mg.t).attr('height', H - mg.b - mg.t).attr('fill', 'transparent').style('cursor', 'pointer')
    .on('mousemove', (ev, d) => showTip(tip, box, ev, `${d.label} · ${d.start_time}`, [[stageColor(d.stage, d.kill), `Boss ${d.boss_txt}`], [null, `Length ${d.length_txt}`], [null, `${d.alive_cp} alive at ${f2(M().checkpoint.t)}`], [null, `4th death at ${d.fourth_txt}`], [null, 'Click to watch']]))
    .on('mouseleave', () => hideTip(tip)).on('click', (ev, d) => openReplay(d.pull, 0));
}

function drawKillers() {
  const box = $('killers'); const got = ready(box, ['cutoff_causes']); if (!got) return;
  const cut = P().cutoff; const rows = got[0].filter((r) => r.cutoff === cut).slice(0, 9);
  box.replaceChildren(); const max = d3.max(rows, (r) => r.deaths) || 1;
  for (const r of rows) {
    const row = el('div', 'hrow'); row.setAttribute('role', 'button'); row.tabIndex = 0;
    const n = el('div'); n.style.display = 'flex'; n.style.alignItems = 'center'; n.style.gap = '6px'; const sw = el('span', 'sw'); sw.style.background = causeColor(r.cause); n.append(sw, r.cause);
    const tr = el('div', 'track');
    const a = el('div', 'fill'); a.style.width = (100 * r.deaths) / max + '%'; a.style.background = `color-mix(in srgb, ${causeColor(r.cause)} 40%, transparent)`;
    const b = el('div', 'fill'); b.style.width = (100 * r.opened) / max + '%'; b.style.background = causeColor(r.cause);
    tr.append(a, b);
    const v = el('div', 'num', String(r.deaths) + (r.opened ? ` · ${r.opened} first` : ''));
    row.append(n, tr, v); row.addEventListener('click', () => openCause(r.cause)); row.addEventListener('keydown', (e) => { if (e.key === 'Enter') openCause(r.cause); });
    box.appendChild(row);
  }
}

function drawFourth() {
  const box = $('fourth-chart'); const got = ready(box, ['pull_view']); if (!got) return;
  const [rows] = got; box.replaceChildren(); const cp = M().checkpoint;
  const W = box.clientWidth || 500, H = 260, mg = { t: 10, r: 14, b: 34, l: 44 };
  const svg = d3.select(box).append('svg').attr('width', '100%').attr('viewBox', `0 0 ${W} ${H}`).attr('height', H);
  const x = d3.scaleLinear([0, Math.ceil(d3.max(rows, (r) => r.fourth_s) / 30) * 30 || 30], [mg.l, W - mg.r]);
  const ext = d3.extent(rows, (r) => r.boss_pct);
  const y = d3.scaleLinear([Math.floor(ext[0] / 5) * 5, Math.max(5, Math.ceil(ext[1] / 5) * 5)], [H - mg.b, mg.t]);
  svg.append('g').selectAll('line').data(y.ticks(4)).join('line').attr('x1', mg.l).attr('x2', W - mg.r).attr('y1', y).attr('y2', y).attr('stroke', 'var(--cds-chart-grid)');
  axisStyle(svg.append('g').attr('transform', `translate(${mg.l},0)`).call(d3.axisLeft(y).ticks(4).tickSize(0).tickFormat((d) => d + '%')));
  const stepT = x.domain()[1] > 300 ? 60 : 30;
  const xa = svg.append('g').attr('transform', `translate(0,${H - mg.b})`).call(d3.axisBottom(x).tickValues(d3.range(0, x.domain()[1] + 1, stepT)).tickSize(0).tickFormat(f2));
  axisStyle(xa, true); xa.selectAll('text').attr('dy', '1em');
  svg.append('text').attr('x', W - mg.r).attr('y', H - 2).attr('text-anchor', 'end').attr('fill', 'var(--color-fg-muted)').style('font-size', 'var(--cds-font-size-caption)').text('When the 4th person died');
  const tip = tipFor(box); const hi = (d) => d.alive_cp >= cp.alive && d.duration_s >= cp.t;
  svg.append('g').selectAll('circle').data(rows).join('circle').attr('cx', (d) => x(d.fourth_s)).attr('cy', (d) => y(d.boss_pct)).attr('r', rows.length > 60 ? 4 : 5.5)
    .attr('fill', (d) => (hi(d) ? dash.colors[0] : 'var(--cds-chart-muted)')).attr('stroke', 'var(--color-panel)').attr('stroke-width', 1.5).style('cursor', 'pointer')
    .on('mousemove', (ev, d) => showTip(tip, box, ev, d.label, [[null, `4th death at ${d.fourth_txt}`], [null, `Boss ended at ${d.boss_txt}`], [hi(d) ? dash.colors[0] : null, `${d.alive_cp} alive at ${f2(cp.t)}`]]))
    .on('mouseleave', () => hideTip(tip)).on('click', (ev, d) => openReplay(d.pull, d.fourth_s - 4));
}

function drawHabits() {
  const tb = $('habits-tbody'); const st = dash.data('mechanics4'); tb.replaceChildren(); const m = M();
  $('habits-card').hidden = !(st.status === 'ok' && st.data.length);
  $('habits-night-th').hidden = !m.multi;
  if (st.status !== 'ok') return;
  for (const r of st.data) {
    const tr = el('tr'); const sc = Number(r.score);
    const fmt = r.count == null ? '—' : r.count >= 100000 ? d3.format('.3~s')(r.count) : d3.format(',')(r.count);
    tr.append(el('td', null, r.label), el('td', 'r', fmt), el('td', 'r' + (r.score == null ? '' : sc < 40 ? ' bad' : sc >= 75 ? ' good' : ''), r.score == null ? '—' : String(r.score)));
    if (m.multi) tr.append(el('td', 'r', (r.by_night || []).map((v) => (v == null ? '—' : v)).join(' · ')));
    tb.appendChild(tr);
  }
}

/* ---------------- the fight ---------------- */
function drawMapLegend() {
  const box = $('map-legend'); box.replaceChildren();
  const all = el('button', 'chip-btn', 'All mechanics'); all.setAttribute('aria-pressed', String(!ui.focus)); all.addEventListener('click', () => { ui.focus = null; render(); }); box.appendChild(all);
  for (const c of M().causes || []) {
    const b = el('button', 'chip-btn'); const sw = el('span', 'sw'); sw.style.background = causeColor(c); b.append(sw, c);
    b.setAttribute('aria-pressed', String(ui.focus === c)); if (ui.focus && ui.focus !== c) b.classList.add('dim');
    b.addEventListener('click', () => { ui.focus = ui.focus === c ? null : c; render(); }); box.appendChild(b);
  }
}

function fillPlayerSelect(sel, none) {
  const p = dash.data('players4'); if (p.status !== 'ok') return;
  if (sel.options.length !== p.data.length + 1) {
    sel.replaceChildren(new Option(none, ''), ...p.data.map((r) => new Option(r.player, r.player)));
    sel.onchange = () => dash.setParams({ player: sel.value || null });
  }
  sel.value = P().player;
}

function drawMap() {
  const box = $('map-chart'); const got = ready(box, ['ranked', 'fight_timeline', 'pull_view']); if (!got) return;
  const [ranked, timeline, pulls] = got; const { cutoff, player } = P(); box.replaceChildren(); const m = M();
  const n = pulls.length; const small = m.multi || n > 45;
  const W = box.clientWidth || 700, rowH = small ? (W < 500 ? 8 : 11) : (W < 500 ? 15 : 19), mg = { t: 48, r: 48, b: 26, l: m.multi ? 56 : 30 }, H = mg.t + rowH * n + mg.b;
  const svg = d3.select(box).append('svg').attr('width', '100%').attr('viewBox', `0 0 ${W} ${H}`).attr('height', H);
  const maxT = d3.max(pulls, (p) => p.duration_s);
  const x = d3.scaleLinear([0, maxT], [mg.l, W - mg.r]);
  const y = (p) => mg.t + (p - 0.5) * rowH;
  bands(svg, x, mg.t - 4, H - mg.b, timeline, { opacity: 0.12 });
  const lab = svg.append('g'); const ends = [-Infinity, -Infinity, -Infinity];
  for (const b of timeline.slice().sort((p, q) => p.start_s - q.start_s)) {
    if (ui.focus && !hasKey(b, ui.focus)) continue;
    const t = lab.append('text').attr('x', x(b.start_s)).attr('fill', 'var(--color-fg-muted)').style('font-size', 'var(--cds-font-size-caption)').text(b.label);
    const tw = t.node().getComputedTextLength(); const x0 = Math.min(x(b.start_s), W - 4 - tw);
    const lane = ends.findIndex((e) => x0 >= e + 8); if (lane < 0) { t.remove(); continue; }
    t.attr('x', x0).attr('y', 12 + lane * 13); ends[lane] = x0 + tw;
  }
  const xa = svg.append('g').attr('transform', `translate(0,${H - mg.b})`).call(d3.axisBottom(x).tickValues(d3.range(0, maxT + 1, maxT > 360 ? 60 : W < 500 ? 30 : 15)).tickSize(0).tickFormat(f2));
  axisStyle(xa, true); xa.selectAll('text').attr('dy', '1em');
  const rows = svg.append('g');
  const nightBest = {}; for (const p of pulls) nightBest[p.night] = Math.min(nightBest[p.night] ?? 999, p.boss_pct);
  pulls.forEach((p, i) => {
    rows.append('line').attr('x1', x(0)).attr('x2', x(p.duration_s)).attr('y1', y(p.pull)).attr('y2', y(p.pull)).attr('stroke', p.kill ? 'var(--color-ok)' : 'var(--cds-chart-grid)').attr('stroke-width', 1.5);
    const nextStart = pulls[i + 1] && pulls[i + 1].np === 1;
    if (m.multi) {
      if (p.np === 1 && p.pull > 1) rows.append('line').attr('x1', 4).attr('x2', W - 4).attr('y1', y(p.pull) - rowH / 2).attr('y2', y(p.pull) - rowH / 2).attr('stroke', 'var(--cds-chart-axis)').attr('stroke-dasharray', '2 3');
      if (p.np === 1 || (p.np % 5 === 0 && !nextStart)) rows.append('text').attr('x', mg.l - 6).attr('y', y(p.pull) + 4).attr('text-anchor', 'end').attr('fill', p.np === 1 ? 'var(--color-fg)' : 'var(--color-fg-muted)').style('font-size', 'var(--cds-font-size-caption)').text(p.np === 1 ? p.night : p.np);
    } else if (rowH >= 17 || p.np % 2 === 1) rows.append('text').attr('x', mg.l - 6).attr('y', y(p.pull) + 4).attr('text-anchor', 'end').attr('fill', 'var(--color-fg-muted)').style('font-size', 'var(--cds-font-size-caption)').text(p.np);
    if (!small || p.boss_pct <= nightBest[p.night]) rows.append('text').attr('x', W - mg.r + 6).attr('y', y(p.pull) + 4).attr('fill', p.boss_pct <= nightBest[p.night] + 2 ? 'var(--color-fg)' : 'var(--color-fg-muted)').style('font-size', 'var(--cds-font-size-caption)').style('font-variant-numeric', 'tabular-nums').text(p.kill ? 'Kill' : p.boss_pct.toFixed(0) + '%');
  });
  const counted = (d) => d.rank <= cutoff;
  const on = (d) => (!ui.focus || ui.focus === causeKey(d.cause)) && (!player || d.player === player);
  svg.append('g').selectAll('circle').data(ranked.slice().sort((a, b) => (on(a) && counted(a)) - (on(b) && counted(b)))).join('circle')
    .attr('cx', (d) => x(d.t)).attr('cy', (d) => y(d.pull)).attr('r', (d) => (counted(d) && on(d) ? (player ? (small ? 4.5 : 5.5) : small ? 3.4 : 4.5) : small ? 1.8 : 2.4))
    .attr('fill', (d) => (counted(d) && on(d) ? causeColor(d.cause) : 'var(--cds-chart-muted)'))
    .attr('opacity', (d) => (counted(d) && on(d) ? 1 : on(d) ? 0.35 : 0.12))
    .attr('stroke', (d) => (counted(d) && on(d) ? 'var(--color-panel)' : 'none')).attr('stroke-width', 1);
  const tip = tipFor(box);
  const delaunay = d3.Delaunay.from(ranked, (d) => x(d.t), (d) => y(d.pull));
  const rowAt = (my) => Math.min(n, Math.max(1, Math.round((my - mg.t) / rowH + 0.5)));
  svg.append('rect').attr('x', mg.l).attr('y', mg.t - 4).attr('width', W - mg.l - mg.r).attr('height', rowH * n + 4).attr('fill', 'transparent').style('cursor', 'pointer')
    .on('mousemove', (ev) => {
      const [mx, my] = d3.pointer(ev); const d = ranked.length ? ranked[delaunay.find(mx, my)] : null;
      const near = d && Math.hypot(x(d.t) - mx, y(d.pull) - my) < 12;
      if (!near) { const pv = pulls[rowAt(my) - 1]; showTip(tip, box, ev, pv.label, [[stageColor(pv.stage, pv.kill), `Boss ${pv.boss_txt} · ${pv.length_txt}`], [null, 'Click to watch this pull']]); return; }
      showTip(tip, box, ev, `${PL(d.pull)} · ${d.t_txt}`, [[causeColor(d.cause), `${d.player}: ${d.cause}`], [null, counted(d) ? `Death #${d.rank} (counted)` : `Death #${d.rank} (pull already lost)`], [null, 'Click to watch it']]);
    })
    .on('mouseleave', () => hideTip(tip))
    .on('click', (ev) => {
      const [mx, my] = d3.pointer(ev); const d = ranked.length ? ranked[delaunay.find(mx, my)] : null;
      if (d && Math.hypot(x(d.t) - mx, y(d.pull) - my) < 12) openReplay(d.pull, d.t - 4); else openReplay(pulls[rowAt(my) - 1].pull, 0);
    });
}

function drawGuide() {
  const box = $('guide'); const got = ready(box, ['mechanic_guide', 'cutoff_causes']); if (!got) return;
  const [guide, cc] = got; const cut = P().cutoff; box.replaceChildren();
  const order = (g) => { const r = cc.find((c) => c.cutoff === cut && c.cause === g.key); return r ? r.deaths : 0; };
  for (const g of guide.slice().sort((a, b) => order(b) - order(a))) {
    const c = el('div', 'gcard'); c.dataset.key = g.key; if (ui.focus && ui.focus === causeKey(g.key)) c.classList.add('focus');
    const top = el('div', 'top'); const sw = el('span', 'sw'); sw.style.background = causeColor(g.key); top.append(sw, el('h3', null, g.name));
    c.append(top, el('div', 'grp', [g.group, g.who].filter(Boolean).join(' · ')), el('p', null, g.what));
    if (g.todo) { const d = el('p', 'do'); d.append(el('b', null, 'Do: '), g.todo); c.appendChild(d); }
    const meta = el('div', 'meta'); const r = cc.find((x) => x.cutoff === cut && x.cause === g.key);
    const left = el('span', null, r ? `${r.deaths} counted deaths` : 'No counted deaths');
    const right = el('span'); right.style.display = 'flex'; right.style.gap = '10px';
    for (const [u, t] of [[g.clip, 'Guide ↗'], [g.clip2, 'Clip ↗']]) if (u && /^https:\/\//.test(u)) { const a = el('a', 'clip', t); a.href = u; a.target = '_blank'; a.rel = 'noopener'; right.appendChild(a); }
    meta.append(left, right); c.appendChild(meta);
    box.appendChild(c);
  }
}

/* ---------------- your report ---------------- */
function drawPickers() {
  const box = $('pickers'); const got = ready(box, ['players4']); if (!got) return;
  const cur = P().player; box.replaceChildren();
  for (const role of ['Tank', 'Healer', 'Ranged', 'Melee']) {
    const ps = got[0].filter((x) => x.role === role); if (!ps.length) continue;
    const row = el('div', 'prow'); row.appendChild(el('span', 'role', role === 'Tank' ? 'Tanks' : role === 'Healer' ? 'Healers' : role));
    for (const p of ps) {
      const b = el('button', 'chip-btn'); const sw = el('span', 'sw'); sw.style.background = CLASS_COLOR[p.cls] || 'var(--cds-chart-muted)'; sw.style.boxShadow = 'inset 0 0 0 1px color-mix(in srgb, var(--color-fg) 35%, transparent)';
      b.append(sw, p.player); b.setAttribute('aria-pressed', String(p.player === cur));
      b.addEventListener('click', () => dash.setParams({ player: p.player })); row.appendChild(b);
    }
    box.appendChild(row);
  }
}

function fixFor(r) {
  const name = r.metric;
  if (/potion/i.test(name) && !/healing/i.test(name)) return { title: 'Use a potion every pull', tip: 'Pre-pot and use your combat potion on every pull.' };
  if (/healthstone/i.test(name)) return { title: 'Press your healthstone', tip: 'Use it the first time you drop low. Do not save it.' };
  const g = (dash.data('mechanic_guide').data || []).find((x) => name.toLowerCase().includes(String(x.key).toLowerCase()));
  return { title: r.dir === 'up' ? `Cut down: ${name}` : `More of: ${name}`, tip: g && g.todo ? g.todo : 'Watch your own pulls in the replay to see when it happens.' , clip: g && g.clip };
}

function drawReport() {
  const { player, cutoff } = P(); const m = M();
  $('report-empty').hidden = !!player; $('report-body').hidden = !player; if (!player) return;
  const pc = dash.data('player_cut'), pm = dash.data('player_metrics'), pl4 = dash.data('players4'), pcs = dash.data('player_causes'), rk = dash.data('ranked'), tl = dash.data('fight_timeline'), pv = dash.data('pull_view');
  if ([pc, pl4, pcs, rk, tl, pv].some((s) => s.status !== 'ok')) return;
  const me = pl4.data.find((p) => p.player === player); if (!me) return;
  $('rp-name').textContent = player; const nPulls = pv.data.length;
  $('rp-role').textContent = `${me.spec} ${me.cls} · ${me.role}` + (me.ilvl ? ` · item level ${me.ilvl}` : '') + (me.pulls < nPulls ? ` · in ${me.pulls} of ${nPulls} pulls` : '');
  const c = pc.data.find((r) => r.key === `${player}|${cutoff}`);
  $('rp-deaths').textContent = c.deaths; $('rp-rank').textContent = c.rank_txt; $('rp-opened').textContent = c.opened; $('rp-avg').textContent = c.avg_txt;
  const scored = pl4.data.filter((p) => p.score != null);
  $('rp-score-stat').hidden = me.score == null;
  if (me.score != null) { $('rp-score').textContent = me.score; $('rp-best').textContent = Math.max(...scored.map((p) => p.score)); }

  const cb = $('rp-causes'); cb.replaceChildren();
  const mine = pcs.data.filter((r) => r.player === player && r.cutoff === cutoff);
  if (!mine.length) cb.appendChild(el('div', 'empty', 'No counted deaths. Nice.'));
  const max = d3.max(mine, (r) => r.deaths) || 1;
  for (const r of mine) {
    const row = el('div', 'hrow'); const n = el('div'); n.style.display = 'flex'; n.style.alignItems = 'center'; n.style.gap = '6px'; const sw = el('span', 'sw'); sw.style.background = causeColor(r.cause); n.append(sw, r.cause);
    const tr = el('div', 'track'); const f = el('div', 'fill'); f.style.width = (100 * r.deaths) / max + '%'; f.style.background = causeColor(r.cause); tr.appendChild(f);
    row.append(n, tr, el('div', 'num', String(r.deaths))); row.addEventListener('click', () => openCause(r.cause)); cb.appendChild(row);
  }

  const box = $('rp-strip'); box.replaceChildren();
  const pts = rk.data.filter((r) => r.player === player && r.rank <= cutoff);
  const maxT = d3.max(pv.data, (p) => p.duration_s);
  const W = box.clientWidth || 400, H = 150, mg = { t: 22, r: 12, b: 26, l: 12 };
  const svg = d3.select(box).append('svg').attr('width', '100%').attr('viewBox', `0 0 ${W} ${H}`).attr('height', H);
  const x = d3.scaleLinear([0, maxT], [mg.l, W - mg.r]);
  bands(svg, x, mg.t, H - mg.b, tl.data, { opacity: 0.14 });
  const xa = svg.append('g').attr('transform', `translate(0,${H - mg.b})`).call(d3.axisBottom(x).tickValues(d3.range(0, maxT + 1, maxT > 300 ? 60 : 30)).tickSize(0).tickFormat(f2));
  axisStyle(xa, true); xa.selectAll('text').attr('dy', '1em');
  const sim = pts.map((p) => ({ ...p, x: x(p.t), y: (mg.t + H - mg.b) / 2 }));
  const fs = d3.forceSimulation(sim).force('x', d3.forceX((d) => x(d.t)).strength(1)).force('y', d3.forceY((mg.t + H - mg.b) / 2).strength(0.08)).force('c', d3.forceCollide(6)).stop();
  for (let i = 0; i < 120; i++) fs.tick();
  const tip = tipFor(box);
  svg.append('g').selectAll('circle').data(sim).join('circle').attr('cx', (d) => d.x).attr('cy', (d) => Math.max(mg.t + 6, Math.min(H - mg.b - 6, d.y))).attr('r', 5.5)
    .attr('fill', (d) => causeColor(d.cause)).attr('stroke', 'var(--color-panel)').attr('stroke-width', 1.2).style('cursor', 'pointer')
    .on('mousemove', (ev, d) => showTip(tip, box, ev, `${PL(d.pull)} · ${d.t_txt}`, [[causeColor(d.cause), d.cause], [null, `Death #${d.rank} of the pull`], [null, 'Click to watch it']]))
    .on('mouseleave', () => hideTip(tip)).on('click', (ev, d) => openReplay(d.pull, d.t - 5));

  const tb = $('rp-tbody'); tb.replaceChildren();
  const rows = pm.status === 'ok' ? pm.data.filter((r) => r.player === player) : [];
  $('rp-table-card').hidden = !rows.length;
  const fmt = (v) => (Math.abs(v) >= 10000 ? d3.format('.3~s')(v) : String(v));
  for (const r of rows) {
    const tr = el('tr');
    tr.append(el('td', null, r.metric), el('td', 'r' + (r.worse ? ' bad' : r.better ? ' good' : ''), fmt(r.you)), el('td', 'r', fmt(r.raid_median)), el('td', 'r', fmt(r.worst)));
    tb.appendChild(tr);
  }
  const fx = $('rp-fixes'); fx.replaceChildren();
  const worst = rows.filter((r) => r.worse).map((r) => ({ r, s: r.dir === 'up' ? (r.you - r.raid_median) / Math.max(1, r.raid_median) : (r.raid_median - r.you) / Math.max(1, r.raid_median) }))
    .sort((a, b) => b.s - a.s).slice(0, 3);
  $('rp-fixes-wrap').hidden = !rows.length;
  if (rows.length && !worst.length) fx.appendChild(el('div', 'card empty', 'You were at or better than the raid median on every mechanic. Keep it up.'));
  for (const { r } of worst) {
    const def = fixFor(r);
    const card = el('div', 'card fix'); card.appendChild(el('div', 'k', r.metric.toUpperCase()));
    card.appendChild(el('h3', null, def.title));
    card.appendChild(el('p', null, `You: ${fmt(r.you)} · raid median: ${fmt(r.raid_median)} (per 10 pulls)`));
    const tp = el('p', null, def.tip); tp.style.fontSize = 'var(--cds-font-size-caption)'; tp.style.color = 'var(--color-fg-muted)'; card.appendChild(tp);
    if (def.clip && /^https:\/\//.test(def.clip)) { const l = el('a', 'clip', 'Guide ↗'); l.href = def.clip; l.target = '_blank'; l.rel = 'noopener'; card.appendChild(l); }
    fx.appendChild(card);
  }
}

/* ---------------- pull detail ---------------- */
function setPull(n) { dash.setParams({ pull: Math.max(1, Math.min(pullCount(), n)) }); }
$('pull-prev').addEventListener('click', () => setPull(P().pull - 1));
$('pull-next').addEventListener('click', () => setPull(P().pull + 1));
$('pull-range').addEventListener('input', (e) => setPull(Number(e.target.value)));
$('pull-best').addEventListener('click', () => setPull(bestPull()));
$('pv-tbody').addEventListener('click', (e) => {
  const tr = e.target.closest('tr[data-key]'); const rk = dash.data('ranked'); if (!tr || rk.status !== 'ok') return;
  const d = rk.data.find((r) => String(r.id) === tr.dataset.key); if (!d) return;
  rpSeek(d.t - 4); $('replay-card').scrollIntoView({ behavior: 'smooth', block: 'start' });
});

function drawPull() {
  const { pull, cutoff } = P(); const m = M();
  const pv = dash.data('pull_view');
  const range = $('pull-range'); range.max = String(pullCount()); range.value = pull;
  const r = pv.status === 'ok' ? pv.data.find((x) => x.pull === pull) : null;
  $('pv-label').textContent = r ? (m.multi ? `${r.label} (${r.pull} of ${pv.data.length})` : r.label) : '—';
  $('pv-alive-lbl').textContent = `Alive at ${f2(m.checkpoint.t)}`;
  $('pv-phase').previousSibling.textContent = (m.stages || []).length > 1 ? 'Reached ' : 'Result ';
  for (const [id, f] of [['pv-boss', 'boss_txt'], ['pv-len', 'length_txt'], ['pv-phase', 'phase_reached'], ['pv-alive', 'alive_cp'], ['pv-fourth', 'fourth_txt'], ['pv-start', 'start_time']]) $(id).textContent = r ? r[f] : '—';
  if (r && /^https:\/\/www\.warcraftlogs\.com\//.test(r.replay_url)) $('wcl-link').href = r.replay_url;
  const box = $('alive-chart'); const got = ready(box, ['ranked', 'fight_timeline', 'pull_view']);
  const tb = $('pv-tbody'); tb.replaceChildren();
  RP.aliveHead = null;
  if (!got) return;
  const [ranked, timeline, pulls] = got;
  for (const d of ranked.filter((q) => q.pull === pull)) {
    const tr = el('tr', 'click' + (d.rank > cutoff ? ' after' : '')); tr.dataset.key = d.id;
    const c = el('td'); c.style.display = 'flex'; c.style.alignItems = 'center'; c.style.gap = '6px'; const sw = el('span', 'sw'); sw.style.background = causeColor(d.cause); c.append(sw, d.cause);
    tr.append(el('td', null, String(d.rank)), el('td', null, d.t_txt), el('td', null, d.player), c, el('td', null, d.note));
    tb.appendChild(tr);
  }
  box.replaceChildren();
  const best = bestPull(); const pp = (n) => pulls.find((q) => q.pull === n) || { duration_s: 0, players: 20 };
  const series = (n) => { const raid = pp(n).players; const pts = [{ t: 0, a: raid }]; let a = raid; for (const d of ranked.filter((q) => q.pull === n)) { a = Math.max(0, a - 1); pts.push({ t: d.t, a, d }); } pts.push({ t: pp(n).duration_s, a }); return pts; };
  const raid = Math.max(pp(pull).players, pp(best).players);
  const W = box.clientWidth || 600, H = 220, mg = { t: 14, r: 14, b: 26, l: 30 };
  const svg = d3.select(box).append('svg').attr('width', '100%').attr('viewBox', `0 0 ${W} ${H}`).attr('height', H);
  const x = d3.scaleLinear([0, Math.max(pp(pull).duration_s, pp(best).duration_s)], [mg.l, W - mg.r]);
  const y = d3.scaleLinear([0, raid], [H - mg.b, mg.t]);
  bands(svg, x, mg.t, H - mg.b, timeline, { opacity: 0.1 });
  svg.append('g').selectAll('line').data(y.ticks(4)).join('line').attr('x1', mg.l).attr('x2', W - mg.r).attr('y1', y).attr('y2', y).attr('stroke', 'var(--cds-chart-grid)');
  axisStyle(svg.append('g').attr('transform', `translate(${mg.l},0)`).call(d3.axisLeft(y).ticks(2).tickSize(0)));
  const xa = svg.append('g').attr('transform', `translate(0,${H - mg.b})`).call(d3.axisBottom(x).tickValues(d3.range(0, x.domain()[1] + 1, x.domain()[1] > 300 ? 60 : 30)).tickSize(0).tickFormat(f2));
  axisStyle(xa, true); xa.selectAll('text').attr('dy', '1em');
  const line = d3.line().curve(d3.curveStepAfter).x((d) => x(d.t)).y((d) => y(d.a));
  if (best !== pull) svg.append('path').datum(series(best)).attr('fill', 'none').attr('stroke', 'var(--cds-chart-muted)').attr('stroke-width', 2).attr('d', line);
  const s = series(pull);
  svg.append('path').datum(s).attr('fill', 'none').attr('stroke', 'var(--color-fg)').attr('stroke-width', 2).attr('stroke-linecap', 'round').attr('d', line);
  const head = svg.append('line').attr('y1', mg.t).attr('y2', H - mg.b).attr('stroke', 'var(--cds-chart-reference)').attr('stroke-width', 1.5).attr('stroke-dasharray', '3 3');
  RP.aliveHead = { head, x };
  const tip = tipFor(box);
  svg.append('rect').attr('x', mg.l).attr('y', mg.t).attr('width', W - mg.l - mg.r).attr('height', H - mg.b - mg.t).attr('fill', 'transparent').style('cursor', 'pointer')
    .on('click', (ev) => { const [mx] = d3.pointer(ev); rpSeek(x.invert(mx)); });
  svg.append('g').selectAll('circle').data(s.filter((q) => q.d)).join('circle').attr('cx', (q) => x(q.t)).attr('cy', (q) => y(q.a)).attr('r', (q) => (q.d.rank <= cutoff ? 5 : 3))
    .attr('fill', (q) => causeColor(q.d.cause)).attr('opacity', (q) => (q.d.rank <= cutoff ? 1 : 0.45)).attr('stroke', 'var(--color-panel)').attr('stroke-width', 1).style('cursor', 'pointer')
    .on('mousemove', (ev, q) => showTip(tip, box, ev, `${q.d.t_txt} · death #${q.d.rank}`, [[causeColor(q.d.cause), `${q.d.player}: ${q.d.cause}`]])).on('mouseleave', () => hideTip(tip))
    .on('click', (ev, q) => rpSeek(q.t - 4));
  svg.append('text').attr('x', W - mg.r).attr('y', mg.t + 10).attr('text-anchor', 'end').attr('fill', 'var(--color-fg-muted)').style('font-size', 'var(--cds-font-size-caption)').text(best !== pull ? `grey = ${PL(best)} (best)` : 'our best pull');
  rpHeads();
}

/* ---------------- replay ---------------- */
const RP = { pull: null, t: 0, dur: 0, playing: false, speed: 2, names: false, last: 0, raf: 0, seek: null, feedN: -1, ctx: null, key: '', aliveHead: null, cache: new Map() };
const RING_COLORS = () => [causeColor(M().rings[0] ? M().rings[0].ability : ''), 'var(--color-fg)', dash.colors[3]];
const ringColor = (i) => { const r = (M().rings || [])[i]; if (!r) return 'var(--color-fg)'; const c = causeColor(r.ability); return c === 'var(--cds-chart-muted)' ? (r.style === 'dash' ? 'var(--color-fg)' : dash.colors[5 + (i % 3)]) : c; };

function rpFrames(row) {
  if (RP.cache.has(row.pull)) return RP.cache.get(row.pull);
  const bin = atob(row.pos); const A = String(row.actors).split('|'); const N = A.length; const n = Number(row.seconds); const u = Number(row.unit) || 0.5;
  const xy = new Float32Array(n * N * 2).fill(NaN);
  for (let s = 0; s < n; s++) for (let a = 0; a < N; a++) {
    const i = (s * N + a) * 2; let vx = bin.charCodeAt(i), vy = bin.charCodeAt(i + 1);
    if (vx === 128) continue; if (vx > 127) vx -= 256; if (vy > 127) vy -= 256; xy[i] = vx * u; xy[i + 1] = vy * u;
  }
  for (let a = 0; a < N; a++) {
    let lx = NaN, ly = NaN;
    for (let s = 0; s < n; s++) { const i = (s * N + a) * 2; if (Number.isNaN(xy[i])) { xy[i] = lx; xy[i + 1] = ly; } else { lx = xy[i]; ly = xy[i + 1]; } }
    let fx = NaN, fy = NaN;
    for (let s = n - 1; s >= 0; s--) { const i = (s * N + a) * 2; if (Number.isNaN(xy[i])) { xy[i] = fx; xy[i + 1] = fy; } else { fx = xy[i]; fy = xy[i + 1]; } }
  }
  const f = { A, N, n, xy, nb: Number(row.boss_actors) || 0, rings: JSON.parse(row.rings || '[]') };
  RP.cache.set(row.pull, f); return f;
}
const rpPos = (f, a, t) => {
  const s0 = Math.max(0, Math.min(f.n - 1, Math.floor(t))), s1 = Math.min(f.n - 1, s0 + 1), fr = Math.max(0, Math.min(1, t - s0));
  const i0 = (s0 * f.N + a) * 2, i1 = (s1 * f.N + a) * 2;
  const x0 = f.xy[i0], y0 = f.xy[i0 + 1], x1 = f.xy[i1], y1 = f.xy[i1 + 1];
  if (Number.isNaN(x0)) return null; if (Number.isNaN(x1)) return [x0, y0];
  return [x0 + (x1 - x0) * fr, y0 + (y1 - y0) * fr];
};

const bossColor = (b) => (b.enrage ? 'var(--color-bad)' : b.kind === 'phase' ? 'var(--cds-chart-muted)' : causeColor(b.event) !== 'var(--cds-chart-muted)' ? causeColor(b.event) : (() => { const i = (M().rings || []).findIndex((r) => r.ability === b.event); return i >= 0 ? ringColor(i) : 'var(--cds-chart-muted)'; })());
const bossText = (b) => (b.kind === 'phase' ? `Phase: ${b.event}` : b.kind === 'debuff' ? `${b.event} on ${b.player}` : b.player ? `${b.event} → ${b.player}` : b.event);

function rpContext(f, pull, bev, ranked, players, arena, code) {
  const ev = bev.filter((b) => b.pull === pull).sort((a, b) => a.t - b.t);
  const deaths = ranked.filter((r) => r.pull === pull);
  const byName = new Map(); for (const d of deaths) { if (!byName.has(d.player)) byName.set(d.player, []); byName.get(d.player).push(d); }
  const cls = new Map(players.map((p) => [p.player, p]));
  const rings = M().rings || [];
  const holding = (name, t) => f.rings.filter(([n, ri, s, e]) => n === name && s <= t && t <= e + 0.3).map(([n, ri]) => ri);
  const feed = [
    ...ev.map((b) => ({ t: b.t, boss: true, color: bossColor(b), text: bossText(b) })),
    ...deaths.map((d) => { const h = holding(d.player, d.t).filter((ri) => rings[ri] && rings[ri].ability !== d.cause); return { t: d.t, boss: false, color: causeColor(d.cause), text: `${d.player} died · ${d.cause}`, had: h.map((ri) => rings[ri].ability), rank: d.rank }; }),
  ].sort((a, b) => a.t - b.t || (a.boss ? -1 : 1));
  const jumps = []; const seen = new Set();
  for (const b of ev) {
    const k = b.kind === 'phase' ? 'phase:' + b.event + ':' + b.t : b.event;
    if (seen.has(k) || (b.kind !== 'phase' && !b.enrage && !(M().major || []).slice(0, 5).includes(b.event))) continue;
    seen.add(k); jumps.push({ label: b.kind === 'phase' ? b.event : b.event, t: Math.max(0, b.t - 3), at: b.t, color: bossColor(b) });
  }
  const d4 = deaths.find((d) => d.rank === 4); if (d4) jumps.push({ label: '4th death', t: Math.max(0, d4.t - 4), at: d4.t, color: 'var(--color-bad)' });
  jumps.sort((a, b) => a.at - b.at);
  const ar = arena.filter((a) => a.kind === 'edge' || !a.code || a.code === code);
  return { f, pull, ev, deaths, byName, cls, holding, feed, jumps: jumps.slice(0, 12), arena: ar };
}

function rpBuild(box, C, W) {
  box.replaceChildren();
  const edge = C.arena.find((a) => a.kind === 'edge') || { r: 40, view: 50, shape: 'circle' };
  const R = Number(edge.view) || 50; const s = W / (2 * R); const X = (v) => W / 2 + v * s; const Y = (v) => W / 2 - v * s;
  const svg = d3.select(box).append('svg').attr('width', '100%').attr('viewBox', `0 0 ${W} ${W}`).attr('height', '100%').attr('role', 'img').attr('aria-label', `Replay of ${PL(C.pull)}`);
  const ap = Number(edge.r) || R * 0.9;
  if (edge.shape === 'octagon') {
    const vr = ap / Math.cos(Math.PI / 8);
    const oct = d3.range(8).map((k) => { const a = Math.PI / 8 + (k * Math.PI) / 4; return [X(vr * Math.cos(a)), Y(vr * Math.sin(a))]; });
    svg.append('polygon').attr('points', oct.map((p) => p.join(',')).join(' ')).attr('fill', 'color-mix(in srgb, var(--cds-chart-muted) 10%, var(--color-panel))').attr('stroke', 'var(--cds-chart-axis)').attr('stroke-width', 1.5);
  } else if (edge.shape !== 'none') {
    svg.append('circle').attr('cx', X(0)).attr('cy', Y(0)).attr('r', ap * s).attr('fill', 'color-mix(in srgb, var(--cds-chart-muted) 10%, var(--color-panel))').attr('stroke', 'var(--cds-chart-axis)').attr('stroke-width', 1.2).attr('stroke-dasharray', edge.shape === 'circle' ? '4 4' : null);
  }
  svg.append('circle').attr('cx', X(0)).attr('cy', Y(0)).attr('r', 3).attr('fill', 'var(--cds-chart-grid)');
  const mk = svg.append('g'); const ms = Math.max(5, Math.min(8, W / 70));
  for (const a of C.arena.filter((q) => q.kind === 'marker')) {
    const [shape, col] = MARKER[a.icon] || ['circle', 'var(--cds-chart-muted)']; const cx = X(Number(a.x)), cy = Y(Number(a.y));
    const g = mk.append('g').attr('transform', `translate(${cx},${cy})`); const st = (e) => e.attr('fill', col).attr('stroke', 'var(--color-fg)').attr('stroke-opacity', 0.45).attr('stroke-width', 0.8);
    if (shape === 'circle') st(g.append('circle').attr('r', ms * 0.9));
    else if (shape === 'square') st(g.append('rect').attr('x', -ms * 0.8).attr('y', -ms * 0.8).attr('width', ms * 1.6).attr('height', ms * 1.6).attr('rx', 1.5));
    else if (shape === 'diamond') st(g.append('path').attr('d', `M0,${-ms} L${ms * 0.75},0 L0,${ms} L${-ms * 0.75},0Z`));
    else if (shape === 'triangle') st(g.append('path').attr('d', `M0,${-ms} L${ms * 0.95},${ms * 0.75} L${-ms * 0.95},${ms * 0.75}Z`));
    else if (shape === 'star') st(g.append('path').attr('d', d3.range(10).map((i) => { const r = i % 2 ? ms * 0.45 : ms; const an = -Math.PI / 2 + (i * Math.PI) / 5; return (i ? 'L' : 'M') + (r * Math.cos(an)).toFixed(2) + ',' + (r * Math.sin(an)).toFixed(2); }).join('') + 'Z'));
    else if (shape === 'moon') st(g.append('path').attr('d', `M${ms * 0.3},${-ms} A${ms},${ms} 0 1 0 ${ms * 0.3},${ms} A${ms * 0.75},${ms * 0.75} 0 1 1 ${ms * 0.3},${-ms}Z`));
    else if (shape === 'cross') st(g.append('path').attr('d', `M${-ms},${-ms * 0.55} L${-ms * 0.55},${-ms} L0,${-ms * 0.45} L${ms * 0.55},${-ms} L${ms},${-ms * 0.55} L${ms * 0.45},0 L${ms},${ms * 0.55} L${ms * 0.55},${ms} L0,${ms * 0.45} L${-ms * 0.55},${ms} L${-ms},${ms * 0.55} L${-ms * 0.45},0Z`));
    else if (shape === 'skull') { st(g.append('path').attr('d', `M${-ms * 0.85},${ms * 0.1} A${ms * 0.85},${ms * 0.85} 0 1 1 ${ms * 0.85},${ms * 0.1} L${ms * 0.5},${ms * 0.45} L${ms * 0.5},${ms * 0.9} L${-ms * 0.5},${ms * 0.9} L${-ms * 0.5},${ms * 0.45}Z`)); g.append('circle').attr('cx', -ms * 0.32).attr('cy', -ms * 0.05).attr('r', ms * 0.2).attr('fill', 'var(--color-bg)'); g.append('circle').attr('cx', ms * 0.32).attr('cy', -ms * 0.05).attr('r', ms * 0.2).attr('fill', 'var(--color-bg)'); }
    g.append('title').text(a.name);
  }
  const layers = { dash: svg.append('g'), ring: svg.append('g'), dead: svg.append('g'), boss: svg.append('g'), dots: svg.append('g'), labels: svg.append('g') };
  const banner = el('div', 'rp-banner'); banner.hidden = true; box.appendChild(banner);
  const tip = tipFor(box);
  svg.on('mousemove', (ev) => {
    const [mx, my] = d3.pointer(ev); const pts = RP.ctx && RP.ctx.pts ? RP.ctx.pts : [];
    let best = null, bd = 14; for (const p of pts) { const d = Math.hypot(p.px - mx, p.py - my); if (d < bd) { bd = d; best = p; } }
    if (!best) { hideTip(tip); return; }
    const lines = [[best.color, best.sub]]; if (best.dead) lines.push([causeColor(best.dead.cause), `Died at ${best.dead.t_txt} · ${best.dead.cause}`]);
    for (const ri of best.rings || []) lines.push([ringColor(ri), `Has ${M().rings[ri].ability}`]);
    showTip(tip, box, ev, best.name, lines);
  }).on('mouseleave', () => hideTip(tip));
  return { svg, layers, banner, X, Y, s };
}

function rpDraw() {
  const C = RP.ctx; if (!C || !C.view) return;
  const { f } = C; const t = RP.t; const V = C.view; const follow = P().player; const rings = M().rings || [];
  const r0 = Math.max(4, Math.min(6.5, V.s * 1.8));
  const pts = [];
  for (let a = 0; a < f.N - f.nb; a++) {
    const name = f.A[a];
    const ds = C.byName.get(name) || []; let dead = null;
    for (let k = 0; k < ds.length; k++) { if (ds[k].t <= t && !(k < ds.length - 1 && t > ds[k].t + 5)) dead = ds[k]; }
    const at = dead ? rpPos(f, a, dead.t) : rpPos(f, a, t); if (!at) continue;
    const p = C.cls.get(name) || {};
    pts.push({ name, a, px: V.X(at[0]), py: V.Y(at[1]), dead, rings: dead ? [] : C.holding(name, t), color: CLASS_COLOR[p.cls] || 'var(--cds-chart-muted)', sub: p.spec ? `${p.spec} ${p.cls}` : '', me: name === follow });
  }
  C.pts = pts;
  const alive = pts.filter((p) => !p.dead), dead = pts.filter((p) => p.dead);
  const ringPts = [], dashPts = [];
  for (const p of alive) for (const ri of p.rings) (rings[ri] && rings[ri].style === 'dash' ? dashPts : ringPts).push({ ...p, ri, key: p.name + ':' + ri });
  V.layers.ring.selectAll('circle').data(ringPts, (d) => d.key).join('circle').attr('cx', (d) => d.px).attr('cy', (d) => d.py).attr('r', (d) => r0 + 4 + 3 * (d.ri % 2))
    .attr('fill', (d) => `color-mix(in srgb, ${ringColor(d.ri)} 16%, transparent)`).attr('stroke', (d) => ringColor(d.ri)).attr('stroke-width', 2);
  V.layers.dash.selectAll('circle').data(dashPts, (d) => d.key).join('circle').attr('cx', (d) => d.px).attr('cy', (d) => d.py).attr('r', r0 + 9)
    .attr('fill', 'none').attr('stroke', (d) => ringColor(d.ri)).attr('stroke-width', 1.5).attr('stroke-dasharray', '3 3');
  const xs = r0 * 0.85;
  V.layers.dead.selectAll('path').data(dead, (d) => d.name).join('path').attr('d', (d) => `M${d.px - xs},${d.py - xs}L${d.px + xs},${d.py + xs}M${d.px + xs},${d.py - xs}L${d.px - xs},${d.py + xs}`)
    .attr('stroke', (d) => causeColor(d.dead.cause)).attr('stroke-width', (d) => (d.me ? 3.5 : 2.4)).attr('stroke-linecap', 'round').attr('opacity', (d) => (d.me || !follow ? 0.95 : 0.7));
  const bp = [];
  for (let a = f.N - f.nb; a < f.N; a++) { const q = rpPos(f, a, t); if (q) bp.push({ a, name: f.A[a], q }); }
  V.layers.boss.selectAll('rect').data(bp, (d) => d.a).join('rect').attr('x', (d) => V.X(d.q[0]) - r0 * 1.6).attr('y', (d) => V.Y(d.q[1]) - r0 * 1.6).attr('width', r0 * 3.2).attr('height', r0 * 3.2).attr('rx', 4)
    .attr('fill', 'var(--color-fg)').attr('opacity', 0.85);
  V.layers.dots.selectAll('circle').data(alive.slice().sort((a, b) => a.me - b.me), (d) => d.name).join('circle').attr('cx', (d) => d.px).attr('cy', (d) => d.py).attr('r', (d) => (d.me ? r0 + 2 : r0))
    .attr('fill', (d) => d.color).attr('stroke', (d) => (d.me ? 'var(--color-fg)' : 'color-mix(in srgb, var(--color-fg) 55%, transparent)')).attr('stroke-width', (d) => (d.me ? 2.2 : 1))
    .attr('opacity', (d) => (!follow || d.me ? 1 : 0.8));
  const lbl = pts.filter((p) => RP.names || p.me).map((p) => ({ key: p.name, x: p.px, y: p.py - r0 - 5, text: p.name, strong: p.me }));
  for (const b of bp) lbl.push({ key: '__boss' + b.a, x: V.X(b.q[0]), y: V.Y(b.q[1]) + r0 * 1.6 + 12, text: b.name, strong: false });
  V.layers.labels.selectAll('text').data(lbl, (d) => d.key).join('text').attr('x', (d) => d.x).attr('y', (d) => d.y).attr('text-anchor', 'middle')
    .attr('fill', (d) => (d.strong ? 'var(--color-fg)' : 'var(--color-fg-muted)')).attr('stroke', 'var(--color-panel)').attr('stroke-width', 3).attr('paint-order', 'stroke')
    .style('font-size', 'var(--cds-font-size-caption)').style('font-weight', (d) => (d.strong ? 'var(--cds-font-weight-medium)' : null)).text((d) => d.text);
  const recent = C.feed.filter((e) => e.boss && e.t <= t && t - e.t < 4).pop();
  V.banner.hidden = !recent;
  if (recent) { const sw = el('span', 'sw'); sw.style.background = recent.color; V.banner.replaceChildren(sw, `${f2(recent.t)} · ${recent.text}`); }
  $('rp-clock').textContent = `${f2(t)} / ${f2(RP.dur)}`;
  rpFeed(); rpHeads();
}

function rpFeed() {
  const C = RP.ctx; const box = $('rp-feed'); if (!C) return;
  const shown = C.feed.filter((e) => e.t <= RP.t);
  if (shown.length === RP.feedN) return; RP.feedN = shown.length;
  box.replaceChildren(el('div', 'fh', shown.length ? 'Latest first' : 'Events show up here as the pull plays.'));
  for (const e of shown.slice(-12).reverse()) {
    const row = el('div', 'fi' + (e.boss ? ' boss' : '')); row.setAttribute('role', 'button'); row.tabIndex = 0;
    const sw = el('span', 'sw'); sw.style.background = e.color;
    const tx = el('span', 'fx', e.text); if (e.had && e.had.length) tx.append(' ', el('span', 'tag', `(had ${e.had.join(', ')})`));
    row.append(el('span', 'ft', f2(e.t)), sw, tx);
    const go = () => rpSeek(e.t - 3); row.addEventListener('click', go); row.addEventListener('keydown', (k) => { if (k.key === 'Enter') go(); });
    box.appendChild(row);
  }
}

function rpHeads() {
  const t = RP.t;
  if (RP.aliveHead) RP.aliveHead.head.attr('x1', RP.aliveHead.x(t)).attr('x2', RP.aliveHead.x(t));
  if (RP.strip) { RP.strip.head.attr('x1', RP.strip.x(t)).attr('x2', RP.strip.x(t)); RP.strip.knob.attr('cx', RP.strip.x(t)); }
  const sb = $('replay-strip'); sb.setAttribute('aria-valuemin', '0'); sb.setAttribute('aria-valuemax', String(Math.round(RP.dur))); sb.setAttribute('aria-valuenow', String(Math.round(t))); sb.setAttribute('aria-valuetext', f2(t));
}

function rpStrip(C) {
  const box = $('replay-strip'); box.replaceChildren(); RP.strip = null;
  const W = box.clientWidth || 600, H = 72, mg = { l: 18, r: 20, t: 6, b: 20 };
  const svg = d3.select(box).append('svg').attr('width', '100%').attr('viewBox', `0 0 ${W} ${H}`).attr('height', H);
  const x = d3.scaleLinear([0, RP.dur], [mg.l, W - mg.r]);
  svg.append('rect').attr('x', mg.l).attr('y', mg.t).attr('width', W - mg.l - mg.r).attr('height', H - mg.t - mg.b).attr('rx', 6).attr('fill', 'color-mix(in srgb, var(--cds-chart-muted) 12%, transparent)');
  const ph = C.ev.filter((b) => b.kind === 'phase');
  ph.forEach((b, i) => { const e = ph[i + 1] ? ph[i + 1].t : RP.dur; if (i % 2 === 0) svg.append('rect').attr('x', x(b.t)).attr('width', Math.max(2, x(e) - x(b.t))).attr('y', mg.t).attr('height', H - mg.t - mg.b).attr('fill', 'var(--cds-chart-muted)').attr('opacity', 0.18); });
  const top = new Set((M().major || []).slice(0, 4));
  const big = C.ev.filter((b) => b.enrage || (b.kind !== 'phase' && top.has(b.event)));
  svg.append('g').selectAll('line').data(big).join('line').attr('x1', (d) => x(d.t)).attr('x2', (d) => x(d.t)).attr('y1', mg.t + 3).attr('y2', mg.t + 24).attr('stroke', (d) => bossColor(d)).attr('stroke-width', 3).attr('stroke-linecap', 'round');
  svg.append('g').selectAll('circle').data(C.deaths).join('circle').attr('cx', (d) => x(d.t)).attr('cy', mg.t + 36).attr('r', 3).attr('fill', (d) => causeColor(d.cause)).attr('opacity', 0.9);
  const xa = svg.append('g').attr('transform', `translate(0,${H - mg.b})`).call(d3.axisBottom(x).tickValues(d3.range(0, RP.dur + 1, RP.dur > 300 ? 60 : W < 420 ? 30 : 15)).tickSize(0).tickFormat(f2));
  axisStyle(xa, false); xa.selectAll('text').attr('dy', '1.1em');
  const head = svg.append('line').attr('y1', mg.t).attr('y2', H - mg.b).attr('stroke', 'var(--color-fg)').attr('stroke-width', 2);
  const knob = svg.append('circle').attr('cy', mg.t).attr('r', 5).attr('fill', 'var(--color-fg)');
  RP.strip = { x, head, knob };
  const tip = tipFor(box); let drag = false;
  const at = (ev) => Math.max(0, Math.min(RP.dur, x.invert(d3.pointer(ev, svg.node())[0])));
  svg.on('pointerdown', (ev) => { drag = true; svg.node().setPointerCapture(ev.pointerId); rpSeek(at(ev)); })
    .on('pointermove', (ev) => {
      const t = at(ev); if (drag) rpSeek(t);
      const near = [...big, ...C.deaths].map((d) => ({ d, k: Math.abs(x(d.t) - x(t)) })).filter((q) => q.k < 5).sort((a, b) => a.k - b.k)[0];
      const lines = near ? [[near.d.cause ? causeColor(near.d.cause) : bossColor(near.d), near.d.cause ? `${near.d.player} died · ${near.d.cause}` : bossText(near.d)]] : [];
      showTip(tip, box, ev, f2(t), lines);
    })
    .on('pointerup pointercancel', () => { drag = false; })
    .on('pointerleave', () => hideTip(tip));
}

function rpSeek(t) { RP.t = Math.max(0, Math.min(RP.dur || 0, t)); rpDraw(); }
function rpSyncPlay() { const b = $('rp-play'); b.textContent = RP.playing ? '❚❚ Pause' : '▶ Play'; b.setAttribute('aria-label', RP.playing ? 'Pause' : 'Play'); }
function rpTick(ts) {
  if (!RP.playing) return;
  const dt = Math.min(0.25, (ts - RP.last) / 1000); RP.last = ts;
  RP.t = Math.min(RP.dur, RP.t + dt * RP.speed); rpDraw();
  if (RP.t >= RP.dur) { rpPause(); return; }
  RP.raf = requestAnimationFrame(rpTick);
}
function rpPlay() { if (!RP.ctx) return; if (RP.t >= RP.dur - 0.05) RP.t = 0; RP.playing = true; RP.last = performance.now(); cancelAnimationFrame(RP.raf); RP.raf = requestAnimationFrame(rpTick); rpSyncPlay(); }
function rpPause() { RP.playing = false; cancelAnimationFrame(RP.raf); rpSyncPlay(); }
$('rp-play').addEventListener('click', () => (RP.playing ? rpPause() : rpPlay()));
document.querySelectorAll('#rp-speed button').forEach((b) => b.addEventListener('click', () => { RP.speed = Number(b.dataset.speed); document.querySelectorAll('#rp-speed button').forEach((q) => q.setAttribute('aria-pressed', String(q === b))); }));
document.querySelectorAll('#rp-speed button').forEach((q) => q.setAttribute('aria-pressed', String(Number(q.dataset.speed) === RP.speed)));
$('rp-names').addEventListener('click', () => { RP.names = !RP.names; $('rp-names').setAttribute('aria-pressed', String(RP.names)); rpDraw(); });
$('replay-strip').addEventListener('keydown', (e) => {
  if (e.key === 'ArrowLeft') { rpSeek(RP.t - 2); e.preventDefault(); } else if (e.key === 'ArrowRight') { rpSeek(RP.t + 2); e.preventDefault(); }
  else if (e.key === 'Home') { rpSeek(0); e.preventDefault(); } else if (e.key === 'End') { rpSeek(RP.dur); e.preventDefault(); }
  else if (e.key === ' ') { RP.playing ? rpPause() : rpPlay(); e.preventDefault(); }
});

function drawKey() {
  const box = $('rp-key'); box.replaceChildren();
  const add = (cls, text, color) => { const s = el('span'); const i = el(cls === 'x' ? 'b' : 'i', cls === 'x' ? 'k-x' : cls, cls === 'x' ? '✕' : null); if (color) i.style.setProperty('--k', color); s.append(i, text); box.appendChild(s); };
  add('k-dot', 'Raider, in class color'); add('k-boss', 'Boss');
  (M().rings || []).forEach((r, i) => add(r.style === 'dash' ? 'k-dash2' : 'k-ring', `Has ${r.ability}`, ringColor(i)));
  add('x', 'Died, colored by what killed them');
}

function drawReplay() {
  const box = $('replay-map'); fillPlayerSelect($('rp-follow'), 'Nobody'); drawKey();
  const got = ready(box, ['replay', 'arena', 'boss_events', 'ranked', 'players4', 'pull_view']);
  if (!got) { rpPause(); RP.ctx = null; RP.key = ''; $('rp-jumps').replaceChildren(); $('rp-feed').replaceChildren(); $('replay-strip').replaceChildren(); return; }
  const [rep, arena, bev, ranked, players, pv] = got;
  const pull = P().pull; const row = rep.find((r) => Number(r.pull) === pull); const pr = pv.find((p) => p.pull === pull);
  if (!row || !pr) { rpPause(); RP.ctx = null; RP.key = ''; box.replaceChildren(el('div', 'fail', 'No replay for this pull')); return; }
  const f = rpFrames(row);
  if (RP.pull !== pull) { rpPause(); RP.pull = pull; RP.t = 0; RP.feedN = -1; RP.key = ''; }
  if (RP.seek != null) { RP.t = RP.seek; RP.seek = null; RP.feedN = -1; }
  RP.dur = pr.duration_s; RP.t = Math.min(RP.t, RP.dur);
  const W = Math.round(Math.min(box.clientWidth || 420, 680));
  const key = pull + '|' + W;
  if (RP.key !== key || !RP.ctx) {
    const C = rpContext(f, pull, bev, ranked, players, arena, pr.code);
    C.view = rpBuild(box, C, W); RP.ctx = C; RP.key = key; RP.feedN = -1;
    const jb = $('rp-jumps'); jb.replaceChildren();
    for (const j of C.jumps) { const b = el('button', 'chip-btn'); const sw = el('span', 'sw'); sw.style.background = j.color; b.append(sw, `${j.label} · ${f2(j.at)}`); b.addEventListener('click', () => rpSeek(j.t)); jb.appendChild(b); }
  }
  rpStrip(RP.ctx);
  rpDraw();
}

/* ---------------- marks + render ---------------- */
function fillMarks() {
  document.querySelectorAll('.rr [data-source][data-field]').forEach((n) => {
    const st = dash.data(n.dataset.source);
    if (st.status === 'ok' || st.status === 'error') n.classList.remove('dash-skeleton');
    if (st.status !== 'ok') { n.textContent = '—'; return; }
    let rows = st.data;
    if (n.dataset.where) { const conds = n.dataset.where.split('&').map((p) => p.split('=').map(decodeURIComponent)); rows = rows.filter((r) => conds.every(([k, v]) => String(r[k]) === v)); }
    const r = rows[0]; n.textContent = r && r[n.dataset.field] != null ? r[n.dataset.field] : '—';
  });
}

function render() {
  const { cutoff } = P();
  document.querySelectorAll('.tabs button').forEach((b) => b.setAttribute('aria-selected', String(b.dataset.tab === ui.tab)));
  document.querySelectorAll('[data-page]').forEach((s) => { s.hidden = s.dataset.page !== ui.tab; });
  document.querySelectorAll('#cut-seg button').forEach((b) => b.setAttribute('aria-pressed', String(Number(b.dataset.cut) === cutoff)));
  drawHeader(); drawLead(); drawTopKiller();
  if (ui.tab === 'issues') drawIssues();
  if (ui.tab === 'overview') { drawTiles(); drawWalls(); drawBoss(); drawKillers(); drawFourth(); drawHabits(); }
  if (ui.tab === 'fight') { drawMapLegend(); fillPlayerSelect($('map-player'), 'Nobody'); drawMap(); drawGuide(); }
  if (ui.tab === 'report') { drawPickers(); drawReport(); }
  if (ui.tab === 'replay') { drawPull(); drawReplay(); }
  fillMarks();
}
