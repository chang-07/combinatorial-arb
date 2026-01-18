### Phase 1 Detail: Finalizing the Atomic Scanner

To complete Phase 1, the scanner must transition from a proof-of-concept poller to a real-time detection system that accounts for live network congestion and order book depth.

#### 1.1 Live Data Ingestion (WebSocket Integration)
* **Goal:** Reduce "Detection Latency" by replacing HTTP polling with a persistent WebSocket connection.
* **Implementation:**
    * Subscribe to the `market` channel via the CLOB WebSocket (`wss://clob.polymarket.com/ws/market`).
    * Use an asynchronous event loop (`asyncio`) to maintain a local, incremental copy of the L2 order book.
    * Implement a "Debounce" mechanism to prevent the Inference Core from triggering on every minor 0.0001 price tick, focusing instead on significant liquidity shifts.

#### 1.2 Realistic Profitability (WAP Slippage & Depth)
* **Goal:** Calculate profit based on "Fillable Liquidity" rather than just the Best Bid/Offer (BBO).
* **Target Size:** Standardize all calculations on a **500 USDC** trade size.
* **Weighted Average Price (WAP) Formula:**
    * `Effective_Price = Σ(price_i * size_i) / Target_Size`.
    * The engine must traverse the `asks` array level-by-level until the `cumulative_size` meets the `Target_Size`.
    * If the book lacks sufficient depth for the 500 USDC target, the opportunity is discarded as "untradable."

#### 1.3 Real-time Friction Accounting (Gas & Fees)
* **Goal:** Dynamically calculate "Net Profit" by ingesting live Polygon network costs.
* **Implementation:**
    * Periodically poll the Polygon Gas Station (every 60s) for `maxPriorityFee` and `estimatedBaseFee`.
    * **Transaction Estimate:** Calculate cost based on ~200,000 gas units for two `createOrder` calls.
    * **Net Profit Formula:** `(1.0 - (WAP_Yes + WAP_No)) * Target_Size - (Total_Gas_USD + Exchange_Fees)`.

#### 1.4 "Hot Path" Decoupling (C++ Prep)
* **Goal:** Isolate the calculation logic for a future C++ port.
* **InferenceCore Class:**
    * A standalone Python class that is **entirely I/O free** (no `print`, no `requests`, no `logging`).
    * **Function:** `calculate_net_profit(target_size, book_yes, book_no, gas_usd)`.
    * This separation ensures the math can be ported to C++ with zero structural changes once verified in Python.

#### 1.5 Structured Opportunity Logging
* **Goal:** Build a dataset for Phase 2 "Probabilistic Forest" clustering.
* **Implementation:**
    * Append all opportunities with a `gross_profit > 0` to `missed_opportunities.json`.
    * Metadata must include: `timestamp`, `market_id`, `wap_yes`, `wap_no`, `gas_price_gwei`, and `total_cost_usd`.
