"""The RadioSilence page: setup with the fan's teams, tracked players and their own checks, and the Presets,
one card per followed team or player, and the catch-up screen a card opens.

app.py builds this page from the same rows /rows answers with, so a list can only show what the Verdict
needs; the catch-up screen is the one screen that shows a game's score and plays, and only those at or
before the moment the fan names. The small scripts do what the server cannot: find a player in the served
rosters, keep the fan's teams, players, settings and each game's catch-up moment on the phone, send them
back on the next visit, and show each slider's value as the fan moves it. The Presets, their sliders and
their words all come from presets.py, each player's checks from players.py, and the catch-up periods from
catchup.py, so the page and the answers read one definition.
"""

import json
from collections import namedtuple
from html import escape
from urllib.parse import urlencode

import catchup
import players
import presets

NAME = "RadioSilence"
TEAMS_KEY = "radiosilence.teams"
PLAYERS_KEY = "radiosilence.players"
SETTINGS_KEY = "radiosilence.settings"
# The id setup's player template names its controls by until the script fills in the chosen player's id.
NEW_PLAYER = "__PLAYER__"
DOT_CLASSES = {"Watch": "watch", "Stay away": "stay", "Too early to call": "early"}
JOIN_WORDS = {"OR": "Any one fits (OR)", "AND": "All must fit (AND)"}
QUARTERS = {1: "1st", 2: "2nd", 3: "3rd", 4: "4th"}
OVERTIME_WARNING = ("Every Preset you picked judges only the final, so if you remember when the game "
                    "tipped off, the time a Watch appears, or doesn't, can hint at overtime.")
# What one request's page carries: the fan's own team picks, the fan's Presets and slider values, and each
# tracked player with his own checks. Every screen and every link needs all three, so they travel as one
# value, and `teams` is only ever the fan's picks, never the team a tracked player happens to play for.
Picks = namedtuple("Picks", "teams fan following")

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
  h1, h2 { font-size:1rem; text-transform:uppercase; letter-spacing:.12em; color:var(--dim);
           margin:22px 18px 8px; font-weight:600; }
  .picks { display:flex; gap:8px; flex-wrap:wrap; padding:0 18px; }
  .search { padding:0 18px; }
  .search input { width:100%; background:var(--card); color:var(--ink); border:1px solid var(--line);
                  border-radius:12px; padding:12px; font:inherit; }
  #player-results { padding:8px 0 0; }
  .pick { border:1px solid var(--line); background:var(--card); color:var(--ink); border-radius:999px;
          padding:8px 14px; font-size:.95rem; cursor:pointer; }
  .pick input { position:absolute; opacity:0; pointer-events:none; }
  .pick:has(input:checked) { background:var(--ink); color:var(--bg); border-color:var(--ink); }
  .pick:has(input:focus-visible) { outline:2px solid var(--early); outline-offset:2px; }
  .pick.on { background:var(--ink); color:var(--bg); border-color:var(--ink); }
  a.pick { text-decoration:none; }
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
  .card .rules p { margin:0 0 4px; }
  .card .actions { grid-column:2; grid-row:1; display:flex; flex-direction:column; gap:6px; }
  .watching { border:1px solid var(--line); background:var(--ink); color:var(--bg); border-radius:999px;
              padding:8px 10px; font-size:.85rem; text-align:center; text-decoration:none;
              white-space:nowrap; }
  .highlights { border:1px solid var(--line); background:var(--card); color:var(--ink); border-radius:999px;
                padding:8px 10px; font-size:.85rem; text-align:center; text-decoration:none; }
  .highlights:disabled { opacity:.35; }
  .dot { width:14px; height:14px; border-radius:50%; flex:none; }
  .dot.watch { background:var(--watch); }
  .dot.stay { background:var(--stay); }
  .dot.early { background:var(--early); }
  .dot.none { background:transparent; border:2px solid var(--line); }
  .notice { margin:10px 18px; padding:10px 12px; border-left:3px solid var(--early);
            background:#221f15; font-size:.85rem; }
  .note { margin:10px 18px; color:var(--dim); font-size:.85rem; }
  .group[hidden], .notice[hidden] { display:none; }
  .pickers { display:flex; gap:8px; padding:0 18px; }
  .pickers select { flex:1; min-width:0; background:var(--card); color:var(--ink);
                    border:1px solid var(--line); border-radius:10px; padding:10px; font-size:1rem; }
  .score { display:flex; justify-content:space-around; align-items:baseline; margin:14px 18px;
           font-size:1.6rem; font-weight:700; }
  .score small { display:block; font-size:.75rem; color:var(--dim); font-weight:400; text-align:center; }
  table.box { width:calc(100% - 36px); margin:0 18px 10px; border-collapse:collapse; font-size:.8rem;
              font-variant-numeric:tabular-nums; }
  table.box th, table.box td { padding:6px 4px; text-align:right; border-bottom:1px solid var(--line); }
  table.box th:first-child, table.box td:first-child { text-align:left; }
  table.box th { color:var(--dim); font-weight:500; }
  table.box tr.total td { font-weight:600; }
  .pbp div { padding:8px 18px; border-bottom:1px solid var(--line); font-size:.9rem; }
  .pbp b { color:var(--dim); font-weight:500; margin-right:8px; }
  .slider { padding:6px 18px 10px; }
  .player-head { display:flex; flex-wrap:wrap; align-items:center; justify-content:space-between;
                 gap:4px 12px; margin:18px 18px 4px; }
  .player-head h2 { margin:0; }
  .join { display:flex; gap:6px; }
  .join .pick { padding:4px 10px; font-size:.75rem; }
  .slider label { display:flex; justify-content:space-between; gap:12px; font-size:.9rem;
                  color:var(--dim); }
  .slider input { width:100%; accent-color:var(--early); }
  .reset { display:block; margin:0 18px 10px; padding:0; background:none; border:0; color:var(--dim);
           font:inherit; font-size:.85rem; text-decoration:underline; cursor:pointer; }
"""

# The script every page runs before it paints: a list page keeps the picks and settings it was asked for,
# a fan who already picked teams or players goes straight to their cards, and the settings go with them.
# Without storage the page still works; it just forgets.
REMEMBER_PICKS = """<script>
(function () {
  const TEAMS = "%(teams_key)s", PLAYERS = "%(players_key)s", SETTINGS = "%(settings_key)s",
        SLIDERS = %(sliders)s;
  function saved() {
    try { return JSON.parse(localStorage.getItem(SETTINGS)); } catch (error) { return null; }
  }
  function store(settings) {
    try { localStorage.setItem(SETTINGS, JSON.stringify(settings)); } catch (error) {}
  }
  // The settings a query names: its Presets, its tracked players, the Presets' join, and a value for each
  // slider or player check it carries.
  function named(query) {
    const picked = query.getAll("presets").join(",").split(",").filter(key => key);
    const tracked = query.getAll("players").flatMap(value => value.split(",")).filter(token => token);
    const values = {};
    for (const parameter of new Set(query.keys()))
      if (SLIDERS.includes(parameter) || parameter.startsWith("player_"))
        values[parameter] = query.get(parameter);
    return {presets: picked, players: tracked,
            join: query.get("join") === "AND" ? "AND" : "OR", values: values};
  }
  // The fan's saved settings as query parameters, and nothing when the phone holds none.
  function settingsQuery() {
    const settings = saved();
    if (!settings) return "";
    const pairs = [["presets", settings.presets.join(",")], ["join", settings.join]];
    for (const player of settings.players || []) pairs.push(["players", player]);
    for (const [parameter, value] of Object.entries(settings.values || {}))
      pairs.push([parameter, value]);
    return "&" + pairs.map(pair => pair[0] + "=" + encodeURIComponent(pair[1])).join("&");
  }
  try {
    const params = new URLSearchParams(location.search);
    const picks = params.getAll("teams").join(",");
    const tracked = params.getAll("players").join(",");
    const settingsNamed = params.has("presets") || params.has("join") || params.has("players")
      || SLIDERS.some(parameter => params.has(parameter));
    if (picks || tracked || settingsNamed) {
      localStorage.setItem(TEAMS, picks);
      localStorage.setItem(PLAYERS, tracked);
      if (settingsNamed) store(named(params));
      return;
    }
    if (params.has("setup")) return;
    const savedTeams = localStorage.getItem(TEAMS);
    const savedPlayers = localStorage.getItem(PLAYERS);
    const query = [savedTeams ? "teams=" + encodeURIComponent(savedTeams) : "",
                   savedPlayers ? "players=" + encodeURIComponent(savedPlayers) : ""]
                    .filter(part => part).join("&");
    if (query) location.replace("/?" + query + settingsQuery());
  } catch (error) {}
})();
</script>""" % {"teams_key": TEAMS_KEY, "players_key": PLAYERS_KEY, "settings_key": SETTINGS_KEY,
                       "sliders": json.dumps([slider.parameter for slider in presets.ALL_SLIDERS])}

# The setup screen's script: it shows the picked Presets' sliders, finds a player by a part of the name and
# gives the chosen player his own controls, shows each value in words, keeps the fan's settings on the phone
# as they change, and puts a Preset's sliders back on Reset to default.
CONTROLS = """<script>
(function () {
  const form = document.getElementById("setup");
  if (!form) return;
  const SETTINGS = "%(settings_key)s";
  // The picks and the Presets' join, which are not values: every other control the form submits is one.
  const PICKS = ["teams", "presets", "join", "players"];
  const chips = Array.from(form.querySelectorAll('input[name="presets"]'));
  // Only a section that names a Preset hides and shows with that Preset's chip; the shared Timing
  // sliders are always on screen, and each tracked player's section sits with his chip.
  const groups = Array.from(form.querySelectorAll("section[data-preset]"));
  const finalOnly = new Set(chips.filter(chip => "finalOnly" in chip.dataset).map(chip => chip.value));
  const panels = form.querySelector("#player-checks");
  const template = document.getElementById("player-checks-template");
  const picks = form.querySelector("#player-picks");
  const search = form.querySelector("#player-search");
  const results = form.querySelector("#player-results");
  const done = form.querySelector("#done");
  const warning = form.querySelector("#overtime");
  let roster = [];

  function settings() {
    const values = {};
    for (const field of form.elements) {
      if (!field.name || PICKS.includes(field.name)) continue;
      if ((field.type === "checkbox" || field.type === "radio") && !field.checked) continue;
      values[field.name] = field.value;
    }
    return {
      presets: chips.filter(chip => chip.checked).map(chip => chip.value),
      players: Array.from(form.querySelectorAll('input[name="players"]'))
        .filter(pick => pick.checked).map(pick => pick.value),
      join: form.querySelector('input[name="join"]:checked').value,
      values: values,
    };
  }
  function showValue(slider) {
    const shown = slider.closest(".slider").querySelector("[data-shown]");
    shown.textContent = JSON.parse(slider.dataset.labels)[slider.value];
  }
  function remember() {
    try { localStorage.setItem(SETTINGS, JSON.stringify(settings())); } catch (error) {}
  }
  // A player's own checks keep the overtime warning away: a number to reach, or a double tick.
  function playerChecks() {
    return Array.from(form.elements).some(field => field.name && field.name.startsWith("player_")
      && (field.type === "range" ? Number(field.value) > 0 : field.type === "checkbox" && field.checked));
  }
  function show() {
    const chosen = settings();
    const picked = chosen.presets;
    for (const group of groups) group.hidden = !picked.includes(group.dataset.preset);
    done.disabled = picked.length === 0 && chosen.players.length === 0;
    warning.hidden = !(picked.length && picked.every(key => finalOnly.has(key)) && !playerChecks());
    remember();
  }
  function playerToken(player) {
    return player.id + ":" + player.team + ":" + player.name;
  }
  // A player as his chip and his panel head name him: his name and his team.
  function playerWords(player) {
    return player.name + " (" + player.team + ")";
  }
  function playerChip(player) {
    const label = document.createElement("label");
    label.className = "pick";
    const input = document.createElement("input");
    input.type = "checkbox";
    input.name = "players";
    input.value = playerToken(player);
    input.checked = true;
    label.append(input, playerWords(player));
    return label;
  }
  // A newly chosen player's own controls: his section of the template, named by his ESPN id, so his
  // targets, ticks and AND or OR travel as his own parameters.
  function playerPanel(player) {
    if (!template) return null;
    const holder = document.createElement("div");
    holder.innerHTML = template.innerHTML.replaceAll("%(new_player)s", player.id);
    const panel = holder.firstElementChild;
    panel.querySelector("[data-player-name]").textContent = playerWords(player);
    return panel;
  }
  function dropPanel(token) {
    const id = token.split(":")[0];
    for (const panel of panels.querySelectorAll("[data-player-checks]"))
      if (panel.dataset.playerChecks === id) panel.remove();
  }
  function alreadyChosen(value) {
    return Array.from(form.querySelectorAll('input[name="players"]'))
      .some(pick => pick.value === value);
  }
  function showResults() {
    if (!results || !search) return;
    const typed = search.value.trim().toLowerCase();
    results.replaceChildren();
    if (!typed) return;
    for (const player of roster.filter(player => player.name.toLowerCase().includes(typed)).slice(0, 10)) {
      if (alreadyChosen(playerToken(player))) continue;
      const choice = document.createElement("button");
      choice.type = "button";
      choice.className = "pick";
      choice.textContent = playerWords(player);
      choice.addEventListener("click", () => {
        picks.append(playerChip(player));
        const panel = playerPanel(player);
        if (panel) panels.append(panel);
        search.value = "";
        showResults();
        show();
      });
      results.append(choice);
    }
  }
  if (search) {
    search.addEventListener("input", showResults);
    fetch("/players").then(response => response.json()).then(answer => {
      roster = answer.players || [];
      showResults();
    }).catch(() => {});
  }
  if (picks) {
    picks.addEventListener("change", (event) => {
      if (event.target.name !== "players" || event.target.checked) return;
      dropPanel(event.target.value);
      event.target.closest("label").remove();
      showResults();
      show();
    });
  }
  form.addEventListener("input", (event) => {
    if (event.target.type === "range") showValue(event.target);
    show();
  });
  form.addEventListener("click", (event) => {
    const reset = event.target.closest("[data-reset]");
    if (!reset) return;
    for (const slider of reset.closest("section").querySelectorAll('input[type="range"]')) {
      slider.value = slider.dataset.default; showValue(slider);
    }
    show();
  });
})();
</script>""" % {"settings_key": SETTINGS_KEY, "new_player": NEW_PLAYER}


def settings_params(fan):
    """The fan's settings as query pairs, so a link carries them the way a request does."""
    return ([("presets", ",".join(preset.key for preset in fan.presets)), ("join", fan.join)]
            + [(parameter, str(value)) for parameter, value in fan.values.items()])


def player_params(following):
    """The tracked players and each player's own checks as query pairs, so a link carries them the way a
    request does."""
    return ([("players", players.player_token(followed.player)) for followed in following]
            + [pair for followed in following
               for pair in followed.checks.query_pairs(followed.player.id)])


def page_href(picks, setup=False, catchup_team=None):
    """The page's address for `picks`; `setup` asks for the setup screen, with the fan's teams and players
    ticked, and `catchup_team` asks for that team's catch-up screen."""
    leading = [("setup", "1")] if setup else []
    if catchup_team:
        leading.append(("catchup", catchup_team))
    return "/?" + urlencode(leading + [("teams", name) for name in picks.teams]
                             + player_params(picks.following) + settings_params(picks.fan))


def preview_words(preview):
    """The Next-game preview's words: day, time and opponent."""
    where = "vs" if preview["home"] else "at"
    return f"{preview['day']}, {preview['time']} {where} {preview['opponent']}"


def notice(text):
    return f'<p class="notice">{escape(text)}</p>' if text else ""


def header(gear_href=None):
    gear = (f'<a class="gear" href="{escape(gear_href)}" aria-label="Setup">⚙︎</a>'
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


def moment_words(seconds):
    """The moment `seconds` of regulation play names, in the words a timing slider shows: 'Tip-off',
    '6:00 left in the 2nd', 'Start of the 3rd' or 'End of the 4th'."""
    if seconds <= 0:
        return "Tip-off"
    quarter = min(4, (seconds - 1) // 720 + 1)  # the quarter played when `seconds` have gone
    left = quarter * 720 - seconds
    if left == 0:
        return f"Start of the {QUARTERS[quarter + 1]}" if quarter < 4 else "End of the 4th"
    return f"{left // 60}:{left % 60:02d} left in the {QUARTERS[quarter]}"


def value_words(slider, value):
    """`value` in `slider`'s unit, as the fan reads it beside the slider: '98%', '5 points', '6:00 left in
    the 2nd', or 'No target' for a check left asking for no number."""
    if slider.unit == "%":
        return f"{value}%"
    if slider.unit == presets.MOMENT:
        return moment_words(value)
    if value == 0 and slider in players.TARGET_SLIDERS:
        return players.NO_TARGET
    unit = slider.unit if value != 1 else slider.unit[:-1]
    return f"{value} {unit}"


def slider_in_words(slider, settings):
    """`slider` with the value held on it, by the fan's settings or by a tracked player's checks, as a fan
    reads the pair in a rules panel."""
    return f"{slider.name} {value_words(slider, settings.value(slider.parameter))}"


def slider_row(slider, settings, parameter=None):
    """One slider: its words, the value the fan set, and every value it can take with the words it shows,
    so the page's script can follow the slider as the fan moves it and put it back on Reset to default.

    `parameter` names the control, for a player's own copy of a check whose value `settings` holds by the
    slider's own parameter; it is that parameter when it is not given.
    """
    parameter = parameter or slider.parameter
    value = settings.value(slider.parameter)
    labels = {str(number): value_words(slider, number)
              for number in range(slider.low, slider.high + 1, slider.step)}
    return f"""<div class="slider" data-slider="{parameter}">
<label for="{parameter}"><span>{escape(slider.name)}</span>
<span data-shown>{escape(labels[str(value)])}</span></label>
<input type="range" id="{parameter}" name="{parameter}" min="{slider.low}" max="{slider.high}"
 step="{slider.step}" value="{value}" data-default="{slider.default}" data-labels="{escape(json.dumps(labels))}">
</div>"""


def preset_group(preset, fan):
    """One Preset's sliders, shown only while the fan has that Preset picked, and its Reset to default."""
    return (f'<section class="group" data-preset="{preset.key}"'
            f'{" hidden" if preset not in fan.presets else ""}'
            f'><h2>{escape(preset.name)}</h2>'
            + "".join(slider_row(slider, fan) for slider in preset.sliders)
            + f'<button type="button" class="reset" data-reset="{preset.key}">Reset to default</button>'
              "</section>")


def timing_group(fan):
    """The shared Judge from and Freeze at sliders, which every fan can move. They are not a Preset's
    sliders, so the section names no Preset and the setup script's hide loop leaves it alone."""
    return ('<section class="group" data-timing><h2>Timing</h2>'
            + "".join(slider_row(slider, fan) for slider in presets.TIMING)
            + "</section>")


def join_picks(name, chosen):
    """The AND or OR choices as chips named `name` for the request, the one `chosen` picked."""
    return "".join(
        f'<label class="pick"><input type="radio" name="{escape(name)}" value="{join}"'
        f'{" checked" if chosen == join else ""}>{JOIN_WORDS[join]}</label>'
        for join in presets.JOINS)


def player_heading(player):
    """A player as the page names him beside his chip and above his checks: his name and his team."""
    return f"{player.name} ({player.team})"


def player_pick(player):
    """One tracked player as a ticked chip, carrying the id, team and name a request names."""
    return (f'<label class="pick"><input type="checkbox" name="players" '
            f'value="{escape(players.player_token(player))}" checked>'
            f'{escape(player_heading(player))}</label>')


def players_section(following):
    """Setup's players section: the tracked players the address names as ticked chips, the search that adds
    another from the served rosters, and each tracked player's own controls under his chip."""
    return f"""<div class="picks" id="player-picks">{"".join(player_pick(followed.player) for followed in following)}</div>
<div class="search"><input type="search" id="player-search" autocomplete="off"
 aria-label="Find a player" placeholder="Type part of a player&rsquo;s name">
<div class="picks" id="player-results"></div></div>
<div id="player-checks">{"".join(player_checks_panel(followed.player.id, player_heading(followed.player), followed.checks)
                                for followed in following)}</div>"""


def player_checks_panel(player_id, heading, checks):
    """One tracked player's own controls: his name with his own AND or OR beside it as a small toggle, a
    target slider for each counting stat, and his double-double and triple-double ticks, every control
    named by his ESPN id and headed `heading`. It never says which check fitted. The setup page also
    renders it once as a template, with no heading, for the search to fill in when the fan adds him."""
    sliders = "".join(
        slider_row(check.slider, checks, players.check_parameter(player_id, check.slider.parameter))
        for check in players.CHECKS)
    doubles = "".join(
        f'<label class="pick"><input type="checkbox" value="1"'
        f' name="{escape(players.check_parameter(player_id, name))}"'
        f'{" checked" if ticked else ""}>{escape(words)}</label>'
        for name, words, ticked in (("double_double", players.DOUBLE_DOUBLE_NAME, checks.double_double),
                                    ("triple_double", players.TRIPLE_DOUBLE_NAME, checks.triple_double)))
    joins = join_picks(players.check_parameter(player_id, "join"), checks.join)
    return f"""<section class="group" data-player-checks="{escape(player_id)}">
<div class="player-head"><h2><span data-player-name>{escape(heading)}</span></h2>
<div class="join" role="group" aria-label="Combine this player's checks">{joins}</div></div>
{sliders}
<div class="picks">{doubles}</div>
<p class="note">Zero asks for no number. Each check is judged against the player&rsquo;s usual minutes.</p>
</section>"""


def player_checks_template():
    """The controls of a player the fan has not added yet, for the setup page's script to fill in with the
    chosen player's id and name, so a player added from the search judges by his own settings."""
    return (f'<template id="player-checks-template">'
            f'{player_checks_panel(NEW_PLAYER, "", players.Checks())}</template>')


def judges_only_the_final(picks):
    """Whether every setting the fan picked judges only the final, so the time a Watch appears, or does
    not, can hint at overtime to a fan who remembers the tip-off."""
    return (bool(picks.fan.presets) and all(preset.final_only for preset in picks.fan.presets)
            and not any(followed.checks for followed in picks.following))


def overtime_warning(picks):
    """The warning about a Watch's timing hinting at overtime, kept in the markup so the page's script can
    show it the moment every setting the fan picked judges only the final."""
    return (f'<p class="notice" id="overtime"{"" if judges_only_the_final(picks) else " hidden"}>'
            f'{escape(OVERTIME_WARNING)}</p>')


def setup_screen(team_names, picks, notice_text=None):
    """Setup: the fan's teams and players, the Presets they like to watch, each tracked player's own
    checks with their sliders, and Done."""
    teams = "".join(
        f'<label class="pick"><input type="checkbox" name="teams" value="{escape(team)}"'
        f'{" checked" if team in picks.teams else ""}>{escape(team)}</label>'
        for team in team_names)
    chips = "".join(
        f'<label class="pick"><input type="checkbox" name="presets" value="{preset.key}"'
        f'{" checked" if preset in picks.fan.presets else ""}'
        f'{" data-final-only" if preset.final_only else ""}>{escape(preset.name)}</label>'
        for preset in presets.SHIPPED)
    joins = join_picks("join", picks.fan.join)
    groups = "".join(preset_group(preset, picks.fan) for preset in presets.SHIPPED if preset.sliders)
    cancel = (f'<a class="btn" href="{escape(page_href(picks))}">Cancel</a>'
              if picks.teams or picks.following else "")
    body = f"""<main id="main">
<h1>Which teams and players do you follow?</h1>
{notice(notice_text)}
<form id="setup" method="get" action="/">
<div class="picks">{teams}</div>
<h2>Players</h2>
{players_section(picks.following)}
<h2>Games I like to watch</h2>
<div class="picks">{chips}</div>
{groups}
<h2>Combine with</h2>
<div class="picks">{joins}</div>
{timing_group(picks.fan)}
{overtime_warning(picks)}
<button class="btn primary" id="done" type="submit"{"" if picks.fan.presets or picks.following else " disabled"}>Done</button>
{cancel}
</form>
{player_checks_template()}
{CONTROLS}
</main>"""
    return shell(body)


def preset_rules(preset, fan):
    """One picked Preset's name and its slider values in the words a fan reads beside the sliders."""
    values = ", ".join(slider_in_words(slider, fan) for slider in preset.sliders)
    return f"{preset.name} ({values})" if values else preset.name


def rules_markup(lines):
    """One rules panel: each line a paragraph, so the words a card lists read one rule at a time."""
    return "\n".join(f"<p>{escape(line)}</p>" for line in lines)


def rules_panel(fan):
    """The rules the fan's settings apply to every team card: the picked Presets with their values, the
    AND or OR, and the shared timing. It never says how any Preset judged the game, so it cannot spoil it."""
    if not fan.presets:
        return "Pick a Preset in setup to judge this game."
    timing = " · ".join(slider_in_words(slider, fan) for slider in presets.TIMING)
    return rules_markup([preset_rules(preset, fan) for preset in fan.presets]
                        + [JOIN_WORDS[fan.join], timing])


def player_rules(checks):
    """The checks the fan's settings apply to every player card: each number to reach, the double checks
    and the AND or OR. It never says which check fitted, so it cannot spoil the night."""
    if not checks:
        return rules_markup([players.NO_CHECKS])
    lines = [slider_in_words(check.slider, checks)
             for check in players.CHECKS if check.stat in checks.targets]
    if checks.double_double:
        lines.append(players.DOUBLE_DOUBLE_NAME)
    if checks.triple_double:
        lines.append(players.TRIPLE_DOUBLE_NAME)
    return rules_markup(lines + [JOIN_WORDS[checks.join]])


def highlights_button(button):
    """The card's highlights control from the row's button: End Highlights opening YouTube when a reel was
    found, or the disabled No highlights yet while there is none. A row with no button, which is a game
    that has not tipped off, gets no control at all, so its absence hints at nothing.
    """
    if not button:
        return ""
    if button["link"]:
        return (f'<a class="highlights" href="{escape(button["link"])}" target="_blank" rel="noopener">'
                f'{escape(button["label"])}</a>')
    return f'<button class="highlights" disabled>{escape(button["label"])}</button>'


def card(row, picks):
    """One followed team's or player's card: a dot carrying the Verdict, its name, the rules applied, the
    button that opens its catch-up screen whatever the Verdict, and its highlights button.

    `picks` carries the fan's team picks, so Back from the catch-up screen returns to them all. A player's
    card names the player and lists that player's own checks rather than the Presets.
    """
    team = escape(row["team"])
    player = row.get("player")
    followed = next((followed for followed in picks.following if followed.player.id == row.get("id")),
                    None)
    name = escape(player) if player else team
    watch = (f'<a class="watching" href="'
             f'{escape(page_href(picks, catchup_team=row["team"]))}">'
             f'I\'m watching</a>')
    verdict, preview = row["verdict"], row["next_game"]
    if verdict:
        dot = (f'<span class="dot {DOT_CLASSES[verdict]}" role="img" '
               f'aria-label="{escape(verdict)}"></span>')
        line = f"<small>{team}</small>" if player else ""
    else:
        # No Verdict yet: a hollow dot, and the Next-game preview or the row's own words under the name.
        dot = '<span class="dot none" aria-hidden="true"></span>'
        under = preview_words(preview) if preview else (row["detail"] or "")
        line = f"<small>{escape(under)}</small>" if under else ""
    rules = player_rules(followed.checks) if followed else rules_panel(picks.fan)
    played = f' data-player="{escape(player)}"' if player else ""
    return f"""<article class="card" data-team="{team}"{played}>
<details><summary>{dot}<span class="t">{name}{line}</span></summary>
<div class="rules">{rules}</div></details>
<div class="actions">{watch}
{highlights_button(row.get("highlights"))}</div>
</article>"""


CATCHUP_KEY = "radiosilence.catchup.%(game)s"
CATCHUP_CONTROLS = """<script>
(function () {
  const KEY = %(key)s;
  const TOPS = %(tops)s;
  const asked = new URLSearchParams(location.search);
  function remember(moment) {
    try { localStorage.setItem(KEY, JSON.stringify(moment)); } catch (error) {}
  }
  function recalled() {
    try { return JSON.parse(localStorage.getItem(KEY)); } catch (error) { return null; }
  }
  // A quarter's clock stops at 12:00 and overtime's at 50:00, so a minutes and seconds pair past its
  // period's top is that clock's top.
  function clamped(moment) {
    const top = TOPS[moment.period];
    const played = moment.minutes * 60 + moment.seconds;
    if (played <= top) return moment;
    const minutes = Math.floor(top / 60);
    return {period: moment.period, minutes: minutes, seconds: top - minutes * 60};
  }
  // A fan coming back to the same game opens at the moment they last named on this phone.
  if (!asked.has("period")) {
    const saved = recalled();
    if (saved) {
      for (const name of ["period", "minutes", "seconds"]) asked.set(name, saved[name]);
      location.replace("?" + asked);
      return;
    }
  }
  document.addEventListener("DOMContentLoaded", function () {
    const form = document.getElementById("catchup");
    if (!form) return;
    const picked = function () {
      return {period: form.elements.period.value,
              minutes: Number(form.elements.minutes.value),
              seconds: Number(form.elements.seconds.value)};
    };
    const moment = clamped(picked());
    remember(moment);
    for (const picker of form.querySelectorAll("select")) {
      picker.addEventListener("change", function () {
        const next = clamped(picked());
        form.elements.period.value = next.period;
        form.elements.minutes.value = next.minutes;
        form.elements.seconds.value = next.seconds;
        remember(next);
        form.submit();
      });
    }
  });
})();
</script>"""
# Each box score column: its heading, and the answer's fields it shows, joined by "/" when it shows two, as
# shooting does.
STAT_COLUMNS = (("PTS", ("points",)), ("REB", ("rebounds",)), ("AST", ("assists",)), ("PF", ("fouls",)),
                ("FG", ("field_goals_made", "field_goals_attempted")),
                ("3PT", ("threes_made", "threes_attempted")),
                ("FT", ("free_throws_made", "free_throws_attempted")))

# The catch-up screen a request names: the team whose game it shows, the fan's picks its links carry so Back
# returns to the whole list, and the moment its pickers name.
CatchUpView = namedtuple("CatchUpView", "team picks moment")


def catchup_href(view, tab):
    """The catch-up screen's address for `view`'s game at its moment, showing the tab `tab`."""
    period, minutes, seconds = view.moment
    return page_href(view.picks, catchup_team=view.team) + "&" + urlencode(
        [("period", period), ("minutes", str(minutes)), ("seconds", str(seconds)), ("tab", tab)])


def catchup_pickers(moment):
    """The period, minutes and seconds pickers at `moment`: the same five periods whatever the game, a
    quarter's clock running 12 to 0 and overtime's 0 to 50 minutes."""
    period, minutes, seconds = moment
    periods = "".join(f'<option value="{value}"{" selected" if value == period else ""}>{value}</option>'
                      for value in catchup.PERIODS)
    top = catchup.CLOCK_SECONDS[period] // 60
    # A quarter's clock counts down to 0, so its minutes run top to 0; overtime counts up from 0.
    minute_values = range(top + 1) if period == catchup.OVERTIME else range(top, -1, -1)
    minute_options = "".join(
        f'<option value="{value}"{" selected" if value == minutes else ""}>{value} min</option>'
        for value in minute_values)
    second_options = "".join(
        f'<option value="{value}"{" selected" if value == seconds else ""}>{value:02d}</option>'
        for value in range(60))
    return f"""<div class="pickers">
<select name="period" aria-label="Period">{periods}</select>
<select name="minutes" aria-label="Minutes">{minute_options}</select>
<select name="seconds" aria-label="Seconds">{second_options}</select>
</div>"""


def catchup_form(view, tab):
    """The pickers' form: the same GET the screen was opened by, carrying its team, the fan's picks and
    settings, so the new moment opens the same way."""
    hidden = ([("catchup", view.team), ("teams", ",".join(view.picks.teams)), ("tab", tab)]
              + player_params(view.picks.following) + settings_params(view.picks.fan))
    fields = "".join(f'<input type="hidden" name="{name}" value="{escape(str(value))}">'
                     for name, value in hidden)
    return f'<form id="catchup" method="get" action="/">{fields}{catchup_pickers(view.moment)}</form>'


def moment_note(moment):
    """The words under the pickers: which moment the screen shows and that nothing later is sent."""
    period, minutes, seconds = moment
    clock = f"{minutes}:{seconds:02d}"
    if period == catchup.OVERTIME:
        return (f"In OT, minutes count overtime played since the end of regulation, each overtime five "
                f"minutes. Showing the game {clock} into overtime. Nothing later is sent to your phone.")
    return f"Showing the game as of {clock} left in the {period} quarter. Nothing later is sent to your phone."


def catchup_score(answer):
    """The score at the fan's moment: each team's points over its abbreviation."""
    cells = "".join(
        f'<span class="team-score">{team["points"]} <small>{escape(team["team"])}</small></span>'
        for team in answer["teams"])
    return f'<div class="score">{cells}</div>'


def stat_cell(line, fields):
    """One stat's cell: its count, or made of attempted for shooting."""
    return "/".join(str(line[field]) for field in fields)


def clock_minutes(minutes):
    """A player's minutes as a box score prints them, minutes and seconds: 2.67 minutes is 2:40."""
    seconds = round(minutes * 60)
    return f"{seconds // 60}:{seconds % 60:02d}"


def box_row(name, line, minutes=None, total=False):
    """One box score row: a name, its minutes when it has them, and every stat column. A team's totals
    row has no minutes and is marked so it stands out from its players."""
    cells = "".join(f"<td>{escape(stat_cell(line, fields))}</td>" for _, fields in STAT_COLUMNS)
    minutes_cell = "—" if minutes is None else clock_minutes(minutes)
    marker = ' class="total"' if total else ""
    return f'<tr{marker}><td>{escape(name)}</td><td>{minutes_cell}</td>{cells}</tr>'


def catchup_box(answer):
    """Each team's players and its totals: minutes, points, rebounds, assists, fouls and shooting."""
    headings = "".join(f"<th>{heading}</th>"
                       for heading in ("Player", "MIN") + tuple(heading for heading, _ in STAT_COLUMNS))
    tables = []
    for team in answer["teams"]:
        players = "".join(box_row(player["name"], player, player["minutes"])
                          for player in answer["players"] if player["team"] == team["team"])
        tables.append(f"""<h2>{escape(team["name"])}</h2>
<table class="box"><thead><tr>{headings}</tr></thead>
<tbody>{players}{box_row(team["team"], team, total=True)}</tbody></table>""")
    return "".join(tables)


def catchup_plays(answer):
    """The plays up to the fan's moment, newest first, each with its period, clock and team."""
    if not answer["plays"]:
        return '<p class="note">No plays at your moment yet.</p>'
    rows = "".join(
        f'<div><b>{escape(" ".join(filter(None, (play["period"], play["clock"]))))}'
        f'{" · " + escape(play["team"]) if play["team"] else ""}</b>{escape(play["text"])}</div>'
        for play in answer["plays"])
    return f'<div class="pbp">{rows}</div>'


# One tab of the catch-up screen: the words its link shows, and the part of the screen it shows.
Tab = namedtuple("Tab", "words body")
# The catch-up screen's two tabs, in the order it offers them, and the one it opens on.
TABS = {"box": Tab("Box score", catchup_box), "plays": Tab("Play-by-play", catchup_plays)}
DEFAULT_TAB = "box"


def catchup_tab(named):
    """The tab a catch-up request's `tab` value names: Box score unless it names Play-by-play."""
    return named if named in TABS else DEFAULT_TAB


def catchup_tabs(view, tab):
    """The catch-up screen's two tabs, the shown one marked, each keeping the moment picked."""
    links = "".join(
        f'<a class="pick{" on" if key == tab else ""}"'
        f' href="{escape(catchup_href(view, key))}">{entry.words}</a>'
        for key, entry in TABS.items())
    return f'<div class="picks">{links}</div>'


def back_link(picks):
    """The Back button from the catch-up screen to the list of the fan's teams and players."""
    return f'<a class="btn" href="{escape(page_href(picks))}">Back</a>'


def catchup_notice(picks, notice_text):
    """The catch-up screen when there is no game to show: the words why, and Back to the list."""
    return shell(f"""<main id="main">
<h1>Catch-up</h1>
{notice(notice_text)}
{back_link(picks)}
</main>""")


def catchup_screen(team, picks, game_id, answer, moment, tab):
    """The catch-up screen for `team`'s game: where the fan is in the recording at `moment`, the score,
    the Box score or Play-by-play tab and Back. The screen's script remembers the moment under `game_id`
    on the phone, so the fan's next visit opens where they left off."""
    view = CatchUpView(team, picks, moment)
    controls = CATCHUP_CONTROLS % {"key": json.dumps(CATCHUP_KEY % {"game": game_id}),
                                   "tops": json.dumps(catchup.CLOCK_SECONDS)}
    body = f"""<main id="main">
{controls}
<h1>Where you are in the recording</h1>
{catchup_form(view, tab)}
<p class="note">{escape(moment_note(view.moment))}</p>
{catchup_score(answer)}
{catchup_tabs(view, tab)}
{TABS[tab].body(answer)}
{back_link(picks)}
</main>"""
    return shell(body)


def list_screen(rows, picks, notice_text=None):
    """The main screen: one card per followed team and player, refreshing itself every minute."""
    body = f"""<main id="main">
{notice(notice_text)}
{"".join(card(row, picks) for row in rows)}
</main>"""
    return shell(body, refresh=True, gear_href=page_href(picks, setup=True))
