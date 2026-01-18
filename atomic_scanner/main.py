import time
import logging
import os
import json
import asyncio
from decimal import Decimal, InvalidOperation
import requests
import websocket
import threading
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
TARGET_SIZE_USD = Decimal('500.0')
EXCHANGE_FEE_PERCENT = Decimal('0.001')  # 0.1%

class MarketManager:
    def __init__(self, client: ClobClient, inference_core: InferenceCore):
        self.client = client
        self.inference_core = inference_core
        self.order_books = {}
        self.last_update_times = {}
        self.debounce_period = 0.5  # 500ms
        self.gas_price_gwei = None
        self.total_gas_cost_usd = None
        self.ws_app = None
        self.ws_thread = None
        self.reconnect_interval = 5  # Initial reconnect interval in seconds
        self.reconnect_attempts = 0
        self.max_reconnect_interval = 60  # Maximum reconnect interval
        self.gas_refreshes = 0
        self.market_ids_to_subscribe = []

    def discover_markets(self):
        """
        Paginates through all markets to find CLOB-compatible ones before connecting to WebSocket.
        """
        logging.info("Starting market discovery...")
        next_cursor = ""
        total_seen = 0
        
        while True:
            try:
                response = self.client.get_markets(next_cursor=next_cursor)
            except Exception as e:
                logging.error(f"Failed to fetch markets at cursor '{next_cursor}': {e}")
                break

            if not response or not response.get('data'):
                break

            markets_in_page = response['data']
            total_seen += len(markets_in_page)

            for market in markets_in_page:
                is_closed = market.get('closed', False)
                tokens = market.get('tokens', [])
                
                if not is_closed and len(tokens) == 2:
                    t0_id = tokens[0].get('clobTokenId') or tokens[0].get('token_id')
                    t1_id = tokens[1].get('clobTokenId') or tokens[1].get('token_id')
                    
                    if t0_id and t1_id:
                        self.market_ids_to_subscribe.append(t0_id)
                        self.market_ids_to_subscribe.append(t1_id)
                        # Link tokens directly to avoid metadata lookups in the Hot Path
                        self.order_books[t0_id] = {"bids": [], "asks": [], "other_side": t1_id, "is_yes": True, "question": market.get("question")}
                        self.order_books[t1_id] = {"bids": [], "asks": [], "other_side": t0_id, "is_yes": False, "question": market.get("question")}

            next_cursor = response.get('next_cursor')
            if not next_cursor or next_cursor.lower() == "none":
                logging.info("Finished fetching all market pages.")
                break
        
        self.market_ids_to_subscribe = list(set(self.market_ids_to_subscribe))
        logging.info(f"Market discovery complete: Found {total_seen} markets, yielding {len(self.market_ids_to_subscribe)} CLOB tokens.")

    def start(self):
        """
        Starts the WebSocket connection thread.
        """
        logging.info("MarketManager: Starting WebSocket thread...")
        self.ws_thread = threading.Thread(target=self.run_websocket)
        self.ws_thread.daemon = True
        self.ws_thread.start()
        logging.info("MarketManager: WebSocket thread started.")


    def run_websocket(self):
        logging.info("MarketManager: run_websocket method executing in new thread.")
        if not API_KEY or not API_SECRET or not API_PASSPHRASE:
            logging.warning("Polymarket API keys not found. Running in Read-Only/Public Mode.")
        
        furl = WEBSOCKET_URL + "/ws/market"
        
        while True:
            self.ws_app = websocket.WebSocketApp(
                furl,
                on_open=self.on_open,
                on_message=self.on_message,
                on_error=self.on_error,
                on_close=self.on_close
            )
            try:
                self.ws_app.run_forever(ping_interval=20, ping_timeout=10)
            except Exception as e:
                logging.error(f"WebSocket run_forever() failed with exception: {e}")

            # Exponential backoff
            self.reconnect_attempts += 1
            wait_time = min(self.reconnect_interval * (2 ** self.reconnect_attempts), self.max_reconnect_interval)
            logging.info(f"WebSocket connection lost. Attempting to reconnect in {wait_time} seconds...")
            time.sleep(wait_time)

    def on_open(self, ws):
        logging.info("WebSocket connection opened.")
        self.reconnect_attempts = 0

        if not self.market_ids_to_subscribe:
            logging.warning("No markets to subscribe to were found during discovery phase.")
            return

        # Batch subscription requests
        chunk_size = 500
        delay_between_batches = 0.1
        total_tokens = len(self.market_ids_to_subscribe)
        
        logging.info(f"Subscribing to {total_tokens} tokens in batches...")
        for i in range(0, total_tokens, chunk_size):
            batch = self.market_ids_to_subscribe[i:i + chunk_size]
            subscription_message = {
                "type": "market",
                "assets_ids": batch,
            }
            ws.send(json.dumps(subscription_message))
            if total_tokens > chunk_size:
                time.sleep(delay_between_batches)
        
        logging.info("Finished sending all subscription requests.")

    def on_message(self, ws, message):
        data = json.loads(message)
        if data.get('event_type') == 'book':
            asset_id = data.get('asset_id')
            if asset_id in self.order_books:
                # Polymarket L2 format is [price, size]
                self.order_books[asset_id]['asks'] = [{"price": x[0], "size": x[1]} for x in data.get('sells', [])]
                self.order_books[asset_id]['bids'] = [{"price": x[0], "size": x[1]} for x in data.get('buys', [])]
                
                now = time.time()
                last_update = self.last_update_times.get(asset_id, 0)
                if now - last_update > self.debounce_period:
                    self.last_update_times[asset_id] = now
                    self.trigger_inference(asset_id)

    def on_error(self, ws, error):
        logging.error(f"WebSocket error: {error}")

    def on_close(self, ws, close_status_code, close_msg):
        logging.info(f"WebSocket connection closed: {close_status_code} - {close_msg}")

    def trigger_inference(self, market_id):
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
                log_opportunity(opportunity_data)
                if net_profit > 0:
                    logging.warning(f"NET PROFITABLE ARBITRAGE FOUND: {market_data.get('question')}")
                    logging.warning(json.dumps(opportunity_data, indent=2))

    async def update_gas_prices(self):
        while True:
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

async def main():
    logging.info("Starting atomic scanner...")
    client = ClobClient(HOST, chain_id=CHAIN_ID, creds=None)
    inference_core = InferenceCore()
    
    # 1. Create manager instance
    market_manager = MarketManager(client, inference_core)
    
    # 2. Perform blocking market discovery first
    market_manager.discover_markets()
    
    # 3. Start the WebSocket thread for real-time data
    market_manager.start()
    
    # 4. Start the gas price updater task
    gas_updater_task = asyncio.create_task(market_manager.update_gas_prices())
    
    try:
        await gas_updater_task
    except KeyboardInterrupt:
        logging.info("Scanner stopped by user.")
        if market_manager.ws_app:
            market_manager.ws_app.close()

if __name__ == "__main__":
    asyncio.run(main())
