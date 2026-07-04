"""Выгрузка собранного графа в Neo4j (для «настоящей» графовой БД и визуализации).

Требует запущенного `docker compose up -d`. Запуск:  python scripts/load_neo4j.py
"""
from __future__ import annotations

import json
import os
from pathlib import Path

from neo4j import GraphDatabase

ROOT = Path(__file__).resolve().parent.parent
URI = os.environ.get("NEO4J_URI", "bolt://localhost:7687")
AUTH = ("neo4j", os.environ.get("NEO4J_PASSWORD", "hackathon2024"))


def load():
    data = json.loads((ROOT / "data" / "graph.json").read_text(encoding="utf-8"))
    driver = GraphDatabase.driver(URI, auth=AUTH)
    with driver.session() as s:
        s.run("MATCH (n) DETACH DELETE n")
        s.run("CREATE INDEX node_id IF NOT EXISTS FOR (n:Entity) ON (n.id)")
        for n in data["nodes"]:
            props = {k: v for k, v in n.items()
                     if k not in ("id", "type") and v is not None}
            s.run(
                f"CREATE (n:Entity:`{n['type']}` {{id:$id}}) SET n += $props",
                id=n["id"], props=props)
        for e in data["links"]:
            s.run(
                "MATCH (a:Entity {id:$s}),(b:Entity {id:$t}) "
                f"CREATE (a)-[:`{e['type']}`]->(b)",
                s=e["source"], t=e["target"])
    driver.close()
    print(f"Загружено в Neo4j: {len(data['nodes'])} узлов, {len(data['links'])} рёбер")
    print("Открой http://localhost:7474 и выполни:  MATCH (n)-[r]->(m) RETURN n,r,m LIMIT 200")


if __name__ == "__main__":
    load()
