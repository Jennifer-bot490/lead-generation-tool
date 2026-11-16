"""CSV / Excel export with Pandas + OpenPyXL."""
import io
import re

import pandas as pd
from openpyxl.styles import Alignment, Font, PatternFill

COLUMNS = [("name", "Business Name"), ("phone", "Phone"), ("email", "Email"), ("website", "Website"),
           ("address", "Address"), ("city", "City"), ("category", "Category"), ("source", "Source")]


def _safe(value, key):
    """Prevent spreadsheet formula injection (cells starting with = + - @)."""
    v = "" if value is None else str(value)
    if key == "phone" and re.fullmatch(r"[+\d\s]*", v):
        return v
    return "'" + v if v[:1] in ("=", "+", "-", "@") else v


def to_dataframe(rows):
    data = [{label: _safe(r.get(k, "N/A"), k) for k, label in COLUMNS} for r in rows if isinstance(r, dict)]
    return pd.DataFrame(data, columns=[label for _, label in COLUMNS])


def to_csv_bytes(rows):
    return to_dataframe(rows).to_csv(index=False).encode("utf-8-sig")  # BOM: Excel reads UTF-8


def to_xlsx_bytes(rows):
    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as writer:
        to_dataframe(rows).to_excel(writer, index=False, sheet_name="Leads")
        ws = writer.sheets["Leads"]
        for c in ws[1]:
            c.font, c.fill = Font(bold=True, color="FFFFFF"), PatternFill("solid", fgColor="4F46E5")
            c.alignment = Alignment(vertical="center")
        for col, w in zip("ABCDEFGH", (32, 18, 30, 36, 44, 16, 20, 16)):
            ws.column_dimensions[col].width = w
        ws.freeze_panes = "A2"
    return buf.getvalue()
