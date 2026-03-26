# ---------------------------------------------------------------------------
# Table extraction
# ---------------------------------------------------------------------------

def extract_tables_with_pdfplumber(plumber_page):
    """
    Extract tables from a pdfplumber page object and convert to Markdown.
    Line-based strategy works well for ISO standard tables which use ruled lines.

    Parameters
    ----------
    plumber_page : pdfplumber.Page
        An already-open pdfplumber page (caller owns the pdfplumber context).
    """
    tables_md = []
    table_settings = {
        "vertical_strategy": "lines",
        "horizontal_strategy": "lines",
    }
    tables = plumber_page.extract_tables(table_settings)
    for table in tables:
        if not table:
            continue
        md_table = ""
        for i, row in enumerate(table):
            clean_row = [
                str(item).replace('\n', ' ').strip() if item is not None else ""
                for item in row
            ]
            md_table += "| " + " | ".join(clean_row) + " |\n"
            if i == 0:
                # Separator row after the header row
                md_table += "|" + "|".join(["---"] * len(clean_row)) + "|\n"
        tables_md.append(md_table)
    return "\n\n".join(tables_md)
