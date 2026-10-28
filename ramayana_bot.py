#!/usr/bin/env python3
"""
Ramayana Tamil IMAX watcher.

Checks Fandango showtimes for theaters in and around Austin, TX and sends a
Telegram message with booking links as soon as a Tamil-language showing of
Ramayana on an IMAX or Cinemark XD screen is listed on a Friday, Saturday or
Sunday. Each showtime is only sent once. Standard library only.

Usage:
  python3 ramayana_bot.py                # check once, send new matches
  python3 ramayana_bot.py --dry-run      # check once, print results, send nothing
  python3 ramayana_bot.py --test         # send a test Telegram message
  python3 ramayana_bot.py --get-chat-id  # list chats that have messaged your bot
"""

import argparse
import datetime
import html
import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from zoneinfo import ZoneInfo

HERE = os.path.dirname(os.path.abspath(__file__))
STATE_PATH = os.path.join(HERE, "state", "state.json")
ENV_PATH = os.path.join(HERE, ".env")

# ---------------------------------------------------------------- settings ---

MOVIE_KEYWORD = "ramayana"
LANGUAGE_KEYWORD = "tamil"

# Screen formats to watch, as Fandango tag keyword -> label. Each format gets
# its own section in the text. They're checked in this order, so an "IMAX 3D"
# show counts as IMAX only. No Cinemark near Austin has IMAX; its premium
# screen is Cinemark XD, so that is watched too.
FORMATS = {
    "imax": "IMAX",
    "xd": "Cinemark XD",
    "3d": "3D",
}

# Some theaters (EVO Belterra and EVO Kyle, two of the five local IMAX venues)
# don't tag the language on Fandango at all. Their showings in these formats
# are listed with booking links in the daily message as "language not listed".
# They aren't confirmed Tamil, so they never get a text of their own. 3D is
# left out: EVO runs untagged 3D shows every week that are almost surely
# Hindi, so those are only counted. Use () to turn this off.
UNLISTED_DAILY_FORMATS = ("IMAX", "Cinemark XD")
LANGUAGE_WORDS = ("hindi", "tamil", "telugu", "kannada", "malayalam", "language", "dubbed")

# Which days to watch (Monday is 0): Friday, Saturday, Sunday.
WATCH_WEEKDAYS = (4, 5, 6)
# The film opens Thursday Nov 5, so the first weekend day is Friday Nov 6.
FIRST_DATE = datetime.date(2026, 11, 6)
# Theaters publish schedules a week or two out, so look this far ahead from
# today on every run; new weekends roll into the window on their own.
LOOKAHEAD_DAYS = 28
# Stop checking after this date (the film will be long gone by then).
STOP_AFTER = datetime.date(2027, 1, 31)

# Chains to watch most closely: matches there are starred and listed first,
# and the daily update reports on every one of their local theaters.
PRIORITY_CHAINS = ("amc", "cinemark")

# Fandango returns theaters within ~15 miles of each zip. Together these cover
# all five Austin-area IMAX screens (Regal Gateway, AMC Barton Creek, EVO
# Belterra, Hooky Hutto, EVO Kyle) and every local AMC and Cinemark.
ZIP_CODES = {
    "78701": "Central Austin",
    "78664": "Round Rock / Hutto / Pflugerville / Georgetown",
    "78613": "Cedar Park / Leander",
    "78640": "Kyle / Buda / San Marcos",
    "78620": "Dripping Springs / Bee Cave",
}

# All dates and times are Austin time, even on GitHub's UTC runners.
TIMEZONE = ZoneInfo("America/Chicago")

# Exactly one daily message, found or not, on the first run at or after this
# local hour. Found showings are also texted the moment they appear; nothing
# else is ever sent, so a day with nothing found is one message.
DAILY_MESSAGE_HOUR = 9

# If Fandango can't be reached, the daily message waits for this many failed
# runs in a row before reporting that instead, so a single blip at 9 AM
# doesn't replace the real update.
FAILURE_ALERT_AFTER = 3

REQUEST_DELAY_SECONDS = 0.7
USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36"
)
FANDANGO_API = "https://www.fandango.com/napi/theaterswithshowtimes"
TELEGRAM_LIMIT = 3900  # Telegram caps messages at 4096 characters


def now():
    return datetime.datetime.now(TIMEZONE)


def log(msg):
    print(f"[{now().strftime('%Y-%m-%d %H:%M:%S %Z')}] {msg}", flush=True)


def load_env():
    if not os.path.exists(ENV_PATH):
        return
    with open(ENV_PATH) as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            os.environ.setdefault(key.strip(), value.strip().strip("\"'"))


def load_state():
    try:
        with open(STATE_PATH) as f:
            return json.load(f)
    except (OSError, ValueError):
        return {"notified": {}, "last_daily": None, "failures": 0}


def save_state(state):
    os.makedirs(os.path.dirname(STATE_PATH), exist_ok=True)
    tmp = STATE_PATH + ".tmp"
    with open(tmp, "w") as f:
        json.dump(state, f, indent=2, sort_keys=True)
        f.write("\n")
    os.replace(tmp, STATE_PATH)


def watch_dates(today):
    first = max(FIRST_DATE, today)
    last = min(today + datetime.timedelta(days=LOOKAHEAD_DAYS), STOP_AFTER)
    days = (last - first).days + 1
    candidates = (first + datetime.timedelta(days=i) for i in range(max(days, 0)))
    return [d for d in candidates if d.weekday() in WATCH_WEEKDAYS]


# ---------------------------------------------------------------- fandango ---

class FetchError(Exception):
    pass


def fetch_showtimes(zip_code, date):
    params = urllib.parse.urlencode({
        "zipCode": zip_code,
        "city": "",
        "state": "",
        "date": date.isoformat(),
        "page": 1,
        "favTheaterOnly": "false",
        "limit": 40,
        "isdesktop": "true",
        "filter": "open-theaters",
        "filterEnabled": "true",
    })
    req = urllib.request.Request(f"{FANDANGO_API}?{params}", headers={
        "User-Agent": USER_AGENT,
        "Accept": "application/json, text/plain, */*",
        "Referer": f"https://www.fandango.com/{zip_code}_movietimes?date={date.isoformat()}",
    })
    last_error = None
    for attempt in range(3):
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                data = json.loads(resp.read().decode("utf-8"))
            if "theaters" not in data:
                raise FetchError("unexpected response shape")
            return data["theaters"]
        except (urllib.error.URLError, ValueError, FetchError, OSError) as e:
            last_error = e
            time.sleep(2 * (attempt + 1))
    raise FetchError(f"{zip_code} {date}: {last_error}")


def contains(texts, keyword):
    return any(keyword in (t or "").lower() for t in texts)


def is_priority(name, chain=""):
    return any(c in f"{name} {chain}".lower() for c in PRIORITY_CHAINS)


def collect_showings(dates):
    """Return (showings, theaters, errors, requests). Each showing is a dict for
    one Ramayana showtime at one theater, deduplicated across zip codes;
    theaters maps every theater seen to its name, city and screen formats."""
    showings = {}
    theaters_seen = {}
    errors = []
    requests = 0
    for date in dates:
        for zip_code in ZIP_CODES:
            requests += 1
            try:
                theaters = fetch_showtimes(zip_code, date)
            except FetchError as e:
                errors.append(str(e))
                log(f"fetch failed: {e}")
                continue
            finally:
                time.sleep(REQUEST_DELAY_SECONDS)
            for theater in theaters:
                priority = is_priority(theater.get("name", ""), theater.get("chainName", ""))
                theaters_seen[theater.get("id", "")] = {
                    "name": theater.get("name", ""),
                    "city": theater.get("city", ""),
                    "priority": priority,
                    # Fandango's format list can miss a screen the name advertises
                    # ("Cinemark Pflugerville 20 and XD"), so check both.
                    "formats": [label for keyword, label in FORMATS.items()
                                if contains((theater.get("formats") or []) + [theater.get("name", "")], keyword)],
                }
                for movie in theater.get("movies") or []:
                    if MOVIE_KEYWORD not in movie.get("title", "").lower():
                        continue
                    for variant in movie.get("variants") or []:
                        for group in variant.get("amenityGroups") or []:
                            tags = [a.get("name", "") for a in group.get("amenities") or []]
                            for show in group.get("showtimes") or []:
                                # ticketingDate looks like "2026-11-05+19:30"
                                when = show.get("ticketingDate", "")
                                if not when.startswith(date.isoformat()):
                                    continue
                                # Fandango omits the numeric showtime id on some
                                # listings, so key on what identifies the screening.
                                key = "|".join([theater.get("id", ""), when,
                                                str(group.get("movieVariantId", "")), ",".join(sorted(tags))])
                                showing = showings[key] = {
                                    "id": key,
                                    "theater_id": theater.get("id", ""),
                                    "date": date.isoformat(),
                                    "time": show.get("date", ""),
                                    "sort_key": when,
                                    "theater": theater.get("name", ""),
                                    "city": theater.get("city", ""),
                                    "priority": priority,
                                    "title": movie.get("title", ""),
                                    "format": variant.get("filmFormatHeader", ""),
                                    "tags": tags,
                                    "url": show.get("ticketingJumpPageURL") or "",
                                    "sold_out": bool(show.get("isSoldOut")),
                                    "expired": bool(show.get("expired")),
                                }
                                showing["watch_format"] = watched_format(showing)
    return list(showings.values()), theaters_seen, errors, requests


def is_language(s):
    return contains([s["title"], s["format"]] + s["tags"], LANGUAGE_KEYWORD)


def watched_format(s):
    """Label of the first watched format this showing is in, or None."""
    for keyword, label in FORMATS.items():
        if contains([s["format"]] + s["tags"], keyword):
            return label
    return None


def has_language_info(s):
    return any(contains([s["title"], s["format"]] + s["tags"], w) for w in LANGUAGE_WORDS)


def languages(s):
    names = [w.title() for w in ("tamil", "hindi", "telugu", "kannada", "malayalam")
             if contains([s["title"]] + s["tags"], w)]
    if contains(s["tags"], "english language") or contains(s["tags"], "english dub"):
        names.append("English")
    return names


def is_bookable(s):
    return bool(s["url"]) and not s["sold_out"] and not s["expired"]


def classify(showings):
    """Split bookable showings into (confirmed, unlisted): confirmed are tagged
    with the language and a watched format; unlisted are in a watched format
    but the theater gave no language at all."""
    confirmed, unlisted = [], []
    for s in showings:
        if not (s["watch_format"] and is_bookable(s)):
            continue
        if is_language(s):
            confirmed.append(s)
        elif not has_language_info(s):
            unlisted.append(s)
    return confirmed, unlisted


# ---------------------------------------------------------------- telegram ---

def telegram_call(method, payload):
    token = os.environ.get("TELEGRAM_BOT_TOKEN", "")
    if not token:
        raise SystemExit("TELEGRAM_BOT_TOKEN is not set. Add it to .env (see README.md).")
    req = urllib.request.Request(
        f"https://api.telegram.org/bot{token}/{method}",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        raise RuntimeError(f"Telegram {method} failed: {e.code} {e.read().decode('utf-8', 'replace')}")


def send_telegram(text):
    chat_id = os.environ.get("TELEGRAM_CHAT_ID", "")
    if os.environ.get("TELEGRAM_BOT_TOKEN") and not chat_id:
        raise SystemExit("TELEGRAM_CHAT_ID is not set. Run --get-chat-id (see README.md).")
    for chunk in split_message(text):
        telegram_call("sendMessage", {
            "chat_id": chat_id,
            "text": chunk,
            "parse_mode": "HTML",
            "disable_web_page_preview": True,
        })


def visible_len(text):
    """Length as Telegram counts it: tags and link URLs don't count."""
    return len(html.unescape(re.sub(r"<[^>]+>", "", text)))


def split_message(text):
    chunks, current = [], ""
    for block in text.split("\n\n"):
        if current and visible_len(current) + visible_len(block) + 2 > TELEGRAM_LIMIT:
            chunks.append(current)
            current = block
        else:
            current = f"{current}\n\n{block}" if current else block
    if current:
        chunks.append(current)
    return chunks


def pretty_date(iso):
    d = datetime.date.fromisoformat(iso)
    return d.strftime("%a, %b ") + str(d.day)


def format_showings(shows):
    e = html.escape
    blocks = []
    groups = {}
    for s in sorted(shows, key=lambda s: (not s["priority"], s["sort_key"], s["theater"])):
        groups.setdefault((s["date"], s["theater"], s["city"], s["priority"], tuple(s["tags"])), []).append(s)
    for (date, theater, city, priority, tags), group in groups.items():
        relevant = [t for t in tags if any(contains([t], k) for k in FORMATS)
                    or contains([t], LANGUAGE_KEYWORD) or contains([t], "subtitle")]
        times = "  ".join(f'<a href="{e(s["url"])}">{e(s["time"])}</a>' for s in group)
        star = "⭐ " if priority else ""
        blocks.append(
            f"{star}<b>{e(pretty_date(date))}</b> · {e(theater)} ({e(city)})\n"
            f"{e(', '.join(relevant) or group[0]['format'])}\n"
            f"🎟 {times}"
        )
    return blocks


def take_blocks(blocks, budget):
    """As many blocks as fit in `budget` visible characters, then a note
    counting the rest, so the daily update always fits in one message."""
    kept, used = [], 0
    for i, block in enumerate(blocks):
        size = visible_len(block) + 2
        if used + size > budget:
            kept.append(f"…and {len(blocks) - i} more on Fandango.")
            break
        kept.append(block)
        used += size
    return kept


def format_by_format(shows, heading, budget=None):
    """One section per watched format, in FORMATS order. A budget, if given,
    is shared by all the sections."""
    e = html.escape
    lines = []
    for label in FORMATS.values():
        group = [s for s in shows if s["watch_format"] == label]
        if not group:
            continue
        blocks = format_showings(group)
        if budget is not None:
            blocks = take_blocks(blocks, budget)
            budget = max(budget - sum(visible_len(b) + 2 for b in blocks), 0)
        lines.append(heading.format(label=e(label)))
        lines += blocks
    return lines


def format_matches(confirmed):
    lines = format_by_format(confirmed, f"🎬 <b>Ramayana — {LANGUAGE_KEYWORD.title()} {{label}} showings found!</b>")
    lines.append("Tap a time to book on Fandango.")
    return "\n\n".join(lines)


def or_list(items):
    items = list(items)
    return items[0] if len(items) == 1 else ", ".join(items[:-1]) + " or " + items[-1]


def format_priority_status(showings, theaters):
    """One line per AMC/Cinemark theater: which languages it is showing the
    movie in during the watch window, and how many shows in each format."""
    e = html.escape
    order = list(FORMATS.values())
    lines = []
    ranked = sorted((t for t in theaters.values() if t["priority"]),
                    key=lambda t: (min((order.index(f) for f in t["formats"]), default=len(order)), t["name"]))
    for t in ranked:
        here = [s for s in showings if s["theater"] == t["name"]]
        label = e(t["name"]) + (f" ({e(', '.join(t['formats']))})" if t["formats"] else "")
        if not here:
            lines.append(f"• {label}: not showing it on these days yet")
            continue
        langs = sorted({l for s in here for l in languages(s)}) or ["language not listed"]
        detail = f"{', '.join(langs)}, {len(here)} shows"
        per_format = [(f, sum(1 for s in here if s["watch_format"] == f)) for f in order]
        if any(n for _, n in per_format):
            detail += " (" + ", ".join(f"{f}: {n}" for f, n in per_format if n) + ")"
        lines.append(f"• {label}: {e(detail)}")
    return "⭐ <b>AMC &amp; Cinemark</b>\n" + "\n".join(lines) if lines else ""


def daily_heading(today):
    return f"📅 <b>Ramayana daily update — {html.escape(pretty_date(today.isoformat()))}</b>"


def format_daily(today, showings, theaters, confirmed, unlisted, dates, errors, requests):
    """The one message sent every day: found or not found first, then detail."""
    e = html.escape
    lang_name = LANGUAGE_KEYWORD.title()
    lines = [daily_heading(today)]
    if confirmed:
        per_format = ", ".join(f"{f}: {n}" for f in FORMATS.values()
                               if (n := sum(1 for s in confirmed if s["watch_format"] == f)))
        lines.append(f"✅ <b>{len(confirmed)} {lang_name} showing{'s' if len(confirmed) != 1 else ''} "
                     f"on sale</b> ({e(per_format)}). Tap a time to book.")
        lines += format_by_format(confirmed, f"🎬 <b>{lang_name} {{label}}</b>", budget=1200)
    else:
        lines.append(f"❌ <b>No {lang_name} showings found yet</b> in {e(or_list(FORMATS.values()))}.")

    lang = [s for s in showings if is_language(s)]
    short = lambda d: d.strftime("%b ") + str(d.day)
    span = f"{short(dates[0])} to {short(dates[-1])}"
    counts = [f"• {len(showings)} Ramayana showtimes listed",
              f"• {len(lang)} in {lang_name} (any format)"]
    for f in FORMATS.values():
        total = sum(1 for s in showings if s["watch_format"] == f)
        found = sum(1 for s in confirmed if s["watch_format"] == f)
        counts.append(f"• {f}: {total} shows, {found} in {lang_name}")
    if unlisted:
        counts.append(f"• {len(unlisted)} with no language listed")
    lines.append(f"Checked every Fri–Sun from {e(span)}, Austin area:\n" + e("\n".join(counts)))

    status = format_priority_status(showings, theaters)
    if status:
        lines.append(status)

    maybe = [s for s in unlisted if s["watch_format"] in UNLISTED_DAILY_FORMATS]
    if maybe:
        lines.append(f"❓ <b>Language not listed</b>: these theaters don't say which language. "
                     f"Could be {lang_name}, so check before buying.")
        lines += take_blocks(format_showings(maybe), 600)

    other = [s for s in lang if not s["watch_format"]]
    if other:
        where = sorted({f"{s['theater']} ({pretty_date(s['date'])})" for s in other})
        lines.append(f"{lang_name} in other formats is playing at: " + e("; ".join(where[:6])))

    if errors:
        lines.append(f"⚠️ {len(errors)} of {requests} Fandango checks failed this run, so this may be incomplete.")
    lines.append("I'll text you the moment a new one is listed." if confirmed
                 else f"I'll text you the moment a {lang_name} showing is listed.")
    return "\n\n".join(lines)


def format_daily_failure(today, failures, error):
    return "\n\n".join([
        daily_heading(today),
        f"⚠️ <b>Couldn't reach Fandango</b> on the last {failures} checks, so I can't tell you "
        f"yet whether a {LANGUAGE_KEYWORD.title()} showing was found today.",
        f"Latest error: {html.escape(error)}",
        "I'll keep checking every 15 minutes and text you the moment one is found.",
    ])


# -------------------------------------------------------------------- main ---

def run(dry_run=False):
    today = now().date()
    if today > STOP_AFTER:
        log("past STOP_AFTER; nothing to do")
        return
    dates = watch_dates(today)
    if not dates:
        log("no Fri/Sat/Sun dates in the window; nothing to do")
        return

    state = load_state()
    showings, theaters, errors, requests = collect_showings(dates)
    confirmed, unlisted = classify(showings)
    new = [s for s in confirmed if s["id"] not in state["notified"]]
    failed = bool(errors) and len(errors) == requests
    log(f"{dates[0]}..{dates[-1]} ({len(dates)} days): {requests} requests, {len(errors)} failed; "
        f"{len(showings)} Ramayana showtimes, {len(confirmed)} {LANGUAGE_KEYWORD} in watched formats, "
        f"{len(unlisted)} with no language, {len(new)} new")

    if dry_run:
        confirmed_ids = {s["id"] for s in confirmed}
        maybe_ids = {s["id"] for s in unlisted if s["watch_format"] in UNLISTED_DAILY_FORMATS}
        for s in sorted(showings, key=lambda s: (s["sort_key"], s["theater"])):
            flag = "MATCH" if s["id"] in confirmed_ids else "MAYBE" if s["id"] in maybe_ids else "     "
            star = "*" if s["priority"] else " "
            print(f"  {flag} {star} {s['date']} {s['time']:>6}  [{s['watch_format'] or '-'}] {s['theater']} — "
                  f"{s['format']} — {', '.join(s['tags'])}")
        messages = [format_matches(new)] if new else []
        messages.append(format_daily(today, showings, theaters, confirmed, unlisted, dates, errors, requests))
        for text in messages:
            parts = len(split_message(text))
            print(f"\n--- Telegram message ({visible_len(text)} characters, {parts} part{'s' * (parts > 1)}) ---\n{text}")
        return

    state["failures"] = state.get("failures", 0) + 1 if failed else 0

    if new:
        send_telegram(format_matches(new))
        for s in new:
            state["notified"][s["id"]] = {k: s[k] for k in ("date", "time", "theater", "url")}
        save_state(state)
        log(f"sent {len(new)} new showtimes to Telegram")

    daily_due = now().hour >= DAILY_MESSAGE_HOUR and state.get("last_daily") != today.isoformat()
    if daily_due and (not failed or state["failures"] >= FAILURE_ALERT_AFTER):
        if failed:
            send_telegram(format_daily_failure(today, state["failures"], errors[-1]))
        else:
            send_telegram(format_daily(today, showings, theaters, confirmed, unlisted, dates, errors, requests))
        state["last_daily"] = today.isoformat()
        log("sent the daily update")

    save_state(state)


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--dry-run", action="store_true", help="print results without sending or saving")
    parser.add_argument("--test", action="store_true", help="send a test Telegram message")
    parser.add_argument("--get-chat-id", action="store_true", help="show chat IDs that have messaged the bot")
    args = parser.parse_args()
    load_env()

    if args.get_chat_id:
        updates = telegram_call("getUpdates", {}).get("result", [])
        chats = {}
        for u in updates:
            msg = u.get("message") or u.get("channel_post") or {}
            chat = msg.get("chat")
            if chat:
                chats[chat["id"]] = chat.get("username") or chat.get("title") or chat.get("first_name")
        if not chats:
            print("No messages yet. Open your bot in Telegram, send it any message, then rerun this.")
        for chat_id, name in chats.items():
            print(f"TELEGRAM_CHAT_ID={chat_id}    ({name})")
        return

    if args.test:
        send_telegram("✅ Ramayana watcher is connected. You'll get booking links here.")
        print("Test message sent.")
        return

    run(dry_run=args.dry_run)


if __name__ == "__main__":
    main()
