r"""Phase 3 check: trigger a run over HTTP and watch its WebSocket stream live.

Usage (from backend/, with the server running):
    .venv\Scripts\python scripts\watch_run.py            # demo repo, bug B3 only
    .venv\Scripts\python scripts\watch_run.py --bugs all
"""
import argparse
import asyncio
import json
import sys
import urllib.request

import websockets

API = "http://localhost:8010/api"
WS = "ws://localhost:8010/ws"


def post(path: str, body: dict) -> dict:
    req = urllib.request.Request(f"{API}{path}", data=json.dumps(body).encode(),
                                 headers={"Content-Type": "application/json"}, method="POST")
    with urllib.request.urlopen(req) as r:
        return json.load(r)


async def watch(run_id: str) -> None:
    async with websockets.connect(f"{WS}/runs/{run_id}", max_size=None) as ws:
        async for raw in ws:
            msg = json.loads(raw)
            if msg["type"] == "reasoning_step":
                d = msg["data"]
                tool = f" [{d['tool_name']}]" if d["tool_name"] else ""
                print(f"{d['sequence']:>3} {d['step_type']:<10}{tool} {d['content'][:150]}")
            else:
                print(f"--- {msg['type']}: {json.dumps(msg['data'])}")


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser()
    parser.add_argument("--bugs", default="B3", help="Comma-separated bug IDs, or 'all'")
    args = parser.parse_args()

    body = {"repo_id": "repo_demo001"}
    if args.bugs != "all":
        body["bug_ids"] = args.bugs.split(",")
    run = post("/runs", body)
    print(f"POST /runs -> {run}")
    asyncio.run(watch(run["id"]))

    with urllib.request.urlopen(f"{API}/runs/{run['id']}") as r:
        print("\nGET /runs/:id ->", json.dumps(json.load(r), indent=2))
    with urllib.request.urlopen(f"{API}/runs/{run['id']}/fix") as r:
        fix = json.load(r)
        print("GET /runs/:id/fix -> files:", fix["files_changed"], "| tests:", fix["tests_summary"])


if __name__ == "__main__":
    main()
