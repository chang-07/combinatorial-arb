### **Agent Task: Fix Market Discovery with Pagination**

**Objective:**
Update `atomic_scanner/main.py` to ensure the scanner finds all available CLOB markets. The current implementation only fetches the first page of market data, causing it to miss critical trading opportunities.

---

### **1. Pagination Implementation**
* **Loop through All Pages:** Refactor the `on_open` method in the `MarketManager` class to use a `while True` loop. 
* **Correct Parameter Name:** Use `next_cursor` as the keyword argument in `self.client.get_markets(next_cursor=...)`. Do **not** use `cursor`, as it causes an "unexpected keyword argument" error.
* **Termination Condition:** The loop must break when the API response no longer contains a `next_cursor` or when the `data` list is empty.

### **2. Enhanced Filtering**
* **Active Market Validation:** Within the loop, ensure markets are only added to the subscription list if:
    1. `accepting_orders` is `True`.
    2. `closed` is `False`.
    3. The market has exactly `2` tokens with valid `clobTokenId` values.
* **State Initialization:** Properly initialize `self.order_books` for every discovered `token0` and `token1` to prevent `KeyError` during WebSocket updates.

### **3. Anonymous WebSocket Integrity**
* **Maintain Public Mode:** Ensure the `on_open` method still sends the standard public subscription message: `{"type": "subscribe", "channel": "market", "markets": [market_ids]}`.
* **Logging:** Add a log statement indicating how many total markets were found and subscribed to after the full pagination scan completes.

---

**Success Criteria:**
1. The scanner successfully retrieves multiple pages of markets from the Polymarket API.
2. The error regarding the `cursor` argument is resolved by using `next_cursor`.
3. The scanner logs a high volume of subscriptions (e.g., "Subscribed to 400+ order books") instead of zero or a single page's worth.

# Example on_open(self,ws):
def on_open(self, ws):
        logging.info("WebSocket connection opened. Fetching all active markets...")
        market_ids = []
        next_cursor = ""
        
        while True:
            try:
                # Use next_cursor for pagination; empty string for the first page
                response = self.client.get_markets(next_cursor=next_cursor)
            except Exception as e:
                logging.error(f"Failed to fetch markets at cursor '{next_cursor}': {e}")
                break

            if not response or not response.get('data'):
                break

            for market in response['data']:
                # Filter for active, non-closed markets with exactly 2 tokens
                if (market.get('accepting_orders') and 
                    not market.get('closed') and 
                    len(market.get('tokens', [])) == 2):
                    
                    token0_id = market['tokens'][0]['clobTokenId']
                    token1_id = market['tokens'][1]['clobTokenId']
                    
                    if token0_id and token1_id:
                        market_ids.append(token0_id)
                        market_ids.append(token1_id)
                        # Initialize local order book state
                        self.order_books[token0_id] = {"bids": [], "asks": [], "market_info": market}
                        self.order_books[token1_id] = {"bids": [], "asks": [], "market_info": market}

            # Check if there is another page
            next_cursor = response.get('next_cursor')
            if not next_cursor:
                break
        
        if not market_ids:
            logging.warning("No CLOB-compatible markets found after full scan.")
            return

        subscription_message = {
            "type": "subscribe",
            "channel": "market",
            "markets": market_ids,
        }
        ws.send(json.dumps(subscription_message))
        logging.info(f"Subscribed to {len(market_ids)} order books across {len(market_ids)//2} markets.")
