"""GST invoice PDF renderer (M5 Task 12). Pure function - no I/O, no
settings lookups: every seller/buyer detail arrives as an argument so both
callers (the worker sweep in ad_orders.py AND the advertiser's on-demand
download route in router.py) render byte-identical output from the same
inputs. fpdf2, plain A4 layout - no logo, no custom fonts.

v1 simplifications (both deliberate, both revisit-if-needed):
- A missing buyer GSTIN (a normal unregistered B2C ad buyer) is treated as
  a same-state buyer -> CGST+SGST split, never IGST. A real cross-state B2C
  sale to an unregistered buyer should legally be IGST, but determining the
  buyer's state without a GSTIN would need a billing-address field this v1
  checkout does not collect. Accepted trade-off for launch.
- "Rs." instead of "₹": fpdf2's built-in core fonts (Helvetica) are
  WinAnsi/Latin-1 only and have no glyph for the Rupee sign - embedding a
  Unicode TTF just for one glyph is not worth it for a v1 invoice. Every
  amount renders as "Rs. 1,234.56" (display formatting only; every amount
  argument below stays an integer paise count).
- compression is OFF (`pdf.compress = False`) so the page content stream
  stays plain text inside the returned bytes - this lets tests
  substring-search the output (e.g. for b"CGST"/b"IGST"/b"SAC 998365")
  without adding a PDF-parsing dependency just for assertions.
"""

from datetime import date

from fpdf import FPDF

SAC_LINE = "SAC 998365 - Sale of internet advertising space"


def _money(paise: int) -> str:
    return f"Rs. {paise / 100:,.2f}"


def _same_state(seller_gstin: str, buyer_gstin: str | None) -> bool:
    """True => CGST+SGST split; False => IGST. See the module docstring for
    the no-buyer-GSTIN v1 simplification (also True there)."""
    if not buyer_gstin or len(seller_gstin) < 2 or len(buyer_gstin) < 2:
        return True
    return seller_gstin[:2] == buyer_gstin[:2]


def render_invoice_pdf(
    *,
    invoice_number: str,
    issued_on: date,
    seller: tuple[str, str, str],  # (name, gstin, address)
    buyer_name: str,
    buyer_gstin: str | None,
    lines: list[tuple[str, int]],
    taxable_paise: int,
    gst_paise: int,
    total_paise: int,
) -> bytes:
    seller_name, seller_gstin, seller_address = seller
    intra_state = _same_state(seller_gstin, buyer_gstin)

    pdf = FPDF(orientation="P", unit="mm", format="A4")
    pdf.compress = False  # see module docstring - keeps text greppable
    pdf.set_auto_page_break(auto=True, margin=15)
    pdf.add_page()

    pdf.set_font("Helvetica", "B", 16)
    pdf.cell(0, 10, "TAX INVOICE", new_x="LMARGIN", new_y="NEXT")

    pdf.set_font("Helvetica", "", 10)
    pdf.multi_cell(0, 5, f"{seller_name}\n{seller_address or '-'}\nGSTIN: {seller_gstin or '-'}")
    pdf.ln(2)
    pdf.cell(0, 5, f"Invoice No: {invoice_number}", new_x="LMARGIN", new_y="NEXT")
    pdf.cell(0, 5, f"Date: {issued_on.isoformat()}", new_x="LMARGIN", new_y="NEXT")
    pdf.ln(2)
    pdf.multi_cell(0, 5, f"Bill To:\n{buyer_name}\nGSTIN: {buyer_gstin or 'Unregistered'}")
    pdf.ln(4)

    pdf.set_font("Helvetica", "B", 10)
    pdf.cell(140, 7, "Description", border=1)
    pdf.cell(50, 7, "Amount", border=1, new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Helvetica", "", 10)
    for label, amount_paise in lines:
        pdf.cell(140, 7, label, border=1)
        pdf.cell(50, 7, _money(amount_paise), border=1, new_x="LMARGIN", new_y="NEXT")
    pdf.ln(2)
    pdf.set_font("Helvetica", "", 9)
    pdf.cell(0, 5, SAC_LINE, new_x="LMARGIN", new_y="NEXT")
    pdf.ln(4)

    pdf.set_font("Helvetica", "", 10)
    pdf.cell(140, 6, "Taxable value", border=0)
    pdf.cell(50, 6, _money(taxable_paise), border=0, new_x="LMARGIN", new_y="NEXT")
    if intra_state:
        # split is always exactly half-and-half so cgst+sgst == gst_paise
        # regardless of the actual configured rate (this function has no
        # settings access - it only ever sees the pre-split total).
        cgst = gst_paise // 2
        sgst = gst_paise - cgst
        pdf.cell(140, 6, "CGST", border=0)
        pdf.cell(50, 6, _money(cgst), border=0, new_x="LMARGIN", new_y="NEXT")
        pdf.cell(140, 6, "SGST", border=0)
        pdf.cell(50, 6, _money(sgst), border=0, new_x="LMARGIN", new_y="NEXT")
    else:
        pdf.cell(140, 6, "IGST", border=0)
        pdf.cell(50, 6, _money(gst_paise), border=0, new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Helvetica", "B", 10)
    pdf.cell(140, 7, "Total", border=0)
    pdf.cell(50, 7, _money(total_paise), border=0, new_x="LMARGIN", new_y="NEXT")

    return bytes(pdf.output())
