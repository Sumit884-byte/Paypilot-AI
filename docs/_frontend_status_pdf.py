"""One-off generator for the Paypilot frontend status PDF."""

from reportlab.lib.colors import Color, HexColor, white
from reportlab.lib.enums import TA_LEFT, TA_RIGHT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (
    BaseDocTemplate,
    Frame,
    NextPageTemplate,
    PageBreak,
    PageTemplate,
    Paragraph,
    Spacer,
    Table,
    TableStyle,
    KeepTogether,
    ListFlowable,
    ListItem,
    HRFlowable,
)

pdfmetrics.registerFont(TTFont("Arial", "/System/Library/Fonts/Supplemental/Arial.ttf"))
pdfmetrics.registerFont(TTFont("Arial-Bold", "/System/Library/Fonts/Supplemental/Arial Bold.ttf"))
pdfmetrics.registerFont(TTFont("Georgia", "/System/Library/Fonts/Supplemental/Georgia.ttf"))
pdfmetrics.registerFont(TTFont("Georgia-Bold", "/System/Library/Fonts/Supplemental/Georgia Bold.ttf"))

NAVY = HexColor("#0B1220")
NAVY_2 = HexColor("#132033")
BLUE = HexColor("#0070BA")
BLUE_SOFT = HexColor("#E8F3FA")
GOLD = HexColor("#8A5A12")
GOLD_SOFT = HexColor("#FBF3E4")
INK = HexColor("#1E293B")
MUTED = HexColor("#475569")
LINE = HexColor("#E2E8F0")
ROW = HexColor("#F8FAFC")
GREEN = HexColor("#047857")
GREEN_SOFT = HexColor("#ECFDF5")
AMBER = HexColor("#B45309")
AMBER_SOFT = HexColor("#FFF7ED")
ROSE = HexColor("#BE123C")
ROSE_SOFT = HexColor("#FFF1F2")

PAGE_W, PAGE_H = A4
LEFT = 16 * mm
RIGHT = 16 * mm
TOP = 18 * mm
BOTTOM = 16 * mm
CONTENT_W = PAGE_W - LEFT - RIGHT

OUT = "/Users/sumitmishra/dev/Paypilot-AI/docs/Paypilot_Frontend.pdf"


def S(name, **kw):
    base = dict(
        fontName="Arial",
        fontSize=10,
        leading=14,
        textColor=INK,
        alignment=TA_LEFT,
    )
    base.update(kw)
    return ParagraphStyle(name, **base)


styles = {
    "cover_kicker": S("cover_kicker", fontName="Arial-Bold", fontSize=9, leading=12, textColor=HexColor("#7DD3FC")),
    "cover_title": S("cover_title", fontName="Georgia-Bold", fontSize=34, leading=38, textColor=white),
    "cover_sub": S("cover_sub", fontName="Georgia", fontSize=14, leading=20, textColor=HexColor("#D6E4F0")),
    "cover_meta": S("cover_meta", fontName="Arial", fontSize=9.5, leading=14, textColor=HexColor("#CBD5E1")),
    "h1": S("h1", fontName="Georgia-Bold", fontSize=18, leading=22, textColor=NAVY, spaceBefore=2, spaceAfter=6),
    "h2": S("h2", fontName="Arial-Bold", fontSize=12, leading=16, textColor=BLUE, spaceBefore=10, spaceAfter=4),
    "body": S("body", fontSize=9.5, leading=13.4, textColor=INK, spaceAfter=6),
    "small": S("small", fontSize=8.5, leading=11.5, textColor=MUTED, spaceAfter=4),
    "th": S("th", fontName="Arial-Bold", fontSize=8, leading=10.5, textColor=white),
    "td": S("td", fontName="Arial", fontSize=8, leading=10.6, textColor=INK),
    "tdm": S("tdm", fontName="Arial", fontSize=8, leading=10.6, textColor=MUTED),
    "badge": S("badge", fontName="Arial-Bold", fontSize=7.5, leading=9, textColor=GREEN),
    "footer": S("footer", fontName="Arial", fontSize=8, leading=10, textColor=HexColor("#94A3B8")),
    "caption": S("caption", fontName="Arial", fontSize=8, leading=11, textColor=MUTED, spaceBefore=2, spaceAfter=8),
}


def P(text, style="body"):
    return Paragraph(text, styles[style])


def badge(label, kind):
    colors = {
        "built": (GREEN, GREEN_SOFT),
        "partial": (AMBER, AMBER_SOFT),
        "planned": (BLUE, BLUE_SOFT),
        "later": (ROSE, ROSE_SOFT),
    }
    fg, bg = colors[kind]
    st = ParagraphStyle(
        f"b_{kind}_{label}",
        fontName="Arial-Bold",
        fontSize=7.5,
        leading=9,
        textColor=fg,
        alignment=1,
    )
    inner = Paragraph(label, st)
    t = Table([[inner]], colWidths=[58])
    t.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), bg),
                ("ALIGN", (0, 0), (-1, -1), "CENTER"),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("LEFTPADDING", (0, 0), (-1, -1), 4),
                ("RIGHTPADDING", (0, 0), (-1, -1), 4),
                ("TOPPADDING", (0, 0), (-1, -1), 3),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
                ("ROUNDEDCORNERS", [4, 4, 4, 4]),
            ]
        )
    )
    return t


def section_rule():
    return HRFlowable(width="100%", thickness=0.6, color=LINE, spaceBefore=2, spaceAfter=8)


def make_table(headers, rows, col_widths, status_col=None):
    head = [Paragraph(h, styles["th"]) for h in headers]
    data = [head]
    for row in rows:
        data.append([Paragraph(str(cell), styles["td"]) for cell in row])
    table = Table(data, colWidths=col_widths, repeatRows=1)
    commands = [
        ("BACKGROUND", (0, 0), (-1, 0), NAVY),
        ("TEXTCOLOR", (0, 0), (-1, 0), white),
        ("FONTNAME", (0, 0), (-1, 0), "Arial-Bold"),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
        ("RIGHTPADDING", (0, 0), (-1, -1), 6),
        ("TOPPADDING", (0, 0), (-1, 0), 6),
        ("BOTTOMPADDING", (0, 0), (-1, 0), 6),
        ("TOPPADDING", (0, 1), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 1), (-1, -1), 5),
        ("LINEBELOW", (0, 0), (-1, 0), 0, NAVY),
        ("LINEBELOW", (0, 1), (-1, -2), 0.3, LINE),
        ("LINEBELOW", (0, -1), (-1, -1), 0.6, LINE),
    ]
    for i in range(1, len(data)):
        if i % 2 == 0:
            commands.append(("BACKGROUND", (0, i), (-1, i), ROW))
        else:
            commands.append(("BACKGROUND", (0, i), (-1, i), white))
    table.setStyle(TableStyle(commands))
    return table


def status_table(headers, rows, col_widths):
    """Last column is a status key: built | partial | planned | later."""
    labels = {
        "built": "Built",
        "partial": "Partial",
        "planned": "Planned",
        "later": "If ahead",
    }
    head = [Paragraph(h, styles["th"]) for h in headers]
    data = [head]
    for row in rows:
        cells = [Paragraph(str(c), styles["td"]) for c in row[:-1]]
        cells.append(badge(labels[row[-1]], row[-1]))
        data.append(cells)
    table = Table(data, colWidths=col_widths, repeatRows=1)
    commands = [
        ("BACKGROUND", (0, 0), (-1, 0), NAVY),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
        ("RIGHTPADDING", (0, 0), (-1, -1), 6),
        ("TOPPADDING", (0, 0), (-1, 0), 6),
        ("BOTTOMPADDING", (0, 0), (-1, 0), 6),
        ("TOPPADDING", (0, 1), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 1), (-1, -1), 5),
        ("LINEBELOW", (0, 1), (-1, -2), 0.3, LINE),
        ("ALIGN", (-1, 1), (-1, -1), "CENTER"),
    ]
    for i in range(1, len(data)):
        commands.append(("BACKGROUND", (0, i), (-2, i), ROW if i % 2 == 0 else white))
    table.setStyle(TableStyle(commands))
    return table


def bullets(items):
    flow = []
    for item in items:
        flow.append(Paragraph("•  " + item, styles["body"]))
    return flow


def header_footer(canvas, doc):
    canvas.saveState()
    canvas.setFillColor(NAVY)
    canvas.rect(0, PAGE_H - 11 * mm, PAGE_W, 11 * mm, fill=1, stroke=0)
    canvas.setFillColor(BLUE)
    canvas.rect(0, PAGE_H - 11.8 * mm, PAGE_W, 0.8 * mm, fill=1, stroke=0)
    canvas.setFillColor(white)
    canvas.setFont("Arial-Bold", 8)
    canvas.drawString(LEFT, PAGE_H - 7.2 * mm, "PAYPILOT AI")
    canvas.setFont("Arial", 8)
    canvas.setFillColor(HexColor("#CBD5E1"))
    canvas.drawRightString(PAGE_W - RIGHT, PAGE_H - 7.2 * mm, "Frontend  ·  what exists and what is planned")

    canvas.setFillColor(HexColor("#F8FAFC"))
    canvas.rect(0, 0, PAGE_W, 11 * mm, fill=1, stroke=0)
    canvas.setStrokeColor(LINE)
    canvas.setLineWidth(0.4)
    canvas.line(LEFT, 11 * mm, PAGE_W - RIGHT, 11 * mm)
    canvas.setFillColor(MUTED)
    canvas.setFont("Arial", 8)
    canvas.drawString(LEFT, 4.6 * mm, "PayPal AI Hackathon  ·  status 26 October 2026")
    canvas.drawRightString(PAGE_W - RIGHT, 4.6 * mm, f"{doc.page}")
    canvas.restoreState()


def cover_page(canvas, doc):
    canvas.saveState()
    canvas.setFillColor(NAVY)
    canvas.rect(0, 0, PAGE_W, PAGE_H, fill=1, stroke=0)
    canvas.setFillColor(BLUE)
    canvas.rect(0, PAGE_H - 8 * mm, PAGE_W, 8 * mm, fill=1, stroke=0)
    canvas.setFillColor(HexColor("#F5B942"))
    canvas.rect(0, 0, 5 * mm, PAGE_H, fill=1, stroke=0)

    canvas.setFillColor(HexColor("#132033"))
    canvas.circle(PAGE_W - 18 * mm, PAGE_H - 48 * mm, 70 * mm, fill=1, stroke=0)
    canvas.setFillColor(HexColor("#0E1A2C"))
    canvas.circle(PAGE_W + 10 * mm, 40 * mm, 55 * mm, fill=1, stroke=0)

    canvas.setFillColor(HexColor("#7DD3FC"))
    canvas.setFont("Arial-Bold", 9)
    canvas.drawString(LEFT + 6 * mm, PAGE_H - 42 * mm, "PAYPAL AI HACKATHON")

    canvas.setFillColor(white)
    canvas.setFont("Georgia-Bold", 36)
    y = PAGE_H - 62 * mm
    for line in ["The frontend,", "as it stands"]:
        canvas.drawString(LEFT + 6 * mm, y, line)
        y -= 13 * mm

    canvas.setFillColor(HexColor("#D6E4F0"))
    canvas.setFont("Georgia", 13)
    canvas.drawString(LEFT + 6 * mm, y - 4 * mm, "What is built in the React app, and what")
    canvas.drawString(LEFT + 6 * mm, y - 11 * mm, "Person 3 still has to ship before 11 November.")

    # Fact strip
    facts = [
        ("Owner", "Person 3"),
        ("Stack", "React 18 + Vite"),
        ("Screens", "7 app screens"),
        ("Submit", "11 Nov 2026"),
    ]
    box_y = 48 * mm
    box_h = 28 * mm
    gap = 3 * mm
    box_w = (CONTENT_W - 6 * mm - 3 * gap) / 4
    x = LEFT + 6 * mm
    for title, value in facts:
        canvas.setFillColor(HexColor("#132033"))
        canvas.roundRect(x, box_y, box_w, box_h, 4, fill=1, stroke=0)
        canvas.setFillColor(HexColor("#7DD3FC"))
        canvas.setFont("Arial-Bold", 7.5)
        canvas.drawString(x + 4 * mm, box_y + box_h - 8 * mm, title.upper())
        canvas.setFillColor(white)
        canvas.setFont("Arial", 8)
        canvas.drawString(x + 4 * mm, box_y + 8 * mm, value)
        x += box_w + gap

    canvas.setFillColor(HexColor("#94A3B8"))
    canvas.setFont("Arial", 8)
    canvas.drawString(LEFT + 6 * mm, 28 * mm, "Source: frontend/ source, docs/, and the PayScore team work split.")
    canvas.drawString(LEFT + 6 * mm, 22 * mm, "Amounts in the product are INR. This note uses Rs so the type stays clear.")
    canvas.restoreState()


def build():
    doc = BaseDocTemplate(
        OUT,
        pagesize=A4,
        title="Paypilot AI — Frontend status",
        author="Paypilot AI",
        subject="What exists in the frontend and what is planned through 11 November 2026",
    )
    cover_frame = Frame(0, 0, PAGE_W, PAGE_H, id="cover", showBoundary=0)
    body_frame = Frame(
        LEFT,
        BOTTOM,
        CONTENT_W,
        PAGE_H - TOP - BOTTOM,
        id="body",
        showBoundary=0,
    )
    doc.addPageTemplates(
        [
            PageTemplate(id="cover", frames=[cover_frame], onPage=cover_page),
            PageTemplate(id="body", frames=[body_frame], onPage=header_footer),
        ]
    )

    story = []
    story.append(NextPageTemplate("body"))
    story.append(PageBreak())

    story.append(P("1.  At a glance", "h1"))
    story.append(section_rule())
    story.append(
        P(
            "The frontend is a React application in <font face='Arial-Bold'>frontend/</font>. "
            "It is the credit-copilot interface for the PayPal AI hackathon: a seller links a "
            "PayPal sandbox account, or tours the product on synthetic data, then walks income, "
            "an explainable PayScore, an offer check, a chat copilot, repayment, and a widget cockpit."
        )
    )
    story.append(
        P(
            "Person 3 (India, PayPal access) owns the agent and every UI screen. The team split "
            "keeps the Pakistan-based teammate on Python and mock data. Final testing, the demo "
            "video, and submission are led by Person 4, with Persons 2 and 3 fixing what breaks. "
            "The aim is to submit on <font face='Arial-Bold'>11 November 2026</font>, one day before "
            "the 12 November, 12:00 pm PT deadline."
        )
    )

    story.append(P("Where the work sits today", "h2"))
    story.append(
        status_table(
            ["Area", "What you can open now", "Status"],
            [
                ["Landing and sign-in", "PayPal login, or a demo tour when the sandbox is not configured", "built"],
                ["App shell", "Sidebar, mobile drawer, light and dark theme, live score in the top bar", "built"],
                ["Income", "12-month profile, area chart, payment rhythm, AG Grid transaction feed", "built"],
                ["PayScore", "300–850 gauge, risk band, SHAP factors, eligible changes, disbursement limit", "built"],
                ["Offer guard", "Manual terms or a PDF upload, cost comparison, KFS checklist, directory result", "built"],
                ["AI copilot", "Chat against the Python agent, with an approval card before a sandbox payout", "partial"],
                ["Repayment", "Fixed EMI, revenue share, and a one-off PayPal checkout", "built"],
                ["AG Studio cockpit", "Local widget board. Not a custom AG Studio agent", "partial"],
                ["PayPal MCP copilot", "Planned for week 2. The chat does not call the MCP server", "planned"],
                ["Bryntum calendar", "Only if the team is ahead in week 3. No calendar dependency is installed", "later"],
            ],
            [118, CONTENT_W - 118 - 70, 70],
        )
    )
    story.append(P("Built means the screen calls a real API. Partial means the screen is usable, and the planned version is still ahead.", "caption"))

    story.append(P("2.  How the frontend is built", "h1"))
    story.append(section_rule())
    story.append(
        P(
            "Run it with <font face='Arial-Bold'>npm install</font> and <font face='Arial-Bold'>npm run dev</font> "
            "inside <font face='Arial-Bold'>frontend/</font>. Vite serves <font face='Arial-Bold'>http://localhost:5173</font> "
            "and proxies API calls to the FastAPI app on port 8000. Set "
            "<font face='Arial-Bold'>PAYSCORE_FRONTEND_URL=http://localhost:5173</font> on the API so PayPal "
            "OAuth returns to <font face='Arial-Bold'>/auth/callback</font>. Leave "
            "<font face='Arial-Bold'>VITE_PAYSCORE_API_URL</font> empty in local development so requests stay same-origin. "
            "Set it only when the UI is hosted apart from the API."
        )
    )

    story.append(
        make_table(
            ["Piece", "Choice in package.json"],
            [
                ["UI", "React 18 and TypeScript"],
                ["Build", "Vite 8, route-level code splitting. Lint with oxlint. Production build is tsc -b and vite build."],
                ["Routing", "React Router 7"],
                ["Styling", "Tailwind CSS 3, Plus Jakarta Sans, PayPal blue #0070BA and gold #F5B942"],
                ["Motion", "Framer Motion. Reduced motion follows the system setting"],
                ["Charts", "Recharts area chart on the income page"],
                ["Grid", "AG Grid Community 32, themed for the income transaction feed"],
            ],
            [110, CONTENT_W - 110],
        )
    )
    story.append(Spacer(1, 8))

    story.append(P("Routes", "h2"))
    story.append(
        P(
            "Every authenticated screen sits under <font face='Arial-Bold'>/app</font> inside "
            "<font face='Arial-Bold'>AppShell</font>. A missing session sends the visitor back to the landing page. "
            "Unknown paths inside the app return to the overview."
        )
    )
    story.append(
        make_table(
            ["Path", "Screen", "File"],
            [
                ["/", "Landing", "pages/Landing.tsx"],
                ["/auth/callback", "PayPal return", "pages/AuthCallback.tsx"],
                ["/app", "Overview", "pages/Overview.tsx"],
                ["/app/income", "Income profile", "pages/Income.tsx"],
                ["/app/score", "PayScore", "pages/Score.tsx"],
                ["/app/offer-guard", "Offer guard", "pages/OfferGuard.tsx"],
                ["/app/copilot", "AI copilot", "pages/Copilot.tsx"],
                ["/app/repay", "Repayment", "pages/Repayment.tsx"],
                ["/app/cockpit", "AG Studio cockpit", "pages/Cockpit.tsx"],
            ],
            [120, 150, CONTENT_W - 270],
        )
    )
    story.append(
        P(
            "pages/Placeholder.tsx is an unused skeleton that says a screen will be wired later. No route renders it.",
            "caption",
        )
    )

    story.append(P("Shell and session", "h2"))
    story.append(
        P(
            "The shell is a 256px sidebar on large screens and a slide-in drawer on small screens. "
            "The top bar shows the wordmark, a live PayScore pill, a demo or PayPal-linked chip, the theme toggle, and sign out. "
            "The live pill polls <font face='Arial-Bold'>GET /score/live</font> every 8 seconds for applicant "
            "<font face='Arial-Bold'>PSC-PRIYA-001</font> and pulses when the number changes."
        )
    )
    story.append(
        P(
            "The session lives in <font face='Arial-Bold'>sessionStorage</font> under "
            "<font face='Arial-Bold'>paypilot.session</font>. "
            "<font face='Arial-Bold'>Log in with PayPal</font> checks <font face='Arial-Bold'>GET /paypal/status</font> "
            "and, when the sandbox is configured, sends the browser to <font face='Arial-Bold'>GET /paypal/auth/login</font>. "
            "A successful return with <font face='Arial-Bold'>linked=true</font> opens the app as a linked session. "
            "An error on the callback offers a return to the landing page or a continue on demo data. "
            "<font face='Arial-Bold'>Tour the cockpit</font> opens the same app with "
            "<font face='Arial-Bold'>demo: true</font> and persona <font face='Arial-Bold'>priya</font>, "
            "without a PayPal account. Sign out clears the session."
        )
    )

    story.append(P("3.  What each screen does", "h1"))
    story.append(section_rule())

    story.append(P("Landing", "h2"))
    story.append(
        P(
            "A full-viewport page with an ambient background, the sandbox badge, and a light/dark toggle. "
            "The headline is the product claim: banks reject freelancers who have no credit score, and PayPal history "
            "can stand in for one. Three steps describe linking a sandbox account, reading 12 months of cashflow, "
            "and seeing a 300–850 score that is labelled as a demo, not a bank decision. Floating cards sit beside the copy. "
            "If sandbox credentials are missing, the PayPal button stays on the page and a notice points people to the tour."
        )
    )

    story.append(P("Overview", "h2"))
    story.append(
        P(
            "Loads <font face='Arial-Bold'>GET /income-profile</font> and "
            "<font face='Arial-Bold'>GET /demo/persona/{name}</font>. The session persona is always Priya today. "
            "Four metric cards show 12-month income, distinct clients, refund rate, and the longest payment gap. "
            "A workspace panel links to income, PayScore, and offer guard. A second card is the 3-minute demo path: "
            "income, score, offer guard, copilot, and repayment. Visited steps are stored in "
            "<font face='Arial-Bold'>paypilot.demo_progress</font>. A demo session shows a notice that the data is synthetic "
            "and that no real credit decision or money movement happens here."
        )
    )

    story.append(P("Income", "h2"))
    story.append(
        P(
            "The profile comes from <font face='Arial-Bold'>GET /income-profile?persona=priya</font>. "
            "When the API source is <font face='Arial-Bold'>paypal</font>, the page says the linked profile is aggregates only. "
            "The transaction grid does not come from that endpoint. It comes from the synthetic persona fixture "
            "<font face='Arial-Bold'>GET /demo/persona/priya</font>, field <font face='Arial-Bold'>recent_transactions</font>."
        )
    )
    story += bullets(
        [
            "Count-up cards for 12-month income, client count, refund rate, and dispute rate.",
            "A Recharts area chart of monthly_income_12m, drawn over about 1.2 seconds.",
            "Payment rhythm: monthly direction, longest income gap, and active buyer count.",
            "An AG Grid with sortable, filterable columns for date, type, amount, category, and status, plus custom cell renderers and a PayPal-blue header theme.",
        ]
    )

    story.append(P("PayScore", "h2"))
    story.append(
        P(
            "<font face='Arial-Bold'>Run PayScore</font> posts the Priya <font face='Arial-Bold'>model_input</font> "
            "to <font face='Arial-Bold'>POST /score</font> and stores the response in "
            "<font face='Arial-Bold'>paypilot.score</font>. The gauge is a ring from 300 to 850 with a needle sweep. "
            "The risk band is coloured green, amber, orange, or rose for low, moderate, elevated, and high."
        )
    )
    story += bullets(
        [
            "When explanation.status is available, the factor cards are TreeSHAP log-odds: factors that lower estimated risk and factors that raise it. The copy says these are attributions, not causes.",
            "A “to move up” line comes back on the score. See eligible changes calls POST /counterfactuals and lists each suggestion with an estimated score and the score difference.",
            "A disbursement card shows eligible or not eligible, and the approved limit in INR when the score clears the server threshold.",
            "The page is locked to the Priya fixture. There is no control to score Arjun or Rohan.",
        ]
    )

    story.append(P("Offer guard", "h2"))
    story.append(
        P(
            "The form accepts a lender name, advertised APR (0–100), processing fee (0–50), principal (1 to 1,000,000,000 INR), "
            "and term (1–360 months). Leaving the file input empty posts those fields to "
            "<font face='Arial-Bold'>POST /offer-guard</font>. Choosing a PDF posts it to "
            "<font face='Arial-Bold'>POST /offer-guard/upload</font> and ignores the manual numbers. "
            "Anything that is not a PDF is rejected in the browser. The result is saved as "
            "<font face='Arial-Bold'>paypilot.offer</font> so the cockpit can read it."
        )
    )
    story += bullets(
        [
            "The result shows advertised APR against the estimated real annualised cost, and highlights a red flag when the server sets red_flag.",
            "A KFS checklist renders item by item. A directory line shows the RBI match status. The page states that a miss is not a confirmed violation, and that the check stays unverified until a retrieved list is loaded.",
            "Extraction notes can include OCR status and LLM status. Both are optional on the server and off in a normal install.",
        ]
    )

    story.append(P("AI copilot", "h2"))
    story.append(
        P(
            "The chat posts to <font face='Arial-Bold'>POST /copilot/chat</font> with applicant "
            "<font face='Arial-Bold'>PSC-PRIYA-001</font>. On first open it waits about 0.8 seconds and sends "
            "“Can I afford Rs 50k?”. Suggested questions cover income trend, PayScore comparison, a loan offer, and EMI. "
            "Command-K or Control-K focuses the input. Replies show the tool name as a chip and, when the server returns one, the analysis kind and status."
        )
    )
    story.append(
        P(
            "If the server sets <font face='Arial-Bold'>approval.required</font>, an approval card appears with the action, "
            "the amount, and Approve / Decline. Decline adds a local message and calls nothing. Approve reads the stored score, "
            "refuses to continue if PayScore has not been run, then calls <font face='Arial-Bold'>POST /disburse</font> "
            "for priya@example.test and saves <font face='Arial-Bold'>paypilot.payout_batch_id</font>. "
            "A link then points at the repayment page to track that batch."
        )
    )
    story.append(
        P(
            "This copilot is the Python agent in payscore/copilot_agent.py. It is not yet wired to the PayPal MCP server. "
            "That wiring is the remaining week-2 item for Person 3.",
            "small",
        )
    )

    story.append(P("Repayment", "h2"))
    story.append(
        P(
            "Three modes share one page. The ledger polls <font face='Arial-Bold'>GET /repayment/status</font> every 15 seconds. "
            "A payout batch id, from the copilot or typed in, polls <font face='Arial-Bold'>GET /disburse/{batch_id}</font> "
            "every 5 seconds and plays a success animation when the batch reaches SUCCESS or COMPLETED. "
            "The page also polls the live score and shows a pulse when it changes."
        )
    )
    story.append(
        make_table(
            ["Mode", "What the screen sends", "What comes back on screen"],
            [
                [
                    "Fixed EMI",
                    "POST /repayment/subscription with the INR amount and the number of instalments",
                    "A schedule of due dates, INR amounts, and the PayPal USD amount",
                ],
                [
                    "Revenue share",
                    "POST /repayment/revenue-share. The fields show 5% and DEMO-PRIYA, and the click handler always sends those two values.",
                    "Whatever schedule the server returns. Typing a different percentage does not change the request.",
                ],
                [
                    "One-off",
                    "POST /repayment/order, then the PayPal JS SDK v6 session from GET /paypal/public-config",
                    "A Pay with PayPal button. After approval the page captures with POST /repayment/order/{id}/capture and can burst confetti",
                ],
            ],
            [78, 210, CONTENT_W - 288],
        )
    )
    story.append(
        P(
            "Subscriptions and orders are presented in INR. The API converts outbound PayPal amounts to USD with a demo rate. The schedule shows both.",
            "caption",
        )
    )

    story.append(P("AG Studio cockpit", "h2"))
    story.append(
        P(
            "The sidebar label is AG Studio. The page is a local React board, not an AG Grid Studio custom agent. "
            "It opens with three widgets: Advertised vs real APR, Score drivers, and Repayment progress. "
            "APR and score widgets read session storage written by the offer and score pages. "
            "Repayment progress reads <font face='Arial-Bold'>GET /repayment/status?applicant_id=PSC-PRIYA-001</font>. "
            "The question bar appends whatever was typed as a new widget title. A few phrases get a drawing: "
            "“income by”, “apr”, “score”, “repayment”, “cashflow”, and “risk”. Other titles render as an empty card. "
            "Widgets can be removed. Nothing here is saved on the server."
        )
    )

    story.append(P("4.  Shared interface", "h1"))
    story.append(section_rule())
    story.append(
        P(
            "The look is a dark navy and charcoal base, with a light theme as well. PayPal blue is the action colour. "
            "Gold is the highlight. Risk uses green, amber, orange, and rose. Cards use a glass blur. "
            "Pages fade and slide in. Interactive cards lift on hover. The landing cards follow the pointer."
        )
    )
    story.append(
        make_table(
            ["File", "Role"],
            [
                ["components/ui/GlassCard.tsx", "Glass card used on every screen"],
                ["components/ui/Button.tsx", "Primary, ghost, and gold buttons"],
                ["components/ui/Workspace.tsx", "Page heading, metric card, count-up, progress ring, notice, field, toast, keyboard hint"],
                ["components/ui/Skeleton.tsx", "Loading placeholders, including the route suspense screen"],
                ["components/ui/ThemeToggle.tsx", "Light and dark, stored as paypilot.theme"],
                ["components/ui/SandboxBadge.tsx", "Persistent sandbox disclaimer"],
                ["components/ui/Confetti.tsx", "Burst used when a sandbox payout completes"],
                ["components/ui/SuccessAnimation.tsx", "Check mark beside a landed payout"],
                ["components/ui/AmbientBackground.tsx", "Soft colour field behind landing and the app"],
                ["components/brand/Logo.tsx", "Mark and wordmark"],
                ["components/landing/FloatingCards.tsx", "Landing illustration"],
                ["components/landing/PayPalLoginButton.tsx", "PayPal-styled login control"],
                ["lib/api.ts", "fetch wrapper, JSON and form posts, INR formatting, persona type"],
                ["lib/motion.ts", "Shared fade, stagger, and hover variants"],
                ["context/AuthContext.tsx", "Demo session and PayPal link"],
                ["context/ThemeContext.tsx", "Theme preference"],
            ],
            [230, CONTENT_W - 230],
        )
    )
    story.append(Spacer(1, 8))
    story.append(P("API surface the UI calls", "h2"))
    story.append(
        P(
            "vite.config.ts proxies these prefixes to 127.0.0.1:8000: "
            "/paypal, /demo, /health, /score, /income-profile, /disburse, /repayment, "
            "/offer-guard, /copilot, /explain, /counterfactuals, /affordability, and /revenue-volatility. "
            "The pages themselves call a subset of those."
        )
    )
    story.append(
        make_table(
            ["Called from the UI", "Used by"],
            [
                ["GET /paypal/status, GET /paypal/auth/login", "Landing login"],
                ["GET /paypal/public-config", "One-off PayPal checkout"],
                ["GET /demo/persona/priya", "Overview, income grid, score, cockpit"],
                ["GET /income-profile", "Overview and income"],
                ["POST /score, POST /counterfactuals", "PayScore"],
                ["GET /score/live", "Top bar and repayment"],
                ["POST /offer-guard, POST /offer-guard/upload", "Offer guard"],
                ["POST /copilot/chat", "Copilot"],
                ["POST /disburse, GET /disburse/{id}", "Copilot approval, repayment status"],
                ["POST /repayment/subscription, /order, /revenue-share", "Repayment setup"],
                ["POST /repayment/order/{id}/capture, GET /repayment/status", "Checkout and ledger"],
            ],
            [280, CONTENT_W - 280],
        )
    )
    story.append(
        P(
            "Proxied and not called by a screen: GET /health, POST /explain, POST /affordability, and POST /revenue-volatility. "
            "Affordability and volatility are reached only when the copilot’s Python agent calls them. "
            "There is no invoice screen, even though the API exposes outstanding invoices, an advance, and an invoice reminder.",
            "caption",
        )
    )

    story.append(P("5.  What is planned", "h1"))
    story.append(section_rule())
    story.append(
        P(
            "The plan below is the Person 3 column of the PayScore team work split "
            "(PayPal AI Hackathon, four people, submit 11 November 2026). "
            "Several week-2 screens are already in the repository. The dates are the plan, not a claim that the later weeks are unfinished in every respect."
        )
    )

    story.append(P("Week 1  ·  22–28 October  ·  setup", "h2"))
    story.append(
        P(
            "Person 3 was asked to get the AG Studio boilerplate running and to check which MCP server tools work in the sandbox. "
            "AG Grid is running on the income feed, and a cockpit page exists. A recorded check of PayPal MCP tools is not in the frontend."
        )
    )
    story.append(
        P(
            "The same week, Person 1 trains the score model and ships a stub /score endpoint, Person 2 creates the sandbox app and a FastAPI skeleton, "
            "and Person 4 writes the Priya stories plus two others and a video script. The UI already assumes Priya."
        )
    )

    story.append(P("Week 2  ·  29 October–4 November  ·  features", "h2"))
    story.append(
        P(
            "Person 3’s week-2 brief is: wire the copilot to the PayPal MCP server, keep a human approval before any money moves, "
            "and build the score and offer-guard screens."
        )
    )
    story += bullets(
        [
            "Score and offer guard are built and already call the Python API, including SHAP factors, counterfactuals, PDF upload, and the KFS checklist.",
            "Human approval before money moves is built for disbursement. The chat does not create a payout until Approve is pressed, and Approve is refused until a score exists in the browser.",
            "Still planned: connect that copilot to the PayPal MCP server. Today the chat is a single POST /copilot/chat to the local Python agent, which picks one Python function from the wording of the question.",
        ]
    )

    story.append(
        KeepTogether(
            [
                P("Week 3  ·  5–11 November  ·  polish and ship", "h2"),
                P(
                    "Person 3’s week-3 brief is AG Studio widgets and a custom agent. A Bryntum calendar is in scope only if the team is ahead. "
                    "The current cockpit is the widget half of that brief, drawn in React. The custom agent is not started, and Bryntum is not a dependency."
                ),
            ]
        )
    )
    story.append(
        P(
            "Test freeze is 9–10 November. Person 4 runs the full sandbox path: login, score, offer guard, copilot, payout, EMI, and invoice paid. "
            "Invoice paid is Person 2’s API and webhook step. There is no invoice screen. "
            "Persons 2 and 3 fix what breaks. The video is recorded and the entry is submitted on 11 November. "
            "Person 1 can review the script and the README remotely. Person 1 does not run the PayPal sandbox."
        )
    )

    story.append(P("Still open in the UI", "h2"))
    story.append(
        status_table(
            ["Item", "Why it is still open", "Status"],
            [
                [
                    "PayPal MCP copilot",
                    "Week 2 plan. The chat UI can stay; the agent behind POST /copilot/chat is not the MCP server.",
                    "planned",
                ],
                [
                    "Custom AG Studio agent",
                    "Week 3 plan. Widgets are local cards with keyword drawings, not a Studio agent that builds views from a question.",
                    "planned",
                ],
                [
                    "Bryntum calendar",
                    "Week 3, and only if the score, offer, copilot, and cockpit work is already solid.",
                    "later",
                ],
                [
                    "MCP tool check",
                    "Week 1 plan. No screen or note in the frontend records which sandbox MCP tools respond.",
                    "planned",
                ],
                [
                    "Priya only",
                    "The written demo is Priya. Arjun and Rohan exist as API fixtures. Score, copilot, repayment, and the cockpit all call PSC-PRIYA-001.",
                    "partial",
                ],
            ],
            [120, CONTENT_W - 120 - 70, 70],
        )
    )
    story.append(Spacer(1, 8))

    story.append(P("What not to treat as future UI work", "h2"))
    story.append(
        P(
            "These items sit next to the frontend and are owned elsewhere, or are already decided limits:"
        )
    )
    story += bullets(
        [
            "The score model, SHAP, counterfactuals, offer-guard maths, affordability, and the revenue-share percentage are Person 1’s Python modules. The UI displays them.",
            "Sandbox login, Transaction Search, Payouts, Subscriptions, Orders, Invoicing, and webhooks are Person 2. The UI already calls the routes those features expose.",
            "The shipped RBI directory snapshot has no lender names, so the offer screen will keep saying the directory check is unverified until a retrieved list is stored. That is a data limit, not a missing component.",
            "OCR and the external offer-term model are off unless extra software and both server flags are set. The upload control already posts the PDF.",
            "Scores, affordability, and revenue share are demo estimates. The screens already say they are not a lending decision.",
        ]
    )

    story.append(P("Suggested order from here", "h2"))
    story.append(
        P(
            "The screens a judge will click are already present. The plan’s remaining frontend work is the agent behind the chat, "
            "then a real cockpit widget, and a calendar only if that work is already solid."
        )
    )
    story.append(
        make_table(
            ["Order", "Work", "Touches"],
            [
                ["1", "Confirm which PayPal MCP tools answer in the sandbox, and point the copilot at that server while keeping the approval card.", "Copilot.tsx and the agent it calls"],
                ["2", "Turn the cockpit question into a real widget, backed by income, score, offer, or repayment data, instead of a title plus a keyword sketch.", "Cockpit.tsx"],
                ["3", "Add Bryntum only after the copilot and the cockpit are demo-stable.", "New dependency and a calendar view"],
            ],
            [48, 280, CONTENT_W - 328],
        )
    )
    story.append(
        P(
            "Sources: frontend/src, frontend/package.json, frontend/vite.config.ts, frontend/README.md, docs/IMPLEMENTATION_REPORT.md, and the PayScore team work split. Where the UI README and the source disagree, this note follows the source.",
            "caption",
        )
    )

    doc.build(story)
    print(OUT)


if __name__ == "__main__":
    build()
