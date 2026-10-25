# Highlights research for Bad Game Warning

## Answer in five sentences

ESPN's NBA summary endpoint returns a `videos` array of single-play clips (15 to 18 seconds in the sampled game) with headline, description, duration, thumbnail, and direct MP4 and HLS links, and the sampled single-play headlines name a player and a play without naming the winner or the score, which makes them the least spoilery source found. The NBA's official YouTube channel posts one "FULL GAME HIGHLIGHTS" video per game with a stable video ID (the October 24, 2026 Spurs at Mavericks game is `vTUV7qXzPSA`), and YouTube oEmbed returns embed code for it, which proves embedding is enabled; however, the channel's player-spotlight titles publish stat lines such as "42 Points and 8 Threes", which spoil. Reddit r/nba has a "Highlight" post flair and per-game highlight posts that link YouTube clips, but Reddit's own JSON endpoints now return a login wall to anonymous requests, so matching would depend on unofficial archives. A YouTube iframe embed cannot hide its title (Google retired the `showinfo` parameter in 2018 and the title and channel avatar now always render), and `rel=0` no longer suppresses related videos, so spoiler-free display has to be built by the site itself with neutral labels, blurred or replaced thumbnails, and hidden durations. For legal use, the YouTube Terms expressly permit showing videos through the embeddable player, which makes official NBA YouTube embeds the safest option for a free or ad-supported page, while hotlinking ESPN CDN files carries no such permission and League Pass condensed games cannot be embedded at all.

## Context

Bad Game Warning (repo `/Users/bradley_mankoff/Developer/personal_code/bad_game_warning`, server in `app.py`) is a spoiler-free page for a Dallas Mavericks fan deciding whether tonight's game is worth watching from behind. The server never sends the score, clock, quarter, or win-probability percentage to the phone, not even in the page source. The owner wants to add a HIGHLIGHTS link for games, especially games judged "Stay away", plus criteria for which highlights to show, possibly per team. All findings below were gathered on 2026-10-25 against the October 24, 2026 Spurs at Mavericks game (ESPN event `401909858`, final: Spurs 122, Mavericks 106).

## 1. ESPN summary `videos` field

The endpoint `https://site.api.espn.com/apis/site/v2/sports/basketball/nba/summary?event=401909858` returns top-level keys including `boxscore`, `plays`, `winprobability`, `header`, and `videos`. The sampled game had 4 clips in `videos`.

Each clip contains: numeric `id`, `source` ("espn"), `headline`, `description`, `duration` in seconds, `thumbnail` (a direct ESPN CDN JPEG), `links.web.href` (an espn.com video clip page), `links.source` (direct MP4 under `espnmedia-cdn.akamaized.net`, plus HLS and CMAF playlist variants), `tracking` (with `coverageType`, e.g. "OnePlay"), and `timeRestrictions` (an `embargoDate` minutes after the play and an `expirationDate` about nine months out, `2027-07-31` for these clips).

The four sampled headlines were "Stephon Castle throws down powerful slam dunk vs. Dallas Mavericks" (18s, id `50271878`), "Naji Marshall gets the basket plus the foul" (15s), "P.J. Washington with the and-1 bucket" (16s), and "Julian Champagnie gets up for the beautiful flush" (16s). None of the four names the winner or gives a score, so single-play headlines read as non-spoilers in this sample.

The sampled thumbnails are also non-spoilers. The Castle clip thumbnail is a wide action still showing the court with the shot clock at 7:08 and no score visible, so it reveals at most that the game was close enough to show a crowd shot, not who won. The thumbnail carries a DAZN logo in the corner, which suggests ESPN sources some clips from broadcast feeds.

Two cautions. First, every clip in this sample has `tracking.coverageType` "OnePlay", meaning single plays, not a full-game recap; a recap-style clip (whose headline could name the winner) may appear for other games but did not appear here, so recap behavior is unverified. Second, each clip carries `geoRestrictions` with a `whitelist` of roughly 100 country codes (the list includes US, UK, and much of the Americas, Europe, and Asia-Pacific), so ESPN clips are not guaranteed playable in every country.

The matching identifier is stable: the same ESPN event ID used for win probability (`401909858`) keys the summary that contains the clips, so no extra lookup is needed to attach ESPN highlights to a game the app already tracks.

## 2. Other highlight sources

### NBA official YouTube channel

The NBA posts one "FULL GAME HIGHLIGHTS" video per game. Verified by YouTube oEmbed responses (no API key needed): `vTUV7qXzPSA` is titled "SPURS at MAVERICKS | FULL GAME HIGHLIGHTS | October 24, 2026" by author "NBA", `7wKdoaRzQB0` is "WARRIORS at SUNS | FULL GAME HIGHLIGHTS | October 24, 2026". The full-game titles name both teams and the date but not the score, so titles alone do not spoil the winner. The sampled Spurs-Mavericks thumbnail is a graphic with two player portraits and "FULL GAME HIGHLIGHTS" text and shows no score, but YouTube thumbnails are editorial and other games may differ, so thumbnails need per-video checking, not a blanket trust.

The channel also posts player-spotlight clips whose titles do spoil: `30RfpjnXCiU` is "Jamal Murray Lights It Up From Deep With 42 Points and 8 Threes" and `X4-58Ns1frs` is "Nikola Jokic Delivers a 35-Point Triple-Double in All-Around Masterclass", both dated October 24, 2026. A spoiler-free page must therefore link only the "FULL GAME HIGHLIGHTS" videos and never spotlight clips or the channel page itself.

Matching a video to a game is feasible but fuzzy: the title pattern "AWAY at HOME | FULL GAME HIGHLIGHTS | Month D, YYYY" plus the upload date gives a match on team abbreviations and date, and oEmbed (`https://www.youtube.com/oembed?url=...&format=json`) confirms a video exists and returns its exact title, author, and thumbnail URL without an API key. oEmbed is verification, not search; finding the video ID still requires the YouTube Data API `search.list` or an unofficial index.

### Team channels

The Dallas Mavericks run an official channel at `https://www.youtube.com/channel/UCwMUtT-zjoJOrtNmSWoMo0w` (handle `@DallasMavs`, page title "Dallas Mavericks"), verified by fetching the handle page and reading its canonical link and `og:title`. Its per-game upload pattern (whether it posts full-game highlights or only feature clips) was not checked in this pass.

### YouTube Data API quota

The current `search.list` documentation page states: "Quota impact: 100 calls per day. A call to this method has a quota cost of 1 unit in the Search Queries quota bucket." That bucket language is newer than the widely cited older scheme (search cost 100 units from a 10,000 unit daily pool), and the full quota table sits behind script-rendered pages that plain fetching could not read, so the exact daily search budget is only partly verified. Practical consequence either way: per-game `search.list` calls are the most expensive operation, so the design should search once per game, cache the video ID, and use keyless oEmbed for verification rather than polling search.

### NBA.com video, NBA app, League Pass

NBA.com serves video through script-rendered pages; fetching `nba.com/stats/video/search` and the NBA stats JSON endpoints returned bot walls ("Content Unavailable" and Akamai "Access Denied"), so no stable NBA.com per-game video identifier was found. The NBA app's store listing (via the iTunes Search API for "NBA: Live Games & Scores" by NBA MEDIA VENTURES, LLC) advertises highlights, favorite teams and players, and personalized updates, which supports per-team and per-player highlight filtering inside the app, but no shareable per-game URL scheme was found. League Pass condensed games are stream-only inside the app and subscriptions with no documented embed or deep-link scheme, so they cannot back a link on this page. The NBA's "Hide Scores" mode (a spoiler-free viewing feature) is widely reported but its primary-source support page sat behind a bot wall in this pass, so it is listed under unknowns rather than asserted.

### Reddit r/nba

The subreddit uses a "Highlight" link flair and post titles such as "[Highlight] Devin Booker vs Warriors Oct 24, 2026 Full Play - 43 Points, 7 Rebounds, 7 Assists!" (post id `1xeu11g`, linking `youtube.com/watch?v=XZUiFfO_n4E`), verified through the third-party Arctic Shift archive API. That example shows both the value (human-curated best plays with stable post IDs and linked YouTube IDs) and the spoiler problem (stat lines in titles). Reddit's own `.json` endpoints returned a login-wall page to anonymous requests, consistent with the post-2023 API restrictions, so first-party Reddit matching now needs authenticated API access; the archive API worked anonymously but is unofficial and rate-limits aggressively (one query in this pass returned "Timeout. Maybe slow down a bit").

## 3. Spoiler-free highlight viewing

Known techniques and products, with what each hides:

- Firefox add-ons found through the add-ons API (47 results for "spoiler youtube") include `youtube-no-spoilers` ("hiding video time info, scrubber, recommendations, comments"), `no-youtube-spoilers` ("blurring and hiding titles and thumbnails"), `youtube-spoiler-blocker` ("blocking video length information"), and `youtube-antispoiler` ("hide time display and progress bar for videos matching words in title"). The recurring toolkit is: blur or replace thumbnails, hide durations and progress bars, suppress titles, recommendations, and comments.
- The page itself can apply the same toolkit with plain markup and styles: link with a neutral label such as "Watch highlights" instead of the video title, a generic play-button graphic instead of the video thumbnail, and no duration anywhere, since durations hint at game shape (a 12-minute reel suggests overtime).
- A YouTube iframe embed cannot hide its title. Google's embed parameter documentation states that `showinfo` is deprecated and "the channel avatar and video title will always display before playback begins, when playback is paused, and when playback ends." The `rel` parameter changed in September 2018 so related videos can no longer be disabled (restrictive mode now shows same-channel videos only). `controls=0` hides the player controls, which removes the visible progress bar, but the title overlay remains, so the safe pattern is a neutral outbound link or a click-to-play facade that only creates the iframe after the user opts in, never an inline titled player on a spoiler-free page.
- ESPN direct MP4 or HLS links have no platform chrome at all (no title, no related videos), which makes them the cleanest technical embed, but the legal section below explains why they are the riskiest to use.

## 4. Legal

YouTube's Terms of Service permit embedding: "You may also show YouTube videos through the embeddable YouTube player." That sentence was read directly from the current Terms page. For NBA uploads specifically, embedding is enabled in practice: YouTube oEmbed returned iframe embed code for all four sampled NBA videos (three game and spotlight clips plus the Spurs-Mavericks reel), and uploaders who disable embedding also disable oEmbed, so a successful oEmbed response doubles as an embed-permission check the server can run per video. YouTube embeds keep YouTube's advertising and view-counting intact, which is the arrangement the platform's business model expects from free or ad-supported third-party pages.

ESPN is different. The MP4 and HLS URLs in the summary response are unsigned and fetched fine anonymously, but no license text was found granting reuse, and ESPN's clip pages and terms were not reviewed in this pass, so hotlinking ESPN video on a public page should be treated as unlicensed until counsel or ESPN's terms say otherwise.

NBA.com's legal pages (`nba.com/terms-of-use`, `legal.nba.com`, and the help center) returned bot-wall or challenge pages to anonymous fetching, so the NBA's own written video-reuse terms are unverified here. The practical reading is conservative: link to or embed the NBA's official YouTube uploads through YouTube's player (the distribution channel the league itself monetizes), and do not rehost video files or hotlink non-YouTube streams.

## 5. Highlight criteria ideas and available metadata

Useful metadata found in this pass, grouped by criterion:

- Per team: the NBA channel's one-reel-per-game pattern with "AWAY at HOME" titles and the Mavericks' official channel give team-scoped sources; ESPN clips carry the opponent in the headline ("vs. Dallas Mavericks") so a text match on the team name filters them.
- Per player: ESPN `plays` entries carry `participants` with ESPN athlete IDs (e.g. Wembanyama `5104157`, Gafford `4278049`) that join to the `boxscore` athlete records with names, jerseys, positions, and stat lines, so "favorite player" filtering can match clips to players. YouTube supports the same by searching player names, at quota cost.
- Play types: ESPN play text uses searchable verbs ("makes running dunk", "and-1 bucket"), and structured fields mark `scoringPlay`, `scoreValue`, `shootingPlay`, and a `type` object with id and text (e.g. id `99`, "Free Throw - 2 of 2"), plus `period`, `clock.displayValue`, and court `coordinate`. A dunk, block, or three-pointer filter can therefore start as text matching on the sampled vocabulary and graduate to the structured `type` ids after sampling more games. ESPN video `tracking.coverageType` ("OnePlay" in this sample) may offer further categorization once more games are sampled.
- Game situation: win probability, period, and clock are already in the app, so criteria like "only show highlights for games that were close" or "clutch plays only" can reuse the existing ESPN data rather than new sources.

Suggested starting criteria for a Dallas Mavericks fan: for "Stay away" games link the single-play ESPN-style clips or the NBA "FULL GAME HIGHLIGHTS" reel behind a neutral label; prefer Mavericks-player plays (join athlete IDs to the Dallas roster from boxscore); exclude spotlight clips and any title containing digits plus "Points" or "Triple-Double"; and never render YouTube titles, thumbnails, durations, related videos, or comments on the page.

## What is still unknown

- Whether ESPN's `videos` field ever contains a full-game recap clip whose headline names the winner, since the sampled blowout contained only single-play clips.
- The exact current YouTube Data API daily search budget, because the quota table pages render client-side; only the "1 unit in the Search Queries quota bucket" line was captured.
- The Mavericks channel's per-game upload pattern and whether its titles or thumbnails spoil scores.
- Whether the NBA's written terms permit or forbid the uses above, since all NBA legal and support pages were bot-walled; this includes primary-source confirmation of League Pass "Hide Scores" and any condensed-game deep links.
- ESPN's terms on reusing its CDN video URLs, which were not reviewed.
- Whether `controls=0` fully hides duration in all YouTube embed contexts, and whether the NBA's YouTube thumbnails ever carry final scores for Mavericks games beyond the sampled reel.
- A durable Reddit matching strategy, since the official API needs authentication and the unofficial archive throttles.
