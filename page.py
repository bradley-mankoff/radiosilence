"""The RadioSilence page: setup with the fan's teams and Presets, then one card per followed team.

app.py builds this page from the same rows /rows answers with, so the page can only show what the Verdict
needs. The small scripts do what the server cannot: keep the fan's teams and Preset settings on the phone,
send them back on the next visit, and show each slider's value as the fan moves it. The Presets, their
sliders and their words all come from presets.py, so the page and the Verdict read one definition.
"""

import json
from html import escape
from urllib.parse import urlencode

import presets

NAME = "RadioSilence"
TEAMS_KEY = "radiosilence.teams"
SETTINGS_KEY = "radiosilence.settings"
DOT_CLASSES = {"Watch": "watch", "Stay away": "stay", "Too early to call": "early"}
JOIN_WORDS = {"OR": "Any one fits (OR)", "AND": "All must fit (AND)"}
QUARTERS = {1: "1st", 2: "2nd", 3: "3rd", 4: "4th"}
OVERTIME_WARNING = ("Every Preset you picked judges only the final, so if you remember when the game "
                    "tipped off, the time a Watch appears, or doesn't, can hint at overtime.")

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
  .card .rules p { margin:0 0 4px; }
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
  .group[hidden], .notice[hidden] { display:none; }
  .slider { padding:6px 18px 10px; }
  .slider label { display:flex; justify-content:space-between; gap:12px; font-size:.9rem;
                  color:var(--dim); }
  .slider input { width:100%; accent-color:var(--early); }
  .reset { display:block; margin:0 18px 10px; padding:0; background:none; border:0; color:var(--dim);
           font:inherit; font-size:.85rem; text-decoration:underline; cursor:pointer; }
"""

# The script every page runs before it paints: a list page keeps the picks and settings it was asked for,
# a fan who already picked teams goes straight to their cards, and the settings go with them. Without
# storage the page still works; it just forgets.
REMEMBER_PICKS = """<script>
(function () {
  const TEAMS = "%(teams_key)s", SETTINGS = "%(settings_key)s", SLIDERS = %(sliders)s;
  function saved() {
    try { return JSON.parse(localStorage.getItem(SETTINGS)); } catch (error) { return null; }
  }
  function store(settings) {
    try { localStorage.setItem(SETTINGS, JSON.stringify(settings)); } catch (error) {}
  }
  // The settings a query names: its Presets, its AND or OR, and a value for each slider it carries.
  function named(query) {
    const picked = query.getAll("presets").join(",").split(",").filter(key => key);
    const values = {};
    for (const parameter of SLIDERS) if (query.has(parameter)) values[parameter] = Number(query.get(parameter));
    return {presets: picked, join: query.get("join") === "AND" ? "AND" : "OR", values: values};
  }
  // The fan's saved settings as query parameters, and nothing when the phone holds none.
  function settingsQuery() {
    const settings = saved();
    if (!settings) return "";
    const pairs = [["presets", settings.presets.join(",")], ["join", settings.join]];
    for (const parameter of SLIDERS) {
      if (settings.values[parameter] !== undefined) pairs.push([parameter, settings.values[parameter]]);
    }
    return "&" + pairs.map(pair => pair[0] + "=" + encodeURIComponent(pair[1])).join("&");
  }
  try {
    const params = new URLSearchParams(location.search);
    const picks = params.getAll("teams").join(",");
    if (picks) {
      localStorage.setItem(TEAMS, picks);
      if (params.has("presets") || params.has("join")) store(named(params));
      return;
    }
    if (params.has("setup")) return;
    const savedTeams = localStorage.getItem(TEAMS);
    if (savedTeams) location.replace("/?teams=" + encodeURIComponent(savedTeams) + settingsQuery());
  } catch (error) {}
})();
</script>""" % {"teams_key": TEAMS_KEY, "settings_key": SETTINGS_KEY,
                       "sliders": json.dumps([slider.parameter for slider in presets.ALL_SLIDERS])}

# The setup screen's script: it shows the picked Presets' sliders, each value in words, keeps the fan's
# settings on the phone as they change, and puts a Preset's sliders back on Reset to default.
CONTROLS = """<script>
(function () {
  const form = document.getElementById("setup");
  if (!form) return;
  const SETTINGS = "%(settings_key)s";
  const chips = Array.from(form.querySelectorAll('input[name="presets"]'));
  const sliders = Array.from(form.querySelectorAll('input[type="range"]'));
  // Only a section that names a Preset hides and shows with that Preset's chip; the shared Timing
  // sliders are always on screen.
  const groups = Array.from(form.querySelectorAll("section[data-preset]"));
  const finalOnly = new Set(chips.filter(chip => "finalOnly" in chip.dataset).map(chip => chip.value));
  const done = form.querySelector("#done");
  const warning = form.querySelector("#overtime");

  function settings() {
    return {
      presets: chips.filter(chip => chip.checked).map(chip => chip.value),
      join: form.querySelector('input[name="join"]:checked').value,
      values: Object.fromEntries(sliders.map(slider => [slider.name, Number(slider.value)])),
    };
  }
  function showValue(slider) {
    const shown = slider.closest(".slider").querySelector("[data-shown]");
    shown.textContent = JSON.parse(slider.dataset.labels)[slider.value];
  }
  function remember() {
    try { localStorage.setItem(SETTINGS, JSON.stringify(settings())); } catch (error) {}
  }
  function show() {
    const picked = settings().presets;
    for (const group of groups) group.hidden = !picked.includes(group.dataset.preset);
    done.disabled = picked.length === 0;
    warning.hidden = !(picked.length && picked.every(key => finalOnly.has(key)));
    remember();
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
</script>""" % {"settings_key": SETTINGS_KEY}


def settings_params(fan):
    """The fan's settings as query pairs, so a link carries them the way a request does."""
    return ([("presets", ",".join(preset.key for preset in fan.presets)), ("join", fan.join)]
            + [(parameter, str(value)) for parameter, value in fan.values.items()])


def page_href(names, fan, setup=False):
    """The page's address for `names` and the fan's settings; `setup` asks for the setup screen, with the
    `names` ticked."""
    leading = [("setup", "1")] if setup else []
    return "/?" + urlencode(leading + [("teams", name) for name in names] + settings_params(fan))


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
    the 2nd'."""
    if slider.unit == "%":
        return f"{value}%"
    if slider.unit == presets.MOMENT:
        return moment_words(value)
    unit = slider.unit if value != 1 else slider.unit[:-1]
    return f"{value} {unit}"


def slider_in_words(slider, fan):
    """`slider` with the fan's value on it, as a fan reads the pair in a rules panel."""
    return f"{slider.name} {value_words(slider, fan.value(slider.parameter))}"


def slider_row(slider, fan):
    """One slider: its words, the value the fan set, and every value it can take with the words it shows,
    so the page's script can follow the slider as the fan moves it and put it back on Reset to default."""
    value = fan.value(slider.parameter)
    labels = {str(number): value_words(slider, number)
              for number in range(slider.low, slider.high + 1, slider.step)}
    return f"""<div class="slider" data-slider="{slider.parameter}">
<label for="{slider.parameter}"><span>{escape(slider.name)}</span>
<span data-shown>{escape(labels[str(value)])}</span></label>
<input type="range" id="{slider.parameter}" name="{slider.parameter}" min="{slider.low}" max="{slider.high}"
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


def judges_only_the_final(fan):
    """Whether every Preset the fan picked judges only the final, so the time a Watch appears, or does not,
    can hint at overtime to a fan who remembers the tip-off."""
    return bool(fan.presets) and all(preset.final_only for preset in fan.presets)


def overtime_warning(fan):
    """The warning about a Watch's timing hinting at overtime, kept in the markup so the page's script can
    show it the moment a fan picks a Preset that judges only the final."""
    return (f'<p class="notice" id="overtime"{"" if judges_only_the_final(fan) else " hidden"}>'
            f'{escape(OVERTIME_WARNING)}</p>')


def setup_screen(team_names, picked, fan, notice_text=None):
    """Setup: the fan's teams, the Presets they like to watch with their sliders, and Done."""
    teams = "".join(
        f'<label class="pick"><input type="checkbox" name="teams" value="{escape(team)}"'
        f'{" checked" if team in picked else ""}>{escape(team)}</label>'
        for team in team_names)
    chips = "".join(
        f'<label class="pick"><input type="checkbox" name="presets" value="{preset.key}"'
        f'{" checked" if preset in fan.presets else ""}'
        f'{" data-final-only" if preset.final_only else ""}>{escape(preset.name)}</label>'
        for preset in presets.SHIPPED)
    joins = "".join(
        f'<label class="pick"><input type="radio" name="join" value="{join}"'
        f'{" checked" if fan.join == join else ""}>{JOIN_WORDS[join]}</label>'
        for join in presets.JOINS)
    groups = "".join(preset_group(preset, fan) for preset in presets.SHIPPED if preset.sliders)
    cancel = (f'<a class="btn" href="{escape(page_href(picked, fan))}">Cancel</a>'
              if picked else "")
    body = f"""<main id="main">
<h1>Which teams do you follow?</h1>
{notice(notice_text)}
<form id="setup" method="get" action="/">
<div class="picks">{teams}</div>
<h2>Games I like to watch</h2>
<div class="picks">{chips}</div>
<h2>Combine with</h2>
<div class="picks">{joins}</div>
{groups}
{timing_group(fan)}
{overtime_warning(fan)}
<button class="btn primary" id="done" type="submit"{"" if fan.presets else " disabled"}>Done</button>
{cancel}
</form>
{CONTROLS}
</main>"""
    return shell(body)


def preset_rules(preset, fan):
    """One picked Preset's name and its slider values in the words a fan reads beside the sliders."""
    values = ", ".join(slider_in_words(slider, fan) for slider in preset.sliders)
    return f"{preset.name} ({values})" if values else preset.name


def rules_panel(fan):
    """The rules the fan's settings apply to every card: the picked Presets with their values, the AND
    or OR, and the shared timing. It never says how any Preset judged the game, so it cannot spoil it."""
    if not fan.presets:
        return "Pick a Preset in setup to judge this game."
    timing = " · ".join(slider_in_words(slider, fan) for slider in presets.TIMING)
    lines = [preset_rules(preset, fan) for preset in fan.presets] + [JOIN_WORDS[fan.join], timing]
    return "\n".join(f"<p>{escape(line)}</p>" for line in lines)


def card(row, fan):
    """One followed team's card: a dot carrying the Verdict, its name, the rules applied, and the
    disabled highlights button."""
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
<div class="rules">{rules_panel(fan)}</div></details>
<button class="highlights" disabled>No highlights yet</button>
</article>"""


def list_screen(rows, fan, notice_text=None):
    """The main screen: one card per followed team, refreshing itself every minute."""
    body = f"""<main id="main">
{notice(notice_text)}
{"".join(card(row, fan) for row in rows)}
</main>"""
    return shell(body, refresh=True, gear_href=page_href([row["team"] for row in rows], fan, setup=True))
