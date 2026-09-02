# SALEZOE deal bot — setup (10 minutes, once)

What it does: every 10 minutes GitHub wakes up, runs `salezoe_bot.py`, and it posts the
next deal from `queue.json` to your Telegram channel — up to 3 a day, at least 4 hours
apart, never the same product twice in 10 days. Every link carries `tag=gidsonjpg-21`.
No prices in posts (Amazon only allows API-sourced prices; your account has no API yet).

## 1. Make the bot (you do this — it needs your Telegram)
1. In Telegram open **@BotFather** → `/newbot` → name it, e.g. `salezoe_deals_bot`.
2. BotFather replies with a **token** (`123456:ABC-...`). Keep it; never paste it in chat.
3. Open your channel **@SALEZOE** → Administrators → Add admin → your bot → allow *Post messages*.

## 2. Put the code on GitHub
1. github.com → New repository → name `salezoe-bot`, **Private** → Create.
2. Upload these files (drag-and-drop works): `salezoe_bot.py`, `queue.json`,
   `posted.json`, `README.md`, and the folder `.github/workflows/post.yml`.
3. Repo → Settings → Secrets and variables → Actions → **New repository secret**:
   Name `TELEGRAM_BOT_TOKEN`, Value = the token from BotFather.
4. Repo → Settings → Actions → General → Workflow permissions → **Read and write** → Save.

## 3. Start it
Repo → **Actions** tab → "SALEZOE deal post" → **Run workflow**. That is the one tap.
From then on it runs itself every 10 minutes; you never need to tap again.
(Phone: the GitHub app has the same Actions → Run workflow button.)

## Refilling deals
`queue.json` is the list of deals. When it runs low the bot prints
`queue exhausted` in the Actions log and posts nothing. Ask Claude for a "new batch";
it hunts the live Amazon deals page through your Chrome, verifies each ASIN, and gives
you a new `queue.json` to upload. Old entries can stay — the 10-day rule handles repeats.

## Changing the pace
Top of `salezoe_bot.py`: `MAX_POSTS_PER_DAY = 3` and `MIN_GAP_MINUTES = 240`.
Your channel description promises "up to 3 a day, 4 hours apart" — 199 subscribers
will leave a channel that posts every 10 minutes. Raise it only if the queue can feed it.

## Test without posting
`python3 salezoe_bot.py --dry` prints the next post. `python3 salezoe_bot.py --selfcheck`
runs the logic tests.

## Not included, and why
- **WhatsApp Channels** have no posting API. Telegram only.
- **Server-side deal scraping.** Amazon blocks scrapers within minutes and terminates
  Associates accounts that do it. The deal hunt runs through your own browser, in a
  Claude session, and lands in `queue.json`. Once you have 3 sales you qualify for
  Amazon's Product Advertising API, and the hunt can be fully automated — legitimately.
