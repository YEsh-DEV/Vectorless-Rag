import sys
import json
from pathlib import Path

# Ensure UTF-8 output on Windows
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")

TREES_DIR = Path("trees")


def list_cached_trees():
    """List all cached tree JSON files in the trees directory."""
    if not TREES_DIR.exists():
        return []
    return sorted(list(TREES_DIR.glob("*_tree.json")))


def print_tree(nodes, indent=0, max_depth=3):
    """Recursively print node titles, IDs, and pages."""
    for node in nodes:
        prefix = "  " * indent + ("└─ " if indent > 0 else "• ")
        page = node.get("start_index", node.get("page_index", "?"))
        title = node.get("title", "Untitled")
        node_id = node.get("node_id", "")
        print(f"{prefix}[{node_id}] {title} (Page {page})")
        if node.get("nodes") and indent < max_depth:
            print_tree(node["nodes"], indent + 1, max_depth=max_depth)


def find_node(nodes, target_id):
    """Find and return a specific node by its ID."""
    for n in nodes:
        if n.get("node_id") == target_id:
            return n
        if n.get("nodes"):
            res = find_node(n["nodes"], target_id)
            if res:
                return res
    return None


def inspect_node(tree_file: Path, target_id: str):
    """Inspect full details of a specific node."""
    with open(tree_file, "r", encoding="utf-8") as f:
        data = json.lo ad(f)
    tree = data.get("result", [])
    node = find_node(tree, target_id)
    if not node:
        print(f"❌ Node ID '{target_id}' not found in {tree_file.name}")
        return

    print("\n" + "=" * 60)
    print(f"Node ID:     {node.get('node_id')}")
    print(f"Title:       {node.get('title')}")
    print(f"Page Range:  {node.get('start_index')} to {node.get('end_index')}")
    print("=" * 60)
    
    summary = node.get("summary")
    if summary:
        print(f"\n📝 Summary:\n{summary}\n")

    text = node.get("text", "")
    print(f"📄 Section Content Preview ({len(text)} chars):")
    print(text[:800] + ("..." if len(text) > 800 else ""))


if __name__ == "__main__":
    cached_trees = list_cached_trees()
    if not cached_trees:
        print("ℹ️ No cached trees found yet in trees/. Run index_book.py first!")
        sys.exit(0)

    print("\n🌲 Cached Trees Available:")
    for idx, t in enumerate(cached_trees, 1):
        print(f"  [{idx}] {t.name}")

    if len(sys.argv) > 2:
        # e.g., python inspect_tree.py 1 0005
        tree_idx = int(sys.argv[1]) - 1
        node_id = sys.argv[2]
        inspect_node(cached_trees[tree_idx], node_id)
    else:
        # Print overview of the first tree
        target_tree = cached_trees[0]
        print(f"\n📖 Inspecting: {target_tree.name}\n")
        with open(target_tree, "r", encoding="utf-8") as f:
            data = json.load(f)
        print_tree(data.get("result", []))
