# Project Instructions for AI Agents

This file provides instructions and context for AI coding agents working on this project.

<!-- BEGIN BEADS INTEGRATION v:1 profile:minimal hash:1105d646 -->
## Beads Issue Tracker

This project uses **bd (beads)** for issue tracking. Run `bd prime` to see full workflow context and commands.

### Quick Reference

```bash
bd ready              # Find available work
bd show <id>          # View issue details
bd update <id> --claim  # Claim work
bd close <id>         # Complete work
```

### Rules

- Use `bd` for ALL task tracking — do NOT use TodoWrite, TaskCreate, or markdown TODO lists
- Run `bd prime` for detailed command reference and session close protocol
- Use `bd remember` for persistent knowledge — do NOT use MEMORY.md files

**Architecture in one line:** issues live in a local Dolt DB; sync uses `refs/dolt/data` on your git remote; `.beads/issues.jsonl` is a passive export. See https://github.com/gastownhall/beads/blob/main/docs/core-concepts/sync-concepts.md for details and anti-patterns.

## Agent Context Profiles

The managed Beads block is task-tracking guidance, not permission to override repository, user, or orchestrator instructions.

- **Conservative (default)**: Use `bd` for task tracking. Do not run git commits, git pushes, or Dolt remote sync unless explicitly asked. At handoff, report changed files, validation, and suggested next commands.
- **Minimal**: Keep tool instruction files as pointers to `bd prime`; use the same conservative git policy unless active instructions say otherwise.
- **Team-maintainer**: Only when the repository explicitly opts in, agents may close beads, run quality gates, commit, and push as part of session close. A current "do not commit" or "do not push" instruction still wins.

## Session Completion

This protocol applies when ending a Beads implementation workflow. It is subordinate to explicit user, repository, and orchestrator instructions.

1. **File issues for remaining work** - Create beads for anything that needs follow-up
2. **Run quality gates** (if code changed) - Tests, linters, builds
3. **Update issue status** - Close finished work, update in-progress items
4. **Handle git/sync by active profile**:
   ```bash
   # Conservative/minimal/default: report status and proposed commands; wait for approval.
   git status

   # Team-maintainer opt-in only, unless current instructions forbid it:
   git pull --rebase
   git push
   git status
   ```
5. **Hand off** - Summarize changes, validation, issue status, and any blocked sync/commit/push step

**Critical rules:**
- Explicit user or orchestrator instructions override this Beads block.
- Do not commit or push without clear authority from the active profile or the current user request.
- If a required sync or push is blocked, stop and report the exact command and error.
<!-- END BEADS INTEGRATION -->


## This project

RadioSilence (called Bad Game Warning until the Boss renamed it on 2026-11-14) tells a fan, without spoilers, whether each followed NBA team's game is worth watching from behind. Its words are in `GLOSSARY.md`; read it before naming anything. Its future is charted as five Wayfinder Maps in Beads (`bd list --label wayfinder:map`); `docs/handoff.html` lays out their open questions for the Boss. The repo, folder and launchd job were renamed to RadioSilence on 2026-11-18; Bead ids keep the `bad_game_warning-` prefix because commits and research notes cite them.

Rules every change must keep:

- The phone never receives anything about a game later than the moment the fan names in the catch-up box score, not even in the page source. With no moment named, only the Verdict and its one-line detail leave the server: no score, clock, quarter or win-probability percentage (the Boss, 2026-11-14).
- The page never makes clear whether a game is over, because a game still going when it ought to have ended gives away overtime. It hides the tip-off time once a game has started, and warns a fan whose only settings judge the final that the timing of a hint can give away overtime (the Boss, 2026-11-14).
- Each Verdict follows the fan's Presets and slider values. No blowout losses holds its Stay away until the opponent's chance drops below the lower line, so a game can go from Stay away back to Watch, and freezes the answer after Freeze at.
- The server stays dependency-free standard-library Python and may be several files: `app.py` serves the page, its static files and the JSON rows, `page.py` renders the page, `judging.py` works out each team's row from ESPN's JSON (allowed by the Spec of bad_game_warning-452), and `catchup.py` rebuilds the score, box score and plays as of a fan's moment from the saved play-by-play.

## Build & Test

```bash
python3 -m unittest                                   # tests (test_app.py, covering judging.py, presets.py, catchup.py, page.py and app.py)
python3 app.py                                        # serve on port 8765 (PORT to change)
launchctl kickstart -k gui/$UID/com.bradley.radiosilence   # restart the always-on copy after editing
python3 docs/research/backtest.py 2026                # replay the rule over the 2025-26 season
```

## Architecture Overview

`/rows?teams=DAL,BOS` answers with one row per named team for today: its Verdict, or its Next-game preview when no game has started. `judging.py` accepts a name only when ESPN's list of the 30 NBA teams has it, or it is one of the common short names for those teams (NYK, GSW, SAS, NOP, UTA, WAS), then gets the row from ESPN's scoreboard, one summary per started game and a team's schedule only for a preview; any other name gets its own row that says so. Each started game is judged with the fan's picked Presets (Wins for my team, No blowout losses), their AND or OR and slider values, and the row never says which Preset fitted. `presets.py` holds each Preset's name, slider ranges and shipped defaults in one place, and `/presets` serves that one definition to the page. `/catchup?teams=DAL&period=3rd&minutes=5&seconds=30` answers with the score, each team's totals, each player's line and minutes, and the plays up to that moment, newest first, rebuilt by `catchup.py` from the game's saved play-by-play and substitution plays; nothing later than the moment is sent, and the answer has no game-over or overtime flag. `app.py` serves those rows, caches ESPN's game JSON for 30 seconds and its team list for a day, and serves the page at `/`: `page.py` renders team setup when the address names no teams, or one card per team when it does; the phone keeps the picks in local storage so the next visit opens them. The page refreshes every 60 seconds, and a web app manifest, an icon and the Apple tags let it sit on the Home Screen as RadioSilence. A launchd agent (`com.bradley.radiosilence.plist`) keeps it running on the Boss's Mac. Research notes for the Maps are in `docs/research/`.
