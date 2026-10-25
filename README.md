# Bad Game Warning

Tells you whether tonight's Dallas Mavericks game is worth watching from behind, without spoilers.

`app.py` reads ESPN's public win-probability data for today's Mavericks game and shows one verdict:

- **Stay away**: from 6:00 left in the 2nd quarter onward, the latest reading gives the opponent more than a 95% chance to win.
- **Watch**: the rule applies and the opponent is at 95% or below. The verdict follows the latest reading, so a game that comes back goes from Stay away to Watch again, and the open page refreshes itself every minute.
- **Too early to call**: the game is on but hasn't reached 6:00 left in the 2nd quarter.
- **Next game**: no game is under way today, so the page shows the next game's day, time and opponent. A game that finished today still gets its verdict, for watching from behind.
- **Can't tell**: ESPN couldn't be reached.

The Mac computes the verdict and the page contains only that verdict: no score, clock, or percentage.

## Running

A launchd agent (`com.bradley.bad-game-warning.plist`, copied to `~/Library/LaunchAgents/`) starts the server at login on port 8765.
Open `http://Bradleys-MacBook-Pro-2.local:8765/` on the home network.

Restart after editing: `launchctl kickstart -k gui/$UID/com.bradley.bad-game-warning`.
Tests: `python3 -m unittest`.
