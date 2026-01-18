# Task: Optimize WebSocket Performance to Fix Infrequent Refreshes

## Context
The `atomic_scanner` is experiencing "bursty" behavior where multiple assets refresh at the exact same millisecond, followed by long periods of silence (up to 36 seconds). This suggests that the WebSocket client is not consuming messages in real-time, causing the OS buffer to fill up or the server to throttle the connection.

## The Problem: Blocking I/O and Synchronous Processing
The current `on_message` handler in `MarketManager` is performing several blocking operations that stop the WebSocket from reading the next packet:
1. **Disk I/O in `log_event`**: On *every single refresh*, the script opens, writes, and closes `market_events.json`. This is a high-latency operation.
2. **Disk I/O in `log_opportunity`**: Profitable checks perform additional blocking writes.
3. **Synchronous Callback**: The `websocket-client` library runs in a single thread. When `on_message` is busy writing to a file, it cannot acknowledge or receive new data from the socket.

## Solution: Pure Async Architecture and Background Logging
To achieve real-time refreshes, the system must be refactored to:
1. **Switch to `websockets` (Async)**: Replace the threaded `websocket-client` with a native `asyncio` implementation to integrate with the existing event loop.
2. **Asynchronous Logging**: Move file writing to a background task using `asyncio.Queue`. The WebSocket should just "drop" the data into a queue and move on immediately.
3. **Decouple Processing**: Offload the inference logic so the socket receiver never waits for math or disk writes.

## Fixed Code Implementation (Refactor for main.py)

### 1. The Async Logger (Add to main.py)
```python
import aiofiles # You may need to add this to requirements.txt

class AsyncLogger:
    def __init__(self, filename):
        self.filename = filename
        self.queue = asyncio.Queue()

    async def log(self, data):
        await self.queue.put(data)

    async def run_worker(self):
        while True:
            data = await self.queue.get()
            async with aiofiles.open(self.filename, mode='a') as f:
                await f.write(json.dumps(data) + '\n')
            self.queue.task_done()


import websockets

class MarketManager:
    def __init__(self, client, inference_core):
        # ... existing init ...
        self.event_logger = AsyncLogger(EVENTS_LOG_FILE)
        self.opp_logger = AsyncLogger(OPPORTUNITIES_LOG_FILE)

    async def run_websocket(self):
        uri = f"{WEBSOCKET_URL}/ws/market"
        async for websocket in websockets.connect(uri):
            try:
                # 1. Subscribe
                subscription_message = {
                    "type": "market",
                    "assets_ids": self.market_ids_to_subscribe,
                }
                await websocket.send(json.dumps(subscription_message))
                
                # 2. Consume Messages
                async for message in websocket:
                    await self.handle_message(message)
            except websockets.ConnectionClosed:
                logging.warning("WebSocket lost. Reconnecting...")
                continue

    async def handle_message(self, message):
        data_payload = json.loads(message)
        events = data_payload if isinstance(data_payload, list) else [data_payload]

        for data in events:
            if data.get('event_type') == 'book':
                asset_id = data.get('asset_id')
                # Update local book (Memory operation - fast)
                self.order_books[asset_id]['asks'] = [{"price": x[0], "size": x[1]} for x in data.get('sells', [])]
                self.order_books[asset_id]['bids'] = [{"price": x[0], "size": x[1]} for x in data.get('buys', [])]
                
                # Background Log (Non-blocking)
                asyncio.create_task(self.event_logger.log({
                    "timestamp": time.time(),
                    "asset_id": asset_id,
                    "best_bid": data.get('buys')[0][0] if data.get('buys') else None
                }))

                # Trigger Hot Path (Non-blocking)
                asyncio.create_task(self.trigger_inference_async(asset_id))

    async def trigger_inference_async(self, asset_id):
        # Move the trigger_inference logic here, making sure 
        # calls to log_opportunity use self.opp_logger.log()
        pass

```