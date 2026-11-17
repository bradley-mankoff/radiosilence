"""Highlights: each started game's End Highlights button, found without spoiling the game.

A fan sees one plain label on a card, End Highlights or No highlights yet, and the link it opens; the
video's title, thumbnail, length and view count never leave this module. The button waits until 3 hours
30 minutes after the scheduled tip-off, so its arrival cannot hint at when the game ended, and it stays
disabled until a reel is found.

Reels come from the NBA channel's uploads playlist page, which needs no key, matched by both teams' names
and the game's date. A video is kept only when keyless oEmbed names the NBA as its author, so an EXTENDED
cut, a team channel's copy or a copycat title is never chosen. The ending video wins when there is one;
otherwise the full-game reel opens two minutes before its end, and its length itself is never sent.
"""

import json
import re
import time
from collections import namedtuple
from datetime import timedelta

from judging import start_time

PLAYLIST = "https://www.youtube.com/playlist?list=UUWJ2lWNubArHWmf3FIHbfcQ"
WATCH_URL = "https://www.youtube.com/watch?v="  # not the Verdict's Watch: YouTube's watch page
WAIT = timedelta(hours=3, minutes=30)  # after the scheduled tip-off, before any reel is looked for
KEPT_SECONDS = 10 * 60  # a game's answer is reused this long before its page is read again
LAST_TWO_MINUTES = 120  # where the full-game reel opens: 120 seconds before its end
NO_HIGHLIGHTS, END_HIGHLIGHTS = "No highlights yet", "End Highlights"
NBA = "nba"

MONTHS = ("January", "February", "March", "April", "May", "June", "July", "August", "September",
          "October", "November", "December")

# One game as the button needs it: ESPN's id for it, both teams' display names, its Game day and its
# scheduled tip-off.
Game = namedtuple("Game", "id teams date tip_off")
# One entry on the playlist page: its video id, its title and its length in seconds when the page shows it.
Video = namedtuple("Video", "id title seconds")

# YouTube's page holds its own JSON in this assignment, and each video's length is the badge's text.
INITIAL_DATA = re.compile(r"var ytInitialData = (\{.*?\});</script>", re.S)
LENGTH_BADGE = re.compile(r"\d+(?::\d\d)+")


def game_of(event):
    """The game ESPN's `event` describes: its id, both teams' names, its Game day and its tip-off."""
    tip_off = start_time(event)
    teams = tuple(side["team"]["displayName"] for side in event["competitions"][0]["competitors"])
    return Game(event["id"], teams, tip_off.date(), tip_off)


def waiting():
    """A fresh No highlights yet button, disabled because no reel has been found."""
    return {"label": NO_HIGHLIGHTS, "link": None}


def found(link):
    """An End Highlights button opening `link`: the only other thing the page ever learns."""
    return {"label": END_HIGHLIGHTS, "link": link}


def words(text):
    """`text` as its lowercase words, with punctuation and spacing folded away."""
    return re.findall(r"[a-z0-9]+", text.lower())


def phrase(text):
    """`text` as the phrase a title holds when it says it: its words joined by one space."""
    return " ".join(words(text))


def nickname(team):
    """The word a title calls `team` by: the last word of its display name, as `words` folds it."""
    called = words(team)
    return called[-1] if called else ""


def date_words(day):
    """The words a title writes the date with, as `words` folds them: November, 13 and 2026."""
    return words(f"{MONTHS[day.month - 1]} {day.day} {day.year}")


def about_the_game(video, game):
    """Whether `video`'s title names both teams and the game's date, and is not an EXTENDED cut."""
    title = words(video.title)
    return (all(nickname(team) in title for team in game.teams)
            and all(word in title for word in date_words(game.date))
            and "extended" not in title)


def is_ending(video, game):
    """Whether `video` is the NBA's ending video for `game`."""
    return about_the_game(video, game) and "ending" in words(video.title)


def is_full_game(video, game):
    """Whether `video` is the NBA's full-game reel for `game`."""
    return about_the_game(video, game) and "full game highlights" in phrase(video.title)


def clock_seconds(badge):
    """A length badge's seconds: '15:02' is 902, and '1:05:00' is 3900."""
    seconds = 0
    for part in badge.split(":"):
        seconds = seconds * 60 + int(part)
    return seconds


def lockups(node):
    """Every `lockupViewModel` in YouTube's page data, in the order the page holds them."""
    if isinstance(node, dict):
        if "lockupViewModel" in node:
            yield node["lockupViewModel"]
        for value in node.values():
            yield from lockups(value)
    elif isinstance(node, list):
        for value in node:
            yield from lockups(value)


def value_at(node, *keys):
    """What `node` holds at `keys`, or None where the page's shape stops short of them."""
    for key in keys:
        if not isinstance(node, dict):
            return None
        node = node.get(key)
    return node


def length_of(lockup):
    """The seconds a lockup shows as its length badge, or None when it shows no length."""
    overlays = value_at(lockup, "contentImage", "thumbnailViewModel", "overlays") or []
    for overlay in overlays:
        badges = value_at(overlay, "thumbnailBottomOverlayViewModel", "badges") or []
        for badge in badges:
            text = value_at(badge, "thumbnailBadgeViewModel", "text")
            if isinstance(text, str) and LENGTH_BADGE.fullmatch(text):
                return clock_seconds(text)
    return None


def playlist_videos(page):
    """The videos a saved uploads playlist page lists, in page order: each one's id, title and length.

    The page carries YouTube's own JSON; a page whose shape has changed lists nothing, so the button
    waits instead of guessing at a title.
    """
    data = INITIAL_DATA.search(page)
    if not data:
        return []
    try:
        videos = json.loads(data.group(1))
    except ValueError:
        return []
    listed = []
    for lockup in lockups(videos):
        video_id = value_at(lockup, "contentId")
        title = value_at(lockup, "metadata", "lockupMetadataViewModel", "title", "content")
        if isinstance(video_id, str) and isinstance(title, str) and video_id and title:
            listed.append(Video(video_id, title, length_of(lockup)))
    return listed


def nba_authored(oembed, video_id):
    """Whether YouTube's oEmbed answer for `video_id` names the NBA as the video's author."""
    try:
        answer = oembed(video_id)
    except (OSError, ValueError):  # gone, unembeddable, or not JSON: no video to link
        return False
    return phrase(str(answer.get("author_name", ""))) == NBA


def reel_link(video):
    """The full-game reel's link, opened two minutes before its end: its finish, not its length."""
    return f"{WATCH_URL}{video.id}&t={max(0, video.seconds - LAST_TWO_MINUTES)}s"


class Highlights:
    """The End Highlights button for each game, reading the uploads playlist page at most once per game
    until what it found could have changed.

    `playlist_page()` returns that page's HTML and is called only once a game is past the wait; `oembed`
    returns YouTube's answer for a video id, or raises when the video is gone. `clock` times the per-game
    cache, so a caller can pass its own.
    """

    def __init__(self, playlist_page, oembed, clock=time.monotonic):
        self.playlist_page, self.oembed, self.clock = playlist_page, oembed, clock
        self.saved = {}  # game id -> (when it was checked, the button it got)

    def button(self, game, now):
        """The button for `game` at `now`: waiting until the wait is over and a reel is found, then End
        Highlights opening that reel. The playlist page is read only once the wait is over."""
        if now < game.tip_off + WAIT:
            return waiting()
        saved = self.saved.get(game.id)
        if saved and self.clock() - saved[0] < KEPT_SECONDS:
            return dict(saved[1])
        answer = self.find(game)
        self.saved[game.id] = (self.clock(), answer)
        return dict(answer)

    def find(self, game):
        """The button `game` gets from the page: the NBA's ending video, else its full-game reel from two
        minutes before its end, else the waiting button. A page YouTube will not serve is no reel, never
        an error, so the Verdicts around it stay up."""
        try:
            videos = playlist_videos(self.playlist_page())
        except (OSError, ValueError):  # YouTube unreachable, or a page this code cannot read
            return waiting()
        for video in videos:
            if is_ending(video, game) and nba_authored(self.oembed, video.id):
                return found(WATCH_URL + video.id)
        for video in videos:
            if (is_full_game(video, game) and video.seconds is not None
                    and nba_authored(self.oembed, video.id)):
                return found(reel_link(video))
        return waiting()
