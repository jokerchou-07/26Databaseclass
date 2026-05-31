# 🗺️ TransitFlow Graph Database (Neo4j) Schema

> 本文件為小組共同遵循的開發規範。
>
> 為確保 Python 查詢層（`queries.py`）與假資料產生層（`seed_neo4j.py`）能夠無縫接軌，所有成員請依照本文件定義之 Graph Schema 進行開發。

---

# 1. Node Labels（節點定義）

所有捷運站與國鐵站統一使用相同的節點標籤，以利跨網路路徑搜尋、轉乘分析與圖形演算法運算。

## `:Station`

### Description

代表運輸網路中的任意車站，包括：

* 城市捷運（M1–M4）
* 國鐵（NR1–NR2）

### Properties

| Property     | Type   | Description                                             |
| ------------ | ------ | ------------------------------------------------------- |
| `station_id` | String | **必須與 PostgreSQL 中的 Station ID 完全一致**（例如：`MS01`、`NR05`） |
| `name`       | String | 車站名稱（中文或英文）                                             |

---

# 2. Relationship Types（關係定義）

車站之間的連線分為兩種類型：

1. 同線相鄰車站連線
2. 跨網路轉乘連線

---

## `:CONNECTS_TO`

### Description

代表同一運輸網路中，相鄰兩站之間的軌道路線連線。

### Direction

雙向（Bidirectional）

建立 Seed Data 時：

* 可建立雙向關係
* 或分別建立兩條反向 Relationship

### Properties

| Property          | Type  | Description                  |
| ----------------- | ----- | ---------------------------- |
| `travel_time_min` | Float | 兩站之間的行車時間（分鐘）                |
| `fare_standard`   | Float | 標準車廂票價（USD）                  |
| `fare_first`      | Float | 頭等車廂票價（USD）<br>若為捷運，可與標準票價相同 |

---

## `:INTERCHANGES_WITH`

### Description

代表捷運站與國鐵站之間的轉乘通道。

用於描述不同運輸網路之間的接駁關係。

### Direction

雙向（Bidirectional）

### Properties

| Property          | Type  | Description         |
| ----------------- | ----- | ------------------- |
| `travel_time_min` | Float | 步行轉乘所需時間（分鐘）        |
| `fare_standard`   | Float | 轉乘手續費（通常為 0 或固定接駁費） |

---

# 3. Available Query Functions（查詢功能）

以下功能已於：

```text
databases/graph/queries.py
```

完成實作，並使用 APOC Graph Algorithms 進行路徑分析。

---

## Fastest Route

### `query_shortest_route(origin_id, destination_id)`

使用 Dijkstra Algorithm 計算：

* 最短總行車時間
* 最快抵達路徑

---

## Cheapest Route

### `query_cheapest_route(origin_id, destination_id, fare_class)`

使用 Dijkstra Algorithm 計算：

* 最低總票價路徑

支援車廂類型：

* `standard`
* `first`

---

## Alternative Routes

### `query_alternative_routes(origin_id, destination_id, avoid_station_id)`

使用 Yen’s Algorithm 計算：

* 繞開指定車站
* 推薦替代路線

適用情境：

* 車站故障
* 誤點
* 臨時封閉

---

## Delay Ripple Analysis

### `query_delay_ripple(delayed_station_id, hops)`

漣漪效應分析（Ripple Effect Analysis）

用於找出：

* 事故發生站點
* 指定 Hop 範圍內
* 可能受到影響的其他車站

適用於延誤影響範圍評估與營運監控分析。
