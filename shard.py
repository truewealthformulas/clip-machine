"""Split pending clip plans into shards so clips render on several servers at once.

19 Sept 2026, the owner: "make sure its running fast". One server rendered clips one
after another (~25 min for a plan). Each shard takes SIZE clips on its own server;
factory/queue.py collects what passed and queues it once.

    python factory/shard.py            # writes matrix=<json> and count=<n> to $GITHUB_OUTPUT
"""
import json, os

HERE = os.path.dirname(os.path.abspath(__file__))
PLANS = os.path.join(HERE, "plans")
SIZE = 2

done = json.load(open(os.path.join(PLANS, "_done.json"))) if os.path.exists(os.path.join(PLANS, "_done.json")) else []
shards = []
for f in sorted(os.listdir(PLANS)):
    if not f.endswith(".json") or f.startswith("_") or f[:-5] in done:
        continue
    n = len(json.load(open(os.path.join(PLANS, f)))["clips"])
    shards += [{"plan": f[:-5], "shard": i} for i in range((n + SIZE - 1) // SIZE)]
print(f"{len(shards)} shard(s): {shards}")
with open(os.environ.get("GITHUB_OUTPUT", "/dev/null"), "a") as fh:
    fh.write(f"matrix={json.dumps(shards)}\ncount={len(shards)}\n")
