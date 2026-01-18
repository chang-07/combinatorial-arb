### **Agent Task: Transition to Anonymous Real-Time Monitoring**

**Objective:**
Refactor the `atomic_scanner/main.py` script to support **Anonymous (Unauthenticated) WebSocket Monitoring** for Phase 1. The current implementation fails because it attempts an authenticated handshake with missing L2 API credentials (API Secret and Passphrase). Since public market data and order book updates do not require authentication on Polymarket, the engine must be adjusted to run in public mode.

---

### **1. WebSocket Refactoring (Anonymous Mode)**
* **Remove Auth Handshake:** Modify the `run_websocket` method in the `MarketManager` class to remove the `auth_payload` and the `Authorization` header from the `websocket.WebSocketApp` initialization.
* **Connection Logic:** Ensure the connection to `WEBSOCKET_URL` is established without any security tokens.
* **Public Subscription:** The `on_open` method must continue to send a subscription message to the `market` channel using the correct format for public streams: `{"type": "subscribe", "channel": "market", "markets": [market_ids]}`.

### **2. Environment Variable & Configuration Updates**
* **Optional Credentials:** Update the script to make `POLYMARKET_API_KEY`, `POLYMARKET_API_SECRET`, and `POLYMARKET_API_PASSPHRASE` optional.
* **Graceful Warnings:** If these keys are missing, the script should log a `WARNING` stating that it is running in "Read-Only/Public Mode" rather than terminating the process.
* **Maintain CoinMarketCap:** Keep `COINMARKETCAP_API_KEY` as a **mandatory** requirement. This is still necessary to fetch MATIC/USD prices for the real-time friction accounting required by Phase 1.3.

### **3. Logic Preservation ("Hot Path" Integrity)**
* **InferenceCore Protection:** Do **not** modify the `inference_core.py` file or the `InferenceCore` class.
* **WAP Continuity:** Ensure the Weighted Average Price (WAP) calculation for the **500 USDC Target Size** remains the primary filter for trade viability.
* **Debounce & Performance:** Retain the `0.5s` debounce period and the `MarketManager`'s local state management to prevent CPU bottlenecking during high-frequency updates.

### **4. Execution Logging for Phase 2**
* **Persistence:** Ensure all opportunities where `gross_profit > 0` are appended to `missed_opportunities.json`.
* **Data Schema:** Each log entry must include the `timestamp`, `market_question`, `wap_yes`, `wap_no`, `gas_price_gwei`, and `total_cost_usd`. This dataset is critical for the upcoming **Phase 2: Spectral Clustering and Graph Laplacian** implementation.

---

**Success Criteria:**
1. The script connects to the Polymarket WebSocket without an `Authorization` error.
2. It successfully logs "Subscribed to [X] order books" and starts receiving market updates.
3. The `update_gas_prices` loop continues to run in the background every 60 seconds to provide the `total_gas_cost_usd` for the inference engine.
