"""Atlas command-line interface."""

from __future__ import annotations

from pathlib import Path

import typer
from rich.console import Console
from rich.table import Table

from .config import ROOT, get_settings

app = typer.Typer(help="Atlas — talk to your supply chain.", no_args_is_help=True)
console = Console()


@app.command()
def generate(out: Path = typer.Option(None, help="Output directory (default: data/seed).")) -> None:
    """Generate the synthetic Nilewave Energy dataset."""
    from .seed import generate as gen
    from .seed.writer import write

    g = gen()
    errors = g.validate()
    if errors:
        for e in errors[:20]:
            console.print(f"[red]✗[/] {e}")
        raise typer.Exit(1)
    manifest = write(g, out or get_settings().seed_dir)
    _print_counts("Generated", manifest["nodes"], manifest["edges"])
    console.print(f"[green]✓[/] {manifest['documents']} documents, validated against the ontology")


@app.command()
def load(wipe: bool = typer.Option(True, help="Delete existing graph first.")) -> None:
    """Load the seed dataset into Neo4j."""
    from .graph.loader import counts
    from .graph.loader import load as do_load

    with console.status("Loading graph into Neo4j…"):
        do_load(get_settings().seed_dir, wipe=wipe)
    c = counts()
    _print_counts("Neo4j", c["labels"], c["relationships"])


@app.command()
def ontology(out: Path = typer.Option(ROOT / "ontology", help="Export directory.")) -> None:
    """Export the ontology as OWL/Turtle, JSON and an LLM prompt."""
    from .ontology import ONTOLOGY
    from .ontology.exporters import to_json, to_owl, to_prompt

    out.mkdir(parents=True, exist_ok=True)
    to_owl(ONTOLOGY).serialize(out / "atlas.ttl", format="turtle")
    (out / "atlas.json").write_text(to_json(ONTOLOGY), encoding="utf-8")
    (out / "atlas.prompt.md").write_text(to_prompt(ONTOLOGY), encoding="utf-8")
    console.print(f"[green]✓[/] Exported {len(ONTOLOGY.classes)} classes, {len(ONTOLOGY.relations)} relations → {out}")


def _print_counts(title: str, nodes: dict, edges: dict) -> None:
    t = Table(title=title, show_lines=False)
    t.add_column("Node label")
    t.add_column("Count", justify="right")
    t.add_column("Relationship")
    t.add_column("Count", justify="right")
    n_items, e_items = list(nodes.items()), list(edges.items())
    for i in range(max(len(n_items), len(e_items))):
        a = n_items[i] if i < len(n_items) else ("", "")
        b = e_items[i] if i < len(e_items) else ("", "")
        t.add_row(a[0], str(a[1]), b[0], str(b[1]))
    console.print(t)


if __name__ == "__main__":
    app()
