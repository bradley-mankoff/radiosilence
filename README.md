# RadioSilence

Tells a fan, without spoilers, whether each followed NBA team's game is worth watching from behind.

Open the page and pick any number of the 30 NBA teams. The phone remembers the picks, and the main screen shows one card per team with only a coloured dot for the Verdict:

- **Watch** (green): your Presets fit the game: any one of them when they are combined with OR, or
  all of them with AND.
- **Stay away** (red): they don't. No blowout losses reads Stay away once the opponent's chance passes
  98%, holds it until the chance drops below 95%, and freezes the answer at 5:00 left in the 4th.
- **Too early to call** (yellow): not enough of the game has been played to judge yet; Wins for my team
  waits for the final.

The Presets that ship are **Wins for my team**, **No blowout losses**, **Close games** and
**High-scoring games**. Setup offers them as chips: pick any number, choose whether a game must fit all of
them (AND) or any one (OR), and move each one's sliders, which show their values as they move (98%, 5
points, 6:00 left in the 2nd). Your edits overwrite the shipped values on the phone, Reset to default puts
them back, and setup warns you when every Preset you picked judges only the final: then the time a Watch
appears, or doesn't, can hint at overtime if you remember the tip-off.

A team with no started game shows its next game's day, time and opponent instead. Tap a card to open the rules applied to it: your Presets with their values, and the AND or OR. The page refreshes itself every minute, and says plainly when ESPN cannot be reached. A finished game keeps its Verdict until midnight.

The Mac computes the Verdicts and the page contains only them: no score, clock, quarter or win-probability percentage. The catch-up view and End Highlights come in later Specs; the highlights button is there and disabled for now.

## Running

A launchd agent (`com.bradley.bad-game-warning.plist`, copied to `~/Library/LaunchAgents/`) starts the server at login on port 8765.
Open `http://Bradleys-MacBook-Pro-2.local:8765/` on the home network, or the Tailscale Serve address from the phone. In Safari, Share, Add to Home Screen adds it as RadioSilence.

Restart after editing: `launchctl kickstart -k gui/$UID/com.bradley.bad-game-warning`.
Tests: `python3 -m unittest`.
