"""Meta-model for the Atlas ontology.

The ontology is declared once in Python (see ``supply_chain.py``) and compiled
into everything else: Neo4j constraints, OWL/Turtle, JSON Schema for LLM tools,
and a compact text description used in agent prompts.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field


class DataType(StrEnum):
    STRING = "string"
    INTEGER = "integer"
    FLOAT = "float"
    BOOLEAN = "boolean"
    DATE = "date"
    POINT = "point"  # geographic coordinate
    STRING_LIST = "string[]"


class Property(BaseModel):
    name: str
    type: DataType = DataType.STRING
    description: str = ""
    required: bool = False
    enum: list[str] | None = None
    unit: str | None = None


class NodeClass(BaseModel):
    """An ontology class, materialised as a Neo4j label."""

    label: str
    description: str
    parent: str | None = None
    key: str = "id"
    properties: list[Property] = Field(default_factory=list)
    synonyms: dict[str, list[str]] = Field(
        default_factory=dict, description="Multilingual synonyms keyed by ISO language code."
    )

    def property(self, name: str) -> Property | None:
        return next((p for p in self.properties if p.name == name), None)


class Relation(BaseModel):
    """An ontology object property, materialised as a Neo4j relationship type."""

    type: str
    description: str
    source: list[str]
    target: list[str]
    properties: list[Property] = Field(default_factory=list)
    inferred: bool = False
    inverse_name: str | None = None


class Ontology(BaseModel):
    name: str
    version: str
    namespace: str
    description: str
    classes: list[NodeClass]
    relations: list[Relation]

    # ------------------------------------------------------------------ lookup
    def cls(self, label: str) -> NodeClass:
        for c in self.classes:
            if c.label == label:
                return c
        raise KeyError(f"Unknown class: {label}")

    def rel(self, rel_type: str) -> Relation:
        for r in self.relations:
            if r.type == rel_type:
                return r
        raise KeyError(f"Unknown relation: {rel_type}")

    def ancestors(self, label: str) -> list[str]:
        """Return the class and all its superclasses, most specific first."""
        chain: list[str] = []
        current: str | None = label
        while current:
            chain.append(current)
            current = self.cls(current).parent
        return chain

    def all_properties(self, label: str) -> list[Property]:
        """Own properties plus inherited ones (subclass wins on name clash)."""
        seen: dict[str, Property] = {}
        for ancestor in reversed(self.ancestors(label)):
            for prop in self.cls(ancestor).properties:
                seen[prop.name] = prop
        return list(seen.values())

    def is_a(self, label: str, ancestor: str) -> bool:
        return ancestor in self.ancestors(label)

    # -------------------------------------------------------------- validation
    def validate_node(self, label: str, data: dict[str, Any]) -> list[str]:
        """Return a list of human-readable violations for a node instance."""
        errors: list[str] = []
        props = {p.name: p for p in self.all_properties(label)}
        key = self.cls(label).key
        if key not in data or data[key] in (None, ""):
            errors.append(f"{label}: missing key '{key}'")
        for name, prop in props.items():
            value = data.get(name)
            if prop.required and value in (None, ""):
                errors.append(f"{label}[{data.get(key)}]: missing required '{name}'")
            if value is not None and prop.enum and value not in prop.enum:
                errors.append(f"{label}[{data.get(key)}]: '{name}'={value!r} not in {prop.enum}")
        for name in data:
            if name not in props and name != key:
                errors.append(f"{label}[{data.get(key)}]: unknown property '{name}'")
        return errors

    def validate_edge(self, rel_type: str, source_label: str, target_label: str) -> list[str]:
        rel = self.rel(rel_type)
        errors = []
        if not any(self.is_a(source_label, s) for s in rel.source):
            errors.append(f"{rel_type}: source {source_label} not in domain {rel.source}")
        if not any(self.is_a(target_label, t) for t in rel.target):
            errors.append(f"{rel_type}: target {target_label} not in range {rel.target}")
        return errors

    def concrete_labels(self, label: str) -> list[str]:
        """Return the class and every descendant."""
        return [c.label for c in self.classes if self.is_a(c.label, label)]
