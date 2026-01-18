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

    def start(self):
        self.ws_thread = threading.Thread(target=self.run_websocket)
        self.ws_thread.daemon = True
        self.ws_thread.start()

    def run_websocket(self):
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
                self.ws_app.run_forever()
            except Exception as e:
                logging.error(f"WebSocket run_forever() failed with exception: {e}")

            # Exponential backoff
            self.reconnect_attempts += 1
            wait_time = min(self.reconnect_interval * (2 ** self.reconnect_attempts), self.max_reconnect_interval)
            logging.info(f"WebSocket connection lost. Attempting to reconnect in {wait_time} seconds...")
            time.sleep(wait_time)



    def on_open(self, ws):
        logging.info("WebSocket connection opened. Fetching all active markets...")
        self.reconnect_attempts = 0
        market_ids = []
        next_cursor = ""  # Start with an empty cursor for the first page
        
        while True:
            try:
                # Use next_cursor for pagination
                response = self.client.get_markets(next_cursor=next_cursor)
            except Exception as e:
                logging.error(f"Failed to fetch markets at cursor '{next_cursor}': {e}")
                break

            if not response or not response.get('data'):
                logging.info("No market data in response.")
                break

            for market in response['data']:
                # Filter for active, non-closed markets with exactly 2 tokens
                if (market.get('accepting_orders') and 
                    not market.get('closed') and 
                    len(market.get('tokens', [])) == 2):
                    
                    token0 = market.get('tokens', [{}])[0]
                    token1 = market.get('tokens', [{}])[1]

                    token0_id = token0.get('clobTokenId')
                    token1_id = token1.get('clobTokenId')
                    
                    if token0_id and token1_id:
                        market_ids.append(token0_id)
                        market_ids.append(token1_id)
                        # Initialize local order book state
                        self.order_books[token0_id] = {"bids": [], "asks": [], "market_info": market}
                        self.order_books[token1_id] = {"bids": [], "asks": [], "market_info": market}

            # Check if there is another page
            next_cursor = response.get('meta', {}).get('next_cursor')
            if not next_cursor:
                logging.info("Finished fetching all market pages.")
                break
        
        if not market_ids:
            logging.warning("No CLOB-compatible markets found after full scan.")
            return

        subscription_message = {
            "type": "subscribe",
            "channel": "market",
            "markets": list(set(market_ids)), # Use set to ensure unique token IDs
        }
        ws.send(json.dumps(subscription_message))
        logging.info(f"Subscribed to {len(set(market_ids))} order books across {len(set(market_ids))//2} markets.")

    def on_message(self, ws, message):
        data = json.loads(message)
        if data.get('channel') == 'market' and 'market' in data:
            market_id = data['market']
            if market_id in self.order_books:
                self.order_books[market_id].update(data['data'])
                
                now = time.time()
                last_update = self.last_update_times.get(market_id, 0)
                if now - last_update > self.debounce_period:
                    self.last_update_times[market_id] = now
                    self.trigger_inference(market_id)

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
            
        parent_market_info = market_data['market_info']
        tokens = parent_market_info['tokens']
        token0_id = tokens[0]['clobTokenId']
        token1_id = tokens[1]['clobTokenId']

        if token0_id not in self.order_books or token1_id not in self.order_books:
            return

        book_yes = self.order_books[token0_id]['asks']
        book_no = self.order_books[token1_id]['asks']

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
                    "market_id": parent_market_info.get("id"),
                    "market_question": parent_market_info.get("question"),
                    "wap_yes": f"{wap_yes:.4f}",
                    "wap_no": f"{wap_no:.4f}",
                    "gas_price_gwei": f"{self.gas_price_gwei:.4f}",
                    "total_cost_usd": f"{self.total_gas_cost_usd:.4f}",
                    "gross_profit_usd": f"{gross_profit:.4f}",
                    "net_profit_usd": f"{net_profit:.4f}",
                }
                log_opportunity(opportunity_data)
                if net_profit > 0:
                    logging.warning(f"NET PROFITABLE ARBITRAGE FOUND: {parent_market_info.get('question')}")
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
                    gas_limit_per_tx = Decimal('200000')
                    num_transactions = 2
                    total_gas_cost_gwei = self.gas_price_gwei * gas_limit_per_tx * num_transactions
                    total_gas_cost_matic = total_gas_cost_gwei / Decimal('1000000000')
                    self.total_gas_cost_usd = total_gas_cost_matic * matic_price_usd
                    logging.info(f"Updated gas cost: ${self.total_gas_cost_usd:.4f}")
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
    market_manager = MarketManager(client, inference_core)
    
    market_manager.start()
    
    gas_updater_task = asyncio.create_task(market_manager.update_gas_prices())
    
    try:
        await gas_updater_task
    except KeyboardInterrupt:
        logging.info("Scanner stopped by user.")
        market_manager.ws_app.close()

if __name__ == "__main__":
    asyncio.run(main())
