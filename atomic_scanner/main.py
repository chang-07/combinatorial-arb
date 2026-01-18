import ssl
import time
import logging
import os
import json
import asyncio
from decimal import Decimal, InvalidOperation
import requests
import websockets
import aiofiles
from py_clob_client.client import ClobClient
from inference_core import InferenceCore
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# --- Configuration ---
HOST = "https://clob.polymarket.com"
CHAIN_ID = 137  # Polygon Mainnet
WEBSOCKET_URL = "wss://ws-subscriptions-clob.polymarket.com"
POLYGON_GAS_STATION_URL = "https://gasstation.polygon.technology/v2"
API_KEY = os.environ.get("POLYMARKET_API_KEY")
API_SECRET = os.environ.get("POLYMARKET_API_SECRET")
API_PASSPHRASE = os.environ.get("POLYMARKET_API_PASSPHRASE")
OPPORTUNITIES_LOG_FILE = "missed_opportunities.json"
EVENTS_LOG_FILE = "market_events.json"
TARGET_SIZE_USD = Decimal('500.0')
EXCHANGE_FEE_PERCENT = Decimal('0.001')  # 0.1%
MIN_VOLUME_THRESHOLD = Decimal('1.0')
CACHE_FILE = "market_cache.json"
CACHE_TTL = 3600  # 1 hour

class MarketManager:
    def __init__(self, client: ClobClient, inference_core: InferenceCore):
        self.client = client
        self.inference_core = inference_core
        self.order_books = {}
        self.last_update_times = {}
        self.debounce_period = 0.5  # 500ms
        self.gas_price_gwei = None
        self.total_gas_cost_usd = None
        self.log_queue = asyncio.Queue()
        self.market_ids_to_subscribe = []
        self.gas_refreshes = 0

    def discover_markets(self):
        """
        Replaces CLOB pagination with Gamma API discovery to find active tokens.
        Fixes the '0 event matches' and '400 Bad Request' cursor errors.
        """
        logging.info("Starting market discovery via Gamma API...")
        
        # Gamma API allows filtering for active/open markets directly
        # 'closed=false' ensures we only get currently trading markets
        url = "https://gamma-api.polymarket.com/events?active=true&closed=false&limit=100"
        
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
                            if isinstance(token_ids, list) and len(token_ids) == 2:
                                discovered_tokens.extend(token_ids)
                                t0_id = token_ids[0]
                                t1_id = token_ids[1]
                                self.order_books[t0_id] = {"bids": [], "asks": [], "other_side": t1_id, "is_yes": True, "question": event.get("question")}
                                self.order_books[t1_id] = {"bids": [], "asks": [], "other_side": t0_id, "is_yes": False, "question": event.get("question")}
                        except (json.JSONDecodeError, TypeError) as e:
                            logging.debug(f"Failed to parse token IDs: {ids_str}")
                            continue
            
            # Deduplicate the list to avoid redundant WebSocket subscriptions
            self.market_ids_to_subscribe = list(set(discovered_tokens))
            logging.info(f"Discovery complete. Found {len(self.market_ids_to_subscribe)} active tokens.")
            
            if not self.market_ids_to_subscribe:
                logging.warning("No active markets found. Verify your IP is not geo-blocked.")
                
        except Exception as e:
            logging.error(f"Discovery failed: {e}")

    def start(self):
        """
        Replaces CLOB pagination with Gamma API discovery to find active tokens.
        Fixes the '0 event matches' and '400 Bad Request' cursor errors.
        """
        logging.info("Starting market discovery via Gamma API...")
        
        # Gamma API allows filtering for active/open markets directly
        # 'closed=false' ensures we only get currently trading markets
        url = "https://gamma-api.polymarket.com/events?active=true&closed=false&limit=100"
        
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
                            if isinstance(token_ids, list) and len(token_ids) == 2:
                                discovered_tokens.extend(token_ids)
                                t0_id = token_ids[0]
                                t1_id = token_ids[1]
                                self.order_books[t0_id] = {"bids": [], "asks": [], "other_side": t1_id, "is_yes": True, "question": event.get("question")}
                                self.order_books[t1_id] = {"bids": [], "asks": [], "other_side": t0_id, "is_yes": False, "question": event.get("question")}
                        except (json.JSONDecodeError, TypeError) as e:
                            logging.debug(f"Failed to parse token IDs: {ids_str}")
                            continue
            
            # Deduplicate the list to avoid redundant WebSocket subscriptions
            self.market_ids_to_subscribe = list(set(discovered_tokens))
            logging.info(f"Discovery complete. Found {len(self.market_ids_to_subscribe)} active tokens.")
            
            if not self.market_ids_to_subscribe:
                logging.warning("No active markets found. Verify your IP is not geo-blocked.")
                
        except Exception as e:
            logging.error(f"Discovery failed: {e}")

    async def run_websocket(self):
        """Async WebSocket consumer."""
        uri = f"{WEBSOCKET_URL}/ws/market"
        async for websocket in websockets.connect(uri):
            try:
                # Subscription logic
                sub_msg = {"type": "market", "assets_ids": self.market_ids_to_subscribe}
                await websocket.send(json.dumps(sub_msg))
                
                async for message in websocket:
                    data = json.loads(message)
                    # Offload processing to background
                    asyncio.create_task(self.handle_event(data))
            except Exception as e:
                logging.error(f"WS Error: {e}")
                await asyncio.sleep(5)

    async def handle_event(self, data):
        """Processes a single event without blocking the socket."""
        if data.get('event_type') == 'book':
            asset_id = data.get('asset_id')
            
            # --- RESTORED LOGGING ---
            logging.info(f"CLOB for asset {asset_id} refreshed.")
            # ------------------------

        for data in events:
            if data.get('event_type') == 'book':
                asset_id = data.get('asset_id')
                if asset_id in self.order_books:
                    self.order_books[asset_id]['asks'] = [{"price": x[0], "size": x[1]} for x in data.get('sells', [])]
                    self.order_books[asset_id]['bids'] = [{"price": x[0], "size": x[1]} for x in data.get('buys', [])]
                    logging.info(f"CLOB for asset {asset_id} refreshed.")
                    
                    # NEW: Log every refresh event for spectral embedding
                    log_event({
                        "timestamp": time.time(),
                        "asset_id": asset_id,
                        "question": self.order_books[asset_id]['question'],
                        "best_bid": data.get('buys')[0][0] if data.get('buys') else None,
                        "best_ask": data.get('sells')[0][0] if data.get('sells') else None
                    })

                    # Trigger Hot Path via debounce
                    now = time.time()
                    if now - self.last_update_times.get(asset_id, 0) > self.debounce_period:
                        self.last_update_times[asset_id] = now
                        self.trigger_inference(asset_id)

    def on_error(self, ws, error):
        logging.error(f"WebSocket error: {error}")

    def on_close(self, ws, close_status_code, close_msg):
        logging.info(f"WebSocket connection closed: {close_status_code} - {close_msg}")

    async def trigger_inference_async(self, market_id):
        if not self.total_gas_cost_usd:
            return

        market_data = self.order_books.get(market_id)
        if not market_data:
            return

        other_side_id = market_data.get("other_side")
        if not other_side_id or other_side_id not in self.order_books:
            return
            
        other_side_market_data = self.order_books.get(other_side_id)

        if market_data["is_yes"]:
            book_yes = market_data['asks']
            book_no = other_side_market_data['asks']
        else:
            book_yes = other_side_market_data['asks']
            book_no = market_data['asks']

        if not book_yes or not book_no:
            return

        result = self.inference_core.calculate_net_profit(
            target_size=TARGET_SIZE_USD,
            book_yes=book_yes,
            book_no=book_no,
            gas_usd=self.total_gas_cost_usd,
            exchange_fee_percent=EXCHANGE_FEE_PERCENT
        )

        if result:
            net_profit, gross_profit, wap_yes, wap_no = result
            if gross_profit > 0:
                opportunity_data = {
                    "timestamp": time.time(),
                    "market_question": market_data.get("question"),
                    "wap_yes": f"{wap_yes:.4f}",
                    "wap_no": f"{wap_no:.4f}",
                    "gas_price_gwei": f"{self.gas_price_gwei:.4f}",
                    "total_cost_usd": f"{self.total_gas_cost_usd:.4f}",
                    "gross_profit_usd": f"{gross_profit:.4f}",
                    "net_profit_usd": f"{net_profit:.4f}",
                }
                await self.log_queue.put((OPPORTUNITIES_LOG_FILE, opportunity_data))
                if net_profit > 0:
                    logging.warning(f"NET PROFITABLE ARBITRAGE FOUND: {market_data.get('question')}")
                    logging.warning(json.dumps(opportunity_data, indent=2))

    async def update_gas_prices(self):
        while True:
            logging.info("Refreshing gas prices...")
            try:
                response = requests.get(POLYGON_GAS_STATION_URL)
                response.raise_for_status()
                gas_data = response.json()
                max_priority_fee = Decimal(gas_data['fast']['maxPriorityFee'])
                estimated_base_fee = Decimal(gas_data['estimatedBaseFee'])
                self.gas_price_gwei = max_priority_fee + estimated_base_fee

                matic_price_usd = self.get_matic_price_usd()
                if matic_price_usd:
                    self.gas_refreshes += 1
                    gas_limit_per_tx = Decimal('200000')
                    num_transactions = 2
                    total_gas_cost_gwei = self.gas_price_gwei * gas_limit_per_tx * num_transactions
                    total_gas_cost_matic = total_gas_cost_gwei / Decimal('1000000000')
                    self.total_gas_cost_usd = total_gas_cost_matic * matic_price_usd
                    logging.info(f"Updated gas cost: ${self.total_gas_cost_usd:.4f} (Refresh #{self.gas_refreshes})")
            except (requests.exceptions.RequestException, KeyError, InvalidOperation) as e:
                logging.error(f"Failed to update gas prices: {e}")
            
            await asyncio.sleep(60)

    def get_matic_price_usd(self):
        """Fetches MATIC price from Coinbase."""
        url = "https://api.coinbase.com/v2/prices/MATIC-USD/spot"
        try:
            response = requests.get(url)
            response.raise_for_status()
            data = response.json()
            logging.info(f"Coinbase API Response: {json.dumps(data, indent=2)}")
            return Decimal(data['data']['amount'])
        except (requests.exceptions.RequestException, KeyError, InvalidOperation) as e:
            logging.error(f"Failed to fetch MATIC price from Coinbase: {e}")
            return None

def log_opportunity(opportunity_data):
    """Logs a profitable opportunity to a JSON file."""
    try:
        with open(OPPORTUNITIES_LOG_FILE, 'a') as f:
            f.write(json.dumps(opportunity_data) + '\n')
    except IOError as e:
        logging.error(f"Error writing to opportunities log: {e}")

def log_event(event_data):
    """Logs every order book refresh for Phase 2 correlation analysis."""
    try:
        with open(EVENTS_LOG_FILE, 'a') as f:
            f.write(json.dumps(event_data) + '\n')
    except IOError as e:
        logging.error(f"Event logging error: {e}")

async def main():
    logging.info("Starting atomic scanner...")
    client = ClobClient(HOST, chain_id=CHAIN_ID, creds=None)
    inference_core = InferenceCore()
    
    # 1. Create manager instance
    market_manager = MarketManager(client, inference_core)
    
    # 2. Perform blocking market discovery first
    market_manager.discover_markets()
    
    # 3. Start logger worker
    log_worker_task = asyncio.create_task(market_manager.log_worker())

    # 4. Start WebSocket and gas price updater tasks
    ws_task = asyncio.create_task(market_manager.run_websocket())
    gas_updater_task = asyncio.create_task(market_manager.update_gas_prices())
    
    try:
        await asyncio.gather(ws_task, gas_updater_task, log_worker_task)
    except KeyboardInterrupt:
        logging.info("Scanner stopped by user.")

if __name__ == "__main__":
    asyncio.run(main())