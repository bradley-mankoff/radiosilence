"""Save ESPN's summary for one live game once a minute, from tip-off to the final.

Usage: python3 docs/research/record_game.py <event id> [folder]
The folder defaults to ~/.local/share/bad-game-warning/recordings/<event id>, outside the repo,
so recordings never reach git. Each file is named by the UTC time it was fetched. Before
tip-off the script checks every five minutes; it stops once ESPN marks the game final.
Once the game is live it holds a caffeinate assertion so the Mac does not idle-sleep mid-game,
while the hours of waiting before tip-off leave sleep alone.
"""

import json
import os
import subprocess
import sys
import time
import urllib.request
from datetime import datetime, timezone

ESPN = "https://site.api.espn.com/apis/site/v2/sports/basketball/nba"


def main():
    event = sys.argv[1]
    folder = sys.argv[2] if len(sys.argv) > 2 else os.path.expanduser(
        f"~/.local/share/bad-game-warning/recordings/{event}")
    os.makedirs(folder, exist_ok=True)
    awake = None
    while True:
        try:
            with urllib.request.urlopen(f"{ESPN}/summary?event={event}", timeout=20) as response:
                body = response.read()
        except OSError as error:  # one failed fetch should not end a three-hour recording
            print(f"{datetime.now(timezone.utc):%H:%M:%S} fetch failed: {error}", flush=True)
            time.sleep(60)
            continue
        game_state = json.loads(body)["header"]["competitions"][0]["status"]["type"]["state"]
        if game_state == "pre":
            time.sleep(300)
            continue
        if awake is None:
            awake = subprocess.Popen(["caffeinate", "-i", "-w", str(os.getpid())])
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        with open(os.path.join(folder, f"{stamp}.json"), "wb") as out:
            out.write(body)
        if game_state == "post":
            print(f"{stamp} final; recording ends", flush=True)
            return
        time.sleep(60)


if __name__ == "__main__":
    main()
