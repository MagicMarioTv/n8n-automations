# w1-rss-notifier

An n8n workflow that watches an RSS feed, keeps only the items matching a keyword, and posts them to Discord.

Week 1 of a 28-week AI automation roadmap. It's deliberately small — the point was the reps and the habits, not the artifact.

---

## Quick start

1. Import `w1-rss-notifier.json` into n8n (Workflows → Import from File).
2. Open the **RSS Read** node and set your feed URL.
3. Open the **Filter** node and set your keyword.
4. Create a **Discord Webhook** credential and paste your webhook URL (Discord: Server Settings → Integrations → Webhooks → New Webhook).
5. Execute the workflow. Matching items post to your channel.

**The webhook URL is a secret.** Anyone holding it can post to your server. It lives in n8n's credential store, not in this repo — if you export the workflow again, check the JSON before committing.

---

## How it works

| Node | What it does | Why this one |
|---|---|---|
| **RSS Read** | Fetches every item currently in the feed | Returns the full feed on every run, so there's always enough data to see the filter working. See trade-off 1. |
| **Filter** | Keeps items whose `title` contains the keyword | Drops non-matching items and continues. An IF node would branch into two paths; there's only one path here. |
| **Discord** | Posts title + link via webhook | Webhook auth needs no OAuth app. See trade-off 2. |

Data moves through as an array of items. Each node runs once per item, and `{{ $json.title }}` refers to the current item's title.

Sample run: **25 items in → 1 kept, 24 discarded.**

---

## Trade-offs

**1. RSS Read instead of RSS Feed Trigger.** The trigger version returns only items it considers *new* since the last poll — correct for production, useless while building, because a single item can't show you whether a filter is working. RSS Read returns everything every time. The cost is dedup: see Limitations.

**2. Discord instead of Slack.** Discord's webhook is a URL you paste into a credential. Slack's node wants a real OAuth app, which is 40 minutes of setup that teaches nothing about n8n. Slack is worth doing later, when the OAuth itself is the thing being learned.

**3. Filter instead of IF.** Filter drops non-matching items and continues down one path. IF splits into two branches. Nothing here needs the second branch.

**4. `contains` instead of `is equal to`.** Exact equality would require typing the entire title character for character. `contains` matches a keyword anywhere in the string.

---

## What broke

**Filter discarded everything.** The condition was `{{ $json.title }} is equal to` with the right-hand value left empty — the box still held its `value2` placeholder. So the condition read *"title equals nothing,"* which is false for every item. A filter condition is three parts: value, operator, comparison value. Naming the field only supplies the first.

**Couldn't tell "no input" from "everything rejected."** The `Kept` tab was empty and it looked like nothing had arrived. The `Discarded (1 item)` tab next to it was the actual signal — the item did arrive and was rejected. Two different failure modes that look identical if you only watch one tab.

**Thought the filter had dumped raw data into the output.** The `Kept` panel was showing a wall of JSON including a huge `content:encoded` HTML blob. Nothing was wrong: the output panel was in JSON view, and a Filter node never modifies items — it only decides which ones survive. Rows, not columns. Switching to Schema or Table view made it readable.

**Only one item to test with.** RSS Feed Trigger returns only new items since the last poll. One item can't demonstrate a filter — you can't distinguish "works" from "passes everything." Swapping to RSS Read gave 25 items and a visible 1/24 split.

**Grabbed the wrong Webhook node.** n8n's **Webhook** node is an inbound door *into n8n* — it hands you a URL others call to start a workflow. A Discord webhook URL is an inbound door *into Discord*, which n8n calls. Both are "webhooks"; they point opposite directions. The right node is the **Discord** node with Authentication set to Webhook.

---

## Limitations

- **No dedup.** RSS Read returns the whole feed every run, so on a schedule this reposts the same items forever. Production needs RSS Feed Trigger, or a dedup step keyed on `guid`/`link`.
- **Case-sensitive.** `contains` is case-sensitive by default, so `Triceps` won't match `triceps`. There's an option to ignore case.
- **No item cap.** If 40 items clear the filter, that's 40 Discord messages. Cheap to learn here, expensive with an email node.
- **Narrow filter.** 1 of 25 items matched. Fine for a demo; on a schedule it would go quiet for days.
- **No error handling.** If Discord is unreachable the run just fails. Retries and a dead-letter path come later in the roadmap.

---

## Next

Week 2 replaces the schedule with a real webhook trigger and an HTTP Request node against a public API.
