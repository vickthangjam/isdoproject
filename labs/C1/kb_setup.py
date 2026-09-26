"""
ISDO - Knowledge Base indexer and retrieval test.

1. Reads every .md file in data/kb/
2. Splits each article into chunks at "## " headings
3. Stores the chunks in the ChromaDB collection 'isdo_kb'
4. Runs sample queries and prints the best matching article + confidence

Uses only the chromadb package (its built-in all-MiniLM-L6-v2 embedding model;
the model downloads once, about 80 MB, on first run).

Run from anywhere:
    labenv\\Scripts\\activate
    python build_kb_index.py
"""

import re
from pathlib import Path

import chromadb

def find_project_root(start: Path) -> Path:
    """Walk up from the script's folder until a folder containing data/kb is found."""
    for folder in [start, *start.parents]:
        if (folder / "data" / "kb").is_dir():
            return folder
    raise SystemExit(f"Could not find a data/kb folder above {start}")


BASE_DIR = find_project_root(Path(__file__).resolve().parent)
KB_DIR = BASE_DIR / "data" / "kb"
DB_DIR = BASE_DIR / "data" / "chroma_db"
COLLECTION_NAME = "isdo_kb"

# Sample queries, with the article each one should match (used for PASS/FAIL).
SAMPLE_QUERIES = [
    ("I changed my password and now the VPN says authentication failed", "vpn_troubleshooting.md"),
    ("My account is locked out after too many wrong login attempts", "password_reset.md"),
    ("Outlook on my phone stopped syncing new emails", "email_troubleshooting.md"),
    ("SAP is down for our whole team and nobody can log in to ERP", "erp_connectivity.md"),
]

# Only level-2 headings start a new chunk ("### Step ..." stays inside its section).
H2_PATTERN = re.compile(r"^## +(.+?)\s*$", re.MULTILINE)
H1_PATTERN = re.compile(r"^# +(.+?)\s*$", re.MULTILINE)


def chunk_markdown(text: str, filename: str) -> list[dict]:
    """Split one article at '## ' headings.

    Text before the first '## ' (title, category, tags) becomes an 'Overview'
    chunk. The article title is prepended to every chunk so each chunk carries
    its context when embedded on its own.
    """
    title_match = H1_PATTERN.search(text)
    title = title_match.group(1) if title_match else Path(filename).stem

    headings = list(H2_PATTERN.finditer(text))
    sections = []

    preamble_end = headings[0].start() if headings else len(text)
    preamble = text[:preamble_end].strip()
    if preamble:
        sections.append(("Overview", preamble))

    for i, match in enumerate(headings):
        end = headings[i + 1].start() if i + 1 < len(headings) else len(text)
        body = text[match.start():end].strip()
        sections.append((match.group(1), body))

    chunks = []
    for idx, (section, body) in enumerate(sections):
        if section == "Overview":
            document = body  # already starts with the title
        else:
            document = f"# {title}\n\n{body}"
        chunks.append({
            "id": f"{Path(filename).stem}::{idx:02d}",
            "document": document,
            "metadata": {
                "article": filename,
                "title": title,
                "section": section,
                "chunk_index": idx,
            },
        })
    return chunks


def load_chunks(kb_dir: Path) -> list[dict]:
    md_files = sorted(kb_dir.glob("*.md"))
    if not md_files:
        raise SystemExit(f"No .md files found in {kb_dir}")

    all_chunks = []
    for path in md_files:
        text = path.read_text(encoding="utf-8")
        chunks = chunk_markdown(text, path.name)
        print(f"  {path.name:<28} {len(chunks)} chunks")
        all_chunks.extend(chunks)
    return all_chunks


def build_collection(chunks: list[dict]):
    client = chromadb.PersistentClient(path=str(DB_DIR))

    # Rebuild from scratch so edited or removed articles don't leave stale chunks.
    try:
        client.delete_collection(COLLECTION_NAME)
    except Exception:
        pass  # collection didn't exist yet

    # Cosine distance, so confidence = 1 - distance is easy to read.
    collection = client.create_collection(
        name=COLLECTION_NAME,
        metadata={"hnsw:space": "cosine"},
    )
    collection.add(
        ids=[c["id"] for c in chunks],
        documents=[c["document"] for c in chunks],
        metadatas=[c["metadata"] for c in chunks],
    )
    return collection


def best_article(collection, query: str, n_results: int = 5):
    """Return (article, title, section, confidence) of the closest chunk."""
    result = collection.query(
        query_texts=[query],
        n_results=n_results,
        include=["metadatas", "distances"],
    )
    metadatas = result["metadatas"][0]
    distances = result["distances"][0]
    if not metadatas:
        return None

    # Results come back sorted by distance, so the first hit is the best chunk.
    meta, distance = metadatas[0], distances[0]
    confidence = max(0.0, min(1.0, 1.0 - distance))
    return meta["article"], meta["title"], meta["section"], confidence


def main():
    print(f"Reading articles from {KB_DIR}")
    chunks = load_chunks(KB_DIR)

    print(f"\nStoring {len(chunks)} chunks in ChromaDB collection '{COLLECTION_NAME}' ({DB_DIR})")
    collection = build_collection(chunks)
    print(f"Collection now holds {collection.count()} chunks")

    print("\nSample queries")
    print("-" * 78)
    passed = 0
    for query, expected in SAMPLE_QUERIES:
        hit = best_article(collection, query)
        if hit is None:
            print(f"Query: {query}\n  No match found\n")
            continue
        article, title, section, confidence = hit
        ok = article == expected
        passed += ok
        print(f"Query:      {query}")
        print(f"Best match: {article}  ({title})")
        print(f"Section:    {section}")
        print(f"Confidence: {confidence:.2%}   [{'PASS' if ok else 'FAIL - expected ' + expected}]")
        print()
    print("-" * 78)
    print(f"{passed}/{len(SAMPLE_QUERIES)} queries matched the expected article")


if __name__ == "__main__":
    main()
