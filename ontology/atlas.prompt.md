# Atlas Supply Chain Ontology v1.0.0
Multi-tier supply network: organizations, facilities, items and bills of materials, logistics lanes through maritime chokepoints, commercial contracts and orders, tariffs, risk events and the documents that evidence them.

## Node labels
- Organization {id, name:string, country_code:string, website:string} — Any legal entity participating in the supply network.
- Company ⊂ Organization {id, name:string, country_code:string, website:string, industry:string, annual_revenue_usd:float} — The focal company that owns this Atlas instance.
- Supplier ⊂ Organization {id, name:string, country_code:string, website:string, tier:integer, category:string, esg_score:float, financial_health:string∈['strong', 'stable', 'watch', 'distressed'], on_time_delivery_pct:float} — Provides materials or components, directly (tier 1) or indirectly (tier 2+).
- Customer ⊂ Organization {id, name:string, country_code:string, website:string, segment:string∈['utility', 'distributor', 'installer', 'oem', 'retail'], region:string, strategic:boolean} — Buys finished products.
- LogisticsProvider ⊂ Organization {id, name:string, country_code:string, website:string, mode:string∈['sea', 'air', 'rail', 'road', 'multimodal']} — Carrier or freight forwarder operating shipping lanes.
- Facility {id, name:string, lat:float, lon:float, city:string} — A physical site.
- Factory ⊂ Facility {id, name:string, lat:float, lon:float, city:string, capacity_units_per_month:integer} — Manufactures components or products.
- Warehouse ⊂ Facility {id, name:string, lat:float, lon:float, city:string, capacity_pallets:integer} — Stores inventory.
- Country {id, name:string, name_ar:string, region:string, political_risk:float} — Sovereign country; key is ISO 3166-1 alpha-2.
- Port {id, name:string, name_ar:string, lat:float, lon:float, kind:string∈['sea', 'air'], congestion_index:float} — Sea or air port; key is UN/LOCODE.
- Chokepoint {id, name:string, name_ar:string, lat:float, lon:float, share_of_global_trade_pct:float} — Maritime passage whose disruption forces rerouting.
- Item {id, name:string, name_ar:string, category:string, hs_code:string, unit:string, unit_cost_usd:float} — Anything that can be bought, made, stocked or sold.
- Material ⊂ Item {id, name:string, name_ar:string, category:string, hs_code:string, unit:string, unit_cost_usd:float, critical:boolean} — Raw or processed material (e.g. lithium carbonate, copper).
- Component ⊂ Item {id, name:string, name_ar:string, category:string, hs_code:string, unit:string, unit_cost_usd:float, lead_time_days:integer} — Purchased part that goes into a product.
- Product ⊂ Item {id, name:string, name_ar:string, category:string, hs_code:string, unit:string, unit_cost_usd:float, sku:string, family:string, unit_price_usd:float, gross_margin_pct:float} — Finished good sold to customers.
- ShippingLane {id, name:string, mode:string∈['sea', 'air', 'rail', 'road'], transit_days:integer, cost_per_teu_usd:float, co2_kg_per_teu:float, is_contingency:boolean} — A recurring origin→destination route with a mode and transit time.
- Contract {id, title:string, kind:string∈['supply', 'sales', 'logistics'], start_date:date, end_date:date, value_usd:float, penalty_per_day_usd:float, force_majeure:boolean, exclusivity:boolean, min_volume_units:integer} — Commercial agreement with a supplier, customer or carrier.
- SalesOrder {id, quantity:integer, value_usd:float, order_date:date, due_date:date, status:string∈['open', 'in_production', 'shipped', 'delivered', 'late'], priority:string∈['standard', 'high', 'critical']} — Customer order for a product.
- Tariff {id, name:string, rate_pct:float, effective_date:date, status:string∈['in_force', 'announced', 'proposed']} — Import duty imposed by a country on goods from an origin.
- RiskEvent {id, title:string, title_ar:string, type:string∈['geopolitical', 'conflict', 'weather', 'labor_strike', 'tariff', 'cyber', 'financial', 'regulatory', 'pandemic', 'infrastructure'], severity:integer, probability:float, status:string∈['active', 'forecast', 'resolved'], start_date:date, expected_duration_days:integer, summary:string} — Real-world event that can disrupt supply, logistics or demand.
- Document {id, title:string, kind:string∈['news', 'contract', 'report', 'email'], language:string∈['en', 'ar'], published_date:date, source:string, path:string, text:string} — Unstructured source (news, contract text, report) linked to graph entities.

## Relationships
- (Organization|Facility|Port)-[:LOCATED_IN]->(Country) — Physical or legal location.
- (Organization)-[:OPERATES]->(Facility) — Organization runs a facility.
- (Facility)-[:SERVED_BY {distance_km:float}]->(Port) — Facility ships through a port.
- (Supplier)-[:SUPPLIES {share_pct:float, unit_cost_usd:float, lead_time_days:integer, capacity_units_per_month:integer}]->(Material|Component) — Supplier sells an item.
- (Supplier)-[:SUPPLIES_TO {annual_spend_usd:float}]->(Company|Supplier) — Commercial supply edge between organizations (builds the tier structure).
- (Supplier)-[:QUALIFIED_FOR {ramp_up_days:integer, max_share_pct:float, unit_cost_usd:float}]->(Material|Component) — Supplier is qualified as an alternative source but not (fully) used.
- (Material|Component|Product)-[:REQUIRES {quantity:float}]->(Component|Material) — Bill of materials: an item is built from another item.
- (Factory)-[:PRODUCES {capacity_units_per_month:integer}]->(Product|Component) — Factory manufactures an item.
- (Facility)-[:STOCKS {units:integer, days_of_cover:float}]->(Material|Component|Product) — Inventory position of an item at a facility.
- (Supplier|Factory)-[:SHIPS_VIA {annual_teu:integer}]->(ShippingLane) — Default lane used to move goods from a supplier or factory.
- (ShippingLane)-[:ORIGIN]->(Port) — Lane start port.
- (ShippingLane)-[:DESTINATION]->(Port) — Lane end port.
- (ShippingLane)-[:TRANSITS {sequence:integer}]->(Chokepoint) — Lane passes through a chokepoint.
- (ShippingLane)-[:ALTERNATIVE_TO {extra_days:integer, extra_cost_pct:float}]->(ShippingLane) — Contingency lane that can replace another lane.
- (ShippingLane)-[:OPERATED_BY]->(LogisticsProvider) — Carrier operating the lane.
- (Customer|Facility)-[:RECEIVES_AT]->(Port) — Customer takes delivery at a port.
- (Customer)-[:PLACED]->(SalesOrder) — Customer placed an order.
- (SalesOrder)-[:FOR_PRODUCT]->(Product) — Order line product.
- (SalesOrder)-[:FULFILLED_BY]->(Factory) — Factory that builds the order.
- (Organization)-[:PARTY_TO]->(Contract) — Organization signed a contract.
- (Contract)-[:COVERS]->(Material|Component|Product|ShippingLane) — What a contract governs.
- (Tariff)-[:IMPOSED_BY]->(Country) — Country levying the tariff.
- (Tariff)-[:ON_ORIGIN]->(Country) — Origin country targeted.
- (Tariff)-[:TARGETS]->(Material|Component|Product) — Goods subject to the tariff.
- (RiskEvent)-[:AFFECTS {impact:string, magnitude:float, added_days:integer}]->(Country|Port|Chokepoint|Organization|Facility|ShippingLane|Material|Component|Product) — Risk event impacts an entity.
- (Document)-[:MENTIONS]->(Organization|Facility|Country|Port|Chokepoint|Material|Component|Product|RiskEvent|Contract|ShippingLane) — Document references an entity.
- (Document)-[:EVIDENCES]->(Contract) — Document is the text of a contract.
- (Product)-[:DEPENDS_ON {tier:integer, via:string[], rule:string}]->(Supplier) [inferred] — Product transitively depends on a supplier through its BOM.
- (Supplier)-[:SINGLE_SOURCE {rule:string}]->(Material|Component) [inferred] — Item has exactly one active supplier and no qualified alternative.
- (Supplier)-[:ROUTED_THROUGH {lane:string, rule:string}]->(Chokepoint) [inferred] — Supplier's inbound flow crosses a chokepoint.
- (Supplier|Product|SalesOrder|Customer)-[:EXPOSED_TO {score:float, path:string[], rule:string}]->(RiskEvent) [inferred] — Entity is exposed to a risk event through some path.