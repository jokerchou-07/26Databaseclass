# TASK 6 EXTENSION: Dynamic Disruption Management and Adaptive Routing Engine
# New function: query_set_station_status(station_id, status)
from __future__ import annotations

from typing import Optional

from neo4j import GraphDatabase

from skeleton.config import NEO4J_URI, NEO4J_USER, NEO4J_PASSWORD


def _driver():
    """Return a Neo4j driver. Caller is responsible for closing."""
    return GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))


# ── Example ───────────────────────────────────────────────────────────────────

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
    """
    Find the fastest route between two stations using APOC Dijkstra.
    Works across metro, national rail, and interchange edges automatically.

    Returns:
        dict with 'path' (list of station dicts) and 'total_time_min', or {'found': False}.
    """
    query = """
    MATCH (start {station_id: $origin_id})
    MATCH (end {station_id: $destination_id})
    CALL apoc.algo.dijkstra(start, end, 'METRO_LINK|RAIL_LINK|INTERCHANGE_TO', 'travel_time_min')
    YIELD path, weight
    RETURN
        [node IN nodes(path) | {station_id: node.station_id, name: node.name}] AS stations,
        weight AS total_time_min
    """
    with _driver() as driver:
        with driver.session() as session:
            result = session.run(query, origin_id=origin_id, destination_id=destination_id)
            record = result.single()

            if not record:
                return {"found": False, "path": [], "total_time_min": 0}

            return {
                "found": True,
                "origin_id": origin_id,
                "destination_id": destination_id,
                "total_time_min": record["total_time_min"],
                "path": record["stations"],
            }


# ── CHEAPEST ROUTE (Dijkstra by fare) ────────────────────────────────────────

def query_cheapest_route(
    origin_id: str,
    destination_id: str,
    network: str = "auto",
    fare_class: str = "standard",
) -> dict:
    """
    Find the cheapest route weighted by fare_standard or fare_first using APOC Dijkstra.
    Falls back to brute-force path enumeration if APOC returns no result.

    The weight_property is dynamically selected based on fare_class so that
    first-class routes use higher edge weights than standard-class routes.

    Returns:
        dict with 'path', 'total_fare_usd', and 'fare_class', or {'found': False}.
    """
    weight_prop = "fare_first" if fare_class == "first" else "fare_standard"

    # Use APOC Dijkstra for efficiency — same algorithm as query_shortest_route
    query = f"""
    MATCH (start {{station_id: $origin_id}})
    MATCH (end {{station_id: $destination_id}})
    CALL apoc.algo.dijkstra(start, end, 'METRO_LINK|RAIL_LINK|INTERCHANGE_TO', '{weight_prop}')
    YIELD path, weight
    RETURN
        [node IN nodes(path) | {{station_id: node.station_id, name: node.name}}] AS stations,
        weight AS total_fare_usd
    """
    with _driver() as driver:
        with driver.session() as session:
            result = session.run(query, origin_id=origin_id, destination_id=destination_id)
            record = result.single()

            if not record:
                return {"found": False, "path": [], "total_fare_usd": 0.0, "fare_class": fare_class}

            fare_val = record["total_fare_usd"]
            return {
                "found": True,
                "fare_class": fare_class,
                "total_fare_usd": float(fare_val) if fare_val else 0.0,
                "path": record["stations"],
            }


# ── ALTERNATIVE ROUTES (avoiding a station) ───────────────────────────────────

def query_alternative_routes(
    origin_id: str,
    destination_id: str,
    avoid_station_id: str,
    network: str = "auto",
    max_routes: int = 3,
) -> list[dict]:
    """
    Find alternative routes bypassing a specific station using APOC allSimplePaths.
    APOC is used instead of variable-length MATCH because it avoids the exponential
    path explosion that occurs with undirected *1..N patterns on dense graphs.
    Results are ordered by total travel time, shortest first.
    """
    query = """
    MATCH (start {station_id: $origin_id})
    MATCH (end {station_id: $destination_id})
    CALL apoc.algo.allSimplePaths(start, end, 'METRO_LINK|RAIL_LINK|INTERCHANGE_TO', 8)
    YIELD path
    WHERE NOT ANY(node IN nodes(path) WHERE node.station_id = $avoid_station_id)
    RETURN
        [node IN nodes(path) | {station_id: node.station_id, name: node.name}] AS route_stations,
        reduce(time = 0, r IN relationships(path) | time + coalesce(r.travel_time_min, 0)) AS total_time_min
    ORDER BY total_time_min ASC
    LIMIT $max_routes
    """
    with _driver() as driver:
        with driver.session() as session:
            result = session.run(
                query,
                origin_id=origin_id,
                destination_id=destination_id,
                avoid_station_id=avoid_station_id,
                max_routes=max_routes,
            )
            return [
                {
                    "path": record["route_stations"],
                    "total_time_min": record["total_time_min"],
                }
                for record in result
            ]

# ── CROSS-NETWORK INTERCHANGE PATH ───────────────────────────────────────────

def query_interchange_path(origin_id: str, destination_id: str) -> dict:
    """
    Find a cross-network path using APOC Dijkstra, traversing INTERCHANGE_TO edges
    to cross between metro and national rail networks.

    The 'has_interchange' flag confirms whether the path actually crossed networks,
    useful for informing the user about the transfer point.

    Returns:
        dict with 'path' (nodes labelled by network type), 'total_time_min',
        'has_interchange', or {'found': False}.
    """
    query = """
    MATCH (start {station_id: $origin_id})
    MATCH (end {station_id: $destination_id})
    CALL apoc.algo.dijkstra(start, end, 'METRO_LINK|RAIL_LINK|INTERCHANGE_TO', 'travel_time_min')
    YIELD path, weight
    RETURN
        [node IN nodes(path) | {
            station_id: node.station_id,
            name: node.name,
            type: labels(node)[0]
        }] AS path,
        weight AS total_time_min,
        [r IN relationships(path) WHERE type(r) = 'INTERCHANGE_TO' | type(r)] AS interchange_edges
    """
    with _driver() as driver:
        with driver.session() as session:
            result = session.run(query, origin_id=origin_id, destination_id=destination_id)
            record = result.single()
            if not record:
                return {"found": False, "path": [], "total_time_min": 0}

            return {
                "found": True,
                "path": record["path"],
                "total_time_min": record["total_time_min"],
                "has_interchange": len(record["interchange_edges"]) > 0,
            }


# ── DELAY RIPPLE ANALYSIS ─────────────────────────────────────────────────────

def query_delay_ripple(delayed_station_id: str, hops: int = 2) -> list[dict]:
    """
    Identify all surrounding stations potentially affected by a delay within N hops.

    hops=0 returns only the delayed station itself (no neighbours).
    hops>=1 uses shortestPath to find all reachable stations up to N hops away,
    returning the hop distance so the caller can assess impact severity.

    Returns:
        List of dicts with 'station_id', 'name', and 'hops_away'.
    """
    if hops == 0:
        query = """
        MATCH (s {station_id: $delayed_station_id})
        RETURN s.station_id AS station_id, s.name AS name, 0 AS hops_away
        """
        with _driver() as driver:
            with driver.session() as session:
                result = session.run(query, delayed_station_id=delayed_station_id)
                return [dict(record) for record in result]

    # hops >= 1: find all stations reachable within N hops via any link type
    query = f"""
    MATCH p = shortestPath(
        (start {{station_id: $delayed_station_id}})-[:METRO_LINK|RAIL_LINK|INTERCHANGE_TO*1..{hops}]-(affected)
    )
    WHERE affected.station_id <> $delayed_station_id
    RETURN
        affected.station_id AS station_id,
        affected.name AS name,
        length(p) AS hops_away
    ORDER BY hops_away ASC
    """
    with _driver() as driver:
        with driver.session() as session:
            result = session.run(query, delayed_station_id=delayed_station_id)
            return [dict(record) for record in result]


# ── STATION CONNECTIONS ───────────────────────────────────────────────────────

def query_station_connections(station_id: str) -> list[dict]:
    """
    List all direct physical or interchange connections for a given station,
    including travel time per connection.

    Returns:
        List of dicts with 'station_id', 'name', 'connection_type', 'travel_time_min'.
    """
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


# ── TASK 6 EXTENSION: DYNAMIC DISRUPTION MANAGEMENT ──────────────────────────

def query_set_station_status(station_id: str, status: str) -> bool:
    """
    TASK 6 EXTENSION: Dynamically update a station's operational status in the graph.
    Used by the incident management system to mark nodes as OPEN or CLOSED.

    Setting a station to CLOSED allows query_alternative_routes to filter it out
    when the caller passes it as avoid_station_id.

    Args:
        station_id: The target station identifier (e.g., "MS02", "NR05")
        status: The desired operational state ('OPEN' or 'CLOSED')
    Returns:
        True if the update was applied to at least one node, False otherwise.
    """
    query = """
    MATCH (s {station_id: $station_id})
    SET s.status = $status
    RETURN s.station_id AS station_id, s.status AS status
    """
    with _driver() as driver:
        with driver.session() as session:
            result = session.run(query, station_id=station_id, status=status)
            return result.single() is not None
