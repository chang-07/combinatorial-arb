# Task: Restore Console Logging for Market Refreshes

## Context
The `atomic_scanner` was recently refactored to an asynchronous architecture to resolve performance bottlenecks. During this process, the console logging for order book refreshes was removed to prioritize ingestion speed. The scanner is working correctly in the background, but the terminal is now silent, making it difficult to monitor live activity.

## Objective
Add real-time console logging back to the `MarketManager` in `atomic_scanner/main.py`. The logging must be implemented without blocking the main WebSocket receiver loop.

## Requirements
1. **Location**: Modify the `handle_event` method in `atomic_scanner/main.py`.
2. **Implementation**: 
    - Re-insert a `logging.info()` statement that triggers whenever a `book` event is processed.
    - Ensure the log includes the `asset_id` to maintain consistency with previous versions.
3. **Performance Preservation**: The log statement should remain inside the `handle_event` method, which is already being executed as a non-blocking `asyncio.task`.

## Proposed Code Change
In `atomic_scanner/main.py`, update the `handle_event` method:

```python
async def handle_event(self, data):
    """Processes a single event without blocking the socket."""
    if data.get('event_type') == 'book':
        asset_id = data.get('asset_id')
        
        # --- RESTORED LOGGING ---
        logging.info(f"CLOB for asset {asset_id} refreshed.")
        # ------------------------

        # Existing logic
        self.order_books[asset_id]['asks'] = [{"price": x[0], "size": x[1]} for x in data.get('sells', [])]
        self.order_books[asset_id]['bids'] = [{"price": x[0], "size": x[1]} for x in data.get('buys', [])]
        
        await self.log_queue.put((EVENTS_LOG_FILE, {"timestamp": time.time(), "asset_id": asset_id}))
        asyncio.create_task(self.trigger_inference_async(asset_id))
