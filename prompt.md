### **Agent Task: Finalize Atomic Scanner Stability & High-Fidelity Data Ingestion**

**Objective:**
Refactor `atomic_scanner/main.py` to resolve persistent `clobTokenId` KeyErrors, fix the broken pagination path, and stabilize the WebSocket "pipe" through correct payload formatting and active heartbeat management.

---

### **1. Resolve `clobTokenId` KeyError & Logic Mismatch**
* **The Problem**: The current `trigger_inference` logic assumes the presence of a `clobTokenId` key inside the `market_info` metadata. However, the discovery phase uses a flexible lookup (`.get('clobTokenId') or .get('token_id')`), creating a mismatch that crashes the "Hot Path" when a message for a `token_id`-only market arrives.
* **The Fix**: Store IDs explicitly in the `self.order_books` state during discovery to remove complex dictionary lookups from the high-frequency inference loop.
* **Critical Code Adjustment**:
    ```python
    # Inside on_open discovery loop
    t0_id = tokens[0].get('clobTokenId') or tokens[0].get('token_id')
    t1_id = tokens[1].get('clobTokenId') or tokens[1].get('token_id')
    
    if t0_id and t1_id:
        # Link tokens directly to avoid metadata lookups in the Hot Path
        self.order_books[t0_id] = {"bids": [], "asks": [], "other_side": t1_id, "question": market.get("question")}
        self.order_books[t1_id] = {"bids": [], "asks": [], "other_side": t0_id, "question": market.get("question")}
    ```

---

### **2. Restore Full Market Discovery (Pagination Fix)**
* **The Problem**: The script currently looks for `next_cursor` inside a `meta` dictionary. In the Polymarket CLOB API, `next_cursor` is a root-level key. This bug causes the scanner to terminate after 1,000 markets.
* **The Fix**: Update the pagination path to `next_cursor = response.get('next_cursor')`.
* **Verification**: Ensure the loop continues until `next_cursor` is `None` or the string `"none"`.

---

### **3. Stabilize the WebSocket "Pipe"**
* **Correct Subscription Payload**: The server is rejecting the current frame. Use the validated public format for the `/ws/market` endpoint:
    ```python
    subscription_message = {
        "type": "market",
        "assets_ids": batch_of_500_ids  # Batching is mandatory
    }
    ```
* **Active Heartbeats**: Add pings to the `run_forever` call to prevent intermediate proxies from dropping the connection during low-volatility periods:
    ```python
    self.ws_app.run_forever(ping_interval=20, ping_timeout=10)
    ```

---

### **4. High-Fidelity Message Handling (L2 Data)**
* **Event Mapping**: The public `market` channel emits `event_type: 'book'` messages. Refactor `on_message` to parse these correctly:
    ```python
    if data.get('event_type') == 'book':
        asset_id = data.get('asset_id')
        if asset_id in self.order_books:
            # Polymarket L2 format is [price, size]
            self.order_books[asset_id]['asks'] = [{"price": x[0], "size": x[1]} for x in data.get('sells', [])]
            self.order_books[asset_id]['bids'] = [{"price": x[0], "size": x[1]} for x in data.get('buys', [])]
    ```

---

### **5. Logic Preservation (Phase 1.3 & 1.4)**
* **InferenceCore Integrity**: Do **not** modify `inference_core.py`. Ensure the `trigger_inference` method in `main.py` passes the correctly formatted `asks` arrays to the core.
* **Real-Time Friction**: Maintain the `update_gas_prices` loop using **Coinbase** for MATIC pricing to ensure `net_profit` remains accurate.

---

**Success Criteria:**
1. **Full Scan**: Discovery logs show 10,000+ markets processed.
2. **Stable Connection**: WebSocket remains open after sending subscription batches.
3. **Zero-Crash Hot Path**: The engine processes live L2 updates without `KeyError` or dictionary-access exceptions.
4. **Logging**: Valid data populates `missed_opportunities.json` with the schema required for Phase 2.
