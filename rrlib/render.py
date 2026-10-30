"""Assemble review pages and the landing page from page data."""
import html, json, os

T = lambda kit, name: open(os.path.join(kit, 'template', name), encoding='utf-8').read()


def page(kit, data, title, default_pull):
    shell = T(kit, 'shell.html')
    body = '<style>\n' + T(kit, 'page.css') + '\n</style>\n' + T(kit, 'page.html') + '\n<script>\n' + T(kit, 'page.js') + '\n' + T(kit, 'issues.js') + '\ndash.onData(render);\n</script>\n'
    out = shell.replace('{{TITLE}}', html.escape(title))
    out = out.replace('{{DEFAULTS}}', json.dumps({'cutoff': 4, 'player': None, 'pull': default_pull}))
    out = out.replace('{{DATA}}', json.dumps(data, ensure_ascii=False, separators=(',', ':')).replace('</', '<\\/'))
    return out.replace('{{PAGE}}', body)


def landing(kit, guild, series):
    """series: [{title, boss, difficulty, all: {file, n_pulls, best, nights} or None, nights: [{file, label, n_pulls, best, kill}]}]"""
    tpl = T(kit, 'landing.html')
    blocks = []
    for s in series:
        cards = []
        if s.get('all'):
            a = s['all']
            cards.append(f'''    <a class="card all" href="{a['file']}">
      <h3>Every pull · {a['n_pulls']} pulls, {html.escape(a['nights'][0])} to {html.escape(a['nights'][-1])}</h3>
      <p>All {len(a['nights'])} nights in one log, with the biggest problems across every wipe ranked first. {html.escape(a['best'])}</p>
      <span class="go">Open the all-pulls review →</span>
    </a>''')
        for n in s['nights']:
            cards.append(f'''    <a class="card" href="{n['file']}">
      <h3>{html.escape(n['label'])} · Review + Replay</h3>
      <p>{n['n_pulls']} pulls. {html.escape(n['best'])} What ended our pulls, the wipe map, your own report and a replay of every pull.</p>
      <span class="go">Open the {html.escape(n['label'])} review →</span>
    </a>''')
        blocks.append(f'  <h2>{html.escape(s["title"])}</h2>\n  <div class="cards">\n' + '\n'.join(cards) + '\n  </div>')
    return tpl.replace('{{GUILD}}', html.escape(guild or 'Raid')).replace('{{BLOCKS}}', '\n'.join(blocks))
