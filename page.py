"""The RadioSilence page: team setup, then one card per followed team.

app.py builds this page from the same rows /rows answers with, so the page can only show what the Verdict
needs. The small script does what the server cannot: keep the fan's teams on the phone, send them back on
the next visit.
"""

from html import escape
from urllib.parse import urlencode

from judging import STAY_AWAY_ODDS

NAME = "RadioSilence"
STORAGE_KEY = "radiosilence.teams"
# Until the Presets Spec lands, every card's rules panel states the one rule its dot follows.
RULES = f"Stay away above {STAY_AWAY_ODDS:.0%} from 6:00 left in the 2nd quarter."
DOT_CLASSES = {"Watch": "watch", "Stay away": "stay", "Too early to call": "early"}

STYLE = """
  :root { --ink:#f2efe8; --dim:#8d8a83; --bg:#111214; --card:#1c1d21; --line:#2c2d33;
          --watch:#2e9e5b; --stay:#c0392b; --early:#e3b341; }
  * { box-sizing:border-box; }
  body { margin:0; background:#000; color:var(--ink); font:16px/1.4 -apple-system,system-ui,sans-serif; }
  .phone { max-width:420px; min-height:100vh; margin:0 auto; background:var(--bg); padding-bottom:24px; }
  header { display:flex; justify-content:space-between; align-items:center; padding:14px 18px;
           border-bottom:1px solid var(--line); }
  header b { letter-spacing:.18em; font-size:.8rem; text-transform:uppercase; }
  header .gear { color:var(--dim); font-size:1.3rem; text-decoration:none; }
  h1 { font-size:1rem; text-transform:uppercase; letter-spacing:.12em; color:var(--dim);
       margin:22px 18px 8px; font-weight:600; }
  .picks { display:flex; gap:8px; flex-wrap:wrap; padding:0 18px; }
  .pick { border:1px solid var(--line); background:var(--card); color:var(--ink); border-radius:999px;
          padding:8px 14px; font-size:.95rem; cursor:pointer; }
  .pick input { position:absolute; opacity:0; pointer-events:none; }
  .pick:has(input:checked) { background:var(--ink); color:var(--bg); border-color:var(--ink); }
  .pick:has(input:focus-visible) { outline:2px solid var(--early); outline-offset:2px; }
  .btn { display:block; width:calc(100% - 36px); margin:10px 18px; padding:14px; border-radius:12px;
         border:1px solid var(--line); background:var(--card); color:var(--ink); font-size:1rem;
         text-align:center; text-decoration:none; }
  .btn.primary { background:var(--ink); color:var(--bg); font-weight:600; }
  .card { margin:12px 18px; background:var(--card); border-radius:14px; padding:14px 16px;
          display:grid; grid-template-columns:1fr auto; align-items:start; gap:8px 12px; }
  .card details { grid-column:1; }
  .card summary { display:flex; align-items:center; gap:12px; cursor:pointer; list-style:none; }
  .card summary::-webkit-details-marker { display:none; }
  .card .t { font-weight:600; }
  .card .t small { display:block; color:var(--dim); font-weight:400; }
  .card .rules { margin-top:10px; padding-top:10px; border-top:1px solid var(--line);
                 font-size:.85rem; line-height:1.6; color:var(--dim); }
  .card > button { grid-column:2; grid-row:1; }
  .highlights { border:1px solid var(--line); background:var(--card); color:var(--ink); border-radius:999px;
                padding:8px 10px; font-size:.85rem; }
  .highlights:disabled { opacity:.35; }
  .dot { width:14px; height:14px; border-radius:50%; flex:none; }
  .dot.watch { background:var(--watch); }
  .dot.stay { background:var(--stay); }
  .dot.early { background:var(--early); }
  .dot.none { background:transparent; border:2px solid var(--line); }
  .notice { margin:10px 18px; padding:10px 12px; border-left:3px solid var(--early);
            background:#221f15; font-size:.85rem; }
"""

# Runs before the page paints: a fan who already picked teams goes straight to their cards, and a list
# page saves the picks it was asked for. Without storage the page still works; it just forgets.
REMEMBER_PICKS = """<script>
(function () {
  try {
    const params = new URLSearchParams(location.search);
    const picked = params.getAll("teams").join(",");
    if (picked) { localStorage.setItem("%(key)s", picked); return; }
    if (params.has("setup")) return;
    const saved = localStorage.getItem("%(key)s");
    if (saved) location.replace("/?teams=" + encodeURIComponent(saved));
  } catch (error) {}
})();
</script>""" % {"key": STORAGE_KEY}


def list_href(names):
    """The list screen's address for `names`."""
    return "/?" + urlencode([("teams", name) for name in names])


def setup_href(names):
    """Setup's address, with the fan's `names` already ticked."""
    return "/?" + urlencode([("setup", "1")] + [("teams", name) for name in names])


def preview_words(preview):
    """The Next-game preview's words: day, time and opponent."""
    where = "vs" if preview["home"] else "at"
    return f"{preview['day']}, {preview['time']} {where} {preview['opponent']}"


def notice(text):
    return f'<p class="notice">{escape(text)}</p>' if text else ""


def header(gear_href=None):
    gear = (f'<a class="gear" href="{escape(gear_href)}" aria-label="Teams">⚙︎</a>'
            if gear_href else "")
    return f"<header><b>{NAME}</b> {gear}</header>"


def shell(body, refresh=False, gear_href=None):
    """The page around `body`: its head tags, the script that remembers picks, and the header."""
    refresh_tag = '<meta http-equiv="refresh" content="60">' if refresh else ""
    return f"""<!doctype html>
<html lang="en"><head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<title>{NAME}</title>
<meta name="theme-color" content="#111214">
<link rel="manifest" href="/manifest.webmanifest">
<link rel="icon" href="/icon-180.png">
<link rel="apple-touch-icon" href="/icon-180.png">
<meta name="apple-mobile-web-app-capable" content="yes">
<meta name="apple-mobile-web-app-title" content="{NAME}">
<meta name="apple-mobile-web-app-status-bar-style" content="black-translucent">
{refresh_tag}
{REMEMBER_PICKS}
<style>{STYLE}</style>
</head><body><div class="phone">{header(gear_href)}{body}</div></body></html>"""


def setup_screen(team_names, picked=(), notice_text=None):
    """Setup: every NBA team by abbreviation, the fan's picks ticked, and Done."""
    picks = "".join(
        f'<label class="pick"><input type="checkbox" name="teams" value="{escape(team)}"'
        f'{" checked" if team in picked else ""}>{escape(team)}</label>'
        for team in team_names)
    cancel = (f'<a class="btn" href="{escape(list_href(picked))}">Cancel</a>'
              if picked else "")
    body = f"""<main id="main">
<h1>Which teams do you follow?</h1>
{notice(notice_text)}
<form id="setup" method="get" action="/">
<div class="picks">{picks}</div>
<button class="btn primary" type="submit">Done</button>
{cancel}
</form>
</main>"""
    return shell(body)


def card(row):
    """One followed team's card: a dot carrying the Verdict, its name, and the disabled highlights button."""
    team = escape(row["team"])
    verdict, preview = row["verdict"], row["next_game"]
    if verdict:
        dot = (f'<span class="dot {DOT_CLASSES[verdict]}" role="img" '
               f'aria-label="{escape(verdict)}"></span>')
        line = ""
    else:
        # No Verdict yet: a hollow dot, and the Next-game preview or the row's own words under the name.
        dot = '<span class="dot none" aria-hidden="true"></span>'
        under = escape(preview_words(preview)) if preview else escape(row["detail"] or "")
        line = f"<small>{under}</small>" if under else ""
    return f"""<article class="card" data-team="{team}">
<details><summary>{dot}<span class="t">{team}{line}</span></summary>
<div class="rules">{escape(RULES)}</div></details>
<button class="highlights" disabled>No highlights yet</button>
</article>"""


def list_screen(rows, notice_text=None):
    """The main screen: one card per followed team, refreshing itself every minute."""
    body = f"""<main id="main">
{notice(notice_text)}
{"".join(card(row) for row in rows)}
</main>"""
    return shell(body, refresh=True, gear_href=setup_href([row["team"] for row in rows]))
