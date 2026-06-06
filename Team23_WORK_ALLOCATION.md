# Work Allocation Report — [Team ID]

> **Instructions:** Complete this document as a team before or alongside your final submission.
> Submit one copy per team via EEClass. This document is shared with all markers.
> Be specific — vague entries ("we all helped") will prevent individual contribution adjustments from being applied in your favour.

---

## 1. Team Members

| Full Name | Student ID |   GitHub Username   |          Email         |
|------------|-----------|---------------------|------------------------|
|   周怡辰   | 112401541 | jokerchou-07        | cocochou2005@gmail.com |
|   林誼婷   | 112102010 | Eating Lin 112102010| st4623280@gmail.com    |
|   梁易軒   | 112707003 | Eason940214         | lys20050214@gmail.com  |
   
---

## 2. Task Ownership

For each task, name the **primary owner** (the person most responsible for delivering it)
and any **supporting members** (who assisted but were not the lead). Leave the Notes column
for anything that deviates from the standard expectation (e.g., task was pair-programmed,
or reassigned mid-project).

### Code Repository

| Task | Primary Owner | Supporting Member(s) | Notes |
|------|--------------|---------------------|-------|
| **Task 1** — Relational schema design (`schema.sql`) | 周怡辰 | 林誼婷 梁易軒| 由Primary Owner製作、修改可完整運行程式，Supporting Member負責測試、小幅度修改|
| **Task 2a** — Core availability & fare queries (`query_national_rail_availability`, `query_metro_schedules`, `query_national_rail_fare`, `query_metro_fare`) | 林誼婷 | 周怡辰| 由Primary Owner製作、修改可完整運行程式，Supporting Member負責測試、小幅度修改|
| **Task 2b** — Seat & user queries (`query_available_seats`, `query_user_profile`, `query_user_bookings`, `query_payment_info`) | 林誼婷 | 周怡辰| 由Primary Owner製作、修改可完整運行程式，Supporting Member負責測試、小幅度修改|
| **Task 2c** — Write operations (`execute_booking`, `execute_cancellation`) | 林誼婷 | 周怡辰| 由Primary Owner製作、修改可完整運行程式，Supporting Member負責測試、小幅度修改|
| **Task 2d** — Authentication queries (`login_user`, `register_user`, `get_user_secret_question`, `verify_secret_answer`, `update_password`) | 周怡辰| 林誼婷| 由Primary Owner製作、修改可完整運行程式，Supporting Member負責測試、小幅度修改|
| **Task 3** — PostgreSQL seeding (`seed_postgres.py`) | 周怡辰| 林誼婷| 由Primary Owner製作、修改可完整運行程式，Supporting Member負責測試、小幅度修改|
| **Task 4** — Neo4j graph design & seeding (`seed_neo4j.py`, `seed.cypher`) | 周怡辰| 林誼婷| 由Primary Owner製作、修改可完整運行程式，Supporting Member負責測試、小幅度修改|
| **Task 5** — Neo4j query functions (`graph/queries.py`) | 林誼婷 | 周怡辰| 由Primary Owner製作、修改可完整運行程式，Supporting Member負責測試、小幅度修改|
| **Task 6** *(if attempted)* — Optional extension | 梁易軒| | |

### Design Document

| Section | Primary Author | Supporting Member(s) | Notes |
|---------|--------------|---------------------|-------|
| Section 1 — ER Diagram | 周怡辰 | | |
| Section 2 — Normalisation Justification | 周怡辰 | | |
| Section 3 — Graph Database Design Rationale | 周怡辰 | | |
| Section 4 — Vector / RAG Design | 周怡辰 | | |
| Section 5 — AI Tool Usage Evidence | 林誼婷| 梁易軒| 林誼婷撰寫example1-3、example4-5|
| Section 6 — Reflection & Trade-offs | 林誼婷| | |
| Section 7 — Optional Extension *(if applicable)* | 梁易軒| | |

---

## 3. Estimated Contribution Percentages

Based on the task allocation above, what percentage of total team effort do you estimate each member contributed?
All members must sum to 100%.

| Member | Estimated % | Brief justification |
|--------|-----------|---------------------|
| 周怡辰 | 45% | 負責Seeding腳本撰寫、Neo4j演算法、協助修改queries、撰寫圖形資料庫、設計文件的理論論述（Sec 1-4）|
| 林誼婷 | 40% | 主要負責PostgreSQL核心查詢模組、撰寫圖形資料庫、協助修改Seeding腳本撰寫、設計文件的理論論述（Sec 5-6）|
| 梁易軒 | 15% | Task 6 加分功能實作、設計文件的理論論述（Sec 5、7）|
| **Total** | **100%** | |

---

## 4. Mid-Project Changes

If any tasks were reassigned or the original plan changed significantly, document it here.
If nothing changed, write "No changes."

| Change | Original plan | Revised plan | Reason |
|--------|--------------|-------------|--------|
| 梁易軒| graph/queries.py | task 6 | too late to finish |

---

## 5. Team Declaration

We confirm that this work allocation accurately reflects how responsibilities were divided within our team.

| Name | Signature / Typed name | Date |
|------|----------------------|------|
| 林誼婷 | 林誼婷 | 2026/06/04 |
| 梁易軒 | 梁易軒 | 2026/06/04 |
| 周怡辰 | 周怡辰 | 2026/06/04 |
