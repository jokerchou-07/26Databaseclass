"""
TransitFlow — Neo4j Seeder
Run once after starting Docker:
    python skeleton/seed_neo4j.py

Loads station and network data from train-mock-data/:
  - metro_stations.json         — city metro stations and adjacencies
  - national_rail_stations.json — national rail stations and adjacencies

Design your graph schema (node labels, relationship types, properties)
based on the data in these files, then implement the seed() function below.
"""

import json
import os
import sys

sys.path.insert(0, ".")

from neo4j import GraphDatabase
from skeleton.config import NEO4J_URI, NEO4J_USER, NEO4J_PASSWORD

_DATA_DIR = os.path.normpath(
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "train-mock-data")
)


def _load(filename):
    with open(os.path.join(_DATA_DIR, filename), encoding="utf-8") as f:
        return json.load(f)


def seed():
    metro_stations = _load("metro_stations.json")
    rail_stations  = _load("national_rail_stations.json")

    driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))
    with driver.session() as session:

        session.run("MATCH (n) DETACH DELETE n")
        print("  Cleared existing graph data")

        # 1. 建立地鐵站節點 (MetroStation Nodes)
        for s in metro_stations:
            session.run(
                "MERGE (n:MetroStation {station_id: $id}) "
                "SET n.name = $name, n.zone = $zone",
                id=s["station_id"], name=s["name"], zone=s.get("zone")
            )
        print(f"  Created {len(metro_stations)} MetroStation nodes")

        # 2. 建立鐵路站節點 (NationalRailStation Nodes)
        for s in rail_stations:
            session.run(
                "MERGE (n:NationalRailStation {station_id: $id}) "
                "SET n.name = $name",
                id=s["station_id"], name=s["name"]
            )
        print(f"  Created {len(rail_stations)} NationalRailStation nodes")

        # 3. 建立地鐵站之間的連線 (METRO_LINK Relationships)
        for s in metro_stations:
            for adj in s.get("adjacent_stations", []):
                session.run(
                    "MATCH (a:MetroStation {station_id: $from_id}) "
                    "MATCH (b:MetroStation {station_id: $to_id}) "
                    "MERGE (a)-[r:METRO_LINK {line: $line}]->(b) "
                    "SET r.travel_time_min = $time",
                    from_id=s["station_id"], to_id=adj["station_id"],
                    line=adj.get("line"), time=adj.get("travel_time_min")
                )
        print("  Created METRO_LINK relationships")

        # 4. 建立鐵路站之間的連線 (RAIL_LINK Relationships)
        for s in rail_stations:
            for adj in s.get("adjacent_stations", []):
                session.run(
                    "MATCH (a:NationalRailStation {station_id: $from_id}) "
                    "MATCH (b:NationalRailStation {station_id: $to_id}) "
                    "MERGE (a)-[r:RAIL_LINK]->(b) "
                    "SET r.travel_time_min = $time",
                    from_id=s["station_id"], to_id=adj["station_id"],
                    time=adj.get("travel_time_min")
                )
        print("  Created RAIL_LINK relationships")

        # 5. 建立跨系統轉乘連線 (INTERCHANGE_TO Relationships)
        for s in metro_stations:
            if s.get("is_interchange_national_rail") and s.get("interchange_rail_station_id"):
                # 轉乘通常是雙向的，所以我們一次建立兩條方向相反的線段
                session.run(
                    "MATCH (m:MetroStation {station_id: $metro_id}) "
                    "MATCH (r:NationalRailStation {station_id: $rail_id}) "
                    "MERGE (m)-[:INTERCHANGE_TO {walk_time_min: 5}]->(r) "
                    "MERGE (r)-[:INTERCHANGE_TO {walk_time_min: 5}]->(m)",
                    metro_id=s["station_id"], rail_id=s["interchange_rail_station_id"]
                )
        print("  Created INTERCHANGE_TO relationships")

    driver.close()
    print("\nNeo4j graph seeded successfully.")
    print("   Open http://localhost:7475 to explore the graph.")


if __name__ == "__main__":
    print("Connecting to Neo4j...")
    seed()