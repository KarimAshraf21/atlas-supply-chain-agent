"""The Atlas supply-chain ontology (v1).

Design notes
------------
* Classes form a small hierarchy (e.g. ``Supplier ⊂ Organization``). In Neo4j a
  node carries its class label *and* every ancestor label, so queries can stay
  generic (``(:Organization)``) or be precise (``(:Supplier)``).
* Asserted relations come from source systems; ``inferred=True`` relations are
  produced only by the reasoning layer and always carry ``rule`` provenance.
* Arabic synonyms make the ontology usable by the multilingual voice agent.
"""

from __future__ import annotations

from .model import DataType as T
from .model import NodeClass, Ontology, Property, Relation

P = Property

# --------------------------------------------------------------------- enums
RISK_TYPES = [
    "geopolitical",
    "conflict",
    "weather",
    "labor_strike",
    "tariff",
    "cyber",
    "financial",
    "regulatory",
    "pandemic",
    "infrastructure",
]
IMPACT_KINDS = ["closure", "delay", "capacity_reduction", "price_increase", "insolvency"]

CLASSES: list[NodeClass] = [
    # ----------------------------------------------------------- organizations
    NodeClass(
        label="Organization",
        description="Any legal entity participating in the supply network.",
        properties=[
            P(name="name", required=True),
            P(name="country_code", description="ISO 3166-1 alpha-2 of headquarters."),
            P(name="website"),
        ],
        synonyms={"ar": ["منظمة", "شركة"]},
    ),
    NodeClass(
        label="Company",
        parent="Organization",
        description="The focal company that owns this Atlas instance.",
        properties=[P(name="industry"), P(name="annual_revenue_usd", type=T.FLOAT, unit="USD")],
        synonyms={"ar": ["الشركة", "شركتنا"]},
    ),
    NodeClass(
        label="Supplier",
        parent="Organization",
        description="Provides materials or components, directly (tier 1) or indirectly (tier 2+).",
        properties=[
            P(name="tier", type=T.INTEGER, required=True, description="1 = direct supplier."),
            P(name="category", required=True),
            P(name="esg_score", type=T.FLOAT, description="0-100, higher is better."),
            P(
                name="financial_health",
                enum=["strong", "stable", "watch", "distressed"],
                description="Credit-style health rating.",
            ),
            P(name="on_time_delivery_pct", type=T.FLOAT, unit="%"),
        ],
        synonyms={"ar": ["مورد", "موردين", "المورد"]},
    ),
    NodeClass(
        label="Customer",
        parent="Organization",
        description="Buys finished products.",
        properties=[
            P(name="segment", enum=["utility", "distributor", "installer", "oem", "retail"]),
            P(name="region", required=True),
            P(name="strategic", type=T.BOOLEAN),
        ],
        synonyms={"ar": ["عميل", "عملاء", "العميل"]},
    ),
    NodeClass(
        label="LogisticsProvider",
        parent="Organization",
        description="Carrier or freight forwarder operating shipping lanes.",
        properties=[P(name="mode", enum=["sea", "air", "rail", "road", "multimodal"])],
        synonyms={"ar": ["شركة شحن", "ناقل"]},
    ),
    # -------------------------------------------------------------- facilities
    NodeClass(
        label="Facility",
        description="A physical site.",
        properties=[
            P(name="name", required=True),
            P(name="lat", type=T.FLOAT, required=True),
            P(name="lon", type=T.FLOAT, required=True),
            P(name="city"),
        ],
        synonyms={"ar": ["منشأة", "موقع"]},
    ),
    NodeClass(
        label="Factory",
        parent="Facility",
        description="Manufactures components or products.",
        properties=[P(name="capacity_units_per_month", type=T.INTEGER)],
        synonyms={"ar": ["مصنع", "المصنع"]},
    ),
    NodeClass(
        label="Warehouse",
        parent="Facility",
        description="Stores inventory.",
        properties=[P(name="capacity_pallets", type=T.INTEGER)],
        synonyms={"ar": ["مستودع", "مخزن"]},
    ),
    # --------------------------------------------------------------- geography
    NodeClass(
        label="Country",
        description="Sovereign country; key is ISO 3166-1 alpha-2.",
        properties=[
            P(name="name", required=True),
            P(name="name_ar"),
            P(name="region", required=True),
            P(name="political_risk", type=T.FLOAT, description="0-1, higher is riskier."),
        ],
        synonyms={"ar": ["دولة", "بلد"]},
    ),
    NodeClass(
        label="Port",
        description="Sea or air port; key is UN/LOCODE.",
        properties=[
            P(name="name", required=True),
            P(name="name_ar"),
            P(name="lat", type=T.FLOAT, required=True),
            P(name="lon", type=T.FLOAT, required=True),
            P(name="kind", enum=["sea", "air"]),
            P(name="congestion_index", type=T.FLOAT, description="0-1, higher is more congested."),
        ],
        synonyms={"ar": ["ميناء", "الميناء"]},
    ),
    NodeClass(
        label="Chokepoint",
        description="Maritime passage whose disruption forces rerouting.",
        properties=[
            P(name="name", required=True),
            P(name="name_ar"),
            P(name="lat", type=T.FLOAT, required=True),
            P(name="lon", type=T.FLOAT, required=True),
            P(name="share_of_global_trade_pct", type=T.FLOAT, unit="%"),
        ],
        synonyms={"ar": ["ممر ملاحي", "مضيق", "قناة"]},
    ),
    # ----------------------------------------------------------------- items
    NodeClass(
        label="Item",
        description="Anything that can be bought, made, stocked or sold.",
        properties=[
            P(name="name", required=True),
            P(name="name_ar"),
            P(name="category", required=True),
            P(name="hs_code", description="Harmonized System tariff code."),
            P(name="unit", description="Unit of measure."),
            P(name="unit_cost_usd", type=T.FLOAT, unit="USD"),
        ],
    ),
    NodeClass(
        label="Material",
        parent="Item",
        description="Raw or processed material (e.g. lithium carbonate, copper).",
        properties=[P(name="critical", type=T.BOOLEAN, description="On a critical-minerals list.")],
        synonyms={"ar": ["مادة خام", "مواد خام"]},
    ),
    NodeClass(
        label="Component",
        parent="Item",
        description="Purchased part that goes into a product.",
        properties=[P(name="lead_time_days", type=T.INTEGER)],
        synonyms={"ar": ["مكون", "قطعة", "مكونات"]},
    ),
    NodeClass(
        label="Product",
        parent="Item",
        description="Finished good sold to customers.",
        properties=[
            P(name="sku", required=True),
            P(name="family", required=True),
            P(name="unit_price_usd", type=T.FLOAT, unit="USD"),
            P(name="gross_margin_pct", type=T.FLOAT, unit="%"),
        ],
        synonyms={"ar": ["منتج", "منتجات"]},
    ),
    # ------------------------------------------------------------- logistics
    NodeClass(
        label="ShippingLane",
        description="A recurring origin→destination route with a mode and transit time.",
        properties=[
            P(name="name", required=True),
            P(name="mode", required=True, enum=["sea", "air", "rail", "road"]),
            P(name="transit_days", type=T.INTEGER, required=True),
            P(name="cost_per_teu_usd", type=T.FLOAT, unit="USD"),
            P(name="co2_kg_per_teu", type=T.FLOAT),
            P(name="is_contingency", type=T.BOOLEAN, description="Backup route, not used by default."),
        ],
        synonyms={"ar": ["خط شحن", "مسار"]},
    ),
    # ------------------------------------------------------------- commercial
    NodeClass(
        label="Contract",
        description="Commercial agreement with a supplier, customer or carrier.",
        properties=[
            P(name="title", required=True),
            P(name="kind", required=True, enum=["supply", "sales", "logistics"]),
            P(name="start_date", type=T.DATE),
            P(name="end_date", type=T.DATE),
            P(name="value_usd", type=T.FLOAT, unit="USD"),
            P(name="penalty_per_day_usd", type=T.FLOAT, unit="USD"),
            P(name="force_majeure", type=T.BOOLEAN),
            P(name="exclusivity", type=T.BOOLEAN),
            P(name="min_volume_units", type=T.INTEGER),
        ],
        synonyms={"ar": ["عقد", "عقود", "اتفاقية"]},
    ),
    NodeClass(
        label="SalesOrder",
        description="Customer order for a product.",
        properties=[
            P(name="quantity", type=T.INTEGER, required=True),
            P(name="value_usd", type=T.FLOAT, required=True, unit="USD"),
            P(name="order_date", type=T.DATE, required=True),
            P(name="due_date", type=T.DATE, required=True),
            P(name="status", enum=["open", "in_production", "shipped", "delivered", "late"]),
            P(name="priority", enum=["standard", "high", "critical"]),
        ],
        synonyms={"ar": ["طلب", "طلبية", "أمر بيع"]},
    ),
    NodeClass(
        label="Tariff",
        description="Import duty imposed by a country on goods from an origin.",
        properties=[
            P(name="name", required=True),
            P(name="rate_pct", type=T.FLOAT, required=True, unit="%"),
            P(name="effective_date", type=T.DATE),
            P(name="status", enum=["in_force", "announced", "proposed"]),
        ],
        synonyms={"ar": ["تعريفة", "رسوم جمركية", "جمارك"]},
    ),
    # ------------------------------------------------------------------ risk
    NodeClass(
        label="RiskEvent",
        description="Real-world event that can disrupt supply, logistics or demand.",
        properties=[
            P(name="title", required=True),
            P(name="title_ar"),
            P(name="type", required=True, enum=RISK_TYPES),
            P(name="severity", type=T.INTEGER, required=True, description="1 (minor) – 5 (critical)."),
            P(name="probability", type=T.FLOAT, description="0-1 likelihood, 1 for ongoing events."),
            P(name="status", required=True, enum=["active", "forecast", "resolved"]),
            P(name="start_date", type=T.DATE),
            P(name="expected_duration_days", type=T.INTEGER),
            P(name="summary"),
        ],
        synonyms={"ar": ["خطر", "مخاطر", "اضطراب", "أزمة"]},
    ),
    # ------------------------------------------------------------- documents
    NodeClass(
        label="Document",
        description="Unstructured source (news, contract text, report) linked to graph entities.",
        properties=[
            P(name="title", required=True),
            P(name="kind", required=True, enum=["news", "contract", "report", "email"]),
            P(name="language", enum=["en", "ar"]),
            P(name="published_date", type=T.DATE),
            P(name="source"),
            P(name="path", description="Relative path of the source file."),
            P(name="text"),
        ],
        synonyms={"ar": ["مستند", "خبر", "تقرير"]},
    ),
]

ITEM_TYPES = ["Material", "Component", "Product"]
GEO_TYPES = ["Country", "Port", "Chokepoint"]

RELATIONS: list[Relation] = [
    # --------------------------------------------------------------- location
    Relation(
        type="LOCATED_IN",
        description="Physical or legal location.",
        source=["Organization", "Facility", "Port"],
        target=["Country"],
    ),
    Relation(
        type="OPERATES", description="Organization runs a facility.", source=["Organization"], target=["Facility"]
    ),
    Relation(
        type="SERVED_BY",
        description="Facility ships through a port.",
        source=["Facility"],
        target=["Port"],
        properties=[P(name="distance_km", type=T.FLOAT)],
    ),
    # ------------------------------------------------------------ supply web
    Relation(
        type="SUPPLIES",
        description="Supplier sells an item.",
        source=["Supplier"],
        target=["Material", "Component"],
        properties=[
            P(name="share_pct", type=T.FLOAT, unit="%", description="Share of the buyer's volume."),
            P(name="unit_cost_usd", type=T.FLOAT),
            P(name="lead_time_days", type=T.INTEGER),
            P(name="capacity_units_per_month", type=T.INTEGER),
        ],
    ),
    Relation(
        type="SUPPLIES_TO",
        description="Commercial supply edge between organizations (builds the tier structure).",
        source=["Supplier"],
        target=["Company", "Supplier"],
        properties=[P(name="annual_spend_usd", type=T.FLOAT)],
    ),
    Relation(
        type="QUALIFIED_FOR",
        description="Supplier is qualified as an alternative source but not (fully) used.",
        source=["Supplier"],
        target=["Material", "Component"],
        properties=[
            P(name="ramp_up_days", type=T.INTEGER),
            P(name="max_share_pct", type=T.FLOAT),
            P(name="unit_cost_usd", type=T.FLOAT),
        ],
    ),
    Relation(
        type="REQUIRES",
        description="Bill of materials: an item is built from another item.",
        source=ITEM_TYPES,
        target=["Component", "Material"],
        properties=[P(name="quantity", type=T.FLOAT, required=True)],
    ),
    Relation(
        type="PRODUCES",
        description="Factory manufactures an item.",
        source=["Factory"],
        target=["Product", "Component"],
        properties=[P(name="capacity_units_per_month", type=T.INTEGER)],
    ),
    Relation(
        type="STOCKS",
        description="Inventory position of an item at a facility.",
        source=["Facility"],
        target=ITEM_TYPES,
        properties=[P(name="units", type=T.INTEGER), P(name="days_of_cover", type=T.FLOAT)],
    ),
    # ------------------------------------------------------------- logistics
    Relation(
        type="SHIPS_VIA",
        description="Default lane used to move goods from a supplier or factory.",
        source=["Supplier", "Factory"],
        target=["ShippingLane"],
        properties=[P(name="annual_teu", type=T.INTEGER)],
    ),
    Relation(type="ORIGIN", description="Lane start port.", source=["ShippingLane"], target=["Port"]),
    Relation(type="DESTINATION", description="Lane end port.", source=["ShippingLane"], target=["Port"]),
    Relation(
        type="TRANSITS",
        description="Lane passes through a chokepoint.",
        source=["ShippingLane"],
        target=["Chokepoint"],
        properties=[P(name="sequence", type=T.INTEGER)],
    ),
    Relation(
        type="ALTERNATIVE_TO",
        description="Contingency lane that can replace another lane.",
        source=["ShippingLane"],
        target=["ShippingLane"],
        properties=[P(name="extra_days", type=T.INTEGER), P(name="extra_cost_pct", type=T.FLOAT)],
    ),
    Relation(
        type="OPERATED_BY",
        description="Carrier operating the lane.",
        source=["ShippingLane"],
        target=["LogisticsProvider"],
    ),
    # ------------------------------------------------------------ commercial
    Relation(
        type="RECEIVES_AT",
        description="Customer takes delivery at a port.",
        source=["Customer", "Facility"],
        target=["Port"],
    ),
    Relation(type="PLACED", description="Customer placed an order.", source=["Customer"], target=["SalesOrder"]),
    Relation(type="FOR_PRODUCT", description="Order line product.", source=["SalesOrder"], target=["Product"]),
    Relation(
        type="FULFILLED_BY", description="Factory that builds the order.", source=["SalesOrder"], target=["Factory"]
    ),
    Relation(
        type="PARTY_TO", description="Organization signed a contract.", source=["Organization"], target=["Contract"]
    ),
    Relation(
        type="COVERS",
        description="What a contract governs.",
        source=["Contract"],
        target=[*ITEM_TYPES, "ShippingLane"],
    ),
    Relation(type="IMPOSED_BY", description="Country levying the tariff.", source=["Tariff"], target=["Country"]),
    Relation(type="ON_ORIGIN", description="Origin country targeted.", source=["Tariff"], target=["Country"]),
    Relation(type="TARGETS", description="Goods subject to the tariff.", source=["Tariff"], target=ITEM_TYPES),
    # ------------------------------------------------------------------ risk
    Relation(
        type="AFFECTS",
        description="Risk event impacts an entity.",
        source=["RiskEvent"],
        target=[*GEO_TYPES, "Organization", "Facility", "ShippingLane", *ITEM_TYPES],
        properties=[
            P(name="impact", required=True, enum=IMPACT_KINDS),
            P(name="magnitude", type=T.FLOAT, description="0-1 share of capacity or flow lost."),
            P(name="added_days", type=T.INTEGER),
        ],
    ),
    # ------------------------------------------------------------- documents
    Relation(
        type="MENTIONS",
        description="Document references an entity.",
        source=["Document"],
        target=["Organization", "Facility", *GEO_TYPES, *ITEM_TYPES, "RiskEvent", "Contract", "ShippingLane"],
    ),
    Relation(
        type="EVIDENCES", description="Document is the text of a contract.", source=["Document"], target=["Contract"]
    ),
    # -------------------------------------------------------------- inferred
    Relation(
        type="DEPENDS_ON",
        description="Product transitively depends on a supplier through its BOM.",
        source=["Product"],
        target=["Supplier"],
        inferred=True,
        properties=[P(name="tier", type=T.INTEGER), P(name="via", type=T.STRING_LIST), P(name="rule")],
    ),
    Relation(
        type="SINGLE_SOURCE",
        description="Item has exactly one active supplier and no qualified alternative.",
        source=["Supplier"],
        target=["Material", "Component"],
        inferred=True,
        properties=[P(name="rule")],
    ),
    Relation(
        type="ROUTED_THROUGH",
        description="Supplier's inbound flow crosses a chokepoint.",
        source=["Supplier"],
        target=["Chokepoint"],
        inferred=True,
        properties=[P(name="lane"), P(name="rule")],
    ),
    Relation(
        type="EXPOSED_TO",
        description="Entity is exposed to a risk event through some path.",
        source=["Supplier", "Product", "SalesOrder", "Customer"],
        target=["RiskEvent"],
        inferred=True,
        properties=[P(name="score", type=T.FLOAT), P(name="path", type=T.STRING_LIST), P(name="rule")],
    ),
]

ONTOLOGY = Ontology(
    name="Atlas Supply Chain Ontology",
    version="1.0.0",
    namespace="https://atlas.dev/ontology/supply-chain#",
    description=(
        "Multi-tier supply network: organizations, facilities, items and bills of materials, "
        "logistics lanes through maritime chokepoints, commercial contracts and orders, "
        "tariffs, risk events and the documents that evidence them."
    ),
    classes=CLASSES,
    relations=RELATIONS,
)
