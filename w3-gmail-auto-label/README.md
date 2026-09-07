# w3-gmail-auto-label

An n8n workflow that reads Gmail, filters messages by sender, and applies a label. Week 3 build.

The workflow is four nodes. The real work was OAuth.

---

## Quick start

1. Import `workflow.json` into n8n.
2. Create a Gmail OAuth2 credential (see **OAuth setup** below; the managed option does not work).
3. Create the target label in Gmail first, then select it in the Add Label node.
4. Set the Gmail query and the filter condition to whatever you want to sort.

**This workflow writes to a real inbox.** It only adds labels: no archive, no delete. Keep it that way while testing.

---

## How it works

| Node | What it does | Why |
|---|---|---|
| **Gmail: Get Many Messages** | Fetches messages matching a Gmail search query, capped at 5 | API-side filtering is cheaper and faster than pulling everything down |
| **Filter** | Keeps messages whose `From` contains the sender address | Workflow-side filtering, deliberately redundant here to practise the split |
| **Gmail: Add Label** | Applies the label, once per item, using `{{ $json.id }}` | The node runs once per item; each execution needs its own message ID |

Sample run: **5 messages fetched, 4 kept, 4 labelled.**

---

## Trade-offs

**API-side vs workflow-side filtering.** The Gmail query could do all the narrowing itself, and in production it should, because filtering at the API is cheaper and returns less data. The Filter node here is partly redundant. It stays because the split between what the API filters and what the workflow filters is a decision worth making consciously in every build, not a thing to do by habit.

**Matching the sender address, not the display name.** `PlatformNotifications-noreply@google.com` rather than `Platform Notifications`. Display names are cosmetic and the sender can change them; the address is the stable identity.

**`contains`, not `is equal to`.** The `From` field holds the whole string `Platform Notifications <PlatformNotifications-noreply@google.com>`, so exact equality never matches.

**Labelling only.** Archive is reversible but hard to verify at a glance. Delete is not reversible at all and has no place in a learning build.

---

## Idempotency

**Safe to re-run.** Gmail labels are idempotent: applying a label a message already carries is a no-op, so a second run changes nothing.

Worth contrasting with a bulk-comment automation I maintain at work, where posting the same note twice *does* duplicate it. That one needs a hash-keyed resume log to stay safe on re-run. Same question, opposite answer, because the underlying operation differs.

The question is worth asking of every workflow before it goes on a schedule: **if this runs twice, what happens?**

---

## OAuth setup

The part that took most of the build.

**Managed OAuth2 does not work for Gmail.** n8n Cloud's built-in Google app sits in Google's "Testing" publishing status, so it only authenticates n8n's own approved testers. Everyone else gets:

```
Access blocked: n8n.cloud has not completed the Google verification process
Error 403: access_denied
```

This is n8n-side and has been open for a long time ([#16249](https://github.com/n8n-io/n8n/issues/16249), [#19265](https://github.com/n8n-io/n8n/issues/19265), [#19386](https://github.com/n8n-io/n8n/issues/19386)). You cannot add yourself as a tester because it isn't your app.

**Use Custom OAuth2 with your own Google Cloud project:**

1. New project, enable the **Gmail API**
2. OAuth consent screen → External
3. **Set publishing status to "In Production," not "Testing"**
4. Create an OAuth client ID, type Web application
5. Copy the redirect URL from n8n's credential panel (it differs between Managed and Custom modes) into Authorized redirect URIs
6. Client ID and secret into n8n, save, then Sign in with Google
7. Click through the unverified-app warning: Advanced → Go to (unsafe)

**Scope:** `gmail.modify`. `gmail.readonly` reads fine and then fails when labelling.

**The publishing status step is the one that bites later.** In Testing with External users, Google revokes refresh tokens after exactly 7 days. The workflow runs fine, then dies a week later with `invalid_grant` and no obvious cause. In Production, the refresh token doesn't expire on that rule. The only cost is one warning screen.

---

## What broke

**Managed OAuth was a dead end.** Cost about twenty minutes before the error made it clear the problem was upstream. Switching to a custom Google Cloud project fixed it.

**Filter discarded everything.** Condition was `From is equal to "Platform Notifications"`, but the field's real value is `Platform Notifications <PlatformNotifications-noreply@google.com>`. Exact equality never matched. Switched to `contains`.

This is the second time I've made this exact mistake. The Week 1 build failed the same way. `is equal to` is almost never right against a field carrying more than the value you're looking for.

**Hardcoded the Message ID.** Typed a static ID into the Add Label node instead of an expression, which would have labelled one fixed message regardless of input. The fix is `{{ $json.id }}`. The underlying idea is that the node runs once per item and each execution gets its own `$json`, the same mechanic as `{{ $json.title }}` in the Week 1 filter, which I hadn't connected until it broke here.

---

## Limitations

- **No error handling.** If the label is missing or Gmail rate-limits, the run fails with no retry and no dead-letter path.
- **No dedup on re-read.** Re-running re-fetches and re-processes the same messages. Harmless because labelling is idempotent, but it would matter if a later version sent replies.
- **Hard item cap of 5.** Deliberate for safety while testing against a live inbox. Removing it needs the error handling above first.
- **Filter is redundant** with the Gmail query as configured.
- **Single sender.** Routing to different labels by sender needs a Switch node.

---

## Next

Week 4 adds the first AI node: an LLM summarizing messages into a digest. Everything up to here is plumbing with zero model calls, which is the cheap part and worth noticing.
