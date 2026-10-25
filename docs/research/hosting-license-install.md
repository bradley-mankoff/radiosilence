# Hosting, license, and installation research for Bad Game Warning

Bad Game Warning (single dependency-free Python file `app.py`, port 8765, launchd on the owner's Mac) can move to public use cheapest on Cloud Run's free tier or a 2 to 5 dollar per month Fly.io or Railway service, can keep its future ad revenue under Apache-2.0 or MIT while AGPL-3.0 would force hosted competitors to publish their changes, can reach phones as an installable PWA with iOS 16.4 plus web push rather than a native wrapper, and can serve 100k users for roughly tens of dollars per month once one cached ESPN fetch per minute replaces today's fetch per page load.

## 0. What the app is today (context for every finding below)

`app.py` is a single dependency-free Python file using only the standard library (`http.server`, `urllib`). It reads the Dallas Mavericks schedule and win-probability data from ESPN's public endpoints (`https://site.api.espn.com/apis/site/v2/sports/basketball/nba`), computes one verdict (Watch, Stay away, Too early to call, Next game, Can't tell), and serves a small HTML page that refreshes every 60 seconds (README.md, app.py). A launchd agent (`com.bradley.bad-game-warning.plist`) starts it at login on port 8765, and the phone opens `http://Bradleys-MacBook-Pro-2.local:8765/` on the home network (README.md). The server log showing TLS handshake bytes means some phone tried `https://` against the plain-HTTP socket, so the server read a TLS ClientHello as garbage. Any option below that terminates TLS (all hosted options, Tailscale Funnel, Cloudflare Tunnel) fixes this with no app change. Serving TLS from `app.py` itself is the alternative passed over, because it would add certificate management code to a file whose value is having none.

## 1. License choices and what each lets a competitor do with a hosted copy

All quotes below were verified against the license texts on 2026-10-25 via choosealicense.com pages and the GitHub Licenses API (`gh api licenses/...`).

### MIT (https://choosealicense.com/licenses/mit/)

The MIT text permits dealing in the software "without restriction, including without limitation the rights to use, copy, modify, merge, publish, distribute, sublicense, and/or sell copies of the Software," with the single condition that "the above copyright notice and this permission notice shall be included in all copies or substantial portions of the Software." The GitHub API records its permissions as commercial-use, modifications, distribution, private-use, its only condition as include-copyright, and its limitations as liability and warranty. A competitor may therefore take the app, run a hosted copy, modify it, close the source, sell ads against it, and never publish changes. The owner keeps full freedom to monetise his own copy with ads later.

### Apache-2.0 (https://choosealicense.com/licenses/apache-2.0/)

Choosealicense.com describes Apache-2.0 as permissive with the added main conditions of preserving copyright and license notices, an express patent grant from contributors, and permission to distribute modified and larger works "under different terms and without source code." The GitHub API adds patent-use to the permission list and document-changes to the conditions. Practically this is MIT plus two differences: contributors grant patent rights (useful once outside contributors exist), and modifiers must state what they changed. A competitor can still run a closed hosted copy with ads. This is the recommended default for an owner who may later monetise with ads, because it is permissive, corporate-accepted, and patent-safe.

### AGPL-3.0 (https://choosealicense.com/licenses/agpl-3.0/)

Choosealicense.com states that permissions are conditioned on making available the complete source of licensed works and modifications, and that "when a modified version is used to provide a service over a network, the complete source code of the modified version must be made available." The GitHub API lists the conditions as include-copyright, document-changes, disclose-source, network-use-disclose, and same-license. A competitor may still run a competing hosted copy and sell ads, but must publish their modified source under AGPL-3.0, which removes the ability to compete on closed improvements. Choose AGPL-3.0 if the goal is deterring closed competitors rather than maximising adoption. Note that ads remain allowed under all three open licenses; none restricts commercial use.

### Source-available: Business Source License 1.1 (https://mariadb.com/bsl11/, SPDX BUSL-1.1)

The BSL publishes source but by default prohibits production use; the licensor grants extra rights through an "Additional Use Grant" parameter, and every copy must convert to a named open license ("Change License," GPL-compatible) on a "Change Date" no more than four years after publication (Wikipedia, "Business Source License," citing the BSL 1.1 text and a 2020 adoption survey). A competitor may read the code but may not run a production hosted copy unless the Additional Use Grant allows it, and the license is not OSI-approved open source. This fits an owner who wants a hard block on competitors running the service while promising eventual openness, at the cost of community trust and the "open source" label.

### Source-available: Elastic License 2.0 (https://www.elastic.co/licensing/elastic-license)

The verified license text forbids providing "the software to third parties as a hosted or managed service, where the service provides users with access to any substantial set of the features or functionality of the software," and requires modified copies to carry prominent notices of modification. A competitor may not offer Bad Game Warning itself as a hosted service, but may still study the code. Like BSL, it is source-available, not open source. It is stricter than needed here unless the owner specifically fears clone-hosting.

### Closed source (all rights reserved)

No reuse, no hosted copies, no modifications by anyone except the owner. This preserves maximum control and every future business model, but prevents community installs, contributions, and Homebrew or Docker distribution, which defeats the stated goal of letting other people use the app.

### Recommendation and relicensing note

Publish under Apache-2.0 now: permissive, ad-compatible, patent grant included. While the owner is the sole author, he can relicense at will later (for example, to AGPL-3.0 if a closed competitor appears), because no contributor consent is needed yet. Once outside contributions are accepted, relicensing requires each contributor's agreement, so pick the long-term license before accepting patches.

## 2. Cheapest hosting for a tiny Python HTTP server with HTTPS

Prices checked 2026-10-25; pages are JavaScript-heavy so figures below come from documentation endpoints and page-embedded data, cited per row.

| Option | Free tier | Paid cost for this app | HTTPS | Python fit |
|---|---|---|---|---|
| Cloud Run (https://cloud.google.com/run/pricing) | 2M requests, 180,000 vCPU-seconds, 360,000 GiB-seconds free per month; $0.40 per million requests after (figures extracted from the pricing page data) | $0 at this app's scale; scales to zero so idle costs nothing | Automatic managed TLS on the provided URL | Native; needs a Dockerfile, minor change from bare `app.py` |
| Fly.io (https://fly.io/docs/about/pricing/) | No standing free allowance for new organizations (pay as you go); free trial covers 2 hours of machine runtime or 7 days; only snapshots, certs, and inbound transfer stay free | Smallest always-on machine (shared-cpu-1x, 256 MB) $2.19/month plus tiny egress; roughly $2 to 4/month total | Automatic managed TLS certificates | Native; needs a Dockerfile |
| Railway (https://docs.railway.com/pricing, fetched 2026-10-25) | Free plan: $0/month with $1 of resource credit | Hobby $5/month subscription covers the first $5 of usage; resources priced at $20/vCPU/month, $10/GB RAM/month, $0.05/GB egress; this app fits inside the $5 Hobby subscription | Automatic managed TLS | Native; deploys from the repo with a start command, no Dockerfile strictly needed |
| Render (https://render.com/docs/free.md, https://render.com/docs/compute-plans.md) | Free web service: 750 instance-hours/month, but spins down after 15 minutes without traffic and takes about a minute to wake; unsuitable for a game-night verdict page | Paid plans from the Starter tier (historically about $7/month; verify on https://render.com/pricing) | Automatic managed TLS on paid and free | Native Python web service |
| Cloudflare Workers (https://developers.cloudflare.com/workers/platform/pricing/) | Free plan has limited usage; Paid plan is $5/month minimum including 10M requests and 30M CPU-ms per month, then $0.30 per extra million requests | $0 to 5/month, but requires rewriting the stdlib server in JS or Python Workers (Python support exists in Workers) | Automatic | Poor fit; rewrite required, so passed over unless request volume justifies it |
| Home Mac plus Tailscale Funnel (https://tailscale.com/kb/1223/funnel, fetched 2026-10-25) | Free on all plans including Personal; command `tailscale funnel 8765` exposes the port as `https://<machine>.<tailnet>.ts.net` | $0 beyond the Mac's electricity | Automatic, TLS-only, Let's Encrypt certificates provisioned by Tailscale | Perfect fit; `app.py` unchanged; fixes the phone-HTTPS log errors with one command |
| Home Mac plus Cloudflare Tunnel (`cloudflared`) (https://developers.cloudflare.com/cloudflare-one/connections/connect-networks/) | Tunnel software free; requires a domain with DNS on Cloudflare (about $10/year) | About $1/month amortised | Full TLS to visitors | Perfect fit; `app.py` unchanged |

Recommendation: keep the home Mac behind Tailscale Funnel for $0 today (fastest fix for the HTTPS errors), and move to Cloud Run when serving strangers, because its free tier (2M requests/month) covers roughly the first 1k to 2k active users at zero cost and it scales to zero between games. Fly.io at about $2.19/month is the cheapest always-on alternative if the owner prefers a VM he controls.

## 3. Installation paths for end users

### PWA add-to-home-screen (recommended; no store needed)

Android/Chrome: a web app manifest (JSON with name, start URL, display mode, and icons) plus installability handling lets users install the app; Chrome shows an install prompt when criteria are met and users can install even outside the prompt flow (web.dev, "Add a web app manifest" and "Promote install," fetched 2026-10-25). The manifest needs at minimum the app name, launch URL, display mode, and icons at 192px and 512px (web.dev manifest article). iOS: users tap Share then Add to Home Screen; if the site serves a manifest with display `standalone` or `fullscreen`, it opens as a separate home-screen web app with its own app-switcher entry (WebKit blog, "Web Push for Web Apps on iOS and iPadOS," 2023-02-16). The current page already carries `apple-mobile-web-app-capable` and `apple-mobile-web-app-title` meta tags (app.py), so the remaining PWA work is: add `manifest.json` with 192/512px icons plus an `apple-touch-icon`, serve over HTTPS (any option in section 2), and optionally add a service worker for offline fallback.

### iOS web push for home-screen web apps (iOS 16.4 and later)

Web Push reached home-screen web apps in iOS/iPadOS 16.4 via the standard Push API, Notifications API, and Service Workers; a home-screen web app may request notification permission only in response to direct user interaction such as tapping a subscribe button, after which notifications behave like native ones on the Lock Screen, Notification Center, and Apple Watch (WebKit blog, 2023-02-16). Yes, the server can push "Stay away" or "Watch" without spoiling: the verdict is computed server-side and the push body carries only the one-line verdict, never the score, clock, or percentage, exactly as the page does today (app.py; project rule that the server never sends score data to the phone). Two caveats: push timing itself leaks a little (a notification implies a game is on and decided), and push requires work the app lacks today, namely a service worker, per-user push subscriptions (Web Push/VAPID keys plus a small subscription store), and HTTPS. Android supports the same standard Web Push without the home-screen prerequisite.

### Native wrapper (Capacitor)

Capacitor is a cross-platform native runtime that wraps a web app for iOS and Android and exposes native features including a Push Notifications plugin (Capacitor docs, https://capacitorjs.com/docs/getting-started, fetched 2026-10-25). It is the fallback if PWA installation proves too much friction, but it adds App Store and Play review, build pipelines, and signing for an app whose entire UI is two lines of text.

### App Store review risk

Guideline 4.2 (Minimum Functionality) states "Your app should include features, content, and UI that elevate it beyond a repackaged website. If your app is not particularly useful, unique, or 'app-like,' it doesn't belong on the App Store" (Apple App Store Review Guidelines, fetched 2026-10-25). A two-line verdict page wrapped natively is a textbook 4.2 rejection risk, which is a strong reason to ship as a PWA and skip the store. Sports content itself is not the obstacle: the gambling provisions (Guideline 5.1.1(ix), highly regulated fields including gambling) apply to gambling and fantasy-sports betting apps, not to a win-probability readout with no wagering. No gambling or contest features should be added without re-examining 5.3 and contest rules.

## 4. Self-host install option (for people who run it themselves)

The app's single-file, zero-dependency shape makes all three one-command paths easy; the Dockerfile and wrapper are the only new files needed.

- Docker (recommended self-host path): add a ~10-line Dockerfile (`FROM python:3-slim`, copy `app.py`, `CMD ["python3", "app.py"]`), then users run one command and get HTTPS by putting Caddy in front or by publishing through a tunnel. Ephemeral filesystem is irrelevant because the app stores nothing.
- pipx: requires adding minimal packaging (`pyproject.toml` with a console script entry point), after which users run `pipx install bad-game-warning`. Passed over as second choice because it adds packaging ceremony to a file whose point is having none.
- Homebrew: requires a formula in a tap (`brew tap owner/tap`), after which users run `brew install bad-game-warning`; the formula can install the launchd plist like the current setup. Best for Mac-only users who want launchd autostart exactly as the owner has it.

## 5. Scaling: one ESPN fetch per game for all users

The current code fetches ESPN on every page load (up to two requests: schedule plus summary), and the page refreshes every 60 seconds, so one fan watching a 3-hour game triggers about 180 page loads and 360 ESPN hits (app.py). The fix is a server-side cache: fetch the verdict once per 30 to 60 seconds during a game and serve every user from memory. ESPN load then becomes constant regardless of audience: about 180 to 360 requests per game, or roughly 15k to 30k requests per full 82-game season, which is negligible against any rate limit and costs nothing to serve on any option in section 2. Cost then scales only with page serving (page is about 1 KB):

| Users (active fans) | Page loads/month (assumes 15 games, 1 hour open per game, 60 refreshes) | Indicative cost |
|---|---|---|
| 1,000 | About 0.9M | $0 on Cloud Run free tier (2M requests), Fly.io (about $2 to 4), or Railway Hobby ($5) |
| 10,000 | About 9M | Cloud Run roughly $3 requests plus a few dollars of CPU and bandwidth (under $10); Render or Railway paid tiers roughly $7 to 25 |
| 100,000 | About 90M | Cloud Run roughly $35 requests plus compute and egress, on the order of $50 to 100 total; a small dedicated VM with caching (about $5 to 20) also handles it since the workload is one tiny cached string |

Assumptions are stated in the table; real cost depends on how long users keep the page open. The cache also needs a lock or single-flight fetch so a cold cache under 100k simultaneous users triggers one ESPN request, not 100k.

## Still unknown

- Whether ESPN's terms permit commercial or ad-supported use of the undocumented `site.api.espn.com` endpoints; the endpoints are public and unauthenticated, but no terms page was reviewed in this pass.
- Current Render Starter pricing in dollars (the pricing page is JavaScript-rendered and was unreadable to the fetcher; historically about $7/month, verify at https://render.com/pricing before recommending it).
- Whether the owner wants multi-team support before launch; the code hardcodes `TEAM = "DAL"` (app.py), and per-team verdict caching changes the ESPN fetch math linearly.
- Whether web push subscription storage (needed for section 3 push) is acceptable statefulness, since the app currently stores nothing and Render free and similar ephemeral hosts lose local files on sleep.
- Ad-network requirements (for example, AdSense site approval, privacy policy, and HTTPS) were not researched in this pass.
