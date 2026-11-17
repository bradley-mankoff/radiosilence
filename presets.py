"""The Presets a fan can pick, their sliders, and the fan's settings for one request.

Each Preset and each shared timing slider is defined once, here: its name, the values it can take and the
value it ships with. page.py renders the page's controls from them, app.py serves them at /presets as
JSON, and judging.py reads the same defaults, so the page and the Verdict cannot disagree.

The phone sends the fan's settings with each request as query parameters: `presets=blow,wins` for the
picked Presets, `join=AND` or `join=OR`, one `<preset>_<slider>=<value>` per slider (`blow_upper=98`),
and `judge_from` / `freeze_at` for the shared timing sliders. A missing or out-of-range value falls back
to the shipped default, and a value between two steps of its slider snaps to the nearer step.
"""

from collections import namedtuple

# One slider: the query parameter it travels as, its words, its range, the value it ships with, and the
# step it moves in (one second unless it names a moment, which moves in 30-second steps).
Slider = namedtuple("Slider", "parameter name default low high unit step", defaults=(1,))
# One Preset: the key its settings are named by, its words, the sliders it has, and whether it judges
# only the final (Wins for my team), which setup warns about because a Watch's timing can hint at overtime.
Preset = namedtuple("Preset", "key name sliders final_only", defaults=(False,))

WINS = Preset("wins", "Wins for my team", (), True)
BLOW = Preset("blow", "No blowout losses", (
    Slider("blow_upper", "Stay away above", 98, 90, 99, "%"),
    Slider("blow_lower", "Back to Watch below", 95, 85, 98, "%"),
))
# Close games' last-minutes window runs inside the 4th, so its length stops at the quarter's 12 minutes.
CLOSE = Preset("close", "Close games", (
    Slider("close_points", "Close ending within", 5, 1, 20, "points"),
    Slider("close_minutes", "Close ending in the last", 5, 1, 12, "minutes"),
    Slider("along_points", "Close along the way within", 9, 1, 20, "points"),
    Slider("along_share", "Close along the way for over", 66, 1, 99, "%"),
))
HIGH = Preset("high", "High-scoring games", (
    Slider("high_total", "Reach a total of", 240, 150, 350, "points"),
))
SHIPPED = (WINS, BLOW, CLOSE, HIGH)

# The unit of a timing slider: each of its values names a moment of the game (6:00 left in the 2nd)
# rather than a count of something, so the page words it as that moment.
MOMENT = "seconds elapsed"

# The timing sliders a Preset can read, in seconds played in regulation, in 30-second steps so each value
# names a moment a fan can read. Judge from runs from tip-off to the start of the 4th, and Freeze at runs
# over the 4th. High-scoring games reads Judge from alone; only the Presets that judge between two moments
# read both.
JUDGE_FROM = Slider("judge_from", "Judge from", 1080, 0, 2160, MOMENT, 30)
FREEZE_AT = Slider("freeze_at", "Freeze at", 2580, 2160, 2880, MOMENT, 30)
TIMING = (JUDGE_FROM, FREEZE_AT)

JOIN = "OR"
JOINS = ("OR", "AND")
PRESET_BY_KEY = {preset.key: preset for preset in SHIPPED}
ALL_SLIDERS = tuple(slider for preset in SHIPPED for slider in preset.sliders) + TIMING


def _number(slider, raw):
    """`raw` as a whole number on the slider's step inside its range, or the slider's default when it is
    missing or out. A value between two steps snaps to the nearer one, so a moment slider never names a
    value the page cannot label."""
    try:
        number = int(raw)
    except (TypeError, ValueError):
        return slider.default
    if not slider.low <= number <= slider.high:
        return slider.default
    return slider.low + (number - slider.low + slider.step // 2) // slider.step * slider.step


class Settings:
    """One fan's Presets, AND or OR, and every slider's value with the shipped defaults filled in."""

    def __init__(self, picked=(), join=JOIN, values=None):
        wanted = [key for key in picked if key in PRESET_BY_KEY]
        self.presets = tuple(PRESET_BY_KEY[key] for key in dict.fromkeys(wanted))
        asked = join.upper() if isinstance(join, str) else ""
        self.join = asked if asked in JOINS else JOIN
        values = values or {}
        self.values = {slider.parameter: _number(slider, values.get(slider.parameter))
                       for slider in ALL_SLIDERS}

    def value(self, parameter):
        """The fan's value for the slider `parameter`, already filled in with the shipped default."""
        return self.values[parameter]


def from_query(params):
    """A fan's settings from a query's parameters: its `presets`, its `join`, and one value per slider."""
    picked = [name.strip() for value in params.get("presets", []) for name in value.split(",") if name.strip()]
    join = (params.get("join") or [JOIN])[-1]
    return Settings(picked, join, {name: values[-1] for name, values in params.items()})


def _served(slider):
    """One slider as /presets serves it: the parameter it travels as, its words, range, unit and default."""
    return {"parameter": slider.parameter, "name": slider.name, "min": slider.low, "max": slider.high,
            "default": slider.default, "unit": slider.unit}


def definitions():
    """The Presets and shared timing sliders as /presets serves them."""
    return {
        "presets": [{"key": preset.key, "name": preset.name,
                     "sliders": [_served(slider) for slider in preset.sliders]}
                    for preset in SHIPPED],
        "shared": [_served(slider) for slider in TIMING],
    }
