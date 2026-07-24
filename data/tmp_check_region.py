import json

with open("data/processed/items.json", encoding="utf-8") as f:
    data = json.load(f)

news = data.get("news", [])
local = [n for n in news if n.get("region") == "local"]
global_ = [n for n in news if n.get("region") == "global"]
other = [n for n in news if n.get("region") not in ("local", "global")]

print(f"Total: {len(news)}  Local: {len(local)}  Global: {len(global_)}  Other: {len(other)}")
if global_:
    print(f"Sample global: [{global_[0]['source']}] {global_[0]['title'][:70]}")
if local:
    print(f"Sample local:  [{local[0]['source']}] {local[0]['title'][:70]}")
