import re
from pathlib import Path

import fitz  # PyMuPDF
import pdfplumber

from .phases.phase1_boilerplate import detect_headers_footers
from .phases.phase2_font import build_font_hierarchy, compute_doc_stats, get_block_text, get_block_dominant_size
from .phases.phase4_format import format_block_as_markdown
from .phases.phase5_tables import extract_tables_with_pdfplumber
from .postprocess import is_toc_page, remove_page_numbers, normalize_whitespace
from .config import _DEBUG_SCORES, _score_log
from .patterns import CLAUSE_START_RE, ANNEX_RE
from .document import ParsedDocument


# ---------------------------------------------------------------------------
# Sub-clause heading fix helpers
# ---------------------------------------------------------------------------

# Detects a body-text block that begins with an inline clause number
# (e.g. "4.4.1\nL'organisme doit…").  Group 1 = clause number, Group 2 = rest.
_INLINE_CLAUSE_RE = re.compile(r'^(\d+(?:\.\d+)+)[ \t\n]+(.+)', re.DOTALL)


def _fix_clause_headings(blocks):
    """
    Fix two sub-clause formatting defects that arise from PyMuPDF block layout:

    A) Inline clause number + body merged in one block:
       "4.4.1\\nL'organisme doit…"  →  ["#### 4.4.1", "L'organisme doit…"]

    B) Blank clause-number heading followed by orphaned title:
       ["#### 5.1.1", "Leadership et engagement"]  →  ["#### 5.1.1 Leadership et engagement"]
    """
    # Pass 0 — collapse multi-line heading blocks
    # PyMuPDF sometimes groups a clause number and its title into one block:
    # e.g. "5.1.1\nGénéralités" → formatted as "#### 5.1.1\nGénéralités".
    # Merge the two lines into a single heading: "#### 5.1.1 Généralités".
    # Guard: title line must be short, not end with '.' (prose) or ':' (list intro).
    collapsed = []
    for block in blocks:
        if block.startswith('#') and '\n' in block:
            heading_line, *rest_lines = block.split('\n')
            rest = ' '.join(l.strip() for l in rest_lines if l.strip())
            is_title_like = (
                rest
                and len(rest) < 120
                and not rest.rstrip().endswith('.')
                and not rest.rstrip().endswith(':')
            )
            collapsed.append(f"{heading_line} {rest}" if is_title_like else block)
        else:
            collapsed.append(block)
    blocks = collapsed

    # Pass 1 — split inline clause numbers out of body-text blocks
    split = []
    for block in blocks:
        if block.startswith('#'):
            split.append(block)
            continue
        m = _INLINE_CLAUSE_RE.match(block)
        if m:
            clause_num = m.group(1)
            rest       = m.group(2).strip()
            depth      = clause_num.count('.')
            level      = min(4, depth + 1)
            split.append('#' * level + ' ' + clause_num)
            if rest:
                split.append(rest)
        else:
            split.append(block)

    # Pass 2 — merge blank clause-number headings with their following title
    merged = []
    i = 0
    while i < len(split):
        block = split[i]
        # Detect a heading whose text is ONLY a clause number (no title after it)
        m = re.match(r'^(#{1,4}) (\d+(?:\.\d+)*)$', block)
        if m and i + 1 < len(split):
            next_block = split[i + 1]
            # Merge if next block is short body text (not another heading, not a
            # section number, not a long paragraph, and does not end with a period
            # — trailing-period text is a prose sentence, not a title)
            is_title_like = (
                not next_block.startswith('#')
                and not re.match(r'^\d+(?:\.\d+)+', next_block)
                and len(next_block) < 120
                and not next_block.rstrip().endswith('.')
            )
            if is_title_like:
                merged.append(f"{block} {next_block}")
                i += 2
                continue
        merged.append(block)
        i += 1

    return merged


# ---------------------------------------------------------------------------
# Main pipeline
# ---------------------------------------------------------------------------

def parse_iso_pdf(pdf_path):
    """
    Full ingestion pipeline for ISO standard PDFs.

    Steps
    -----
    1.  Detect recurring headers/footers to strip from every page.
    2.  Build a font-size -> heading-level map from a full document scan.
    3.  For each page:
          a. Extract tables (heuristic: >=4 drawing paths -> pdfplumber fallback).
          b. Parse text blocks using PyMuPDF dict format (carries font metadata).
          c. Classify each block as heading or body via font size + ISO patterns.
          d. Skip TOC pages, remove standalone page numbers, normalize whitespace.
    4.  Assemble pages with <!-- page:N --> markers (no hard separators) so clause
        content flows across page boundaries for downstream ISOSegmenter clause-aligned
        chunking.  Page numbers satisfy NormChunk.page_number (P2 traceability).
    """
    doc = fitz.open(pdf_path)

    # ── Phase 1: strip running headers / footers ───────────────────────────
    common_headers_footers = detect_headers_footers(doc)
    print(f"[Header/Footer] {len(common_headers_footers)} repeating block(s) detected.")

    # ── Phase 2: build font hierarchy for heading detection ────────────────
    font_levels, body_size = build_font_hierarchy(doc)

    # ── Phase 2b: compute layout statistics for heading scoring ────────────
    avg_body_indent, avg_line_spacing = compute_doc_stats(doc, body_size)
    print(f"[Doc Stats] avg_body_indent={avg_body_indent:.1f}pt | "
          f"avg_line_spacing={avg_line_spacing:.1f}pt")

    full_markdown = []
    # Counters for the end-of-run diagnostic summary
    heading_counts = {1: 0, 2: 0, 3: 0, 4: 0}

    # ── Document-section state machine ─────────────────────────────────────
    # FRONT_MATTER : skip blocks until clause "1 <X>" heading is found
    # CLAUSES      : normal extraction (the normative body)
    # BACK_MATTER  : stop — annex heading detected, discard the rest
    _parse_state = "FRONT_MATTER"

    with pdfplumber.open(pdf_path) as plumber_pdf:
      for page_num in range(len(doc)):
        if _parse_state == "BACK_MATTER":
            break

        page = doc[page_num]

        # ── Phase 3: Table detection via pdfplumber.find_tables() ────────────
        # Replaces the len(paths) >= 4 drawing-count heuristic.
        # find_tables() returns actual table objects, so decorative borders and
        # ruled lines that don't form a grid no longer trigger false positives.
        plumber_page = plumber_pdf.pages[page_num]
        detected_tables = plumber_page.find_tables()
        has_table = len(detected_tables) > 0
        tables_md = ""
        if has_table:
            print(f"  [Table] Extracting via pdfplumber on page {page_num + 1} "
                  f"({len(detected_tables)} table(s) found)...")
            tables_md = extract_tables_with_pdfplumber(plumber_page)

        # ── Text extraction with font-aware dict format ────────────────────
        # get_text("dict") provides per-span font size/flags, unlike "blocks"
        # which returns raw text only.  sort=True preserves reading order.
        page_dict = page.get_text("dict", sort=True)
        page_md_blocks = []
        prev_block_y1 = 0.0  # reset per page for vertical gap tracking

        for block in page_dict.get("blocks", []):
            # ── State machine: skip front matter / stop at back matter ──────
            block_text = get_block_text(block).strip()
            block_size = get_block_dominant_size(block)
            is_heading_font = block_size > body_size

            if _parse_state == "FRONT_MATTER":
                if CLAUSE_START_RE.match(block_text) and is_heading_font:
                    _parse_state = "CLAUSES"
                    print(f"  [State] Clause start: '{block_text[:60]}' — page {page_num + 1}")
                else:
                    continue  # discard front matter

            elif _parse_state == "CLAUSES":
                if ANNEX_RE.match(block_text) and is_heading_font:
                    _parse_state = "BACK_MATTER"
                    print(f"  [State] Back matter start: '{block_text[:60]}' — page {page_num + 1}")
                    break  # outer loop will break on next iteration

            md_block = format_block_as_markdown(
                block, font_levels, body_size, common_headers_footers,
                avg_body_indent=avg_body_indent,
                prev_block_y1=prev_block_y1,
                avg_line_spacing=avg_line_spacing,
                page_height=page.rect.height,
                is_table_page=has_table,
            )
            if md_block is None:
                continue

            # Update prev_block_y1 only for rendered (non-skipped) blocks.
            # Skipped header/footer blocks are not part of the content flow,
            # so their y1 must not reset the spacing baseline.
            prev_block_y1 = block["bbox"][3]

            page_md_blocks.append(md_block)

        # Fix sub-clause heading defects before joining into page text.
        # Must run before heading_counts so counts reflect the corrected blocks.
        page_md_blocks = _fix_clause_headings(page_md_blocks)

        # Track heading occurrences for the diagnostic summary (post-fix)
        for blk in page_md_blocks:
            if blk.startswith("#### "):   heading_counts[4] += 1
            elif blk.startswith("### "): heading_counts[3] += 1
            elif blk.startswith("## "):  heading_counts[2] += 1
            elif blk.startswith("# "):   heading_counts[1] += 1

        page_text = "\n\n".join(page_md_blocks)

        # ── Skip TOC pages ─────────────────────────────────────────────────
        if is_toc_page(page_text):
            print(f"  [TOC] Skipping page {page_num + 1}.")
            continue

        # ── Post-processing ────────────────────────────────────────────────
        page_text = remove_page_numbers(page_text)
        page_text = normalize_whitespace(page_text)

        # Append table markdown below the page text (if any tables were found).
        # Only include tables for pages that are in the CLAUSES section:
        # - Exclude front-matter tables (page_md_blocks empty → no clause text yet)
        # - Exclude annex tables (state flipped to BACK_MATTER mid-page)
        if tables_md and page_md_blocks and _parse_state == "CLAUSES":
            page_text = f"{page_text}\n\n{tables_md}"

        # Skip pages that produced no content after all filters
        # (front-matter pages where every block was discarded).
        if not page_text.strip():
            continue

        # Prepend a page-number marker so the ISOSegmenter can populate
        # NormChunk.page_number (P2 traceability).  The marker uses HTML
        # comment syntax — invisible in rendered Markdown, trivially parseable
        # by the segmenter with: re.findall(r'<!-- page:(\d+) -->', text)
        page_marker = f"<!-- page:{page_num + 1} -->"
        full_markdown.append(f"{page_marker}\n{page_text}")

    doc.close()

    # ── Diagnostic summary ─────────────────────────────────────────────────
    print(f"\n[Heading Detection Results]")
    print(f"  H1 (#)    : {heading_counts[1]} headings")
    print(f"  H2 (##)   : {heading_counts[2]} headings")
    print(f"  H3 (###)  : {heading_counts[3]} headings")
    print(f"  H4 (####) : {heading_counts[4]} headings")
    if _DEBUG_SCORES and _score_log:
        from collections import Counter
        dist = Counter(_score_log)
        print(f"  Score distribution: { {k: dist[k] for k in sorted(dist)} }")
        _score_log.clear()

    # Pages are joined with a plain blank line — no hard separator.
    # Clause content that spans a page boundary flows continuously.
    # The ISOSegmenter splits on heading markers (##, ###), not on page breaks.
    assembled = "\n\n".join(full_markdown)

    # ── Build page_map: char_offset → page_num ─────────────────────────────
    page_map = {
        m.start(): int(m.group(1))
        for m in re.finditer(r'<!-- page:(\d+) -->', assembled)
    }

    # ── Build heading_positions: [{offset, level, text}] ───────────────────
    heading_positions = [
        {"offset": m.start(), "level": len(m.group(1)), "text": m.group(2).strip()}
        for m in re.finditer(r'^(#{1,4}) (.+)$', assembled, re.MULTILINE)
    ]

    return ParsedDocument(
        standard_id=Path(pdf_path).stem,
        markdown=assembled,
        page_map=page_map,
        heading_positions=heading_positions,
    )


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    base_dir = Path(__file__).parent.parent
    pdf_path = base_dir / "data" / "n9001.pdf"

    if not pdf_path.exists():
        print(f"Error: PDF not found at {pdf_path}")
    else:
        print(f"Parsing PDF: {pdf_path}\n")
        result = parse_iso_pdf(str(pdf_path))

        output_dir = base_dir / "output"
        output_dir.mkdir(exist_ok=True)

        output_path = output_dir / "ISO-n14001-2015.md"
        with open(output_path, "w", encoding="utf-8") as f:
            f.write(result.markdown)

        print(f"\nMarkdown saved to: {output_path}")
