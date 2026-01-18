### **Agent Task: Resolve WebSocket Pipe Breaks & Subscription Overload**

**Objective:** Fix the connectivity issues in `atomic_scanner/main.py` by implementing **Subscription Batching** and **Connection Heartbeats**. The scanner currently fails because it sends too many subscription requests in rapid succession during the market discovery phase.

---

### **1. Move Subscription Logic (The "One-Shot" Fix)**
* **Problem:** The subscription code is currently inside the pagination loop, causing multiple massive requests to fire.
* **Fix:** Move the `subscription_message` and `ws.send()` logic in `on_open` to be **after** the `while True` loop. The engine must collect ALL `market_ids` first, then send a single subscription request for the entire set.

### **2. Implement Subscription Batching**
* **Constraint:** Polymarket limits subscriptions to **500 instruments per connection**. 
* **Logic:** In `on_open`, if `len(market_ids) > 500`, the script must split the IDs into chunks of 500 and send them with a small delay (e.g., 0.1s) between each `ws.send()` to avoid triggering rate-limiters.

### **3. Add Connection Heartbeats (Pings)**
* **Problem:** Anonymous connections are often dropped by the server or intermediate proxies if no data is sent for 30–60 seconds.
* **Fix:** Update the `run_forever()` call in `run_websocket` to include heartbeats:
    ```python
    self.ws_app.run_forever(ping_interval=30, ping_timeout=10)
    ```

### **4. Error Handling & Reconnection**
* **Graceful Close:** Update `on_close` to log the specific error code. If a `1006` (Abnormal Closure) is detected, ensure the exponential backoff logic is properly triggered.
* **Filter Refinement:** To reduce the initial load, prioritize markets with the highest volume or activity first to stay well under the 500-instrument limit per pipe.

---

**Success Criteria:**
1. The scanner completes the 10,000+ market scan without the WebSocket closing.
2. Only one set of batched subscription messages is sent to the server.
3. The connection remains stable for 10+ minutes with active "ping/pong" logs.
