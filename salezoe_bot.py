#!/usr/bin/env python3
"""SALEZOE Telegram deal poster. Stdlib only.

Posts the next unposted deal from queue.json to a Telegram channel, records it in
posted.json, and refuses to repeat an ASIN within REPEAT_DAYS. Run it as often as you
like (every 10 min via cron is fine): MAX_POSTS_PER_DAY and MIN_GAP_MINUTES decide
whether a run actually posts, so cron frequency cannot drain the queue.

Env:  TELEGRAM_BOT_TOKEN   from @BotFather (bot must be admin of the channel)
      TELEGRAM_CHANNEL     e.g. @SALEZOE
"""
import json, os, sys, urllib.request, urllib.parse
from datetime import datetime, timedelta, timezone

TAG = "gidsonjpg-21"          # the only place the tag lives
REPEAT_DAYS = 10              # never post the same ASIN twice within this window
MAX_POSTS_PER_DAY = 25        # owner set 25 on 2 Sept 2026
MIN_GAP_MINUTES = 30          # 25 posts across the 07:00-23:00 window
QUIET_HOURS = range(23, 24), range(0, 7)   # no posts at night, IST
IST = timezone(timedelta(hours=5, minutes=30))
HERE = os.path.dirname(os.path.abspath(__file__))

def load(name, default):
    p = os.path.join(HERE, name)
    return json.load(open(p)) if os.path.exists(p) else default

def save(name, data):
    json.dump(data, open(os.path.join(HERE, name), "w"), indent=1, ensure_ascii=False)

def link(asin, now):
    sub = f"tg-{now:%Y%m%d}-{now:%H%M}"
    return f"https://www.amazon.in/dp/{asin}?tag={TAG}&ascsubtag={sub}"

def render(deal, now):
    # No price, no MRP, no "% off": Amazon only permits prices sourced from PA-API.
    return (f"{deal['emoji']} {deal['name']}.\n\n{deal['blurb']}\n\n"
            f"Check the live price on Amazon:\n{link(deal['asin'], now)}\n\n"
            "Paid link — SALEZOE may earn a commission at no extra cost to you.")

def pick(queue, posted, now):
    cutoff = now - timedelta(days=REPEAT_DAYS)
    if any(now.hour in r for r in QUIET_HOURS):
        return None, "quiet hours"
    today = [t for t in posted.values() if datetime.fromisoformat(t).date() == now.date()]
    if len(today) >= MAX_POSTS_PER_DAY:
        return None, "daily cap reached"
    last = max((datetime.fromisoformat(t) for t in posted.values()), default=None)
    if last and now - last < timedelta(minutes=MIN_GAP_MINUTES):
        return None, f"last post {int((now-last).total_seconds()//60)} min ago, gap is {MIN_GAP_MINUTES}"
    for d in queue:
        t = posted.get(d["asin"])
        if t is None or datetime.fromisoformat(t) < cutoff:
            return d, "ok"
    return None, "queue exhausted — refill queue.json"

def send(text):
    token, chan = os.environ["TELEGRAM_BOT_TOKEN"], os.environ["TELEGRAM_CHANNEL"]
    body = urllib.parse.urlencode({"chat_id": chan, "text": text,
                                   "disable_web_page_preview": "false"}).encode()
    req = urllib.request.Request(f"https://api.telegram.org/bot{token}/sendMessage", body)
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.load(r)["ok"]

def main(dry=False):
    now = datetime.now(IST)
    queue, posted = load("queue.json", []), load("posted.json", {})
    deal, why = pick(queue, posted, now)
    if not deal:
        print("skip:", why); return 0
    text = render(deal, now)
    if dry:
        print(text); return 0
    if send(text):
        posted[deal["asin"]] = now.isoformat()
        save("posted.json", posted)
        print("posted", deal["asin"], deal["name"])
    return 0

def _selfcheck():
    now = datetime(2026, 9, 1, 9, 0, tzinfo=IST)
    q = [{"asin": "A", "name": "a", "emoji": "x", "blurb": "b"},
         {"asin": "B", "name": "b", "emoji": "x", "blurb": "b"}]
    assert pick(q, {}, now)[0]["asin"] == "A"
    assert pick(q, {"A": now.isoformat()}, now + timedelta(hours=5))[0]["asin"] == "B"          # A recent → B
    assert pick(q, {"A": now.isoformat()}, now + timedelta(minutes=10))[0] is None                # gap
    assert pick(q, {"A": (now - timedelta(days=11)).isoformat()}, now)[0]["asin"] == "A"          # repeat ok after 10d
    assert pick(q, {"A": now.isoformat(), "B": now.isoformat()}, now + timedelta(hours=9))[1] != "ok"
    assert pick(q, {}, datetime(2026, 9, 1, 3, 0, tzinfo=IST))[1] == "quiet hours"
    assert "?tag=gidsonjpg-21" in link("B0TEST0001", now) and "₹" not in render(q[0], now)
    print("selfcheck ok")

if __name__ == "__main__":
    if "--selfcheck" in sys.argv: _selfcheck()
    else: sys.exit(main(dry="--dry" in sys.argv))
