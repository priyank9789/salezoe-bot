#!/usr/bin/env python3
"""SALEZOE Telegram deal poster. Stdlib only.

Posts one deal per run-step to a Telegram channel as a photo card with a buy button, records it in
posted.json, rotates categories, and refuses to repeat a deal within REPEAT_DAYS.
Pool = queue.json (Amazon, no prices allowed) + live store-feed deals from salezoe.com (real price).
--loop keeps posting every MIN_GAP_MINUTES for RUN_MINUTES (one GitHub Actions run); next run takes over.

queue.json entry: {"asin": "B0...", "name": "...", "emoji": "x", "img": "61H7-uZtqyL"}
Env: TELEGRAM_BOT_TOKEN from @BotFather (bot must be admin of the channel)
     TELEGRAM_CHANNEL   e.g. @SALEZOE
"""
import json, os, re, subprocess, sys, time, urllib.error, urllib.request, urllib.parse
from datetime import datetime, timedelta, timezone

TAG = "gidsonjpg-21"          # the only place the tag lives
MORE_URL = "https://salezoe.com/today-deals/?utm_source=telegram"
REPEAT_DAYS = 2               # pool is ~110 deals at 48/day, so a deal may return after 2 days
MAX_POSTS_PER_DAY = 48        # owner decision: one deal every 20 min, 07:00-23:00 IST
MIN_GAP_MINUTES = 20
QUIET_HOURS = range(23, 24), range(0, 7)   # no posts at night, IST
LIVE = "https://salezoe.com/wp-json/salezoe/v1/live-deals"   # store feed deals with price
RUN_MINUTES = 340             # loop inside one Actions run (limit 360); next run takes over
IST = timezone(timedelta(hours=5, minutes=30))
HERE = os.path.dirname(os.path.abspath(__file__))

def load(name, default):
    p = os.path.join(HERE, name)
    return json.load(open(p)) if os.path.exists(p) else default

def save(name, data):
    json.dump(data, open(os.path.join(HERE, name), "w"), indent=1, ensure_ascii=False)

CATS = [("garbage|cleaner|iron|vacuum", "🧹"), ("charger|cable|keyboard|mic|headphone|earbud|hdmi|batter|usb|screen|phone|laptop|tablet|ipad|speaker|camera|drone|router", "🔌"),
        ("watch|band", "⌚"), ("light|lamp|bulb|led", "💡"), ("shampoo|face wash|cream|soap|serum|hair|beauty|dryer|honey|magnesium|shilajit|tissue", "🧴"),
        ("shirt|cargo|kurta|cap|saree|polo|earring|necklace|jewel|mask|shoe|jacket", "👕"), ("backpack|sling bag|trolley|luggage", "🎒"),
        ("curtain|bedsheet|comforter|mattress|towel|pillow|basket|laundry|rack|stand|container|kitchen", "🏠"), ("massage|resistance|pull up|fitness|gauge|gym", "💪"),
        ("baby|kid|toy|book|play", "🧸"), ("seed|oats|snack|food|chia|tea|coffee", "🥗")]

def cat(d):
    return next((e for p, e in CATS if re.search(p, d["name"].lower())), d.get("emoji", "🔥"))

def live_pool():
    """Store-feed deals (real price + old price) from the website; silent no-op if the site is unreachable."""
    try:
        req = urllib.request.Request(LIVE, headers={"User-Agent": "Mozilla/5.0 salezoe-bot"})
        items = json.load(urllib.request.urlopen(req, timeout=20)).get("items", [])
    except Exception as e:
        print("live feed unavailable:", e); return []
    return [{"asin": "L" + str(i["id"]), "name": i["name"][:80], "emoji": "🔥", "img_url": i["img"], "url": i["url"],
             "store": i["store"], "price": i["price"], "old": i["old"], "off": i["off"], "cur": i.get("cur", "INR")}
            for i in items if i.get("img") and i.get("url") and i.get("price")]

def link(asin, now):
    sub = f"tg-{now:%Y%m%d}-{now:%H%M}"
    return f"https://www.amazon.in/dp/{asin}?tag={TAG}&ascsubtag={sub}"

def render(deal, now):
    if deal.get("price"):
        sym = {"INR": "₹", "USD": "$"}.get(deal.get("cur"), "₹")
        return (f"{cat(deal)} {deal['name']}\n\n{sym}{deal['price']:,.0f}  (was {sym}{deal['old']:,.0f}, {deal['off']}% off) at {deal['store']}.\n\n"
                "Paid link — SALEZOE may earn a commission at no extra cost to you.")
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
    ok = [d for d in queue if posted.get(d["asin"]) is None or datetime.fromisoformat(posted[d["asin"]]) < cutoff]
    if not ok:
        return None, "queue exhausted — refill queue.json"
    # different category every time: take the deal whose category was posted longest ago (never = first)
    seen = {}
    for d in queue:
        if d["asin"] in posted:
            seen[cat(d)] = max(seen.get(cat(d), ""), posted[d["asin"]])
    return min(ok, key=lambda d: seen.get(cat(d), "")), "ok"

def payload(deal, now):
    """Telegram method + fields: photo card when the deal has an image id, else text."""
    url = deal.get("url") or link(deal["asin"], now)
    buy = f"🛒 Buy on {deal['store']}" if deal.get("store") else "🛒 View on Amazon"
    fields = {"chat_id": os.environ["TELEGRAM_CHANNEL"],
              "reply_markup": json.dumps({"inline_keyboard": [[{"text": buy, "url": url}],
                                                              [{"text": "🔥 More deals on salezoe.com", "url": MORE_URL}]]})}
    if deal.get("img") or deal.get("img_url"):
        fields.update(photo=deal.get("img_url") or f"https://m.media-amazon.com/images/I/{deal['img']}._SL500_.jpg",
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

def once(dry=False):
    now = datetime.now(IST)
    queue, posted = load("queue.json", []), load("posted.json", {})
    queue = queue + live_pool()
    deal, why = pick(queue, posted, now)
    if not deal:
        print("skip:", why); return why
    if dry:
        print(payload(deal, now)); return "dry"
    try:
        ok = send(deal, now)
    except urllib.error.HTTPError as e:   # 400 = Telegram rejected this photo/link: skip the deal, keep the loop alive
        if e.code != 400: raise
        print("send failed:", deal["asin"], e); ok = True
    if ok:
        posted[deal["asin"]] = now.isoformat()
        save("posted.json", posted)
        print("posted", deal["asin"], deal["name"])
        if os.environ.get("GITHUB_ACTIONS"):   # push the register after every post so a cancelled run never loses it
            for c in (["git", "config", "user.name", "salezoe-bot"], ["git", "config", "user.email", "bot@salezoe.com"],
                      ["git", "add", "posted.json"], ["git", "commit", "-qm", f"posted {deal['asin']}"], ["git", "push", "-q"]):
                subprocess.run(c, cwd=HERE, check=False)
    return "ok"

def main(dry=False, loop=False):
    end = time.time() + RUN_MINUTES * 60
    while True:
        why = once(dry)
        if not loop or time.time() > end or why.startswith("quiet"):
            return 0
        time.sleep(60)

def _selfcheck():
    os.environ.setdefault("TELEGRAM_CHANNEL", "@test")
    now = datetime(2026, 9, 1, 9, 0, tzinfo=IST)
    q = [{"asin": "A", "name": "a", "emoji": "x", "img": "IMG1"},
         {"asin": "B", "name": "b", "emoji": "x", "blurb": "b"}]
    assert pick(q, {}, now)[0]["asin"] == "A"
    assert pick(q, {"A": now.isoformat()}, now + timedelta(hours=5))[0]["asin"] == "B"   # A recent → B
    assert pick(q, {"A": now.isoformat()}, now + timedelta(minutes=10))[0] is None     # gap 20 min
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
    else: sys.exit(main(dry="--dry" in sys.argv, loop="--loop" in sys.argv))
