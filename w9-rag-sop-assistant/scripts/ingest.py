"""Post every SOP in ../corpus to the ingest webhook and print what the vector store reports back.

The workflow deletes the collection before inserting, so running this twice leaves the same chunks, not twice as many.

  SOP_INGEST_URL=https://<your-instance>/webhook/sop-ingest SOP_INGEST_TOKEN=<token> python ingest.py
"""
import json, os, urllib.request

CORPUS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "corpus")
URL = os.environ["SOP_INGEST_URL"]
TOKEN = os.environ["SOP_INGEST_TOKEN"]

docs = []
for name in sorted(os.listdir(CORPUS)):
    if name.endswith(".md"):
        with open(os.path.join(CORPUS, name), encoding="utf-8") as f:
            docs.append({"filename": name, "text": f.read()})

req = urllib.request.Request(URL, data=json.dumps({"docs": docs}).encode("utf-8"), method="POST")
req.add_header("Content-Type", "application/json")
req.add_header("X-Ingest-Token", TOKEN)
print(f"posting {len(docs)} docs, {sum(len(d['text']) for d in docs):,} characters")
with urllib.request.urlopen(req, timeout=180) as r:
    print(r.status, json.dumps(json.loads(r.read()), indent=2))
