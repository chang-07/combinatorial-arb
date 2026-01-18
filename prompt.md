### **Agent Task: Implement Full Event Logging for Spectral Clustering Analysis**

**Objective:**
Refactor `atomic_scanner/main.py` to implement **Full Event Logging**. While the scanner currently logs "Net Profitable" opportunities, Phase 2 (Spectral Clustering) requires a dataset of all market refreshes to identify "Logical Neighborhoods"—markets that move together even when they aren't profitable.

---

### **1. Define Event Logging Infrastructure**
* **The Problem:** The current logging is restricted to `missed_opportunities.json` and only triggers when `gross_profit > 0`. This is insufficient for building the **Adjacency Matrix ($A$)** needed for the **Graph Laplacian**, as that requires data on temporal correlations between all market updates.
* **The Fix:** Create a secondary, append-only log file for all valid order book refreshes.

### **2. Implement `log_event` Logic**
* **Log File:** `market_events.json`.
* **Placement:** The logging must occur inside `on_message` immediately after a valid `book` event is parsed but **before** the debounce check. This ensures we capture the high-resolution frequency of updates.
* **Schema Requirements:**
    * `timestamp`: Precise epoch time of the update.
    * `asset_id`: The ID of the token being refreshed.
    * `market_question`: The semantic name of the market.
    * `best_bid`: The top-of-book bid price.
    * `best_ask`: The top-of-book ask price.

### **3. Critical Code Adjustment (Example for `main.py`)**

```python
# In Configuration section
EVENTS_LOG_FILE = "market_events.json"

def log_event(event_data):
    """Logs every order book refresh for Phase 2 correlation analysis."""
    try:
        with open(EVENTS_LOG_FILE, 'a') as f:
            f.write(json.dumps(event_data) + '\n')
    except IOError as e:
        logging.error(f"Event logging error: {e}")

# Inside on_message for event_type == 'book'
asset_id = data.get('asset_id')
if asset_id in self.order_books:
    # ... existing update logic ...
    
    # NEW: Log every refresh event for spectral embedding
    log_event({
        "timestamp": time.time(),
        "asset_id": asset_id,
        "question": self.order_books[asset_id]['question'],
        "best_bid": data.get('buys')[0][0] if data.get('buys') else None,
        "best_ask": data.get('sells')[0][0] if data.get('sells') else None
    })
