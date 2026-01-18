### **Agent Task: Implement Heuristic Pruning & Market Caching**

**Objective:**
Refactor `atomic_scanner/main.py` to implement **Heuristic Pruning** and **Market Caching**. This will reduce the WebSocket subscription load from 52,000+ tokens to a high-velocity subset based on 24h volume, while eliminating redundant discovery scans upon reconnection.

---

### **1. Volume-Based Heuristic Pruning**
* **The Problem**: Monitoring the entire "firehose" of 52,000+ tokens causes significant processing lag and "slow activity" logs during low-volatility periods.
* **The Fix**: Filter markets during `discover_markets` using the `volume_24h` field.
* **Critical Logic**:
    * Define a `MIN_VOLUME_THRESHOLD = Decimal('1000.0')`.
    * Only add tokens to `self.market_ids_to_subscribe` if `Decimal(str(market.get('volume_24h', 0))) >= MIN_VOLUME_THRESHOLD`.

### **2. Implement Discovery Caching**
* **The Problem**: The scanner performs a full ~344,000 market scan every time the WebSocket connection resets, leading to minutes of downtime.
* **The Fix**: Save the `market_ids_to_subscribe` and `order_books` state to a local JSON file (`market_cache.json`) and load it on startup if the cache is < 1 hour old.

---

### **3. Implementation Details for `discover_markets`**

```python
# Constants to be added to Configuration section
MIN_VOLUME_THRESHOLD = Decimal('1000.0')
CACHE_FILE = "market_cache.json"
CACHE_TTL = 3600  # 1 hour

def discover_markets(self):
    """
    Paginates with volume-based pruning and cache checks.
    """
    # 1. Check for valid cache
    if os.path.exists(CACHE_FILE):
        if time.time() - os.path.getmtime(CACHE_FILE) < CACHE_TTL:
            with open(CACHE_FILE, 'r') as f:
                cache = json.load(f)
                self.market_ids_to_subscribe = cache['ids']
                self.order_books = cache['books']
                logging.info(f"Loaded {len(self.market_ids_to_subscribe)} tokens from cache.")
                return

    logging.info("Starting fresh market discovery with volume pruning...")
    next_cursor = ""
    # ... (existing pagination loop logic)

    # Inside the loop, replace current filtering with:
    volume_24h = Decimal(str(market.get('volume_24h', 0)))
    if not is_closed and len(tokens) == 2 and volume_24h >= MIN_VOLUME_THRESHOLD:
        # (Add to subscribe list and link order_books as currently implemented)

    # 2. After loop finishes, save to cache
    cache_data = {
        "ids": self.market_ids_to_subscribe,
        "books": self.order_books
    }
    with open(CACHE_FILE, 'w') as f:
        json.dump(cache_data, f)
    logging.info(f"Discovery complete. Cached {len(self.market_ids_to_subscribe)} active tokens.")
