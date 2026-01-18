import asyncio
import websockets
import json

async def test_websocket():
    uri = "wss://ws-subscriptions-clob.polymarket.com/ws/"
    try:
        async with websockets.connect(uri) as websocket:
            print(f"Connected to {uri}")
            
            # Example subscription
            await websocket.send(json.dumps({
                "type": "subscribe",
                "channel": "order_book",
                "market": "0x99924235c3c674a4185642d4b2099d020b12a6f3c5130b47b6202caf3612a1e9" # Example market
            }))
            print("Sent subscription request")

            while True:
                message = await websocket.recv()
                print(f"Received message: {message}")

    except websockets.exceptions.InvalidStatus as e:
        print(f"Failed to connect: {e}")
    except Exception as e:
        print(f"An error occurred: {e}")

if __name__ == "__main__":
    asyncio.run(test_websocket())
