import os
import sys
import json
import time
from pathlib import Path
from dotenv import load_dotenv
from pageindex import PageIndexClient

sys.stdout.reconfigure(encoding="utf-8")
load_dotenv()

pi_client = PageIndexClient(api_key=os.getenv("PAGEINDEX_API_KEY"))
doc_id = "pi-cmuq0016c000n0bp11dyk7ftt"
output_path = Path("trees/Deep_Learning_with_Python_tree.json")

print(f"⏳ Waiting for tree generation on doc_id: {doc_id} ...")
t0 = time.time()

while True:
    info = pi_client.get_document(doc_id)
    status = info.get("status")
    elapsed = int(time.time() - t0)
    print(f"[{elapsed}s] Status: {status}", flush=True)

    if status == "completed":
        print(f"\n✨ Indexing completed in {elapsed}s! Fetching full tree...")
        tree_data = pi_client.get_tree(doc_id, node_summary=True, include_text=True)
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(tree_data, f, ensure_ascii=False, indent=2)
        print(f"💾 Tree saved to: {output_path}")
        nodes = tree_data.get("result", [])
        print(f"📊 Top-level sections: {len(nodes)}")
        break
    elif status == "failed":
        print(f"❌ Indexing failed: {info}")
        break

    time.sleep(8)
