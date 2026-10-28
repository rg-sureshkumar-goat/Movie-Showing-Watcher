# Ramayana Tamil IMAX watcher

Checks Fandango every 15 minutes for **Ramayana: Rise of a Legend** showings in
**Tamil** around Austin, TX, on any **Friday, Saturday or Sunday**, in any of
three formats: **IMAX**, **Cinemark XD** and **3D**. When one shows up, it sends
you a Telegram message with a booking link for each showtime. Each format gets
its own section in the message. It runs on GitHub Actions, like Gary, so it
keeps checking while your Mac is asleep.

Each run looks at every Fri/Sat/Sun from Nov 6 (the first weekend after the
Nov 5 opening) to 4 weeks out. New weekends roll in on their own as theaters
publish them, through Jan 31, 2027.

## Where it looks

Each zip searches roughly 15 miles around it:

| Zip | Area | IMAX screens nearby |
|---|---|---|
| 78701 | Central Austin | ⭐ AMC Barton Creek Square 14, Regal Gateway 4DX & IMAX |
| 78664 | Round Rock / Hutto / Pflugerville / Georgetown | Hooky Entertainment Hutto + IMAX |
| 78613 | Cedar Park / Leander | — |
| 78640 | Kyle / Buda / San Marcos | EVO Entertainment Kyle + IMAX |
| 78620 | Dripping Springs / Bee Cave | EVO Cinemas Belterra Village + IMAX |

**AMC and Cinemark (⭐):** any match at these chains is starred and listed first.
The daily check-in also reports on each of their local theaters. Of the 3 AMCs
nearby, only **AMC Barton Creek Square 14** has IMAX. **No Cinemark in the Austin
area has IMAX.** Their premium screen is Cinemark XD, so XD is watched as its own
format. Today that's Cinemark Pflugerville 20 and XD.

## What you'll get

There are only two kinds of messages. A day with nothing found is **exactly one
message**.

- **📅 Daily update**: one message every day, on the first run after 9 AM
  Austin time. It always fits in a single Telegram message. It leads with either:
  - **❌ No Tamil showings found yet**, or
  - **✅ N Tamil showings on sale**, with a booking link for every show still on sale.

  After that come counts per format and a line for every AMC and Cinemark. Any
  "language not listed" shows also go here (see below). If Fandango couldn't be
  reached on the last 3+ checks, the update says so instead. That replaces the
  normal update for the day and isn't sent as an extra message.
- **🎬 Found!**: sent the moment a new Tamil IMAX, Cinemark XD or 3D showing
  appears, at any hour, with one section per format in that order. Each show
  appears in only one section: an "IMAX 3D" show is listed under IMAX, and a
  Cinemark XD 3D show under XD. Each showtime is texted once.

**Language not listed:** the EVO theaters don't tag a language on Fandango, so
their IMAX and XD Ramayana shows *might* be Tamil. They aren't confirmed, so they
don't get their own text. They're listed with booking links in the daily update.
Untagged 3D shows are only counted. EVO runs a few every weekend, and they're
almost surely Hindi.

`state/state.json` records what's been texted and whether today's update went
out. The workflow commits it back to the repo after every run.

## Setup on GitHub

1. **Telegram bot.** This bot uses its own Telegram bot, separate from Gary's.
   Message **@BotFather** in Telegram, send `/newbot`, copy the token, then send
   your new bot any message. To find the chat ID, open
   `https://api.telegram.org/bot<TOKEN>/getUpdates` and look for
   `"chat":{"id":`. Or put the token in a local `.env` (copy `.env.example`)
   and run `python3 ramayana_bot.py --get-chat-id`.
2. **Create a repo** on github.com, e.g. `ramayana-watcher`. Make it public like
   Gary: Actions minutes are free on public repos. A private repo gets 2,000
   free minutes a month, and this bot uses about 3,000. Nothing private is in the
   repo; the token stays in secrets.
3. **Add the secrets** under Settings → Secrets and variables → Actions → New
   repository secret: `TELEGRAM_BOT_TOKEN` and `TELEGRAM_CHAT_ID`.
4. **Push this folder** to the repo.
5. **Test it** under Actions → "ramayana - watch" → Run workflow. The first run
   after 9 AM sends that day's update, so you'll know messages arrive.

GitHub's scheduler is best-effort: runs can start a few minutes late, and
occasionally one is skipped when GitHub is busy.

## Running it locally

```bash
python3 ramayana_bot.py --dry-run
```
This prints every Ramayana showtime it finds, plus the messages it would send:
the daily update, and a "found" alert if there's a new show. It sends nothing
and saves nothing. `--test` sends a test
Telegram message using `.env`.

## Changing what it looks for

Edit the settings at the top of `ramayana_bot.py` and push:

- `WATCH_WEEKDAYS`: days to watch (Monday is 0; Fri/Sat/Sun is `(4, 5, 6)`)
- `LOOKAHEAD_DAYS` / `STOP_AFTER`: how far ahead, and when to stop for good
- `LANGUAGE_KEYWORD`: e.g. `"telugu"`
- `FORMATS`: formats to watch, in priority order; add e.g. `"dolby": "Dolby Cinema"`
- `UNLISTED_DAILY_FORMATS`: formats whose "language not listed" shows are listed in the daily update; `()` to turn this off
- `PRIORITY_CHAINS`: chains to star and report on daily
- `ZIP_CODES`: areas to search
- `DAILY_MESSAGE_HOUR`: Austin-time hour of the daily update (default 9 AM)
