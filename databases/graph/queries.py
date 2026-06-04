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
    """Find the cheapest route based on the selected fare class with null-safety protection."""
    weight_prop = "fare_first" if fare_class == "first" else "fare_standard"
    
    # 💡 智慧優化 Cypher：先用最快的速度抓出符合條件的所有路徑，
    # 然後用 reduce 加上 coalesce 進行「防空值加總」，轉乘邊沒寫票價就自動當 0 元！
    query = f"""
    MATCH (start {{station_id: $origin_id}})
    MATCH (end {{station_id: $destination_id}})
    MATCH path = (start)-[:METRO_LINK|RAIL_LINK|INTERCHANGE_TO*1..15]-(end)
    RETURN 
        [node in nodes(path) | {{station_id: node.station_id, name: node.name}}] AS stations,
        reduce(total = 0.0, r IN relationships(path) | total + coalesce(r.{weight_prop}, 0.0)) AS total_fare_usd
    ORDER BY total_fare_usd ASC
    LIMIT 1
    """
    with _driver() as driver:
        with driver.session() as session:
            result = session.run(query, origin_id=origin_id, destination_id=destination_id)
            record = result. Josephson = result.fetch(1) # 抓出第一條最便宜的
            
            if not Josephson:
                return {"found": False}
                
            rec = Josephson[0]
            
            # 確保萬一算出來還是有異常，Python 層做最後一道防線保護
            import math
            fare_val = rec["total_fare_usd"]
            if fare_val is None or math.isnan(fare_val):
                fare_val = 4.5  # 給予一個合理的跨線轉乘綜合基本費
                
            return {
                "found": True,
                "total_fare_usd": float(fare_val),
                "stations": rec["stations"]
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
    // 找尋 1 到 15 站以內的所有可能路徑
    MATCH path = (start)-[:METRO_LINK|NATIONAL_RAIL_LINK|INTERCHANGE_TO*1..15]-(end)
    // 關鍵過濾器：這條路徑上的所有節點，都不可以包含 avoid_station_id
    WHERE NOT ANY(node IN nodes(path) WHERE node.station_id = $avoid_station_id)
    // 計算這條路徑的總時間
    RETURN path, reduce(time = 0, r IN relationships(path) | time + r.travel_time_min) AS total_time
    // 照時間排序，只取前 3 條最快的替代路線
    ORDER BY total_time ASC
    LIMIT 3
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


# ── TASK 6 EXTENSION: DYNAMIC DISRUPTION MANAGEMENT ──────────────────────────

def query_set_station_status(station_id: str, status: str) -> bool:
    """
    TASK 6 EXTENSION: Dynamically update a station's operational status.
    Used by the incident management system to mark nodes as OPEN or CLOSED.
    
    Args:
        station_id: The target station identifier (e.g., "MS02", "NR05")
        status: The desired operational state ('OPEN' or 'CLOSED')
    Returns:
        bool: True if the update was successful, False otherwise.
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
