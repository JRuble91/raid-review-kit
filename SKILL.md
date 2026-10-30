---
name: raid-review
description: Build World of Warcraft raid review dashboards (biggest problems, wipe map, per-player reports, replays) from Warcraft Logs and Wipefest for any guild and boss, and publish them. Use when given a Warcraft Logs report or guild link, or asked for a raid review or dashboard.
---

# Raid review

Turns Warcraft Logs reports into review pages for any guild and boss. Each page has a Biggest problems tab, then an overview, the wipe map, a per-player report, and a top-down replay of every pull. With several nights of the same boss it also builds an every-pull page that compares the nights.

## Settings (people you share this with change these)

- **KIT_REPO**: `JRuble91/raid-review-kit`. This is the GitHub repo with the code: fetch.js, rr.py, rrlib/, template/, bosses/. If you got this skill from someone else, fork their kit and put your fork here. Boss profiles you add are saved there.
- Each run asks where the pages go, unless the person already said.
  - **GitHub Pages**: a repo like `you/guild-reviews`, with Pages turned on for main / root.
  - **claude.ai page**: an Artifact.

## What you need

- **A browser that can open warcraftlogs.com and wipefest.gg.** Use the built-in browser (Claude desktop app) or Claude in Chrome. Read that browser's skill first. The shell can't reach those sites.
- **A way to publish.** For GitHub Pages: git push access to the output repo, or Claude in Chrome signed in to GitHub (upload page). For claude.ai: the Artifact tool.
- **Python 3.** It uses the standard library only.

## Steps

### 1. Work out what to build

- **Inputs** can be any of:
  - a report link (`warcraftlogs.com/reports/<code>`)
  - a guild link (`warcraftlogs.com/guild/...`), or "last night" plus a guild
  - several reports for one week
- **Output:** ask where the pages go (GitHub Pages repo, or a claude.ai page) unless the person said.
- **Get the kit** with `git clone --depth 1 https://github.com/<KIT_REPO>.git kit`. If the clone fails, ask the person to attach the kit files.
- **Get the existing site**, if it already exists:
  - GitHub: clone the output repo. Earlier nights' raw data is in its `data/` folder.
  - claude.ai: read its `data/*.json` files with the Artifact tool (`read`, `path`).
  - Work in a folder `site/` with `site/data/`.

### 2. Load the collector in the browser

Open a tab on `https://www.warcraftlogs.com` and run this with the browser's JavaScript tool:
```js
(0, eval)(await (await fetch('https://raw.githubusercontent.com/<KIT_REPO>/main/fetch.js')).text())
```
If the fetch is blocked, paste the contents of `kit/fetch.js` instead. It should return `raid-review-kit collector v1 ready`.

- Guild link: `await RR.reports('<guild reports-list id or guild page path>')` lists the reports with their dates. Pick the ones asked for. "This week" means every raid night since the last weekly reset.
- `await RR.report('<code>')` lists that report's bosses: encounter id, difficulty (3 Normal, 4 Heroic, 5 Mythic), pulls, kills and best %. Pick the boss being progressed: the most pulls at the highest difficulty, unless the person names one.

### 3. Collect

For each report and boss, run these in the Warcraft Logs tab:
1. `RR.collect('<code>', <encounter>, <difficulty>)` collects deaths with their last hits, boss casts, boss debuffs and buffs, phases, and replay positions. It takes about 2–4 minutes for 40 pulls.
2. Poll `RR.status()` every ~30 s. The tool times out at 45 s, so never wait inside one call longer than ~35 s. If the job errors, read `RR.status().error`, and retry once.
3. When it's done, run `RR.parts()`. Then run `RR.dump('W<code>', i)` once for each `i` from 0 to parts−1, each in its own call.
   - Each result is saved to a file, because it is too big to show.
   - The link to a remote computer cuts single results off around 260K characters, so never dump the whole thing in one call.
4. In the shell: `python3 kit/rr.py extract W<code> site/data/<code>-<encounter>-<difficulty>.wcl.json`. If it can't find the saved files, pass `--from <path>` with the path the tool printed.

Then Wipefest. It's optional but adds mechanic ranks against other raids and per-player counts.
1. Get the fight ids with `await RR.fightIds('<code>', <encounter>, <difficulty>)` in the Warcraft Logs tab.
2. Open a second tab on `https://www.wipefest.gg/report/<code>` and load the collector there too.
3. Run `RR.collectWipefest('<code>', <encounter>, [fight ids])`.
4. Poll `RR.status()`, then dump with marker `F<code>`. Extract to `site/data/<code>-<encounter>-<difficulty>.wf.json`.
- If every fight errors, Wipefest hasn't processed the report. Leave the page open a minute and retry once. After that, carry on without it.

### 4. Make sure the boss has a profile

- `kit/bosses/<encounter>.json` is the boss profile; `kit/bosses/README.md` explains every field. If one exists, use it.
- If it doesn't (a new boss), build once without one first. Then:
  1. Run `python3 kit/rr.py site site --guild "<Guild>"` and read what it found: the top causes of death, the walls and the problems. To print the meta, use `python3 -c "import sys,json,glob; sys.path.insert(0,'kit'); from rrlib import build as B; n=[B.load_night(f, f.replace('.wcl.','.wf.')) for f in sorted(glob.glob('site/data/*-<encounter>-<difficulty>.wcl.json'))]; d=B.page_data(n, B.load_profile(<encounter>,'kit')); print(json.dumps(d['meta'], indent=1)); [print(c['title'], '|', c['summary']) for c in d['issues']['cards']]"`.
  2. Research the boss: search the web for its Mythic guide on Mythic Trap, Method, Wowhead or Icy Veins, and read it.
  3. Write `kit/bosses/<encounter>.json`:
     - a `guide` entry (what, todo, fixes, clip) for each of the top causes and for `Enrage` if the boss has one
     - `stages` names, if the boss has phases
     - `enrage` ability names and `enrage_enough_alive`
     - `rings`, if the automatic ones are wrong
     - `arena`, if you know the room shape
  4. Keep every tip to what the guides say and what the logs show. Never invent mechanics.
  5. Rebuild and read the problems again.
- A boss plugin (`bosses/<encounter>.py`) is for a boss-specific check the generic detectors can't do. `bosses/3420.py` is an example. Only write one when the logs clearly support it.

### 5. Build and check

- Run `python3 kit/rr.py site site --guild "<Guild>"`. It builds one page per night, an `-all.html` page when there are 2+ nights of the same boss, and `index.html`. If the site already has its own landing page, add `--keep-index` and add cards to that page by hand.
- Before publishing, read the problem cards. Each card's numbers must follow from the data, and its wording mustn't claim more than the numbers show. Fix the profile or wording, not the data.
- Smoke-test every page in Playwright at 1280 and 390 wide, clicking each tab:
  - no console errors
  - no "NaN" or "undefined"
  - no sideways scroll
  - the replay plays

### 6. Publish

- **GitHub Pages:**
  - Push the new files: the pages, `index.html` and `data/*.json`.
  - With git access, commit and push.
  - Otherwise use Claude in Chrome on `https://github.com/<repo>/upload/main` (and `/upload/main/data` for the data). File uploads must come from `/mnt/user-data/uploads/`, so copy the files there first, then commit.
  - Check that the commit matches with a fresh clone and `cmp`.
  - Then wait for the Pages build and load the live page.
- **claude.ai:**
  - Publish with the Artifact tool. The landing page is the page, and the review pages and `data/*.json` go in `files`.
  - Republish to the same URL later to add nights.

### 7. Report back

- Send the links.
- Give each night's pull count and best pull, plus the top 2–3 problems in a line each.
- Mention anything left out, such as Wipefest missing for a night.
