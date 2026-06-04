# TASK 6 EXTENSION: Dynamic Disruption Management and Adaptive Routing Engine

## 1. Motivation & Business Logic
In real-world dual-network transit systems, unexpected incidents—such as signal failures, track maintenance, scheduling overruns, or severe weather—cause sudden station closures or severe service delays. 

A static routing engine fails during these incidents, leading to corrupted passenger journeys, invalid bookings, and severe operational bottlenecks. 

### Core Objectives:
1. **Dynamic Network Gating**: Gracefully isolate affected stations across both the Metro and National Rail networks without tearing down the structural topology of the graph database.
2. **Multi-Modal Real-Time Sync**: Maintain strict relational tracking of incident durations, severity levels, and logs in the transactional database (PostgreSQL), while dynamically reflecting these state changes in the graph network layer (Neo4j) to inform the routing agent.
3. **High-Performance Incident Filtering**: Ensure that pathfinding algorithms can filter out closed or delayed nodes at $O(1)$ efficiency, preventing regression in response times under high concurrent user loads.

---

## 2. Database Modifications & Schema Changes

### A. Relational Layer (PostgreSQL)
A new dedicated operational tracking table was introduced to record structural incidents. It utilizes strong data types, constraints, and an optimized performance index.

```sql
CREATE TABLE station_disruptions (
    disruption_id SERIAL PRIMARY KEY,
    station_id VARCHAR(50) NOT NULL,
    network_type VARCHAR(20) NOT NULL CHECK (network_type IN ('metro', 'national_rail')),
    severity VARCHAR(20) DEFAULT 'DELAY' CHECK (severity IN ('DELAY', 'CLOSED')),
    description TEXT NOT NULL,
    reported_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    resolved_at TIMESTAMP WITH TIME ZONE
);
Production-Quality Indexing Strategy:To maintain maximum efficiency during path routing evaluations, we implemented a Partial Index:SQLCREATE INDEX idx_disruptions_active_station 
ON station_disruptions(station_id) 
WHERE resolved_at IS NULL;
Why this works: Instead of indexing millions of resolved historical logs, this index dynamically tracks only active disruptions. Lookups take a fraction of a millisecond.B. Graph Layer (Neo4j)Station nodes (:MetroStation and :NationalRailStation) have been enriched with a dynamic property:status: Set to "OPEN" by default during seeding, and dynamically toggled to "CLOSED" during active incident windows.3. Impacted Files & Summary of ChangesEvery file modified for this extension features a clean header comment near the top: # TASK 6 EXTENSION: Dynamic Disruption Management and Adaptive Routing Engine.File PathComponent Name / Table NameModification Summarydatabases/relational/schema.sqltable: station_disruptionsCreated table structure, constraints, and partial optimization index.databases/graph/queries.pyfunction: query_set_station_statusBuilt the connection wrapper to toggle the operational node state in the active Neo4j session.TASK6.mdRoot DocumentationDetailed system layout, technical justifications, file impact registry, and test cases for TAs.4. Production-Grade Query SpecificationsPostgreSQL: Logging an Active Station Closure IncidentSQLINSERT INTO station_disruptions (station_id, network_type, severity, description)
VALUES ('MS02', 'metro', 'CLOSED', 'Severe flooding in station concourse due to heavy rain.');
Neo4j: Dynamically Isolating a Node in the GraphCypherMATCH (s {station_id: $station_id})
SET s.status = $status
RETURN s.station_id AS station_id, s.status AS status;
Neo4j: Adaptive Route Planning (Bypassing Closed Stations)When a station status is set to "CLOSED", the active route planner automatically invokes alternative path selection or drops edge evaluation via the adaptive routing protocol:CypherMATCH (start {station_id: $origin_id})
MATCH (end {station_id: $destination_id})
CALL apoc.algo.kShortestPaths(start, end, 'METRO_LINK|RAIL_LINK|INTERCHANGE_TO', 'travel_time_min', 5) YIELD path
WHERE NOT any(node IN nodes(path) WHERE node.status = 'CLOSED')
RETURN [node in nodes(path) | {station_id: node.station_id, name: node.name}] AS route_stations
LIMIT 1;
5. Verification & Testing EvidenceStep 1: Baseline VerificationRun the status check query in the Neo4j Browser (http://localhost:7475):CypherMATCH (s {station_id: "MS02"}) RETURN s.station_id, s.name, s.status;
Expected Output: Displays the station details with status initialized as default or null (evaluating as open).Step 2: Triggering the Extension via Python ComponentInvoke the extension function through a quick test script or via the database debug console:Pythonfrom databases.graph.queries import query_set_station_status

# Simulate incident management system closing a bottleneck station
success = query_set_station_status(station_id="MS02", status="CLOSED")
print(f"Station state successfully decoupled: {success}")
