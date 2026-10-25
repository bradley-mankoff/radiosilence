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

Bad Game Warning tells one fan, without spoilers, whether that day's Dallas Mavericks game is worth watching from behind. Its words are in `GLOSSARY.md`; read it before naming anything. Its future is charted as five Wayfinder Maps in Beads (`bd list --label wayfinder:map`); `docs/handoff.html` lays out their open questions for the Boss.

Rules every change must keep:

- The phone never receives the score, clock, quarter or win-probability percentage, not even in the page source. Only the Verdict and its one-line detail leave the server.
- The Verdict follows only the latest Reading, so a game can go from Stay away back to Watch.
- `app.py` stays one dependency-free Python file until a Spec says otherwise.

## Build & Test

```bash
python3 -m unittest                                   # tests (test_app.py)
python3 app.py                                        # serve on port 8765 (PORT to change)
launchctl kickstart -k gui/$UID/com.bradley.bad-game-warning   # restart the always-on copy after editing
python3 docs/research/backtest.py 2026                # replay the rule over the 2025-26 season
```

## Architecture Overview

`app.py` answers each page load by fetching the Mavericks schedule from ESPN's public site API, finding today's game, and, if it has tipped off, fetching that game's summary and judging its latest win-probability Reading against the Stay away line (95%) inside the Judging window (6:00 left in the 2nd quarter onward). It renders one full-screen colour page that refreshes every 60 seconds. A launchd agent (`com.bradley.bad-game-warning.plist`) keeps it running on the Boss's Mac. Research notes for the Maps are in `docs/research/`.
