/* ---------------- biggest problems (generic cards from DATA.issues) ---------------- */
const endColor = (k) => (k === 'Enrage' ? 'var(--color-bad)' : k === 'Kill' ? 'var(--color-ok)' : k === 'Something else' ? 'var(--cds-chart-muted)' : causeColor(k));
const cardColor = (c) => (c.color === 'bad' ? 'var(--color-bad)' : c.cause ? causeColor(c.cause) : 'var(--color-fg)');

function issPill(r) {
  const b = el('button', 'chip-btn'); const sw = el('span', 'sw'); sw.style.background = CLASS_COLOR[r.cls] || 'var(--cds-chart-muted)';
  sw.style.boxShadow = 'inset 0 0 0 1px color-mix(in srgb, var(--color-fg) 35%, transparent)';
  b.append(sw, el('b', null, r.player), el('span', 't', r.txt));
  b.setAttribute('aria-label', `${r.player}: ${r.txt}. Open their report`);
  b.addEventListener('click', () => { dash.setParams({ player: r.player }); setTab('report'); $('top').scrollIntoView({ behavior: 'smooth' }); });
  return b;
}

function issSide(s) {
  if (s.type === 'who') {
    const w = el('div', 'iwho'); w.appendChild(el('h3', null, s.label));
    const ps = el('div', 'pills'); for (const r of s.items) ps.appendChild(issPill(r)); w.appendChild(ps);
    if (!s.items.length) w.appendChild(el('div', 'sub', 'Nobody stands out.'));
    return w;
  }
  if (s.type === 'trend') {
    const w = el('div', 'itrend'); w.appendChild(el('h3', null, s.label));
    const max = s.unit === '%' || s.unit === 'rank' ? 100 : Math.max(...s.items.map((x) => x.value || 0)) || 1;
    const cols = el('div', 'itcols'); cols.style.gridTemplateColumns = `repeat(${Math.max(1, s.items.length)}, minmax(0, 1fr))`;
    s.items.forEach((x, i) => {
      const c = el('div', 'itcol' + (i === s.items.length - 1 ? ' last' : ''));
      const tr = el('div', 'ittrack'); const b = el('div', 'itbar'); b.style.height = Math.max(3, (100 * (x.value || 0)) / max) + '%'; tr.appendChild(b);
      c.append(el('div', 'itv', x.txt), tr, el('div', 'itn', x.night)); cols.appendChild(c);
    });
    w.appendChild(cols); return w;
  }
  return el('div');
}

function issMain(s, col) {
  if (s.type === 'note') return el('p', 'note', s.text);
  const box = el('div', 'idetail'); box.appendChild(el('h3', null, s.title));
  const max = Math.max(1, ...s.rows.map((r) => r.max || r.value || 0));
  for (const r of s.rows) {
    const row = el('div', 'irow' + (r.go ? ' click' : ''));
    const nm = el('div', 'nm'); nm.append(el('span', null, r.label)); if (r.desc) nm.append(el('span', 'd', r.desc));
    const tr = el('div', 'track'); const scale = r.max || max;
    const a = el('div', 'fill'); a.style.width = (100 * (r.value || 0)) / scale + '%'; a.style.background = r.dark != null ? `color-mix(in srgb, ${col} 40%, transparent)` : col; tr.appendChild(a);
    if (r.dark != null) { const b = el('div', 'fill'); b.style.width = (100 * r.dark) / scale + '%'; b.style.background = col; tr.appendChild(b); }
    const v = el('div', 'num', r.num || String(r.value)); if (r.go) v.append(el('span', 'go', ' ▶'));
    row.append(nm, tr, v);
    if (r.go) {
      const go = () => openReplay(r.go.pull, r.go.t);
      row.setAttribute('role', 'button'); row.tabIndex = 0; row.setAttribute('aria-label', `${r.label}: ${r.num}. Watch the worst one`);
      row.addEventListener('click', go); row.addEventListener('keydown', (e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); go(); } });
    }
    box.appendChild(row);
  }
  return box;
}

function issEndings(I) {
  const card = el('div', 'card'); card.id = 'iss-endings';
  card.append(el('h2', null, I.n_nights > 1 ? 'What ended each pull, night by night' : 'What ended each pull'));
  card.append(el('p', 'note', 'Each pull counts once: by what caused its biggest burst of deaths (6 seconds), or the enrage if that came first.'));
  const leg = el('div', 'legend');
  for (const k of I.end_order) {
    const s = el('span', 'pill'); s.style.display = 'inline-flex'; s.style.alignItems = 'center'; s.style.gap = '6px';
    const w = el('span', 'sw'); w.style.background = endColor(k); s.append(w, `${k} · ${I.end_all[k]}`); leg.appendChild(s);
  }
  const rows = el('div', 'iend');
  const all = Object.assign({ night: 'All pulls', pulls: I.n_pulls }, I.end_all);
  for (const r of I.n_nights > 1 ? [all, ...I.endings] : [all]) {
    const row = el('div', 'ierow' + (r === all && I.n_nights > 1 ? ' all' : '')); const lab = el('div'); lab.append(el('b', null, r.night), el('span', 'sub', ` · ${r.pulls} pulls`));
    const bar = el('div', 'iebar'); bar.setAttribute('role', 'img');
    bar.setAttribute('aria-label', `${r.night}: ` + I.end_order.filter((k) => r[k]).map((k) => `${k} ${r[k]}`).join(', '));
    for (const k of I.end_order) {
      const n = r[k] || 0; if (!n) continue;
      const seg = el('div', 'ieseg'); seg.style.flex = `${n} 1 0`; seg.style.background = endColor(k); seg.title = `${k}: ${n} of ${r.pulls}`;
      if (n / r.pulls >= 0.1) seg.textContent = n; bar.appendChild(seg);
    }
    row.append(lab, bar); rows.appendChild(row);
  }
  card.append(leg, rows); return card;
}

function issShort(I) {
  const card = el('div', 'card');
  card.append(el('h2', null, 'The short version'));
  const best = I.best.kill ? `First kill: ${I.best.label}.` : `Best pull: ${I.best.label} at ${I.best.pct.toFixed(1)}%.`;
  card.append(el('p', 'note', `${I.n_pulls} ${pl(I.n_pulls, 'pull')} and ${d3.format(',')(I.n_deaths)} deaths${I.n_nights > 1 ? ` over ${I.n_nights} nights` : ''}. ${best} These are the problems behind most of the wipes, biggest first.`));
  if (!I.cards.length) { card.append(el('p', 'note', 'Not enough pulls yet to see a pattern.')); return card; }
  const ol = el('ol', 'ishort');
  I.cards.forEach((c) => {
    const li = el('li'); const a = el('button', 'ilink'); a.textContent = c.title;
    a.addEventListener('click', () => { const t = $('issue-' + c.key); if (t) t.scrollIntoView({ behavior: 'smooth', block: 'start' }); });
    const meta = el('span', 'sub'); meta.append(`${c.big} ${c.big_lbl} · `, el('span', 'itag ' + c.status.tone, c.status.text));
    li.append(a, meta); ol.appendChild(li);
  });
  card.appendChild(ol); return card;
}

function issCard(c, i) {
  const col = cardColor(c);
  const card = el('div', 'card issue'); card.id = 'issue-' + c.key; card.style.setProperty('--ic', col);
  const head = el('div', 'ihead'); head.append(el('span', 'irank', String(i + 1)), el('h2', null, c.title), el('span', 'itag ' + c.status.tone, c.status.text));
  const grid = el('div', 'igrid'); const main = el('div', 'imain'); const side = el('div', 'iside');
  const big = el('div', 'ibig'); big.append(el('span', 'v', c.big), el('span', 'l', c.big_lbl));
  main.append(big, el('p', 'isum', c.summary));
  for (const s of c.main || []) main.appendChild(issMain(s, col));
  for (const s of c.side || []) side.appendChild(issSide(s));
  grid.append(main, side);
  card.append(head, grid);
  if (c.fixes && c.fixes.length) { const fx = el('div', 'ifix'); fx.appendChild(el('h3', null, 'What to do')); const ul = el('ul'); for (const t of c.fixes) ul.appendChild(el('li', null, t)); fx.appendChild(ul); card.appendChild(fx); }
  if (c.examples && c.examples.length) {
    const wb = el('div', 'iwatch'); wb.appendChild(el('span', 'sub', 'Watch it:'));
    for (const e of c.examples) { const b = el('button', 'chip-btn', '▶ ' + e.label); b.addEventListener('click', () => openReplay(e.pull, e.t)); wb.appendChild(b); }
    card.appendChild(wb);
  }
  return card;
}

function drawIssues() {
  const box = $('issues-body'); const st = dash.data('issues');
  if (st.status !== 'ok') { box.replaceChildren(el('div', 'card empty', 'Loading…')); return; }
  const I = st.data; box.replaceChildren();
  box.append(issShort(I), issEndings(I));
  I.cards.forEach((c, i) => box.appendChild(issCard(c, i)));
}
