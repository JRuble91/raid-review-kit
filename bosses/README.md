# Boss profiles

A profile makes the pages read better for one boss. Without one, everything is worked out from the logs. With one, the tips, names and phase labels come from you.

## Files

- `bosses/<encounter id>.json` is the profile.
- `bosses/<encounter id>.py` is an optional plugin with extra problem checks.
- The encounter id is the `encounter` that `RR.report()` prints. For example, 3420 is Sszorak.
- `3420.json` and `3420.py` are a complete example.

## Profile fields (all optional)

| Field | What it does |
|---|---|
| `guide` | One entry per cause of death (use the exact ability name from the logs), plus `Enrage`. Each entry can have `name`, `group`, `who`, `what` (what the mechanic does), `todo` (one-line advice, shown on the wipe walls and ability cards), `fixes` (a list shown under "What to do" on a problem card), `clip` and `clip2` (https links to a guide or video). |
| `stages` | Labels for how far a pull got: `[stage 0, stage 1, stage 2+]`. Stage = number of phase changes in the pull. Example: `["Wiped in Stage 1", "Reached the winds", "Made it through the winds"]`. |
| `stage_tile` | Label for the overview tile that counts pulls reaching stage 1. |
| `enrage` | Ability names (boss casts or buffs) that mean the boss enraged. Default: anything named "enrage" or "berserk". |
| `enrage_enough_alive` | How many alive is enough to have done the mechanic that prevents the enrage. On Sszorak it's 14, for the Fury soak. |
| `enrage_title` | Title of the enrage wall. |
| `rings` | Debuffs to draw on the replay: `[{"ability": "Virulence", "style": "ring"}, {"ability": "Serpent's Fury", "style": "dash"}]`. Use `ring` for debuffs many people carry, `dash` for a single marked player. Default: picked from the logs. |
| `arena` | `shape` (`circle`, `octagon` or `none`), `r` (edge radius in yards), `view` (half-width shown, in yards), `rotate` (degrees) or `rotate_to` (a debuff name: the replay is turned so where its first holder stood points up). |
| `checkpoint` | `{"t": 75, "alive": 17}`: the "N alive at time T" split used across the page. Default: T from the median 4th death, N = raid size − 3. |
| `cause_alias` | Merge ability names, e.g. `{"Melee": "Boss melee"}`. |
| `events.major` | Boss abilities to show on the timeline and replay. Default: the boss's regular casts linked to the most deaths. |
| `walls` | Hand-written wipe walls, to replace the automatic ones (see `walls_def` in a built page for the shape). |
| `sources` | Links to the guides you used. |

## Writing one for a new boss

1. Build the boss once without a profile and read what it found: the top causes of death, the walls and the problem cards.
2. Read a Mythic guide (Mythic Trap, Method, Wowhead, Icy Veins).
3. Write a `guide` entry for every top cause. Use the ability name exactly as the page shows it. Keep tips to what the guide says and what the logs show.
4. Add `stages` if the boss has phases, and `enrage` / `enrage_enough_alive` if it has a soak or enrage check.
5. Rebuild, read the problem cards again, and save the profile in the kit repo so the next run uses it.

## Plugins

A plugin is for a boss-specific check that the generic detectors can't do. On Sszorak, the plugin checks whether Crosswinds launches set off Cyst wipes.

- Write `def issues(ctx, H): return [cards]` in `bosses/<id>.py`. Cards use the format at the top of `rrlib/issues.py`.
- A card with `"replaces": "cause-<Ability>"` removes the generic card for that cause.
- `ctx` holds the merged pulls, deaths, debuff windows, boss events, the wipe bursts and the raw replay positions.
- `H` holds helpers: `trend`, `status`, `who`, `ex`, `f2`, `pct` and `num`.
- Only claim what the numbers show. The Sszorak plugin only calls Crosswinds the trigger when the data supports it.
