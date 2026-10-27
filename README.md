# Ramayana Tamil IMAX watcher

Checks Fandango every 15 minutes for **Ramayana: Rise of a Legend** showings in
**Tamil** on **IMAX** screens around Austin, TX, on any **Friday, Saturday or
Sunday**. When one shows up, it sends you a Telegram message with a booking link
for each showtime. It runs on GitHub Actions, like Gary, so it keeps checking
while your Mac is asleep.

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
area has IMAX.** Their premium screen is Cinemark XD. To count XD too, see
"Changing what it looks for" below.

## What you'll get

- **🎬 Tamil IMAX found**: the theater lists the show as Tamil and IMAX. Tap a time to book.
- **❓ IMAX, language not listed**: the EVO theaters don't tag a language on
  Fandango at all, so their IMAX Ramayana shows are sent too, clearly marked. Check
  the language before buying.
- **👀 Daily check-in** (first run after 9 AM Austin time): how many shows are
  Tamil and how many are IMAX, plus a line for every AMC and Cinemark. This also
  tells you the bot is still running.
- **⚠️ Alert** if Fandango can't be reached 3 runs in a row.

Each showtime is sent once. `state/state.json` records what's been sent, and the
workflow commits it back to the repo after every run.

## Setup on GitHub

1. **Telegram bot.** Reuse Gary's bot (same token and chat ID) or make a new one:
   message **@BotFather** in Telegram, send `/newbot`, copy the token, then send
   your new bot any message. To find the chat ID, put the token in a local `.env`
   (copy `.env.example`) and run `python3 ramayana_bot.py --get-chat-id`.
2. **Create a repo** on github.com, e.g. `ramayana-watcher`. Make it public like
   Gary: Actions minutes are free on public repos. A private repo gets 2,000
   free minutes a month, and this bot uses about 3,000. Nothing private is in the
   repo; the token stays in secrets.
3. **Add the secrets** under Settings → Secrets and variables → Actions → New
   repository secret: `TELEGRAM_BOT_TOKEN` and `TELEGRAM_CHAT_ID`.
4. **Push this folder** to the repo.
5. **Test it** under Actions → "ramayana - watch" → Run workflow. The first run
   after 9 AM sends the daily check-in, so you'll know messages arrive.

GitHub's scheduler is best-effort: runs can start a few minutes late, and
occasionally one is skipped when GitHub is busy.

## Running it locally

```bash
python3 ramayana_bot.py --dry-run
```
This prints every Ramayana showtime it finds, the message it would send, and the
daily check-in. It sends nothing and saves nothing. `--test` sends a test
Telegram message using `.env`.

## Changing what it looks for

Edit the settings at the top of `ramayana_bot.py` and push:

- `WATCH_WEEKDAYS`: days to watch (Monday is 0; Fri/Sat/Sun is `(4, 5, 6)`)
- `LOOKAHEAD_DAYS` / `STOP_AFTER`: how far ahead, and when to stop for good
- `LANGUAGE_KEYWORD`: e.g. `"telugu"`
- `FORMAT_KEYWORD`: e.g. `"xd"` for Cinemark XD, or `"dolby"`
- `PRIORITY_CHAINS`: chains to star and report on daily
- `ZIP_CODES`: areas to search
- `NOTIFY_UNLISTED_LANGUAGE`: `False` to skip the "language not listed" alerts
- `HEARTBEAT_HOUR`: `None` to turn off the daily check-in
