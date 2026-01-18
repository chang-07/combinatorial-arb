### **Agent Task: Resolve WebSocket Heartbeat Configuration Error**

**Objective:**
Refactor `atomic_scanner/main.py` to fix the `Ensure ping_interval > ping_timeout` exception that is causing the WebSocket connection to enter a rapid failure and reconnection loop.

---

### **1. Fix WebSocket Heartbeat Logic**
* **The Problem**: In the `MarketManager.run_websocket` method, the `ping_interval` is set to 10 seconds and the `ping_timeout` is set to 20 seconds. The `websocket-client` library requires the interval between pings to be strictly greater than the timeout duration.
* **The Fix**: Update the `run_forever` parameters to ensure the interval is longer than the timeout.
* **Critical Code Adjustment**:
    ```python
    # Inside run_websocket method
    self.ws_app.run_forever(
        ping_interval=30,  # Increased to be > timeout
        ping_timeout=10,   # Set lower than interval
        sslopt={"cert_reqs": ssl.CERT_NONE}
    )
    ```

---

### **2. Maintain System Integrity**
* **Market Discovery**: Ensure the `discover_markets()` method remains as the primary blocking initialization step. It successfully identifies over 50,000 tokens, which must be preserved for the subscription phase.
* **Subscription Batching**: Keep the chunking logic (500 tokens per batch) in `on_open` to comply with Polymarket's connection limits.
* **Friction Accounting**: Ensure the `update_gas_prices` task continues to run every 60 seconds to provide accurate `total_gas_cost_usd` for the `InferenceCore`.
* **Hot Path Isolation**: Do **not** modify `inference_core.py`. The calculation logic must remain pure for future C++ porting.

---

**Success Criteria:**
1. The `WebSocket run_forever() failed` exception is resolved.
2. The scanner successfully finishes the batch subscription process for all 52,000+ discovered tokens.
3. The connection remains stable, and the engine starts processing live `event_type: 'book'` updates.
