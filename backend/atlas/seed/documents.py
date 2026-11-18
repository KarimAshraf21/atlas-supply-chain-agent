"""Unstructured documents: news, contract text and internal reports.

Each document becomes a ``Document`` node (with full text, for GraphRAG) linked
by ``MENTIONS`` / ``EVIDENCES`` edges, and a Markdown file with front matter.
"""

from __future__ import annotations

import random
from datetime import date, timedelta
from typing import TYPE_CHECKING, Any

from .events import RISK_EVENTS

if TYPE_CHECKING:
    from .generator import GraphData

OUTLETS = ["Maritime Ledger", "Gulf Trade Wire", "Asia Supply Monitor", "Nile Business Daily", "Energy Storage Brief"]
OUTLETS_AR = ["الوسيط البحري", "نشرة تجارة الخليج", "النيل للأعمال"]


def _add(
    g: GraphData,
    doc_id: str,
    *,
    title: str,
    kind: str,
    language: str,
    published: date,
    source: str,
    text: str,
    mentions: list[str],
    folder: str,
    evidences: str | None = None,
) -> None:
    path = f"documents/{folder}/{doc_id.lower()}.md"
    g.node(
        "Document",
        doc_id,
        title=title,
        kind=kind,
        language=language,
        published_date=published.isoformat(),
        source=source,
        path=path,
        text=text,
    )
    for target in dict.fromkeys(mentions):
        if target in g.nodes:
            g.edge("MENTIONS", doc_id, target)
    if evidences:
        g.edge("EVIDENCES", doc_id, evidences)
    front: dict[str, Any] = {
        "id": doc_id,
        "title": title,
        "kind": kind,
        "language": language,
        "published": published.isoformat(),
        "source": source,
        "mentions": [m for m in mentions if m in g.nodes],
    }
    g.documents.append({"path": path, "front_matter": front, "body": text})


def _news(g: GraphData, rng: random.Random, as_of: date) -> None:
    for i, ev in enumerate(RISK_EVENTS, start=1):
        published = min(as_of - timedelta(days=1), as_of + timedelta(days=ev.start_offset))
        if ev.status == "forecast":
            published = as_of - timedelta(days=rng.randint(1, 4))
        where = ", ".join(g.nodes[t]["props"].get("name", t) for t, *_ in ev.affects if t in g.nodes)
        paragraphs = [
            ev.summary,
            ev.detail,
            f"Affected: {where}." if where else "",
            (
                "Supply-chain analysts advise manufacturers with exposure to review safety stock, qualify "
                "alternative sources and check force-majeure provisions in customer contracts."
                if ev.status != "resolved"
                else "Operations have since returned to normal, though some backlogs remain."
            ),
        ]
        text = "\n\n".join(p for p in paragraphs if p)
        _add(
            g,
            f"DOC-NEWS-{i:02d}",
            title=ev.title,
            kind="news",
            language="en",
            published=published,
            source=OUTLETS[i % len(OUTLETS)],
            text=text,
            mentions=[ev.id, *ev.mentions],
            folder="news",
        )
        if ev.arabic_article:
            _add(
                g,
                f"DOC-NEWS-{i:02d}-AR",
                title=ev.title_ar,
                kind="news",
                language="ar",
                published=published,
                source=OUTLETS_AR[i % len(OUTLETS_AR)],
                text=ev.arabic_article,
                mentions=[ev.id, *ev.mentions],
                folder="news",
            )


def _contract_text(g: GraphData, cid: str) -> tuple[str, list[str], str]:
    c = g.nodes[cid]["props"]
    parties = [e["source"] for e in g.edges if e["type"] == "PARTY_TO" and e["target"] == cid]
    counterparty = next(p for p in parties if p != "ORG-NILEWAVE")
    cp_name = g.nodes[counterparty]["props"]["name"]
    covered = [e["target"] for e in g.edges if e["type"] == "COVERS" and e["source"] == cid]
    covered_names = "; ".join(g.nodes[x]["props"]["name"] for x in covered) or "as specified in purchase orders"
    buyer, seller = ("Nilewave Energy", cp_name) if c["kind"] == "supply" else (cp_name, "Nilewave Energy")

    fm = (
        "Neither party shall be liable for delay or failure to perform caused by events beyond its reasonable "
        "control, including war, armed conflict, acts of terrorism, blockade, closure of international shipping "
        "routes, epidemic, natural disaster or governmental action, provided that the affected party notifies the "
        "other within five (5) business days and uses commercially reasonable efforts to mitigate."
        if c.get("force_majeure")
        else "The parties expressly agree that this Agreement contains no force-majeure relief for delays arising "
        "from logistics or shipping-route disruptions. The Seller bears all transport risk until delivery and "
        "remains liable for liquidated damages irrespective of the cause of delay."
    )
    exclusivity = (
        f"\n\n## 4. Exclusivity\n{seller} is the exclusive source for the Products during the Term. The Buyer may "
        "only qualify alternative sources after a documented supply failure exceeding thirty (30) days."
        if c.get("exclusivity")
        else ""
    )
    text = f"""# {c["title"]}

**Contract ID:** {cid}
**Buyer:** {buyer}
**Seller:** {seller}
**Term:** {c.get("start_date")} to {c.get("end_date")}
**Estimated value:** USD {c.get("value_usd", 0):,.0f}

## 1. Scope
The Seller shall supply the following: {covered_names}.

## 2. Delivery
Deliveries are made DAP at the Buyer's nominated site. Lead times are confirmed per purchase order; the Seller
shall notify the Buyer of any expected delay of more than three (3) days.

## 3. Liquidated damages
For each day of late delivery the Seller shall pay liquidated damages of USD {c.get("penalty_per_day_usd", 0):,.0f},
capped at ten percent (10%) of the annual contract value.{exclusivity}

## 5. Force majeure
{fm}

## 6. Minimum volumes
{("The Buyer commits to a minimum of " + format(c["min_volume_units"], ",") + " units per year.") if c.get("min_volume_units") else "No minimum volume commitment applies."}

## 7. Governing law
This Agreement is governed by the laws of England and Wales. Disputes are settled by arbitration in London (LCIA).
"""
    return text, [counterparty, *covered], cp_name


def _contracts(g: GraphData, as_of: date) -> None:
    contracts = [nid for nid, n in g.nodes.items() if n["label"] == "Contract" and n["props"]["kind"] != "logistics"]
    for cid in contracts:
        text, mentions, _ = _contract_text(g, cid)
        c = g.nodes[cid]["props"]
        start = date.fromisoformat(c["start_date"]) if c.get("start_date") else as_of
        _add(
            g,
            f"DOC-{cid}",
            title=c["title"],
            kind="contract",
            language="en",
            published=start,
            source="Nilewave Legal",
            text=text,
            mentions=mentions,
            folder="contracts",
            evidences=cid,
        )


REPORTS = [
    (
        "DOC-RPT-Q3RISK",
        "Q3 2026 Supplier Risk Review",
        "report",
        40,
        """# Q3 2026 Supplier Risk Review — Procurement Council

## Headline
Our exposure is concentrated in three places: **SiC power modules** (single source: FormoSiC Semiconductor,
Kaohsiung), **LFP cells** (70% Zhengyuan Cell Technology, Ningbo) and **DSP chips** (single source: Tamsui
Microelectronics). All three ship through the Taiwan Strait, the Strait of Malacca and Bab el-Mandeb.

## Watch list
- **Daegu Copper Foil** (tier 2, Korea) — financial health downgraded to *distressed*. Supplies copper foil to
  both of our cell suppliers. No second plant.
- **Shenghua Magnetics** — quality audit findings on inductor windings; Anatolia Elektronik is qualified for up to
  60% of volume with a 45-day ramp.
- **Hanseong Energy Solution** is qualified for up to 50% of LFP cell volume (60-day ramp) but not yet contracted.

## Recommendations
1. Raise SiC module safety stock at 10th of Ramadan from 16 to 45 days.
2. Start a second-source qualification for SiC modules (target: European or Japanese supplier).
3. Pre-negotiate Cape of Good Hope contingency capacity with Cape Express Shipping.
""",
        [
            "SUP-FORMOSIC",
            "SUP-ZHENGYUAN",
            "SUP-TAMSUI",
            "SUP-DAEGU",
            "SUP-SHENGHUA",
            "SUP-ANATOLIA",
            "SUP-HANSEONG",
            "CMP-SICMOS",
            "CMP-LFPCELL",
            "CMP-DSP",
            "TAIWAN_STRAIT",
            "MALACCA",
            "BAB_EL_MANDEB",
            "LP-CAPEEX",
        ],
    ),
    (
        "DOC-EML-DAEGU",
        "RE: Daegu foil — contingency plan?",
        "email",
        3,
        """From: Head of Procurement
To: COO; Battery Operations Director
Subject: RE: Daegu foil — contingency plan?

Both Zhengyuan and Mekong confirmed they buy 6 µm foil from Daegu. Zhengyuan says it holds about five weeks of
foil; Mekong is lower after the ransomware incident. If Daegu stops shipping, cell output would start dropping in
roughly a month. Hanseong in Ulsan uses its own foil supply — worth accelerating their qualification.

Can we discuss at Thursday's S&OP?
""",
        ["SUP-DAEGU", "SUP-ZHENGYUAN", "SUP-MEKONG", "SUP-HANSEONG", "MAT-CUFOIL", "RE-DAEGU"],
    ),
    (
        "DOC-RPT-LOGWK46",
        "Logistics Weekly — Week 46: Red Sea diversion costs",
        "report",
        2,
        """# Logistics Weekly — Week 46

- 31 inbound containers to **Ain Sokhna** were rerouted via the **Cape of Good Hope** and discharged at
  **Port Said East**, then trucked to the Sokhna Gigafactory (+2 days road).
- Average added transit on Asia lanes: **+14 days**; average added cost per TEU: **+38%**.
- Outbound grid-storage containers to **Jebel Ali** and **Dammam** also transit Bab el-Mandeb and are delayed.
- Suez convoys add ~3 days on Europe–Sokhna flows.

Action: confirm with Sales which strategic customer orders carry liquidated damages without force-majeure relief.
""",
        ["EGSOK", "CAPE", "EGPSD", "FAC-SOKHNA", "AEJEA", "SADMM", "BAB_EL_MANDEB", "SUEZ", "RE-REDSEA", "RE-SUEZ"],
    ),
]


def build_documents(g: GraphData, rng: random.Random, as_of: date) -> None:
    _news(g, rng, as_of)
    _contracts(g, as_of)
    for doc_id, title, kind, days_ago, text, mentions in REPORTS:
        _add(
            g,
            doc_id,
            title=title,
            kind=kind,
            language="en",
            published=as_of - timedelta(days=days_ago),
            source="Nilewave internal",
            text=text,
            mentions=mentions,
            folder="reports",
        )
