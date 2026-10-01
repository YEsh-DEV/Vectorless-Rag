import os
import sys
import json
import time
from pathlib import Path
from dotenv import load_dotenv
from pageindex import PageIndexClient

# Ensure proper UTF-8 output on Windows terminal
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")

# 1. Load Environment Variables
load_dotenv()
PAGEINDEX_API_KEY = os.getenv("PAGEINDEX_API_KEY")

if not PAGEINDEX_API_KEY:
    print("❌ Error: PAGEINDEX_API_KEY not found in .env file.")
    sys.exit(1)

# Initialize PageIndex client
pi_client = PageIndexClient(api_key=PAGEINDEX_API_KEY)

# Define directories
BOOKS_DIR = Path(r"Y:\F-Drive\Data Science\Deep Learning")
TREES_DIR = Path("trees")
TREES_DIR.mkdir(exist_ok=True)


def list_available_books():
    """List all PDF files in the target deep learning directory."""
    if not BOOKS_DIR.exists():
        print(f"❌ Error: Directory not found: {BOOKS_DIR}")
        return []
    return sorted(list(BOOKS_DIR.glob("*.pdf")))


def count_nodes(nodes):
    """Recursively count the total number of nodes in the hierarchical tree."""
    total = len(nodes)
    for n in nodes:
        if n.get("nodes"):
            total += count_nodes(n["nodes"])
    return total


def print_tree_preview(nodes, indent=0, max_display=12):
    """Print an indentation-based preview of the document hierarchy."""
    displayed = 0
    for node in nodes:
        if displayed >= max_display:
            print("  " * indent + "... [additional sections omitted for brevity]")
            break
        prefix = "  " * indent + ("└─ " if indent > 0 else "• ")
        page = node.get("start_index", node.get("page_index", "?"))
        title = node.get("title", "Untitled")
        node_id = node.get("node_id", "")
        print(f"{prefix}[ID: {node_id}] {title} (p.{page})")
        displayed += 1
        if node.get("nodes") and indent < 2:
            print_tree_preview(node["nodes"], indent + 1, max_display=4)


def index_book(pdf_path: Path):
    """
    Submits a PDF to PageIndex, polls for tree completion, 
    and saves the tree locally to JSON.
    """
    slug = pdf_path.stem.replace(" ", "_")[:50]
    cache_path = TREES_DIR / f"{slug}_tree.json"

    # Check local cache first
    if cache_path.exists():
        print(f"\n📂 Local cache found: {cache_path}")
        with open(cache_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        tree = data.get("result", [])
        print(f"✅ Loaded cached tree for: {pdf_path.name}")
        print(f"📊 Top-level sections: {len(tree)}")
        print(f"🔢 Total nodes in tree: {count_nodes(tree)}")
        return data

    print(f"\n=======================================================")
    print(f"📖 Submitting Document: {pdf_path.name}")
    print(f"📏 Size: {pdf_path.stat().st_size / (1024 * 1024):.2f} MB")
    print(f"=======================================================")

    # Step 1: Submit document to PageIndex
    print("📤 Uploading PDF to PageIndex Cloud...")
    submission = pi_client.submit_document(str(pdf_path))
    doc_id = submission["doc_id"]
    print(f"✅ Uploaded successfully! Document ID: {doc_id}")

    # Step 2: Poll status until tree indexing is complete
    print("\n⏳ Building hierarchical tree index...")
    print("   PageIndex is reading document structure (Chapters, Sections, Pages)...")
    start_time = time.time()
    
    while True:
        status_info = pi_client.get_document(doc_id)
        status = status_info.get("status")
        elapsed = int(time.time() - start_time)
        print(f"   [{elapsed}s] Status: {status}")

        if status == "completed":
            print(f"\n✨ Tree index built successfully in {elapsed} seconds!")
            break
        elif status == "failed":
            print(f"\n❌ Indexing failed: {status_info.get('error', 'Unknown error')}")
            return None

        time.sleep(6)

    # Step 3: Fetch the complete tree with summaries and text
    print("\n📥 Fetching full tree structure with section summaries...")
    tree_data = pi_client.get_tree(doc_id, node_summary=True, include_text=True)
    tree_nodes = tree_data.get("result", [])

    # Step 4: Save locally to disk for instant, cost-free queries
    with open(cache_path, "w", encoding="utf-8") as f:
        json.dump(tree_data, f, ensure_ascii=False, indent=2)

    print(f"💾 Tree cached locally at: {cache_path}")
    print(f"📊 Top-level sections: {len(tree_nodes)}")
    print(f"🔢 Total nodes in tree: {count_nodes(tree_nodes)}")

    print("\n🌲 Document Hierarchy Preview:")
    print_tree_preview(tree_nodes)

    return tree_data


if __name__ == "__main__":
    books = list_available_books()
    if not books:
        print("No books found.")
        sys.exit(1)

    print("\n📚 Available Books:")
    for idx, book in enumerate(books, 1):
        size_mb = book.stat().st_size / (1024 * 1024)
        print(f"  [{idx}] {book.name} ({size_mb:.1f} MB)")

    # Support CLI argument or interactive input
    import argparse
    parser = argparse.ArgumentParser(description="Index a Machine Learning / Deep Learning textbook")
    parser.add_argument("--book", type=int, help="Index of the book to process (1, 2, or 3)", default=None)
    args = parser.parse_args()

    if args.book is not None and 1 <= args.book <= len(books):
        selected_idx = args.book - 1
    else:
        try:
            choice = input("\nEnter book number to index (default is 2 - François Chollet): ").strip()
            selected_idx = int(choice) - 1 if choice.isdigit() and 1 <= int(choice) <= len(books) else 1
        except EOFError:
            selected_idx = 1
    
    selected_book = books[selected_idx]
    index_book(selected_book)
