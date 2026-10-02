import os
import sys
import json
from pathlib import Path
from dotenv import load_dotenv
from groq import Groq

# Ensure UTF-8 output on Windows terminal
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")

# 1. Load API Key & Initialize Groq Client
load_dotenv()
GROQ_API_KEY = os.getenv("GROQ_API_KEY")

if not GROQ_API_KEY:
    print("❌ Error: GROQ_API_KEY not found in .env file.")
    sys.exit(1)

groq_client = Groq(api_key=GROQ_API_KEY)
DEFAULT_MODEL = "openai/gpt-oss-120b"


# ---------------------------------------------------------------------------
# FUNCTION 1: generate_tree_outline
# Purpose: Transform the nested JSON tree into a clean, human-like Table
# of Contents outline.
# Why: A structured text outline uses 70% fewer tokens than raw JSON
# (~3,800 tokens vs ~14,000 tokens), preventing rate limits while preserving
# all chapter/section titles, start pages, and high-level summaries.
# ---------------------------------------------------------------------------
def generate_tree_outline(nodes: list, indent: int = 0) -> str:
    """
    Recursively converts tree nodes into a compact, indented text outline.
    Format: [node_id] Title (p.PageNumber) | Summary preview...
    """
    lines = []
    for node in nodes:
        prefix = "  " * indent + ("- " if indent > 0 else "# ")
        nid = node.get("node_id", "")
        title = node.get("title", "Untitled")
        page = node.get("start_index", node.get("page_index", "?"))
        
        # Add summary only for top-level chapters and major sections
        summary = (node.get("summary") or "").strip().replace("\n", " ")
        summary_str = f" | {summary[:75]}..." if summary and indent <= 1 else ""

        lines.append(f"{prefix}[{nid}] {title} (p.{page}){summary_str}")

        if node.get("nodes"):
            lines.append(generate_tree_outline(node["nodes"], indent + 1))

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# FUNCTION 2: llm_tree_search
# Purpose: Send the user query + book outline to Groq.
# Groq reasons through the structure to identify the exact section node IDs.
# ---------------------------------------------------------------------------
def llm_tree_search(query: str, outline_text: str, model: str = DEFAULT_MODEL) -> dict:
    """
    Uses Groq LLM reasoning to navigate the document outline and select
    the top 1-3 most relevant section node IDs.
    """
    system_prompt = (
        "You are an expert research librarian and deep learning specialist.\n"
        "You analyze a technical book's Table of Contents outline to locate exact sections containing the answer.\n"
        "You must respond ONLY with valid JSON."
    )

    user_prompt = f"""Examine the book outline below and determine which specific section node IDs most likely contain the answer to the user's question.

Question:
{query}

Book Table of Contents Outline:
{outline_text}

Respond in this exact JSON format:
{{
  "thinking": "Step-by-step reasoning explaining which chapter and subsections are relevant and why.",
  "node_list": ["<node_id_1>", "<node_id_2>"]
}}"""

    response = groq_client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt}
        ],
        response_format={"type": "json_object"},
        temperature=0.1
    )

    try:
        return json.loads(response.choices[0].message.content)
    except json.JSONDecodeError:
        print("⚠️ Warning: Failed to parse JSON from LLM search response.")
        return {"thinking": "JSON parsing error", "node_list": []}


# ---------------------------------------------------------------------------
# FUNCTION 3: find_nodes_by_ids
# Purpose: Walk the full document tree and extract the complete text,
# title, and page range for the nodes chosen by the LLM.
# ---------------------------------------------------------------------------
def find_nodes_by_ids(nodes: list, target_ids: list) -> list:
    """
    Recursively walks the full tree and returns the complete node objects
    for all matching node_ids.
    """
    target_set = set(target_ids)
    matched_nodes = []

    def _walk(node_list):
        for node in node_list:
            if node.get("node_id") in target_set:
                matched_nodes.append(node)
            if node.get("nodes"):
                _walk(node["nodes"])

    _walk(nodes)
    return matched_nodes


# ---------------------------------------------------------------------------
# FUNCTION 4: generate_grounded_answer
# Purpose: Assemble full section text into context and prompt Groq to
# synthesize a comprehensive answer with explicit page and section citations.
# ---------------------------------------------------------------------------
def generate_grounded_answer(query: str, retrieved_nodes: list, model: str = DEFAULT_MODEL) -> str:
    """
    Generates a grounded, factual answer based strictly on retrieved sections,
    citing section titles and page numbers.
    """
    if not retrieved_nodes:
        return "⚠️ No relevant sections could be retrieved from the book."

    # Build the grounded context block from retrieved nodes
    context_blocks = []
    for node in retrieved_nodes:
        title = node.get("title", "Untitled Section")
        start_page = node.get("start_index", node.get("page_index", "?"))
        end_page = node.get("end_index", start_page)
        text = node.get("text", "").strip()

        block = (
            f"=== [Section: '{title}' | Pages {start_page}-{end_page}] ===\n"
            f"{text}"
        )
        context_blocks.append(block)

    full_context = "\n\n" + ("\n" + "-" * 50 + "\n").join(context_blocks)

    system_instruction = (
        "You are an expert deep learning instructor. Answer the user's question using ONLY the provided textbook context.\n"
        "Guidelines:\n"
        "1. For every key point, formula, or concept you explain, explicitly cite the section title and page number in parentheses, e.g. (Section: '...', Page X).\n"
        "2. Do not hallucinate or use external information outside the provided text.\n"
        "3. Provide a clear, thorough, and technically accurate explanation with code or formulas if present in the text."
    )

    user_prompt = f"""Question: {query}

Reference Context from Textbook:
{full_context}

Grounded Answer:"""

    response = groq_client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": system_instruction},
            {"role": "user", "content": user_prompt}
        ],
        temperature=0.2
    )

    return response.choices[0].message.content.strip()


# ---------------------------------------------------------------------------
# FUNCTION 5: vectorless_rag (Pipeline Coordinator)
# Purpose: Ties Step 3 (Search) and Step 4 (Retrieve & Generate) together.
# ---------------------------------------------------------------------------
def vectorless_rag(query: str, tree_path: str = "trees/Deep_Learning_with_Python_tree.json", verbose: bool = True) -> dict:
    """
    Full End-to-End Vectorless RAG Pipeline:
    Query -> LLM Tree Search -> Node Extraction -> Grounded Answer Synthesis
    """
    tree_file = Path(tree_path)
    if not tree_file.exists():
        raise FileNotFoundError(f"Tree file not found at: {tree_file}")

    with open(tree_file, "r", encoding="utf-8") as f:
        tree_raw = json.load(f)

    full_tree = tree_raw.get("result", [])

    if verbose:
        print("\n" + "=" * 65)
        print(f"🔍 QUERY: {query}")
        print("=" * 65)

    # Step 1: Generate compact outline for LLM reasoning
    outline_text = generate_tree_outline(full_tree)

    # Step 2: Reasoning Tree Search
    if verbose:
        print("\n🧠 Step 1: Groq LLM reasoning over document hierarchy...")
    search_result = llm_tree_search(query, outline_text)
    node_ids = search_result.get("node_list", [])

    if verbose:
        print(f"💭 Reasoning:\n{search_result.get('thinking', 'N/A')}")
        print(f"\n🎯 Selected Node IDs: {node_ids}")

    # Step 3: Node Retrieval
    if verbose:
        print("\n📥 Step 2: Extracting full section content...")
    retrieved_nodes = find_nodes_by_ids(full_tree, node_ids)

    if verbose:
        for n in retrieved_nodes:
            print(f"   • [{n.get('node_id')}] {n.get('title')} (Pages {n.get('start_index')}-{n.get('end_index')})")

    # Step 4: Grounded Answer Generation
    if verbose:
        print("\n📝 Step 3: Synthesizing grounded answer with citations...")
    answer = generate_grounded_answer(query, retrieved_nodes)

    if verbose:
        print("\n" + "=" * 65)
        print("📖 GROUNDED ANSWER:")
        print("=" * 65)
        print(answer)
        print("=" * 65 + "\n")

    return {
        "query": query,
        "thinking": search_result.get("thinking"),
        "node_ids": node_ids,
        "retrieved_nodes": [n.get("title") for n in retrieved_nodes],
        "answer": answer
    }


# ---------------------------------------------------------------------------
# Interactive Execution
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    default_tree = "trees/Deep_Learning_with_Python_tree.json"

    sample_queries = [
        "How do residual connections work and why are they important?",
        "What is self-attention and how does it compute representations in Transformers?",
        "Explain the difference between Batch Normalization and standard normalization.",
        "What is the convolution operation and how do convnets process visual patterns?"
    ]

    print("\n📚 Vectorless RAG Pipeline Ready!")
    print("Choose an option:")
    print("  [1] Run a sample question")
    print("  [2] Ask your own custom question")
    
    choice = input("\nEnter choice (1 or 2, default is 1): ").strip()
    
    if choice == "2":
        user_q = input("\nEnter your question: ").strip()
        if user_q:
            vectorless_rag(user_q, tree_path=default_tree)
    else:
        print("\nAvailable Sample Queries:")
        for idx, q in enumerate(sample_queries, 1):
            print(f"  [{idx}] {q}")
        q_idx = input(f"\nSelect query (1-{len(sample_queries)}, default is 1): ").strip()
        selected_q = sample_queries[int(q_idx) - 1] if q_idx.isdigit() and 1 <= int(q_idx) <= len(sample_queries) else sample_queries[0]
        vectorless_rag(selected_q, tree_path=default_tree)
