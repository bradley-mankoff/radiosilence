# RadioSilence

Tells a fan, without spoilers, whether each followed NBA team's game or tracked player's night is worth watching from behind.

Open the page and pick any number of the 30 NBA teams and, if you like, players by typing part of a name. The phone remembers the picks, and the main screen shows one card per team and player with only a coloured dot for the Verdict:

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

Tracking a player adds his card to the same list, with his own settings: set numbers to reach for
points, rebounds, assists, threes made, steals and blocks, tick double-double or triple-double, and choose
Any one fits or All must fit from a small toggle beside his name. Each tracked player keeps his own
targets, ticks and AND or OR, so two players can aim at different nights. During the game a player is
Watch when on track by the share of his usual minutes already played; after the final only the numbers
actually reached count. A player who did not play stays silent on the list.

A team with no started game shows its next game's day, time and opponent instead. Tap a card to open the rules applied to it: your Presets with their values and the AND or OR, or a tracked player's own numbers, ticks and AND or OR. The page refreshes itself every minute, and says plainly when ESPN cannot be reached. A finished game keeps its Verdict until midnight.

The Mac computes the Verdicts and the page contains only them: no score, clock, quarter or win-probability percentage. Each card whose game has tipped off also carries a highlights button: it reads **No highlights yet** and is disabled until 3 hours 30 minutes after the scheduled tip-off and until a reel is found, then **End Highlights** opens YouTube at the NBA's ending video, or at the last two minutes of its full-game reel. The page never carries a video's title, thumbnail or length. The catch-up view opens from a card's **I'm watching** button.

## Running

A launchd agent (`com.bradley.bad-game-warning.plist`, copied to `~/Library/LaunchAgents/`) starts the server at login on port 8765.
Open `http://Bradleys-MacBook-Pro-2.local:8765/` on the home network, or the Tailscale Serve address from the phone. In Safari, Share, Add to Home Screen adds it as RadioSilence.

Restart after editing: `launchctl kickstart -k gui/$UID/com.bradley.bad-game-warning`.
Tests: `python3 -m unittest`.
