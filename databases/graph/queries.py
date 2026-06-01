"""
TransitFlow — Neo4j Graph Database Layer
=========================================
This module handles all queries to Neo4j.

GRAPH ROLE:
  - Model the dual transit network (city metro M1–M4 + national rail NR1–NR2)
  - Find fastest routes (Dijkstra by travel_time_min via APOC)
  - Find cheapest routes (Dijkstra by fare via APOC)
  - Find alternative routes avoiding a given station
  - Find cross-network interchange paths (metro → rail or rail → metro)
  - Show delay ripple: which stations are affected within N hops

STUDENT TASK
------------
Design your graph schema (node labels, relationship types, properties)
based on the data in train-mock-data/, seed it with skeleton/seed_neo4j.py,
then implement the query_ functions below.

Functions prefixed with `query_` are called by the agent (skeleton/agent.py).
"""

from __future__ import annotations

from typing import Optional

from neo4j import GraphDatabase

from skeleton.config import NEO4J_URI, NEO4J_USER, NEO4J_PASSWORD


def _driver():
    """Return a Neo4j driver. Caller is responsible for closing."""
    return GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))


# ── Example ───────────────────────────────────────────────────────────────────
# The block below shows the query pattern: open a session, run Cypher, return data.

def example_count_nodes() -> int:
    """Example: count all nodes currently in the graph."""
    with _driver() as driver:
        with driver.session() as session:
            result = session.run("MATCH (n) RETURN count(n) AS total")
            return result.single()["total"]

# ─────────────────────────────────────────────────────────────────────────────

# ── FASTEST ROUTE (Dijkstra by travel_time_min) ───────────────────────────────

def query_shortest_route(
    origin_id: str,
    destination_id: str,
    network: str = "auto",
) -> dict:
    """Find the fastest route between two stations using Dijkstra's algorithm."""
    # Modified: Removed node labels to support both networks and updated relationship types
    query = """
    MATCH (start {station_id: $origin_id})
    MATCH (end {station_id: $destination_id})
    CALL apoc.algo.dijkstra(start, end, 'METRO_LINK|RAIL_LINK|INTERCHANGE_TO', 'travel_time_min') YIELD path, weight
    RETURN [node in nodes(path) | {station_id: node.station_id, name: node.name}] AS stations, weight AS total_time_min
    """
    with _driver() as driver:
        with driver.session() as session:
            result = session.run(query, origin_id=origin_id, destination_id=destination_id)
            record = result.single()
            
            if not record:
                return {"found": False}
                
            return {
                "found": True,
                "origin_id": origin_id,
                "destination_id": destination_id,
                "total_time_min": record["total_time_min"],
                "path": record["stations"]
            }


# ── CHEAPEST ROUTE (Dijkstra by fare) ────────────────────────────────────────

def query_cheapest_route(
    origin_id: str,
    destination_id: str,
    network: str = "auto",
    fare_class: str = "standard",
) -> dict:
    """Find the cheapest route based on the selected fare class."""
    weight_prop = "fare_first" if fare_class == "first" else "fare_standard"
    
    # Modified: Removed node labels to support both networks and updated relationship types
    query = f"""
    MATCH (start {{station_id: $origin_id}})
    MATCH (end {{station_id: $destination_id}})
    CALL apoc.algo.dijkstra(start, end, 'METRO_LINK|RAIL_LINK|INTERCHANGE_TO', '{weight_prop}') YIELD path, weight
    RETURN [node in nodes(path) | {{station_id: node.station_id, name: node.name}}] AS stations, weight AS total_fare_usd
    """
    with _driver() as driver:
        with driver.session() as session:
            result = session.run(query, origin_id=origin_id, destination_id=destination_id)
            record = result.single()
            
            if not record:
                return {"found": False}
                
            return {
                "found": True,
                "total_fare_usd": record["total_fare_usd"],
                "stations": record["stations"]
            }


# ── ALTERNATIVE ROUTES (avoiding a station) ───────────────────────────────────

def query_alternative_routes(
    origin_id: str,
    destination_id: str,
    avoid_station_id: str,
    network: str = "auto",
    max_routes: int = 3,
) -> list[list[dict]]:
    """Find alternative routes that completely bypass a specific station."""
    # Modified: Removed node labels to support both networks and updated relationship types
    query = """
    MATCH (start {station_id: $origin_id})
    MATCH (end {station_id: $destination_id})
    CALL apoc.algo.kShortestPaths(start, end, 'METRO_LINK|RAIL_LINK|INTERCHANGE_TO', 'travel_time_min', $search_limit) YIELD path
    WHERE NOT any(node IN nodes(path) WHERE node.station_id = $avoid_station_id)
    RETURN [node in nodes(path) | {station_id: node.station_id, name: node.name}] AS route_stations
    LIMIT $max_routes
    """
    with _driver() as driver:
        with driver.session() as session:
            result = session.run(query, origin_id=origin_id, destination_id=destination_id, 
                                 avoid_station_id=avoid_station_id, search_limit=max_routes + 3, max_routes=max_routes)
            return [record["route_stations"] for record in result]


# ── CROSS-NETWORK INTERCHANGE PATH ───────────────────────────────────────────

def query_interchange_path(origin_id: str, destination_id: str) -> dict:
    """Wrapper function to find cross-network paths."""
    return query_shortest_route(origin_id, destination_id)


# ── DELAY RIPPLE ANALYSIS ─────────────────────────────────────────────────────

def query_delay_ripple(delayed_station_id: str, hops: int = 2) -> list[dict]:
    """Identify all surrounding stations affected by a delay within N hops."""
    # Modified: Removed node labels and updated relationship types
    query = f"""
    MATCH p = shortestPath((start {{station_id: $delayed_station_id}})-[:METRO_LINK|RAIL_LINK|INTERCHANGE_TO*1..{hops}]-(affected))
    WHERE affected.station_id <> $delayed_station_id
    RETURN affected.station_id AS station_id, affected.name AS name, length(p) AS hops_away
    ORDER BY hops_away ASC
    """
    with _driver() as driver:
        with driver.session() as session:
            result = session.run(query, delayed_station_id=delayed_station_id)
            return [dict(record) for record in result]


# ── STATION CONNECTIONS ───────────────────────────────────────────────────────

def query_station_connections(station_id: str) -> list[dict]:
    """List all direct physical or interchange connections for a given station."""
    # Modified: Removed node labels and updated relationship types
    query = """
    MATCH (start {station_id: $station_id})-[r:METRO_LINK|RAIL_LINK|INTERCHANGE_TO]-(connected)
    RETURN 
        connected.station_id AS station_id, 
        connected.name AS name, 
        type(r) AS connection_type, 
        r.travel_time_min AS travel_time_min
    """
    with _driver() as driver:
        with driver.session() as session:
            result = session.run(query, station_id=station_id)
            return [dict(record) for record in result]
    """
    List all direct connections from a given station.

    Args:
        station_id: e.g. "MS01" or "NR01"
    """
    query = """
    MATCH (start:Station {station_id: $station_id})-[r:CONNECTS_TO|INTERCHANGES_WITH]-(connected:Station)
    RETURN 
        connected.station_id AS station_id, 
        connected.name AS name, 
        type(r) AS connection_type, 
        r.travel_time_min AS travel_time_min
    """
    with _driver() as driver:
        with driver.session() as session:
            result = session.run(query, station_id=station_id)
            return [dict(record) for record in result]
