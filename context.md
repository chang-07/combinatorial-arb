# Project: The Probabilistic Forest Engine

## 1. Core Mission & Objectives
To develop a high-performance **Inference and Execution Engine** capable of detecting and exploiting structural mispricings (arbitrage) in prediction markets. This project utilizes advanced data structures and graph theory to solve the $O(2^{n+m})$ complexity problem associated with combinatorial event mapping.

### Phase 1 Detail: Finalizing the Atomic Scanner

To complete Phase 1, the scanner must move beyond simple price-sum checks and incorporate live network conditions and order book depth.

#### 1.1 Live Data Ingestion (WebSocket Integration)
* **Goal:** Replace HTTP polling with a persistent WebSocket connection to reduce "Detection Latency."
* **Implementation:**
    * Subscribe to the `order_book` channel via the CLOB WebSocket for real-time L2 updates.
    * Implement a local order book manager that updates incrementally to avoid frequent full-book fetches.
    * Use an event-driven loop (e.g., `asyncio`) to handle simultaneous updates across multiple active markets.

#### 1.2 Realistic Profitability (Slippage & Depth)
* **Goal:** Calculate profit based on "Fillable Liquidity" rather than just the Best Bid/Offer (BBO).
* **Implementation:**
    * Define a standard "Target Trade Size" (e.g., 500 USDC).
    * **Slippage Calculation:** Traverse the `asks` array to find the weighted average price required to fill the target size.
    * **Formula:** `Effective_Price = Σ(price_i * volume_i) / Target_Size`.
    * Discard opportunities where the order book depth cannot support the trade without pushing the `price_sum` above $1.00.

#### 1.3 Real-time Friction Accounting (Gas & Fees)
* **Goal:** Calculate "Net Profit" by ingesting live Polygon network costs.
* **Implementation:**
    * Integrate a gas price provider (e.g., Alchemy or Infura) to fetch current `maxPriorityFeePerGas` on Polygon (Chain ID 137).
    * **Transaction Cost:** Estimate the gas limit for two `createOrder` transactions (one for 'Yes', one for 'No').
    * **Net Profit Formula:** `(1.0 - (Effective_Yes + Effective_No)) * Target_Size - (Total_Gas_Cost + Exchange_Fees)`.

#### 1.4 "Hot Path" Decoupling
* **Goal:** Isolate the calculation logic for a future C++ port.
* **Implementation:**
    * Create a standalone `InferenceCore` class or module.
    * **Input:** A clean data structure containing current bid/ask arrays and network gas prices.
    * **Output:** A boolean `ArbVerdict` and an `ExpectedReturn` float.
    * **Constraint:** This core must remain free of I/O operations (No API calls or prints) to ensure it can be ported to C++ with zero structural changes.

#### 1.5 Execution Logging & Alerting
* **Goal:** Create a dataset of "missed opportunities" for Phase 2 clustering analysis.
* **Implementation:**
    * Log all detected opportunities with a `PriceSum < 1.0` to a structured format (JSON or CSV).
    * Include metadata: `Timestamp`, `Market_Question`, `Expected_Profit`, and `Network_Congestion_Level`.
---

## 2. Technical Stack & Methodology
* **Performance Layer (C++):** Implementation of the **Inference Engine** using **lock-free data structures**, **SIMD instructions**, and **Bitmasking** to achieve sub-millisecond latency.
* **Intelligence Layer (Python):** Utilization of **Large Language Models (LLMs)** for **Semantic Analysis** and market relationship extraction.
* **Data Structures:** Modeling dependencies as a **Directed Acyclic Graph (DAG)**.
* **Advanced Math:** Application of the **Graph Laplacian ($L = D - A$)** for **Spectral Clustering** and anomaly detection within "logical neighborhoods."

---

## 3. System Architecture (The Pipeline)
1.  **Ingestion:** Real-time polling via `py_clob_client` and WebSockets.
2.  **Pruning:** **Heuristic-Driven Reduction** based on temporal proximity and semantic similarity.
3.  **Mapping:** Constructing a **Probabilistic Forest** where nodes represent events and edges represent conditional probabilities.
4.  **Inference:** Checking for violations of the **No-Arbitrage Condition** using **Topological Sorting** and **Transitive Inference**.
5.  **Execution:** Calculating slippage and transaction costs to ensure net profitability.

---

## 4. Current Milestone: Phase 1 (Atomic Scanner)
**Goal:** Build a robust Python-based scanner to detect arbitrage in single binary markets.
* **Logic:** $P(Yes) + P(No) < (1.0 - \text{threshold})$.
* **Requirements:**
    * Monitor live Order Books via Polymarket API.
    * Account for gas fees and exchange slippage.
    * Provide a clear logging system for potential "risk-free" spreads.
    * Structure the "Hot Path" of calculations to be easily ported to **C++**.

---

## 5. Long-term Roadmap
* **Phase 2:** Implement **Spectral Embedding** using the **Fiedler Vector** for automated market grouping.
* **Phase 3:** Expand logic to **Combinatorial Arbitrage** (Cross-market dependencies).
* **Phase 4:** Optimize C++ execution for **Non-Atomic** multi-leg trade sequences.

---

## 6. Key Interview Highlights (The "Power" Bullet)
* "Architected a high-throughput **inference engine** treats prediction markets as a **DAG**, utilizing **Graph Laplacians** and **Bitmasking** to reduce search complexity from $O(2^{n+m})$ to **$O(V+E)$ amortized time**."
