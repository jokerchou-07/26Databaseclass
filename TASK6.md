# TASK 6 EXTENSION: Dynamic Disruption Management and Adaptive Routing Engine

## 1. Motivation & Business Logic

In real-world dual-network transit systems, unexpected incidents—such as signal failures, track maintenance, scheduling overruns, or severe weather—cause sudden station closures or severe service delays. 

A static routing engine fails during incidents, leading to corrupted passenger journeys, invalid bookings, and severe operational bottlenecks. 

### Core Objectives:
* **Dynamic Network Gating**: Gracefully isolate affected stations across both the Metro and National Rail networks without tearing down the structural topology of the graph database.
* **Multi-Modal Real-Time Sync**: Maintain relational tracking of incident durations, severity levels, and logs in PostgreSQL, while dynamically reflecting these state changes in Neo4j to inform the routing agent.
* **High-Performance Incident Filtering**: Ensure that pathfinding algorithms can filter out closed or delayed nodes at `O(1)` efficiency, preventing regression in response times under high concurrent user loads.

---

## 2. Database Modifications & Schema Changes

### A. Relational Layer (PostgreSQL)

A new dedicated operational tracking table was introduced to record structural incidents. It utilizes strong data types, constraints, and an optimized performance index.

#### Table Structure: `station_disruptions`
* `disruption_id`: `SERIAL PRIMARY KEY`
* `station_id`: `VARCHAR(50) NOT NULL`
* `network_type`: `VARCHAR(20) NOT NULL CHECK (network_type IN ('metro', 'national_rail'))`
* `severity`: `VARCHAR(20) DEFAULT 'DELAY' CHECK (severity IN ('DELAY', 'CLOSED'))`
* `description`: `TEXT NOT NULL`
* `reported_at`: `TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP`
* `resolved_at`: `TIMESTAMP WITH TIME ZONE`

#### Production-Quality Indexing Strategy: `idx_disruptions_active_station`

To prevent system performance degradation as incident logs grow over time, we implemented a highly optimized Partial Index:

```sql
CREATE INDEX idx_disruptions_active_station 
ON station_disruptions(station_id) 
WHERE resolved_at IS NULL;

```
## B. Graph Layer (Neo4j)

Station nodes (:MetroStation and :NationalRailStation) have been enriched with a dynamic property:

**status:** Set to `"OPEN"` by default during seeding, and dynamically toggled to `"CLOSED"` during active incident windows.

## 3. Impacted Files & Summary of Changes

Every file modified for this extension features a clean header comment near the top:

```python
# TASK 6 EXTENSION: Dynamic Disruption Management and Adaptive Routing Engine.
```

### File Path: databases/relational/schema.sql   

**Component Name:** table: station_disruptions, index: idx_disruptions_active_station

**Modification Summary:** Created table structure, constraints, and the conditional partial optimization index for live event lookups.

### File Path: databases/graph/queries.py

**Component Name:** function: query_set_station_status

**Modification Summary:** Built the connection wrapper to toggle the operational node state in the active Neo4j session.

### File Path: TASK6.md

**Component Name:** Root Documentation

**Modification Summary:** Detailed system layout, technical justifications, file impact registry, and test cases for TAs.

## 4. Production-Grade Query Specifications

### PostgreSQL: Logging an Active Station Closure Incident

#### SQL

```sql
INSERT INTO station_disruptions (station_id, network_type, severity, description) 
VALUES ('MS02', 'metro', 'CLOSED', 'Severe flooding due to heavy rain.');
```

### Neo4j: Dynamically Isolating a Node in the Graph

#### Cypher

```cypher
MATCH (s {station_id: $station_id}) 
SET s.status = $status 
RETURN s.station_id AS station_id, s.status AS status;
```

### Neo4j: Adaptive Route Planning (Bypassing Closed Stations)

#### Cypher

```cypher
MATCH (start {station_id: $origin_id}) 
MATCH (end {station_id: $destination_id}) 
CALL apoc.algo.kShortestPaths(start, end, 'METRO_LINK|RAIL_LINK|INTERCHANGE_TO', 'travel_time_min', 5) YIELD path 
WHERE NOT any(node IN nodes(path) WHERE node.status = 'CLOSED') 
RETURN [node in nodes(path) | {station_id: node.station_id, name: node.name}] AS route_stations 
LIMIT 1;
```

## 5. Verification & Testing Evidence

### Step 1: Baseline Verification

Run the status check query in the Neo4j Browser (http://localhost:7475):

#### Cypher

```cypher
MATCH (s {station_id: "MS02"}) RETURN s.station_id, s.name, s.status;
```

**Expected Output:** Displays the station details with status initialized as default or null (evaluating as open).

### Step 2: Triggering the Extension via Python Component

Invoke the extension function through a quick test script or via the database debug console:

#### Python

```python
from databases.graph.queries import query_set_station_status

success = query_set_station_status(station_id="MS02", status="CLOSED")

print(f"Station state successfully decoupled: {success}")
```
