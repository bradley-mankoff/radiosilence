# RadioSilence

Tells a fan, without spoilers, whether each followed NBA team's game is worth watching from behind.

Open the page and pick any number of the 30 NBA teams. The phone remembers the picks, and the main screen shows one card per team with only a coloured dot for the Verdict:

- **Watch** (green): your Presets fit the game: any one of them when they are combined with OR, or
  all of them with AND.
- **Stay away** (red): they don't. No blowout losses reads Stay away once the opponent's chance passes
  98%, holds it until the chance drops below 95%, and freezes the answer at 5:00 left in the 4th.
- **Too early to call** (yellow): not enough of the game has been played to judge yet; Wins for my team
  waits for the final.

The Presets that ship are **Wins for my team** and **No blowout losses**, combined with AND or OR over
one set of sliders; picking them on the setup screen comes with the next pass.

A team with no started game shows its next game's day, time and opponent instead. Tap a card to open its rules panel. The page refreshes itself every minute, and says plainly when ESPN cannot be reached. A finished game keeps its Verdict until midnight.

The Mac computes the Verdicts and the page contains only them: no score, clock, quarter or win-probability percentage. The catch-up view and End Highlights come in later Specs; the highlights button is there and disabled for now.

## Running

A launchd agent (`com.bradley.bad-game-warning.plist`, copied to `~/Library/LaunchAgents/`) starts the server at login on port 8765.
Open `http://Bradleys-MacBook-Pro-2.local:8765/` on the home network, or the Tailscale Serve address from the phone. In Safari, Share, Add to Home Screen adds it as RadioSilence.

Restart after editing: `launchctl kickstart -k gui/$UID/com.bradley.bad-game-warning`.
Tests: `python3 -m unittest`.
