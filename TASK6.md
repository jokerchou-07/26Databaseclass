# TASK 6 EXTENSION: Dynamic Disruption Management and Adaptive Routing Engine

## 1. Motivation & Business Logic
In real-world dual-network transit systems, unexpected incidents—such as signal failures, track maintenance, scheduling overruns, or severe weather—cause sudden station closures or severe service delays. 

A static routing engine fails during these incidents, leading to corrupted passenger journeys, invalid bookings, and severe operational bottlenecks. 

### Core Objectives:
1. **Dynamic Network Gating**: Gracefully isolate affected stations across both the Metro and National Rail networks without tearing down the structural topology of the graph database.
2. **Multi-Modal Real-Time Sync**: Maintain strict relational tracking of incident durations, severity levels, and logs in the transactional database (PostgreSQL), while dynamically reflecting these state changes in the graph network layer (Neo4j) to inform the routing agent.
3. **High-Performance Incident Filtering**: Ensure that pathfinding algorithms can filter out closed or delayed nodes at O(1) efficiency, preventing regression in response times under high concurrent user loads.

---

## 2. Database Modifications & Schema Changes

### A. Relational Layer (PostgreSQL)
A new dedicated operational tracking table was introduced to record structural incidents. It utilizes strong data types, constraints, and an optimized performance index.

#### Table Structure: `station_disruptions`
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

Production-Quality Indexing Strategy: idx_disruptions_active_station
To prevent system performance degradation as incident logs grow over time, we implemented a highly optimized Partial Index:
CREATE INDEX idx_disruptions_active_station 
ON station_disruptions(station_id) 
WHERE resolved_at IS NULL;

Performance Justification: In a production environment, historical incident records can reach millions of rows, but active disruptions at any given moment are usually less than 1%.

By adding the WHERE resolved_at IS NULL predicate, this index completely ignores resolved historical data and only maps live incidents.

This allows the routing engine to fetch the current system bottlenecks with O(1) look-up efficiency, drastically reducing memory consumption and preventing B-Tree page bloat in PostgreSQL.
