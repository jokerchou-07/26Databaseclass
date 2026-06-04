# IM2002 — Student Guide: Design Document Evaluation · /100

## Mark Summary

| Section | Max |
|---------|-----|
| Section 1 — Entity-Relationship Diagram | 25 |
| Section 2 — Normalisation Justification | 20 |
| Section 3 — Graph Database Design Rationale | 25 |
| Section 4 — Vector / RAG Design | 15 |
| Section 5 — AI Tool Usage Evidence | 10 |
| Section 6 — Reflection & Trade-offs | 5 |
| **Total** | **100** |
| Task 6 Bonus — Section 7 (optional) | +15 |

---

## Section 1 — Entity-Relationship Diagram · /25
![TransitFlow ER Diagram](https://raw.githubusercontent.com/jokerchou-07/26Databaseclass/main/ERDiagram.png)
各資料表之主鍵（Primary Key, PK）皆統一採用 VARCHAR(50) 型態，以提供足夠的識別彈性並方便與其他系統整合。

1. Users（使用者基本資料表）

此資料表用於儲存系統使用者之基本資訊與登入資料。
user_id (PK)：VARCHAR(50)，系統生成之使用者唯一識別碼。
email (Unique)：VARCHAR(150)，使用者登入電子郵件，具備唯一性限制。
password：VARCHAR(255)，儲存經安全雜湊演算法（如 Argon2id 或 bcrypt）處理後之密碼字串。

其他主要欄位包括：
first_name：VARCHAR(50)，使用者名字。
surname：VARCHAR(50)，使用者姓氏。
created_at：TIMESTAMPTZ，帳號建立時間。

2. Metro_Stations 與 National_Rail_Stations（車站資料表）

此類資料表用於儲存捷運及國鐵車站資訊。
station_id (PK)：VARCHAR(50)，車站唯一識別碼，可對應圖形資料庫中的節點 ID。

其他主要欄位包括：
name：VARCHAR(100)，車站名稱。
zone：INT，捷運車站分區代碼（僅捷運車站適用）。

3. Metro_Schedules 與 National_Rail_Schedules（運輸班次表）
此類資料表用於管理捷運與國鐵班次資訊。
schedule_id (PK)：VARCHAR(50)，班次唯一識別碼。

其他主要欄位包括：
line / route_name：VARCHAR，路線名稱。
fare / fare_standard：NUMERIC(10,2)，票價資訊，提供精確金額計算。
departure_time、arrival_time：班次出發與抵達時間。

4. Metro_Schedule_Stops（捷運班次停靠站結合表）

本表用於記錄捷運班次與停靠車站之多對多關係，為符合第三正規化（3NF）所建立之關聯資料表。
schedule_id (PK, FK)：參照 metro_schedules(schedule_id)，採用 ON DELETE CASCADE。
station_id (PK, FK)：參照 metro_stations(station_id)，採用 ON DELETE CASCADE。

其他主要欄位包括：
arrival_time：TIME，列車抵達時間。
stop_order：INT，停靠順序編號。

5. National_Rail_Seat_Layouts（國鐵座位配置表）

本表用於管理各國鐵班次之座位配置資訊。
layout_id (PK)：VARCHAR(50)，座位配置唯一識別碼。
schedule_id (FK)：參照 national_rail_schedules(schedule_id)，採用 ON DELETE CASCADE。

其他主要欄位包括：
coach_number：VARCHAR(10)，車廂編號。
seat_number：VARCHAR(10)，座位編號。
fare_class：VARCHAR(50)，座位等級（如 Standard、First Class）。

6. Bookings（國鐵訂位紀錄表）

本表用於儲存使用者之國鐵訂票資訊。
booking_id (PK)：VARCHAR(50)，訂位紀錄唯一識別碼。
user_id (FK)：參照 users(user_id)，採用 ON DELETE CASCADE。
schedule_id (FK)：參照 national_rail_schedules(schedule_id)。

其他主要欄位包括：
travel_date：DATE，搭乘日期。
departure_time：TIME，出發時間。
carriage_number：VARCHAR(10)，車廂編號。
seat_number：VARCHAR(10)，座位編號。
amount_usd：NUMERIC(10,2)，訂票金額。
status：VARCHAR(50)，訂單狀態。

7. Metro_Travel_History（捷運搭乘歷史紀錄表）

本表用於記錄使用者之捷運進出站與搭乘紀錄。
history_id (PK)：VARCHAR(50)，乘車紀錄唯一識別碼。
user_id (FK)：參照 users(user_id)，採用 ON DELETE CASCADE。
entry_station_id (FK)：參照 metro_stations(station_id)。
exit_station_id (FK)：參照 metro_stations(station_id)。

其他主要欄位包括：
entry_time：TIMESTAMPTZ，進站時間。
exit_time：TIMESTAMPTZ，出站時間。
fare：NUMERIC(10,2)，實際搭乘費用。

8. Payments（付款交易紀錄表）

本表用於管理系統中的付款與交易資訊。
payment_id (PK)：VARCHAR(50)，付款交易唯一識別碼。
booking_id (FK)：參照 bookings(booking_id)，採用 ON DELETE SET NULL。
history_id (FK)：參照 metro_travel_history(history_id)，採用 ON DELETE SET NULL。

其他主要欄位包括：
amount_usd：NUMERIC(10,2)，付款金額。
payment_method：VARCHAR(50)，付款方式。
status：VARCHAR(50)，付款狀態。
payment_date：TIMESTAMPTZ，付款時間。

9. Feedback（使用者意見回饋表）

本表用於蒐集使用者對系統服務之評價與意見。
feedback_id (PK)：VARCHAR(50)，回饋紀錄唯一識別碼。
user_id (FK)：參照 users(user_id)，採用 ON DELETE CASCADE。

其他主要欄位包括：
rating：INT，評分等級，限制介於 1 至 5 顆星。
comments：TEXT，使用者意見內容。
submitted_at：TIMESTAMPTZ，回饋提交時間。

## Section 2 — Normalisation Justification · /20
2.1 3NF Normalisation Decision在 TransitFlow 關聯式資料庫的綱要設計中，我們嚴格遵循了第三正規化（3NF）的規範，以確保資料的一致性並消除不必要的冗餘。決策實例（Design Decision）：我們並未在捷運班次表（metro_schedules）中直接使用 PostgreSQL 的陣列欄位（如 text[]）來儲存該班次所經過的所有車站，而是將停靠資訊獨立抽離，建立了一張專門的結合表（Junction Table）——metro_schedule_stops。功能相依性與正規化論述（Functional Dependency & Normalisation Argument）：如果在 metro_schedules 中引入陣列或複合欄位來存儲車站與到站時間，將會違反第一正規化（1NF）的「屬性原子性（Atomicity）」原則。進一步分析其功能相依性（Functional Dependency, FD），在我們的結合表中，非主鍵屬性「抵達時間（arrival_time）」與「停靠順序（stop_order）」必須同時由「班次代碼（schedule_id）」與「車站代碼（station_id）」共同決定，亦即：$\{\text{schedule\_id}, \text{station\_id}\} \rightarrow \text{arrival\_time}, \text{stop\_order}$因為複合主鍵 $X = \{\text{schedule\_id}, \text{station\_id}\}$ 為該表的候選鍵（Candidate Key），且表中不存在任何非主鍵屬性對於主鍵的「部份相依（Partial Dependency）」或「傳遞相依（Transitive Dependency）」。換言之，每一個非主鍵屬性都直接且僅相依於超鍵（Super Key）。這完全符合第三正規化（3NF）與 BCNF 的嚴格定義，從根本上杜絕了當某個車站更名或班次調整時，可能引發的更新異常（Update Anomaly）、插入異常與刪除異常。

2.2 Deliberate De-normalisation Trade-off雖然完整正規化能保證資料結構的嚴謹度，但在現實的大眾運輸系統高併發查詢場景中，有時必須進行具備工程合理性的調整。決策實例（De-normalisation Choice）：在國鐵訂位紀錄表（bookings）與付款紀錄表（payments）中，我們選擇了反正規化（De-normalisation）策略，直接冗餘儲存了交易當下的實付金額欄位——amount_usd。讀取效能與複雜度權衡（Rationale & Trade-offs）：若按照純 3NF 的教條設計，訂單的總金額應該在執行期（Runtime）透過 bookings 串接 national_rail_seat_layouts 判定艙等，再 Join national_rail_schedules 取得基本票價，最後進行算術運算得出。然而，大眾運輸系統中「查詢個人歷史訂單」與「核對歷史帳務」的頻率極高。如果每次讀取都要執行昂貴的多表串接（Multi-table Joins）與 CPU 算術解算，將會對資料庫造成巨大的負載。我們引入此反正規化設計，犧牲了極少量的儲存空間，但換取了直接讀取的效能，顯著降低了 CPU 開銷；同時，這也能對抗「歷史票價變更黃金軌跡丟失」的風險——即便未來鐵路調漲基本票價，過去已完成的訂單金額也絕對不會被錯誤地連動更新。

2.3 Password Hashing Implementation保障使用者隱私與帳號安全是系統設計的重中之重。在 users 資料表中，我們拒絕使用明文（Plain-text），而是強制規定密碼欄位必須儲存經過密碼學雜湊後的安全字串。演算法選擇與淘汰過時密碼學（Algorithm Selected vs Alternatives）：我們在後端登冊系統中選擇了 Argon2id（或 bcrypt）作為核心雜湊演算法，並果斷淘汰了傳統的 MD5、SHA-1 或 SHA-256。主要理由在於：MD5 與 SHA-1 屬於高計算速度的常規雜湊函數，這意味著攻擊者可以利用現代 GPU 的並行運算能力，進行每秒數十億次的暴力破解（Brute-force）。相反地，Argon2id 是一種自適應金鑰延伸演算法（Adaptive Key Stretching Algorithm）。它設計了可調參數來設定「記憶體硬度（Memory Hardness）」與「時間成本（Time Cost）」，迫使單次雜湊計算必須消耗特定的記憶體空間與時間。這使得依靠 GPU 叢集或專用 ASIC 晶片的硬體暴力破解在經濟成本與時間成本上變得完全不可行。Salt（鹽）的管理與防禦彩虹表機制（Salt Management vs Rainbow-table）：當使用者註冊時，密碼雜湊模組會在核心隨機生成一段足夠長度的隨機位元組字串作為 Salt（鹽），與用戶輸入的明文密碼拼接後，再進行雜湊。最終儲存在 password 欄位的字串會同時包含 Salt 參數與雜湊結果。Salt 的核心價值在於防範彩虹表（Rainbow-table Attacks）與預先計算攻擊。如果沒有 Salt，當兩個使用者剛好設定了完全相同的密碼，資料庫中就會存儲兩個一模一樣的雜湊字串。有了隨機的 Salt，即便全站有 1000 個使用者的明文密碼完全一致，經過不同的 Salt 加鹽後，在資料庫中產生的雜湊字串也完全不同。這徹底癱瘓了彩虹表快速查表比對的攻擊手段，將安全性提升至生產環境級別。

---

## Section 3 — Graph Database Design Rationale · /25
3.1 Graph Model Architecture
在 TransitFlow 專案中，我們將運輸網路轉換為屬性圖（Property Graph）模型，設計如下：
Nodes（節點）：
包含 MetroStation 與 NationalRailStation 兩種標籤。
節點代表現實世界中具備獨立語意與空間意義的實體（Entities），如車站。車站作為運輸網路中的起點、中繼點與終點，天然具有「圖結構中的點（Vertex）」特性，因此適合作為節點建模。

Relationships（關係）：
包含同系統內的 METRO_LINK、RAIL_LINK，以及跨系統的 INTERCHANGE_TO。
關係代表節點之間的可通行路徑（Traversable Paths），用於描述實際移動行為。其中 INTERCHANGE_TO 特別用於建模不同運輸系統間的步行轉乘行為，使跨網路路徑能被明確表示。

Properties（屬性）：
節點包含 name 等基本資訊；關係則包含 travel_time_min。
將時間成本設計於關係上，可直接作為圖演算法中的邊權重（Edge Weight），支援最短路徑與最佳化查詢。

3.2 Graph vs Relational Algorithmic Argument
對於最短路徑（Shortest Path）與延誤漣漪（Delay Ripple）等高度連通性查詢，圖形資料庫相較於關聯式資料庫具有明顯的演算法優勢，其差異主要來自「資料存取方式與搜尋策略」。

關聯式資料庫（SQL）的限制：
在 PostgreSQL 中進行最短路徑查詢時，必須依賴 Recursive CTE 逐層展開搜尋。每一層遞迴都需要透過 self-join 將邊表重新與中間結果集合併，並維護 visited set 與 cumulative cost。此過程的問題在於：每一層遞迴都會產生新的中間結果集，隨著 hop 數增加，候選路徑數量快速膨脹，系統需要重複掃描邊表與進行集合運算，因此其成本主要來自「中間狀態爆炸」與「重複 join 計算」。

圖形資料庫（Graph Database）的優勢：
圖形資料庫（如 Neo4j）採用 Index-free Adjacency 結構，每個節點直接保存與鄰居節點的關係引用，使查詢可以直接進行 graph traversal，而非透過 join 重建關係。在此架構下：搜尋沿著邊直接擴展，不需要重新組合表格，不產生大量中間 join 結果

在演算法層面，可直接套用：
Dijkstra（加權最短路徑）
BFS（最少轉乘路徑）
其時間複雜度主要與實際走訪的節點與邊數相關（O(V + E log V)），而非資料表大小。

核心差異總結：圖形資料庫的優勢在於「查詢成本與圖結構本身成正比」，而關聯式資料庫則因 recursive join 與集合運算導致計算成本隨搜尋深度非線性上升。

3.3 Query Scenario Enablement
此圖形模型可有效支援以下兩種關鍵查詢：
Scenario 1：最短時間路徑（query_shortest_route）
由於 travel_time_min 直接建模於關係上，可直接作為邊權重輸入 Dijkstra 演算法（如 APOC implementation）。
系統可自動計算：1.所有可能路徑 2.累積時間成本 3.最短總時間路徑
此類問題在關聯式資料庫中需透過多層 recursive CTE 才能近似實現，且效率較低。

Scenario 2：跨系統轉乘路徑（query_interchange_path）
透過 INTERCHANGE_TO 關係，捷運與國鐵形成可連通圖。
使用 Cypher pattern matching：
(m:MetroStation)-[:INTERCHANGE_TO]->(r:NationalRailStation)
圖形資料庫可直接將不同子圖連接成單一搜尋空間，避免 SQL 中需使用 UNION 或多表查詢來整合不同系統資料結構。

3.4 Node Identity Decision
本系統採用 station_id 作為唯一節點識別碼（Node Identity）。
選擇原因如下：
一致性（Consistency）：與 PostgreSQL 主鍵一致，確保跨系統資料對齊。
穩定性（Stability）：station_id 為不可變識別碼，即使車站名稱或屬性變更仍不影響索引。
系統整合（Integration）：Neo4j 計算結果可直接回傳 station_id 至關聯式資料庫查詢票價與附加資訊。
此設計支援 Polyglot Persistence 架構，使圖形資料庫負責路徑計算，而關聯式資料庫負責交易與靜態資料查詢。
---

## Section 4 — Vector / RAG Design · /15
4.1 Embedding & Cosine Similarity
本系統將TransitFlow的Policy Documents，如退票規範、訂位規則與乘客行為守則等內容進行文本切片，並轉換為高維向量（embeddings）後儲存於資料庫中，用於後續語意檢索。

在語意搜尋中，我們選擇餘弦相似度作為主要距離度量方法，其計算方式為向量內積除以向量長度的乘積，本質上衡量的是兩個向量在高維空間中的方向相似性，而非數值大小。此特性使其特別適用於語意搜尋場景，因為不同文本長度（例如短句查詢與長篇政策文件）在向量長度上存在顯著差異，但語意方向仍可能高度一致。因此 cosine similarity 能有效避免因文本長度不同造成的匹配偏差。

4.2 The RAG Pipeline Architecture
本系統採用 Retrieval-Augmented Generation（RAG）架構，其完整流程如下：

1. Query Embedding（查詢向量化）
使用者透過 UI 輸入自然語言問題後，系統會透過 embedding model 將查詢轉換為高維向量表示。

2. Similarity Search（語意檢索）
查詢向量被送入 PostgreSQL 的 pgvector 模組，並透過 HNSW（Hierarchical Navigable Small World）索引進行近似最近鄰搜尋（ANN search），從 policy_documents.embedding 中檢索 Top-K 最相關文本片段。

3. Prompt Augmentation（提示詞增強）
系統將檢索到的政策文件內容作為 context，與使用者原始問題結合，組裝成結構化 prompt，以提供 LLM 足夠的外部知識支援。

4. LLM Generation（語言模型生成）
強化後的 prompt 被送入大型語言模型進行推理與生成。模型僅能基於提供的 context 回答，以降低 hallucination 並提升回覆與實際政策一致性。

4.3 Embedding Dimension Consistency & Provider Switching Risk
本系統目前使用 vector(768) 作為 embedding storage dimension，對應當前 embedding provider 所輸出的固定維度向量。

Dimension Consistency Requirement
在向量資料庫中，cosine similarity 與 nearest-neighbor search 的成立前提是：查詢向量與資料庫中向量必須處於相同維度的向量空間，若維度不一致，則無法進行有效的相似度計算。

Provider Switching Problem
若系統在已完成資料 embedding 與 seeding 後更換 embedding provider（例如改用 OpenAI 1536 維或 Gemini 3072 維模型），將導致：query vector 與 stored vectors 維度不一致，pgvector index（HNSW）無法正常運作，similarity search 直接失效

Required System Recovery Procedure
此情況無法透過修改 API 解決，必須執行完整重建流程：Drop existing embedding column / index，更新 schema 至新 embedding dimension，重新對所有 policy documents 進行 embedding（re-seeding，重建 HNSW index。
---

## Section 5 — AI Tool Usage Evidence · /10

**Requirement:** 3 to 5 examples. Each example must include all three fields: **Context**, **Prompt**, **Outcome**.

| Criterion | What earns full marks |
|-----------|-----------------------|
| 3–5 distinct examples covering different aspects (schema design, query writing, debugging, design rationale, etc.) | At least 3 examples; each covers a genuinely different aspect of the project |
| Each example contains all three required fields: context + prompt + outcome | All three fields present in every example |
| At least one example discusses a case where the AI output was wrong or needed correction | Describes the specific error, how it was identified, and what correction was made |
| Overall quality: prompts are specific and purposeful (not generic like "explain databases") | Prompts show that the AI was given meaningful project context |
| **Section 5 Total** | |

**Three-fields scoring (3 marks):** All 3 fields present in every example = 3 ·
**Three-fields scoring:** All 3 fields present in every example = full marks · 1–2 fields missing in some examples = deduction · Missing fields throughout = 0 mark

**Correction example scoring:** Describes a specific AI error and how it was identified and fixed · Missing = 0

> **Tip:** Every example must have all three fields — **Context** (what you were trying to do), **Prompt** (what you asked), and **Outcome** (what happened, whether it was useful, and what you did next). Examples missing any field lose marks regardless of how many examples are provided. At least one example must describe a case where the AI gave incorrect output and explain how you identified and corrected it.

---

## Section 6 — Reflection & Trade-offs · /5

| Criterion | What earns full marks |
|-----------|-----------------------|
| Identifies at least two specific design decisions and explains the reasoning behind each | Two decisions named with clear reasoning — not vague ("we thought it was better"), but specific (e.g., "we chose SERIAL over UUID because our system is single-region and integer joins are faster") |
| Discusses one aspect that would be different in a production system | Names a concrete production concern (schema migrations, connection pooling, secret management, indexing strategy, etc.) and explains why it would need to change |
| **Section 6 Total** | |

**Design decisions scoring (3 marks):** Two specific decisions with clear reasoning = 3 ·
**Design decisions scoring:** Two specific decisions with clear reasoning = 3 · Vague decisions without reasoning = 1–2 · Missing = 0

**Production difference scoring:** Identifies a concrete production concern with explanation = 2 · Mentions something production-related without depth = 1 · Missing = 0

---

## Task 6 — Optional Extension Bonus · Section 7 · up to +15

To be eligible for the bonus in any marking scheme, all four of the following must be present:

1. The extension touches database code (new schema, queries, or seed data), or includes a substantial UI improvement. Substantial means it adds a meaningful new interaction or surfaces data the current UI cannot show — for example, a trip history panel, a route visualiser, or an analytics dashboard. Cosmetic-only changes (theme colours, button labels, layout tweaks) do not qualify. UI-only submissions are capped at 3 marks per component; database extensions are eligible for the full 15.
2. Detailed inline comments explain every new database operation *(not required for UI-only submissions)*.
3. A **Section 7** in this design document covers motivation, schema changes, example queries, and testing evidence; for UI-only submissions, cover motivation, UI design decisions, and screenshots instead.
4. A **`TASK6.md`** file at the repo root lists every file modified or added, with specific function and table names. Each modified file must also have a `# TASK 6 EXTENSION:` comment near the top.

The Section 7 bonus marks in this scheme are awarded for the quality of the document section only.
The code and live components have their own independent bonus marks.

| Criterion | Max | What earns full marks |
|-----------|-----|-----------------------|
| **Motivation** — explains why this extension adds value to the TransitFlow assistant | 3 | Clear, specific argument for why the feature improves the system — not just "it adds more features" |
| **Database changes** — new tables, relationships, or vector entries described with schema snippets | 4 | Actual schema or Cypher shown for new structures; not a prose-only description |
| **Example queries** — SQL/Cypher/similarity search shown with expected output | 4 | At least one complete query shown with the output it produces |
| **Testing evidence** — screenshots, query output in pgAdmin/Neo4j Browser, or chat UI demo | 4 | Evidence that the extension was actually run and produced correct output |
| **Task 6 Doc Bonus Total** | **+15** | |

> **UI-only extension:** Section 7 for a UI-only submission should cover motivation and include screenshots or a component description instead of schema snippets. Up to 3 marks awarded holistically.

> If Section 7 is present but the code does not include `TASK6.md` or per-file comment markers, the live and code bonus sections will not be awarded — only this document bonus can be graded.
