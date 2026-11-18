"""Compile the ontology into Neo4j DDL, OWL/Turtle, JSON and prompt text."""

from __future__ import annotations

import json

from rdflib import OWL, RDF, RDFS, XSD, Graph, Literal, Namespace, URIRef

from .model import DataType, Ontology

_XSD = {
    DataType.STRING: XSD.string,
    DataType.INTEGER: XSD.integer,
    DataType.FLOAT: XSD.double,
    DataType.BOOLEAN: XSD.boolean,
    DataType.DATE: XSD.date,
    DataType.POINT: XSD.string,
    DataType.STRING_LIST: XSD.string,
}


def neo4j_constraints(onto: Ontology) -> list[str]:
    """Uniqueness constraints on root classes plus indexes on common lookups.

    Every node carries its ancestor labels, so a constraint on the root class
    (e.g. ``Organization``) enforces uniqueness across all subclasses.
    """
    stmts: list[str] = []
    for cls in onto.classes:
        if cls.parent is None:
            stmts.append(
                f"CREATE CONSTRAINT {cls.label.lower()}_{cls.key} IF NOT EXISTS "
                f"FOR (n:{cls.label}) REQUIRE n.{cls.key} IS UNIQUE"
            )
        if cls.property("name"):
            stmts.append(f"CREATE INDEX {cls.label.lower()}_name IF NOT EXISTS FOR (n:{cls.label}) ON (n.name)")
    stmts.append(
        "CREATE FULLTEXT INDEX entity_names IF NOT EXISTS FOR "
        "(n:Organization|Facility|Country|Port|Chokepoint|Item|RiskEvent|ShippingLane) "
        "ON EACH [n.name, n.name_ar, n.title, n.title_ar]"
    )
    stmts.append("CREATE FULLTEXT INDEX document_text IF NOT EXISTS FOR (n:Document) ON EACH [n.title, n.text]")
    return stmts


def to_owl(onto: Ontology) -> Graph:
    ns = Namespace(onto.namespace)
    g = Graph()
    g.bind("atlas", ns)
    g.bind("owl", OWL)
    iri = URIRef(onto.namespace.rstrip("#"))
    g.add((iri, RDF.type, OWL.Ontology))
    g.add((iri, RDFS.label, Literal(onto.name)))
    g.add((iri, OWL.versionInfo, Literal(onto.version)))
    g.add((iri, RDFS.comment, Literal(onto.description)))

    for cls in onto.classes:
        c = ns[cls.label]
        g.add((c, RDF.type, OWL.Class))
        g.add((c, RDFS.label, Literal(cls.label, lang="en")))
        g.add((c, RDFS.comment, Literal(cls.description, lang="en")))
        for word in cls.synonyms.get("ar", []):
            g.add((c, RDFS.label, Literal(word, lang="ar")))
        if cls.parent:
            g.add((c, RDFS.subClassOf, ns[cls.parent]))
        for prop in cls.properties:
            p = ns[f"{cls.label[0].lower()}{cls.label[1:]}_{prop.name}"]
            g.add((p, RDF.type, OWL.DatatypeProperty))
            g.add((p, RDFS.label, Literal(prop.name)))
            g.add((p, RDFS.domain, c))
            g.add((p, RDFS.range, _XSD[prop.type]))
            if prop.description:
                g.add((p, RDFS.comment, Literal(prop.description)))

    for rel in onto.relations:
        r = ns[rel.type]
        g.add((r, RDF.type, OWL.ObjectProperty))
        g.add((r, RDFS.label, Literal(rel.type)))
        g.add((r, RDFS.comment, Literal(rel.description)))
        for s in rel.source:
            g.add((r, RDFS.domain, ns[s]))
        for t in rel.target:
            g.add((r, RDFS.range, ns[t]))
        if rel.inferred:
            g.add((r, RDFS.comment, Literal("Inferred by the Atlas reasoning layer.")))
    return g


def to_prompt(onto: Ontology) -> str:
    """Compact schema description for LLM system prompts (text-to-Cypher etc.)."""
    lines = [f"# {onto.name} v{onto.version}", onto.description, "", "## Node labels"]
    for cls in onto.classes:
        props = ", ".join(
            f"{p.name}:{p.type.value}" + (f"∈{p.enum}" if p.enum else "") for p in onto.all_properties(cls.label)
        )
        parent = f" ⊂ {cls.parent}" if cls.parent else ""
        lines.append(f"- {cls.label}{parent} {{{cls.key}, {props}}} — {cls.description}")
    lines += ["", "## Relationships"]
    for rel in onto.relations:
        props = ", ".join(f"{p.name}:{p.type.value}" for p in rel.properties)
        tag = " [inferred]" if rel.inferred else ""
        lines.append(
            f"- ({'|'.join(rel.source)})-[:{rel.type}{' {' + props + '}' if props else ''}]->"
            f"({'|'.join(rel.target)}){tag} — {rel.description}"
        )
    return "\n".join(lines)


def to_json(onto: Ontology) -> str:
    return json.dumps(onto.model_dump(mode="json"), ensure_ascii=False, indent=2)
