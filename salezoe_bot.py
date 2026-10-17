#!/usr/bin/env python3
"""SALEZOE Telegram deal poster. Stdlib only.

Posts the next unposted deal from queue.json to a Telegram channel as a photo card
with a "View on Amazon" button, records it in posted.json, and refuses to repeat an
ASIN within REPEAT_DAYS. Run it as often as you like (every 10 min via cron is fine):
MAX_POSTS_PER_DAY and MIN_GAP_MINUTES decide whether a run actually posts, so cron
frequency cannot drain the queue.

queue.json entry: {"asin": "B0...", "name": "...", "emoji": "x", "img": "61H7-uZtqyL"}
"img" is the Amazon image id (m.media-amazon.com/images/I/<img>._SL500_.jpg);
without it the deal is posted as plain text.

Env: TELEGRAM_BOT_TOKEN from @BotFather (bot must be admin of the channel)
     TELEGRAM_CHANNEL   e.g. @SALEZOE
"""
import json, os, sys, urllib.request, urllib.parse
from datetime import datetime, timedelta, timezone

TAG = "gidsonjpg-21"          # the only place the tag lives
MORE_URL = "https://salezoe.com/today-deals/?utm_source=telegram"
REPEAT_DAYS = 10              # never post the same ASIN twice within this window
MAX_POSTS_PER_DAY = 4         # curated channels get 10-60% view rate, firehoses ~1%
MIN_GAP_MINUTES = 120         # spread 4 posts across the day
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
    blurb = deal.get("blurb") or "Great Indian Festival deal. Tap for today's price on Amazon."
    return (f"{deal['emoji']} {deal['name']}\n\n{blurb}\n\n"
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

def payload(deal, now):
    """Telegram method + fields: photo card when the deal has an image id, else text."""
    url = link(deal["asin"], now)
    fields = {"chat_id": os.environ["TELEGRAM_CHANNEL"],
              "reply_markup": json.dumps({"inline_keyboard": [[{"text": "🛒 View on Amazon", "url": url}],
                                                              [{"text": "🔥 More deals on salezoe.com", "url": MORE_URL}]]})}
    if deal.get("img"):
        fields.update(photo=f"https://m.media-amazon.com/images/I/{deal['img']}._SL500_.jpg",
                      caption=render(deal, now))
        return "sendPhoto", fields
    fields.update(text=render(deal, now) + "\n" + url, disable_web_page_preview="false")
    return "sendMessage", fields

def send(deal, now):
    method, fields = payload(deal, now)
    req = urllib.request.Request(f"https://api.telegram.org/bot{os.environ['TELEGRAM_BOT_TOKEN']}/{method}",
                                 urllib.parse.urlencode(fields).encode())
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.load(r)["ok"]

def main(dry=False):
    now = datetime.now(IST)
    queue, posted = load("queue.json", []), load("posted.json", {})
    deal, why = pick(queue, posted, now)
    if not deal:
        print("skip:", why); return 0
    if dry:
        print(payload(deal, now)); return 0
    if send(deal, now):
        posted[deal["asin"]] = now.isoformat()
        save("posted.json", posted)
        print("posted", deal["asin"], deal["name"])
    return 0

def _selfcheck():
    os.environ.setdefault("TELEGRAM_CHANNEL", "@test")
    now = datetime(2026, 9, 1, 9, 0, tzinfo=IST)
    q = [{"asin": "A", "name": "a", "emoji": "x", "img": "IMG1"},
         {"asin": "B", "name": "b", "emoji": "x", "blurb": "b"}]
    assert pick(q, {}, now)[0]["asin"] == "A"
    assert pick(q, {"A": now.isoformat()}, now + timedelta(hours=5))[0]["asin"] == "B"   # A recent → B
    assert pick(q, {"A": now.isoformat()}, now + timedelta(minutes=10))[0] is None     # gap
    assert pick(q, {"A": (now - timedelta(days=11)).isoformat()}, now)[0]["asin"] == "A"  # repeat ok after 10d
    assert pick(q, {"A": now.isoformat(), "B": now.isoformat()}, now + timedelta(hours=9))[1] != "ok"
    assert pick(q, {}, datetime(2026, 9, 1, 3, 0, tzinfo=IST))[1] == "quiet hours"
    m, f = payload(q[0], now)
    assert m == "sendPhoto" and "IMG1._SL500_" in f["photo"] and "?tag=gidsonjpg-21" in f["reply_markup"]
    m, f = payload(q[1], now)
    assert m == "sendMessage" and "?tag=gidsonjpg-21" in f["text"] and "₹" not in f["text"]
    assert len(f["text"]) < 1024
    print("selfcheck ok")

if __name__ == "__main__":
    if "--selfcheck" in sys.argv: _selfcheck()
    else: sys.exit(main(dry="--dry" in sys.argv))
