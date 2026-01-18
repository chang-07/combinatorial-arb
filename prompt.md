# Task: Fix Polymarket Market Discovery and Token Ingestion Logic

## Context
I am developing a Python-based trading scanner for Polymarket. The system uses a `MarketManager` to discover active markets and then opens a WebSocket connection to the Polymarket CLOB (Central Limit Order Book) to monitor real-time order book updates.

## Current Technical Stack
- **Language:** Python 3
- **APIs:** Polymarket CLOB API (`clob.polymarket.com`)
- **Transport:** `requests` for discovery, `websocket-client` for real-time data.

## The Problem
The current discovery logic is failing in two ways:
1. **Pagination Error:** When iterating through the CLOB `/markets` endpoint using the `next_cursor`, the script eventually hits a `400 Bad Request` when it reaches the terminal cursor (e.g., `next_cursor=LTE=`).
2. **Empty Matches:** Even when the API calls return `200 OK`, the discovery phase concludes with `Cached 0 active tokens`. This suggests the filtering logic is either too strict or is looking at the wrong fields to identify tradable markets.

## Error Logs
```text
2026-01-18 00:08:39,851 - INFO - HTTP Request: GET [https://clob.polymarket.com/markets?next_cursor=MzQ0MDAw](https://clob.polymarket.com/markets?next_cursor=MzQ0MDAw) "HTTP/2 200 OK"
2026-01-18 00:08:40,325 - INFO - HTTP Request: GET [https://clob.polymarket.com/markets?next_cursor=LTE=](https://clob.polymarket.com/markets?next_cursor=LTE=) "HTTP/2 400 Bad Request"
2026-01-18 00:08:40,325 - INFO - Market discovery complete: Reached end of market list.
2026-01-18 00:08:40,326 - INFO - Discovery complete. Cached 0 active tokens.
2026-01-18 00:08:40,328 - WARNING - No markets to subscribe to were found during discovery phase.

To fix the "0 event matches" issue, the discovery logic must be migrated from the CLOB API to the Gamma API. Unlike the CLOB API, which is a raw record of all order book contracts, the Gamma API is optimized for metadata discovery and allows direct filtering for active, tradable events.
Implementation Requirements:

    New Discovery Endpoint: Use https://gamma-api.polymarket.com/events.

    Active Filtering: The request must include query parameters: active=true and closed=false.

    Token ID Extraction: Iterate through the events -> markets list and extract clobTokenIds. This field is usually a stringified JSON list (e.g., '["id1", "id2"]') and must be parsed into a Python list.

    Deduplication: Ensure the final list of Token IDs passed to the WebSocket thread is unique.

```
```
```
```
```
import requests
import json
import logging

def discover_markets(self):
    """
    Replaces CLOB pagination with Gamma API discovery to find active tokens.
    Fixes the '0 event matches' and '400 Bad Request' cursor errors.
    """
    logging.info("Starting market discovery via Gamma API...")
    
    # Gamma API allows filtering for active/open markets directly
    # 'closed=false' ensures we only get currently trading markets
    url = "[https://gamma-api.polymarket.com/events?active=true&closed=false&limit=100](https://gamma-api.polymarket.com/events?active=true&closed=false&limit=100)"
    
    try:
        response = requests.get(url)
        response.raise_for_status()
        events = response.json()
        
        discovered_tokens = []
        for event in events:
            # Each event contains a 'markets' list with the actual tradable instruments
            for market in event.get('markets', []):
                ids_str = market.get('clobTokenIds')
                if ids_str:
                    # clobTokenIds is returned as a stringified list by Gamma API
                    try:
                        token_ids = json.loads(ids_str)
                        if isinstance(token_ids, list):
                            discovered_tokens.extend(token_ids)
                    except (json.JSONDecodeError, TypeError) as e:
                        logging.debug(f"Failed to parse token IDs: {ids_str}")
                        continue
        
        # Deduplicate the list to avoid redundant WebSocket subscriptions
        self.active_tokens = list(set(discovered_tokens))
        logging.info(f"Discovery complete. Found {len(self.active_tokens)} active tokens.")
        
        if not self.active_tokens:
            logging.warning("No active markets found. Verify your IP is not geo-blocked.")
            
        return self.active_tokens

    except Exception as e:
        logging.error(f"Discovery failed: {e}")
        return []
```
```
```
