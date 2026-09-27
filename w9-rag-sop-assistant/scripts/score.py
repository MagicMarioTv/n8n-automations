"""Run ../golden-set.json against the live SOP assistant and score every answer on two axes.

  answer:   every must_contain string appears in the reply (case insensitive)
  citation: every expected source file is cited, and the superseded 2025 edition is never cited
            without the reply also saying it is superseded
  decline items pass both axes only if the reply says the SOPs do not cover it and cites nothing

Automatic misses are a first pass: read each one by hand before calling it a miss.
Every question runs in a fresh chat session.

  SOP_CHAT_URL=https://<your-instance>/webhook/<chat-webhook-id>/chat
  SOP_CHAT_USER, SOP_CHAT_PASS   the chat trigger's Basic Auth
  optional, for token counts:  N8N_API_URL=https://<your-instance>/api/v1  N8N_API_KEY  SOP_WORKFLOW_ID

  python score.py            all twenty
  python score.py Q14 Q17    just those
"""
import base64, json, os, re, sys, time, urllib.request, uuid

HERE = os.path.dirname(os.path.abspath(__file__))
BUILD = os.path.join(HERE, "..")
SUPERSEDED = "qc-hold-procedure-2025.md"
DECLINE = re.compile(r"(do not|don't|does not|doesn't|not) (cover|contain|include|address|mention)|no information|not covered|couldn't find|could not find", re.I)
AUTH = "Basic " + base64.b64encode(f"{os.environ['SOP_CHAT_USER']}:{os.environ['SOP_CHAT_PASS']}".encode()).decode()
API, API_KEY, WF = os.environ.get("N8N_API_URL"), os.environ.get("N8N_API_KEY"), os.environ.get("SOP_WORKFLOW_ID")


def api(path):
    req = urllib.request.Request(API + path, headers={"X-N8N-API-KEY": API_KEY, "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.loads(r.read())


def ask(question):
    body = json.dumps({"action": "sendMessage", "chatInput": question, "sessionId": str(uuid.uuid4())}).encode()
    req = urllib.request.Request(os.environ["SOP_CHAT_URL"], data=body, method="POST")
    req.add_header("Content-Type", "application/json")
    req.add_header("Authorization", AUTH)
    with urllib.request.urlopen(req, timeout=180) as r:
        return json.loads(r.read()).get("output", "")


def latest_execution():
    d = api(f"/executions?workflowId={WF}&limit=1")
    return int(d["data"][0]["id"]) if d.get("data") else 0


def tokens(exec_id):
    """Sum tokenUsage over every chat model call in the execution."""
    run = api(f"/executions/{exec_id}?includeData=true")["data"]["resultData"]["runData"]
    p = c = calls = 0
    for r in run.get("Anthropic Chat Model", []):
        for out in r.get("data", {}).get("ai_languageModel", [[]])[0]:
            u = out["json"].get("tokenUsage", {})
            p += u.get("promptTokens", 0); c += u.get("completionTokens", 0); calls += 1
    return p, c, calls


def score(item, reply):
    # Brackets can hold one file or several: [a.md] or [a.md, b.md]
    cited = set()
    for group in re.findall(r"\[([^\]]*\.md[^\]]*)\]", reply):
        cited.update(re.findall(r"[\w.-]+\.md", group))
    low = reply.lower()
    if item["expect_decline"]:
        ok = bool(DECLINE.search(reply)) and not cited
        return ok, ok, cited
    answer_ok = all(s.lower() in low for s in item["must_contain"])
    citation_ok = set(item["expected_sources"]) <= cited
    if SUPERSEDED in cited and "supersed" not in low:
        citation_ok = False
    return answer_ok, citation_ok, cited


def main():
    items = json.load(open(os.path.join(BUILD, "golden-set.json"), encoding="utf-8"))["items"]
    only = set(sys.argv[1:])
    items = [i for i in items if not only or i["id"] in only]
    counting = bool(API and API_KEY and WF)
    results, tot_p, tot_c = [], 0, 0
    for item in items:
        before = latest_execution() if counting else 0
        reply = ask(item["question"])
        ex, p, c, calls = None, 0, 0, 0
        if counting:
            for _ in range(10):
                ex = latest_execution()
                if ex > before:
                    break
                time.sleep(1)
            p, c, calls = tokens(ex)
        tot_p += p; tot_c += c
        a, ci, cited = score(item, reply)
        results.append({"id": item["id"], "category": item["category"], "answer_ok": a, "citation_ok": ci,
                        "cited": sorted(cited), "execution": ex, "llm_calls": calls,
                        "prompt_tokens": p, "completion_tokens": c, "reply": reply})
        print(f"{item['id']} {'PASS' if a else 'miss'} / {'PASS' if ci else 'miss'}  {p}+{c} tok  cited {sorted(cited)}")
    summary = {"run_at": time.strftime("%Y-%m-%d %H:%M"), "questions": len(results),
               "answer_correct": sum(r["answer_ok"] for r in results),
               "citation_correct": sum(r["citation_ok"] for r in results),
               "both_correct": sum(r["answer_ok"] and r["citation_ok"] for r in results),
               "prompt_tokens": tot_p, "completion_tokens": tot_c,
               "cost_usd_haiku": round(tot_p / 1e6 * 1 + tot_c / 1e6 * 5, 5)}
    print(json.dumps(summary, indent=2))
    if only:
        print("partial run, golden-results.json left untouched")
        return
    json.dump({"summary": summary, "results": results},
              open(os.path.join(BUILD, "golden-results.json"), "w", encoding="utf-8"), indent=2, ensure_ascii=False)


if __name__ == "__main__":
    main()
