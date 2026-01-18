### **Agent Task: Finalize Market Discovery & WebSocket Stability**

**Objective:**
Refactor `atomic_scanner/main.py` to fix the broken pagination loop and stabilize the WebSocket "pipe" by correcting the subscription payload and adding active heartbeats.

---

### **1. Fix Pagination (Correct `next_cursor` Path)**
* **Problem:** The script currently checks `response.get('meta', {}).get('next_cursor')`, causing it to miss all markets beyond the first page.
* **Fix:** Update the pagination logic in `on_open` to retrieve `next_cursor` directly from the root of the response: `next_cursor = response.get('next_cursor')`.
* **Verification:** The scanner should log "Processed 10,000+ markets" during the discovery phase.

### **2. Correct WebSocket Subscription Payload**
* **Problem:** The server drops the connection immediately after the first subscription batch is sent, indicating a rejected frame format.
* **Fix:** For the `market` channel, ensure the subscription message uses uppercase for the type and the correct field for token IDs:
    ```python
    subscription_message = {
        "type": "market",  # Ensure this matches "market" or "MARKET" as per docs
        "assets_ids": batch, # Use assets_ids specifically for the market channel
    }
    ```
* **Batching:** Retain the 500-instrument batching logic to stay within Polymarket's connection limits.

### **3. Implement Active Heartbeats (Pings)**
* **Fix:** Add explicit heartbeat parameters to the `run_forever` call in `run_websocket` to prevent proxy/server timeouts:
    ```python
    self.ws_app.run_forever(ping_interval=20, ping_timeout=10)
    ```

### **4. Update Message Handling**
* **Event Mapping:** Ensure `on_message` is correctly parsing the `event_type: 'book'` messages typically emitted by the public market channel. Use the `asset_id` to route updates to the local order books.

---

**Success Criteria:**
1. The scanner successfully retrieves all market pages (e.g., 10,000+ markets).
2. The WebSocket connection remains open after subscription batches are sent.
3. Live L2 data (bids/asks) begins populating the local state and triggering the `InferenceCore`.
