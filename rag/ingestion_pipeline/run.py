import os
from pathlib import Path
from parser import parse_iso_pdf
from pipeline import segment, embed_and_store

base_dir = Path(__file__).parent
pdf_path = base_dir / "data" / "n9001.pdf"

if not pdf_path.exists():
    print(f"Error: PDF not found at {pdf_path}")
else:
    print(f"Parsing PDF: {pdf_path}\n")
    doc = parse_iso_pdf(str(pdf_path))

    output_dir = base_dir / "output"
    result = segment(doc, output_dir=str(output_dir), language="FR")

    print(f"\nDone.")
    print(f"  standard : {result.standard_id}")
    print(f"  chunks   : {len(result.chunks)}")
    print(f"  tree     : {len(result.tree.children)} top-level clauses")

    # Phase 7 — opt-in embedding (set EMBEDDING_ENABLED=true to activate)
    if os.getenv("EMBEDDING_ENABLED", "false").lower() == "true":
        collection = os.getenv("QDRANT_COLLECTION", "norms")
        print(f"\n[Phase 7] Embedding into Qdrant collection '{collection}'...")
        count = embed_and_store(result, collection=collection)
        print(f"[Phase 7] Complete — {count} chunks stored.")
    else:
        print("\n[Phase 7] Skipped. Set EMBEDDING_ENABLED=true to embed into Qdrant.")
