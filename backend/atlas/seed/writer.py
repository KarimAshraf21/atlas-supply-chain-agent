"""Write generated data to disk: graph JSONL, per-class CSV exports and Markdown documents."""

from __future__ import annotations

import csv
import json
import shutil
from collections import defaultdict
from pathlib import Path

from .generator import AS_OF, GraphData


def _front_matter(meta: dict) -> str:
    # JSON scalars and arrays are valid YAML, so this stays dependency-free.
    lines = ["---"] + [f"{k}: {json.dumps(v, ensure_ascii=False)}" for k, v in meta.items()] + ["---", ""]
    return "\n".join(lines)


def write(g: GraphData, out_dir: Path) -> dict:
    if out_dir.exists():
        shutil.rmtree(out_dir)
    (out_dir / "graph").mkdir(parents=True)
    (out_dir / "erp").mkdir()

    with (out_dir / "graph" / "nodes.jsonl").open("w", encoding="utf-8") as f:
        for n in g.nodes.values():
            props = {k: v for k, v in n["props"].items() if k != "text"}
            f.write(json.dumps({"label": n["label"], **props}, ensure_ascii=False) + "\n")
    with (out_dir / "graph" / "edges.jsonl").open("w", encoding="utf-8") as f:
        for e in g.edges:
            f.write(json.dumps(e, ensure_ascii=False) + "\n")

    by_label: dict[str, list[dict]] = defaultdict(list)
    for n in g.nodes.values():
        by_label[n["label"]].append({k: v for k, v in n["props"].items() if k != "text"})
    for label, rows in by_label.items():
        cols = list(dict.fromkeys(k for r in rows for k in r))
        with (out_dir / "erp" / f"{label}.csv").open("w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=cols)
            w.writeheader()
            w.writerows(rows)

    for doc in g.documents:
        path = out_dir / doc["path"]
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(_front_matter(doc["front_matter"]) + doc["body"].strip() + "\n", encoding="utf-8")

    manifest = {
        "company": "Nilewave Energy (fictional)",
        "as_of": AS_OF.isoformat(),
        **g.stats(),
        "documents": len(g.documents),
    }
    (out_dir / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return manifest
