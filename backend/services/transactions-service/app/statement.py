"""Generarea extrasului de cont (PDF) — vezi app/service.py::generate_account_statement
pentru interogarea DB și reconstrucția soldurilor; acest modul se ocupă
STRICT de randare (reportlab — pur Python, fără dependențe de sistem grele
în imaginea Docker, spre deosebire de alternative ca WeasyPrint/wkhtmltopdf,
care ar cere Cairo/Pango).

Separat intenționat în două bucăți testabile independent:
  - `reconstruct_statement_balances` — funcție PURĂ (fără DB/HTTP), ușor
    de testat cu documente sintetice — vezi tests/test_statement.py.
  - `render_statement_pdf` — doar randare, testată prin verificarea că
    output-ul e un PDF valid (magic bytes "%PDF"), nu prin parsare de
    conținut (ar necesita o librărie suplimentară doar pentru teste).
"""

import logging
import os
from datetime import datetime, timezone
from io import BytesIO
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.enums import TA_RIGHT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from app.money import format_minor_amount

logger = logging.getLogger("transactions-service")

# Fonturile de bază ale PDF-ului (Helvetica) NU au glife pentru diacriticele
# românești (ă, â, î, ș, ț) — apar ca pătrățele goale. DejaVu Sans le
# acoperă complet; instalat via apt (fonts-dejavu-core, vezi Dockerfile),
# NU adus ca fișier binar în git. Fallback pe Helvetica dacă fontul nu e
# găsit (ex. dev local fără imaginea rebuild-uită) — extrasul tot se
# generează, doar cu diacriticele stricate, nu crapă.
_DEJAVU_REGULAR_PATH = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
_DEJAVU_BOLD_PATH = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
if os.path.exists(_DEJAVU_REGULAR_PATH) and os.path.exists(_DEJAVU_BOLD_PATH):
    pdfmetrics.registerFont(TTFont("Statement", _DEJAVU_REGULAR_PATH))
    pdfmetrics.registerFont(TTFont("Statement-Bold", _DEJAVU_BOLD_PATH))
    FONT_REGULAR = "Statement"
    FONT_BOLD = "Statement-Bold"
else:
    logger.warning("app.statement: DejaVu Sans indisponibil — extrasul de cont va folosi Helvetica (diacritice RO stricate).")
    FONT_REGULAR = "Helvetica"
    FONT_BOLD = "Helvetica-Bold"

def _format_iban_display(iban: str) -> str:
    """RO53MAES2105322292430503 -> "RO53 MAES 2105 3222 9243 0503" — grupare
    pe 4 caractere, exact cum tipăresc IBAN-ul băncile reale pe extrase
    (și cum e deja tipărit fizic pe orice card/document bancar)."""
    return " ".join(iban[i : i + 4] for i in range(0, len(iban), 4))


def _draw_footer(canvas, doc) -> None:
    """Subsol pe fiecare pagină — număr de pagină + linie standard de
    autenticitate ("document generat automat, fără semnătură"), ca pe un
    extras de cont real."""
    canvas.saveState()
    canvas.setFont(FONT_REGULAR, 7)
    canvas.setFillColor(colors.HexColor("#9aa5b8"))
    canvas.drawString(18 * mm, 10 * mm, "MaestroBank — document generat automat, valabil fără semnătură sau ștampilă.")
    canvas.drawRightString(A4[0] - 18 * mm, 10 * mm, f"Pagina {canvas.getPageNumber()}")
    canvas.restoreState()


ACCOUNT_TYPE_LABELS = {
    "current": "Cont curent",
    "savings": "Cont de economii",
    "deposit": "Depozit",
    "student": "Cont student",
    "eur": "Cont EUR",
    "usd": "Cont USD",
    "gbp": "Cont GBP",
}


def reconstruct_statement_balances(
    *,
    current_balance_minor: int,
    movements: list[dict],
    date_from: datetime,
    date_to: datetime,
) -> tuple[int, int, list[dict]]:
    """Reconstruiește soldul de ÎNCEPUT/SFÂRȘIT al perioadei din soldul
    CURENT al contului + istoricul complet de mișcări — nu există un tabel
    de solduri istorice separat în acest model de date, la fel ca restul
    rapoartelor din acest serviciu (CSV export, analytics).

    `movements` — shape GENERIC, deja normalizat de apelant (vezi
    app/service.py::generate_account_statement), NU documente Mongo brute:
    fiecare e `{"created_at": datetime naive-UTC, "delta_minor": int (+
    credit / - debit), "description": str, "category": str}`. Generic
    intenționat — un cont poate primi bani atât din transferuri (tx_db,
    transactions-service) cât și din schimb valutar (exchange-service,
    invizibil pentru tx_db); apelantul le unifică ÎNAINTE să ajungă aici,
    ca funcția asta să rămână o simplă reconstrucție aritmetică, ușor de
    testat cu date sintetice (vezi tests/test_statement.py), fără să știe
    nimic despre de UNDE vine fiecare mișcare.

    `created_at` trebuie normalizat la naive-UTC de apelant (vezi
    gotcha-ul Motor documentat în _payment_request_effective_status —
    aici comparăm direct în Python, nu doar în query Mongo), iar lista NU
    trebuie să fie pre-sortată (sortăm aici, ca apelantul să poată doar
    concatena sursele fără să se mai gândească la ordine).

    Returnează (opening_balance_minor, closing_balance_minor, period_movements)
    — `period_movements` sunt mișcările din [date_from, date_to], în ordine
    cronologică, fiecare cu `running_balance_minor` adăugat.
    """
    ordered = sorted(movements, key=lambda m: m["created_at"])

    net_after = 0
    period: list[dict] = []
    for movement in ordered:
        created_at = movement["created_at"]
        if created_at > date_to:
            net_after += movement["delta_minor"]
        elif created_at >= date_from:
            period.append(movement)

    net_in_period = sum(m["delta_minor"] for m in period)

    closing_balance_minor = current_balance_minor - net_after
    opening_balance_minor = closing_balance_minor - net_in_period

    running = opening_balance_minor
    enriched: list[dict] = []
    for movement in period:
        running += movement["delta_minor"]
        enriched.append({**movement, "running_balance_minor": running})

    return opening_balance_minor, closing_balance_minor, enriched


def render_statement_pdf(
    *,
    holder_name: str,
    iban: str,
    account_type: str,
    currency: str,
    date_from: datetime,
    date_to: datetime,
    opening_balance_minor: int,
    closing_balance_minor: int,
    lines: list[dict],
) -> bytes:
    """`lines` — mișcări GENERICE (shape-ul întors de reconstruct_statement_balances:
    `created_at`/`delta_minor`/`description`/`category`/`running_balance_minor`),
    ordonate cronologic — vezi acolo de ce shape-ul e generic, nu documente
    Mongo brute."""
    buffer = BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        leftMargin=18 * mm,
        rightMargin=18 * mm,
        topMargin=16 * mm,
        bottomMargin=16 * mm,
        title="Extras de cont MaestroBank",
    )
    styles = getSampleStyleSheet()
    normal_style = ParagraphStyle("MBNormal", parent=styles["Normal"], fontName=FONT_REGULAR)
    title_style = ParagraphStyle(
        "MBTitle",
        parent=styles["Heading1"],
        fontName=FONT_BOLD,
        fontSize=18,
        spaceAfter=2,
        textColor=colors.HexColor("#0a1226"),
    )
    meta_style = ParagraphStyle(
        "MBMeta", parent=normal_style, fontSize=9, textColor=colors.HexColor("#54627a")
    )
    cell_style = ParagraphStyle("MBCell", parent=normal_style, fontSize=8, leading=10)
    right_style = ParagraphStyle("MBRight", parent=cell_style, alignment=TA_RIGHT)

    story = [
        Paragraph("MaestroBank", title_style),
        Paragraph("Extras de cont", meta_style),
        Spacer(1, 10),
    ]

    info_rows = [
        ["Titular", escape(holder_name)],
        ["IBAN", _format_iban_display(iban)],
        ["Tip cont", ACCOUNT_TYPE_LABELS.get(account_type, account_type)],
        ["Monedă", currency],
        ["Perioadă", f"{date_from.date().isoformat()} – {date_to.date().isoformat()}"],
        ["Generat la", datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")],
    ]
    info_table = Table(info_rows, colWidths=[32 * mm, 122 * mm])
    info_table.setStyle(
        TableStyle(
            [
                ("FONTNAME", (0, 0), (-1, -1), FONT_REGULAR),
                ("FONTSIZE", (0, 0), (-1, -1), 9),
                ("TEXTCOLOR", (0, 0), (0, -1), colors.HexColor("#54627a")),
                ("FONTNAME", (0, 0), (0, -1), FONT_BOLD),
                ("TOPPADDING", (0, 0), (-1, -1), 2),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
            ]
        )
    )
    story.append(info_table)
    story.append(Spacer(1, 8))

    balance_rows = [
        ["Sold inițial", f"{format_minor_amount(opening_balance_minor)} {currency}"],
        ["Sold final", f"{format_minor_amount(closing_balance_minor)} {currency}"],
    ]
    balance_table = Table(balance_rows, colWidths=[32 * mm, 122 * mm])
    balance_table.setStyle(
        TableStyle(
            [
                ("FONTSIZE", (0, 0), (-1, -1), 10),
                ("FONTNAME", (0, 0), (-1, -1), FONT_BOLD),
                ("TEXTCOLOR", (0, 0), (-1, -1), colors.HexColor("#0a1226")),
                ("TOPPADDING", (0, 0), (-1, -1), 2),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
            ]
        )
    )
    story.append(balance_table)
    story.append(Spacer(1, 14))

    if not lines:
        story.append(Paragraph("Nicio tranzacție finalizată în această perioadă.", normal_style))
    else:
        header = ["Data", "Descriere", "Categorie", "Debit", "Credit", "Sold"]
        rows: list[list] = [header]
        for line in lines:
            delta = line["delta_minor"]
            debit = format_minor_amount(-delta) if delta < 0 else ""
            credit = format_minor_amount(delta) if delta > 0 else ""
            rows.append(
                [
                    Paragraph(line["created_at"].strftime("%Y-%m-%d"), cell_style),
                    Paragraph(escape(line["description"]), cell_style),
                    Paragraph(escape(line.get("category", "other")), cell_style),
                    Paragraph(debit, right_style),
                    Paragraph(credit, right_style),
                    Paragraph(format_minor_amount(line["running_balance_minor"]), right_style),
                ]
            )
        tx_table = Table(
            rows,
            colWidths=[24 * mm, 54 * mm, 22 * mm, 22 * mm, 22 * mm, 24 * mm],
            repeatRows=1,
        )
        tx_table.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#0a1226")),
                    ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                    ("FONTNAME", (0, 0), (-1, 0), FONT_BOLD),
                    ("FONTSIZE", (0, 0), (-1, 0), 8),
                    ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f5f7fb")]),
                    ("GRID", (0, 0), (-1, -1), 0.3, colors.HexColor("#d8dee8")),
                    ("TOPPADDING", (0, 0), (-1, -1), 4),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ]
            )
        )
        story.append(tx_table)

    doc.build(story, onFirstPage=_draw_footer, onLaterPages=_draw_footer)
    return buffer.getvalue()
