# Agent Instructions

## This project

RadioSilence (called Bad Game Warning until the Boss renamed it on 2026-11-14) tells a fan, without spoilers, whether each followed NBA team's game is worth watching from behind. Its words are in `GLOSSARY.md`; read it before naming anything. Its future is charted as five Wayfinder Maps in Beads (`bd list --label wayfinder:map`); `docs/handoff.html` lays out their open questions for the Boss. The repo, folder and launchd job were renamed to RadioSilence on 2026-11-18; Bead ids keep the `bad_game_warning-` prefix because commits and research notes cite them.

Rules every change must keep:

- The phone never receives anything about a game later than the moment the fan names in the catch-up box score, not even in the page source. With no moment named, only the Verdict and its one-line detail leave the server: no score, clock, quarter or win-probability percentage (the Boss, 2026-11-14).
- The page never makes clear whether a game is over, because a game still going when it ought to have ended gives away overtime. It hides the tip-off time once a game has started, and warns a fan whose only settings judge the final that the timing of a hint can give away overtime (the Boss, 2026-11-14).
- Each Verdict follows the fan's Presets and slider values. No blowout losses holds its Stay away until the opponent's chance drops below the lower line, so a game can go from Stay away back to Watch, and freezes the answer after Freeze at.
- The server stays dependency-free standard-library Python and may be several files: `app.py` serves the page, its static files and the JSON rows, `page.py` renders the page, `judging.py` works out each team's row from ESPN's JSON (allowed by the Spec of bad_game_warning-452), `players.py` judges each tracked player's night and serves this season's rosters, `catchup.py` rebuilds the score, box score and plays as of a fan's moment from the saved play-by-play, and `highlights.py` finds each started game's End Highlights reel on the NBA's YouTube channel.

## Build & Test

```bash
python3 -m unittest                                   # tests (test_app.py, covering judging.py, players.py, presets.py, catchup.py, highlights.py, page.py and app.py)
python3 app.py                                        # serve on port 8765 (PORT to change)
launchctl kickstart -k gui/$UID/com.bradley.radiosilence   # restart the always-on copy after editing
python3 docs/research/backtest.py 2026                # replay the rule over the 2025-26 season
```

## Architecture Overview

`/rows?teams=DAL,BOS` answers with one row per named team for today: its Verdict, or its Next-game preview when no game has started. `judging.py` accepts a name only when ESPN's list of the 30 NBA teams has it, or it is one of the common short names for those teams (NYK, GSW, SAS, NOP, UTA, WAS), then gets the row from ESPN's scoreboard, one summary per started game and a team's schedule only for a preview; any other name gets its own row that says so. Each started game is judged with the fan's picked Presets (Wins for my team, No blowout losses, Close games, High-scoring games), their AND or OR and slider values, and the row never says which Preset fitted. The same answer may carry tracked players named as `players=<ESPN id>:<team>:<name>`, each row naming the player's ESPN id and judging him by his own checks: number targets for points, rebounds, assists, threes made, steals and blocks as `player_<id>_points=30` and the like, double-double and triple-double as `player_<id>_double_double=1`, and his own `player_<id>_join`, all from his usual minutes; `/players` serves this season's NBA rosters, fetched once a day, for setup's search, and a player who did not play stays silent on the list. `presets.py` holds each Preset's name, slider ranges, steps and shipped defaults in one place; `page.py` renders setup's controls from it, and `/presets` serves the same definitions as JSON. `/catchup?teams=DAL&period=3rd&minutes=5&seconds=30` answers with the score, each team's totals, each player's line and minutes, and the plays up to that moment, newest first, rebuilt by `catchup.py` from the game's saved play-by-play and substitution plays; nothing later than the moment is sent, and the answer has no game-over or overtime flag. `app.py` serves those rows, caches ESPN's game JSON for 30 seconds and its team list, rosters and a player's usual minutes for a day, and serves the page at `/`: `page.py` renders setup when the address names no teams or players or asks for it, or one card per team and player when it does: setup shows the fan's teams, a search of this season's rosters that adds a tracked player, each tracked player's own controls (his number target sliders, his double-double and triple-double ticks and his own AND or OR), the Presets as chips, the Any one fits (OR) or All must fit (AND) choice for the Presets, each Preset's sliders built from those definitions with the value in words as it moves and a Reset to default, the shared Judge from and Freeze at sliders as moments (6:00 left in the 2nd), and the warning that a Watch's timing can hint at overtime when every picked setting judges only the final; a team card's rules panel lists the picked Presets, the join and the values, and a player card's lists that player's own checks, never which one fitted; the phone keeps the teams, players and settings in local storage and sends the settings with each request. The page refreshes every 60 seconds, and a web app manifest, an icon and the Apple tags let it sit on the Home Screen as RadioSilence. A launchd agent (`com.bradley.radiosilence.plist`) keeps it running on the Boss's Mac. A started game's row also carries `highlights`, the button state and link: `highlights.py` reads the NBA's uploads playlist page without a key only from 3 hours 30 minutes after the scheduled tip-off, matches both teams and the date, rejects EXTENDED cuts and every team channel's videos by confirming the NBA as the author with keyless oEmbed, and opens the NBA's ending video or its full-game reel two minutes before the end. The page gets only the plain label and link, never a title, thumbnail, length or view count, and a game without a reel yet keeps No highlights yet. Research notes for the Maps are in `docs/research/`.

This project uses **bd** (beads) for issue tracking. Run `bd prime` for full workflow context.

> **Architecture in one line:** Issues live in a local Dolt database
> (`.beads/dolt/`); cross-machine sync uses `bd dolt push/pull` (a
> git-compatible protocol), stored under `refs/dolt/data` on your git
> remote — separate from `refs/heads/*` where your code lives.
> `.beads/issues.jsonl` is a passive export, not the wire protocol.
>
> See [sync-concepts](https://github.com/gastownhall/beads/blob/main/docs/core-concepts/sync-concepts.md)
> for the one-screen overview and anti-patterns (don't treat JSONL as the
> source of truth; don't `bd import` during normal operation; don't
> reach for third-party Dolt hosting before trying the default).

## Quick Reference

```bash
bd ready              # Find available work
bd show <id>          # View issue details
bd update <id> --claim  # Claim work atomically
bd close <id>         # Complete work
bd dolt push          # Push beads data to remote
```

## Non-Interactive Shell Commands

**ALWAYS use non-interactive flags** with file operations to avoid hanging on confirmation prompts.

Shell commands like `cp`, `mv`, and `rm` may be aliased to include `-i` (interactive) mode on some systems, causing the agent to hang indefinitely waiting for y/n input.

**Use these forms instead:**
```bash
# Force overwrite without prompting
cp -f source dest           # NOT: cp source dest
mv -f source dest           # NOT: mv source dest
rm -f file                  # NOT: rm file

# For recursive operations
rm -rf directory            # NOT: rm -r directory
cp -rf source dest          # NOT: cp -r source dest
```

**Other commands that may prompt:**
- `scp` - use `-o BatchMode=yes` for non-interactive
- `ssh` - use `-o BatchMode=yes` to fail instead of prompting
- `apt-get` - use `-y` flag
- `brew` - use `HOMEBREW_NO_AUTO_UPDATE=1` env var

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

<!-- BEGIN BEADS CODEX SETUP: generated by bd setup codex -->
## Beads Issue Tracker

Use Beads (`bd`) for durable task tracking in repositories that include it. Use the `beads` skill at `.agents/skills/beads/SKILL.md` (project install) or `~/.agents/skills/beads/SKILL.md` (global install) for Beads workflow guidance, then use the `bd` CLI for issue operations.

### Quick Reference

```bash
bd ready                # Find available work
bd show <id>            # View issue details
bd update <id> --claim  # Claim work
bd close <id>           # Complete work
bd prime                # Refresh Beads context
```

### Rules

- Use `bd` for all task tracking; do not create markdown TODO lists.
- Run `bd prime` when Beads context is missing or stale. Codex 0.129.0+ can load Beads context automatically through native hooks; use `/hooks` to inspect or toggle them.
- Keep persistent project memory in Beads via `bd remember`; do not create ad hoc memory files.

**Architecture in one line:** issues live in a local Dolt DB; sync uses `refs/dolt/data` on your git remote; `.beads/issues.jsonl` is a passive export. See https://github.com/gastownhall/beads/blob/main/docs/core-concepts/sync-concepts.md for details and anti-patterns.
<!-- END BEADS CODEX SETUP -->

<!-- gitnexus:start -->
# GitNexus — Code Intelligence

This project is indexed by GitNexus as **radiosilence** (1016 symbols, 2726 relationships, 74 execution flows).

> Index stale? Run `node .gitnexus/run.cjs analyze --index-only` from the project root — it auto-selects an available runner. No `.gitnexus/run.cjs` yet? Bootstrap with `npx`, `bunx`, or `pnpm dlx` — e.g. `bunx gitnexus@latest analyze` (npm 11 npx crash; #1939).

## Always Do

- **MUST run impact before editing.** Use `impact({target: "symbolName", direction: "upstream"})` or `node .gitnexus/run.cjs impact "symbolName" --direction upstream --repo .`; report callers, processes, and risk. Never substitute grep for graph analysis.
- **MUST analyze graph changes before committing.** Use `detect_changes({scope: "all"})` (MCP) or `node .gitnexus/run.cjs detect-changes --scope all --repo .` (CLI fallback). `partial: true` or `truncated: true` is not a clean check — a zero means unseen, not unaffected; re-run it. For regression review: `detect_changes({scope: "compare", base_ref: "main"})` or `node .gitnexus/run.cjs detect-changes --scope compare --base-ref "main" --repo .`.
- MUST warn on HIGH/CRITICAL `risk` pre-edit; never use `riskSharedAxes` to waive a HIGH/CRITICAL `risk` warning. Compare File/symbol: MCP File omits axes; Graph-RAG expands File.
- **MUST treat `risk: UNKNOWN` as unresolved, not as low.** An empty caller set is not evidence the symbol is unused — it can also mean the callers are not resolvable by the index (plain-object property access, dynamic dispatch, cross-language calls). `impact` pairs `UNKNOWN` with a `riskNote` saying so. Confirm with a text search before treating the symbol as safe to change or delete; do not proceed on the strength of a zero.
- **MUST use `query({search_query: "concept"})` for concepts/flows, `context({name: "symbolName"})` for a named symbol, or `impact` for blast radius, on read-only callers, dependencies, imports, or execution flow.** Graph first; text search only for empty/`UNKNOWN`/literals.
- For security review, `explain({target: "fileOrSymbol"})` lists taint findings (source→sink flows; needs `analyze --pdg`).

## Never Do

- NEVER edit a function, class, or method before MCP/CLI impact analysis.
- NEVER ignore HIGH or CRITICAL risk warnings from impact analysis, and never read `UNKNOWN` as an all-clear — it means the walk could not answer, which is the one verdict that requires confirming by other means.
- NEVER rename symbols with find-and-replace — use `rename` which understands the call graph.
- NEVER commit before MCP/CLI graph change analysis.

## Resources

| Resource | Use for |
| --- | --- |
| `gitnexus://repo/radiosilence/context` | Codebase overview, check index freshness |
| `gitnexus://repo/radiosilence/clusters` | All functional areas |
| `gitnexus://repo/radiosilence/processes` | All execution flows |
| `gitnexus://repo/radiosilence/process/{name}` | Step-by-step execution trace |

## CLI

| Task | Read this skill file |
| --- | --- |
| Understand architecture / "How does X work?" | `.claude/skills/gitnexus-exploring/SKILL.md` |
| Blast radius / "What breaks if I change X?" | `.claude/skills/gitnexus-impact-analysis/SKILL.md` |
| Trace bugs / "Why is X failing?" | `.claude/skills/gitnexus-debugging/SKILL.md` |
| Rename / extract / split / refactor | `.claude/skills/gitnexus-refactoring/SKILL.md` |
| Tools, resources, schema reference | `.claude/skills/gitnexus-guide/SKILL.md` |
| Index, status, clean, wiki CLI commands | `.claude/skills/gitnexus-cli/SKILL.md` |

<!-- gitnexus:end -->
