# raid-review-kit

Raid review dashboards for any World of Warcraft guild and boss, built from Warcraft Logs (including its replay) and Wipefest. A Claude skill does the work: give it a report or guild link and it collects the logs, finds the biggest problems, builds the pages and publishes them.

**Each review has:**
- **Biggest problems:** what keeps ending your pulls, ranked, with trends across nights, who's involved, what to do, and buttons that jump to the moment in the replay.
- **Overview:** what ended each pull, boss health at every pull, top killers, and Wipefest ranks against other raids.
- **The fight:** a wipe map of every death on the boss timeline, plus a card for each ability that killed people.
- **Your report:** each player's deaths, what got them, and how they compare with the raid.
- **Replay & pulls:** a top-down replay of every pull, with debuff rings, boss casts and deaths.

With two or more nights of the same boss you also get an every-pull page that merges them and shows how each problem changed.

## Using it

1. Add the skill in `SKILL.md` to Claude.
2. Give it a Warcraft Logs report or guild link and say where the pages go: a GitHub Pages repo, or a claude.ai page.
3. Claude needs a browser that can open warcraftlogs.com and wipefest.gg: the Claude desktop app's built-in browser, or Claude in Chrome. To publish to GitHub without connecting GitHub to Claude, it uses Claude in Chrome signed in to GitHub.

## If someone shared this with you

1. Fork this repo (or use it as a template) so the code and your boss profiles live in your own GitHub.
2. In `SKILL.md`, change `KIT_REPO` to your fork. Keep the fork public so Claude can load `fetch.js` from it.
3. For GitHub Pages output, make a repo for your guild's pages and turn on Pages (Settings → Pages → main / root).

## What's in here

| Path | What it is |
|---|---|
| `fetch.js` | Browser-side collector. It reads Warcraft Logs' own site data (no API key; public reports work signed out) and Wipefest's API. |
| `rr.py` | Command line: `extract` (save a collector result), `site` (build every page), `summary`. |
| `rrlib/` | Normalizing any boss's data, the timeline, wipe walls and replay, the problem detectors, and page assembly. |
| `template/` | The page (HTML, CSS, JS) and the landing page. |
| `bosses/` | Optional per-boss profiles and plugins. See `bosses/README.md`. Sszorak (3420) is the worked example. |

## How the numbers are made

- **Death cause:** the killing blow Warcraft Logs records. When there isn't one (knocked off a platform, fall damage), the cause is the newest boss hit in the death's last three hits. Background damage that shows up in most deaths is skipped.
- **What ended a pull:** the ability behind the biggest burst of deaths in 6 seconds, or the enrage if that came first.
- **"N alive at time T":** splits pulls by how many people were still up at a checkpoint near the usual 4th death. It's the clearest predictor of how far a pull gets.
- **Wipefest ranks:** each mechanic against other raids on the same boss (100 is best), with Wipefest's 4-death cutoff. They're averaged over pulls.
- **Replay:** positions are taken once a second, so fast knockbacks are approximate.

The collector uses Warcraft Logs' website endpoints rather than its official API, so a site change can break collection until `fetch.js` is updated.
