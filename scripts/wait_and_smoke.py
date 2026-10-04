"""End-to-end smoke: wait for the API, upload a document, wait for the worker to index it, run a query.

Usage: python scripts/wait_and_smoke.py [http://localhost:8000]
Used by the Compose and kind checks in CI. Exits non-zero on any failure.
"""

import sys
import time

import httpx

base = sys.argv[1] if len(sys.argv) > 1 else "http://localhost:8000"
client = httpx.Client(base_url=base, timeout=180)

for _ in range(90):
    try:
        if client.get("/healthz").status_code == 200:
            break
    except httpx.HTTPError:
        pass
    time.sleep(2)
else:
    sys.exit("api never became healthy")

doc = client.post(
    "/documents",
    files={"file": ("smoke.md", b"The smoke test limit is ninety-nine widgets per day.", "text/markdown")},
).json()
print("uploaded", doc)

for _ in range(120):
    status = client.get(f"/documents/{doc['doc_id']}").json()["status"]
    if status == "ready":
        break
    if status == "failed":
        sys.exit("ingest failed")
    time.sleep(2)
else:
    sys.exit("ingest never finished")

r = client.post("/query", json={"question": "What is the smoke test limit?"})
r.raise_for_status()
body = r.json()
print(body)
assert body["citations"], "expected at least one citation"
assert "ninety-nine" in body["citations"][0]["text"]
print("SMOKE OK")
