import time
import logging
import os
from decimal import Decimal, InvalidOperation
import requests
from py_clob_client.client import ClobClient

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# --- API & Network Configuration ---
COINMARKETCAP_API_KEY = os.environ.get("COINMARKETCAP_API_KEY")
POLYGON_GAS_STATION_URL = "https://gasstation.polygon.technology/v2"
COINMARKETCAP_URL = "https://pro-api.coinmarketcap.com/v1/cryptocurrency/quotes/latest"

def get_polygon_gas_price():
    """Fetches the standard gas price from Polygon Gas Station."""
    try:
        response = requests.get(POLYGON_GAS_STATION_URL)
        response.raise_for_status()
        gas_data = response.json()
        return Decimal(gas_data['standard']['maxFee'])
    except (requests.exceptions.RequestException, KeyError, InvalidOperation) as e:
        logging.error(f"Failed to fetch Polygon gas price: {e}")
        return None

def get_matic_price_usd():
    """Fetches the current MATIC to USD price from CoinMarketCap."""
    if not COINMARKETCAP_API_KEY:
        logging.warning("COINMARKETCAP_API_KEY not set. Cannot fetch MATIC price.")
        return None

    headers = {
        'Accepts': 'application/json',
        'X-CMC_PRO_API_KEY': COINMARKETCAP_API_KEY,
    }
    parameters = {
        'symbol': 'MATIC',
        'convert': 'USD'
    }
    try:
        response = requests.get(COINMARKETCAP_URL, headers=headers, params=parameters)
        response.raise_for_status()
        data = response.json()
        return Decimal(data['data']['MATIC']['quote']['USD']['price'])
    except (requests.exceptions.RequestException, KeyError, InvalidOperation) as e:
        logging.error(f"Failed to fetch MATIC price: {e}")
        return None

def main():
    """
    Main function to monitor Polymarket for atomic arbitrage opportunities.
    """
    logging.info("Starting atomic scanner...")

    # --- Configuration ---
    host = "https://clob.polymarket.com"
    chain_id = 137 # Polygon Mainnet

    # --- Client Initialization ---
    try:
        client = ClobClient(host, chain_id=chain_id, creds=None)
        logging.info("Successfully connected to the CLOB API.")
    except Exception as e:
        logging.error(f"Failed to connect to the CLOB API: {e}")
        return

    # Arbitrage threshold and trade size
    threshold = Decimal('0.01') 
    min_trade_size_usd = Decimal('10.0')
    logging.info(f"Arbitrage threshold set to: {threshold}")
    logging.info(f"Minimum trade size (USD) set to: {min_trade_size_usd}")

    try:
        while True:
            logging.info("Fetching active markets and network conditions...")
            
            # Fetch external data
            gas_price_gwei = get_polygon_gas_price()
            matic_price_usd = get_matic_price_usd()

            if gas_price_gwei is None or matic_price_usd is None:
                logging.error("Could not fetch network or price data. Skipping cycle.")
                time.sleep(60)
                continue
            
            # Estimate gas cost for a hypothetical 2-transaction arbitrage
            # This is a rough estimate. Real costs depend on contract complexity.
            gas_limit_per_tx = Decimal('200000') # A guess for a simple swap
            num_transactions = 2
            total_gas_cost_gwei = gas_price_gwei * gas_limit_per_tx * num_transactions
            total_gas_cost_matic = total_gas_cost_gwei / Decimal('1000000000') # Gwei to MATIC
            total_gas_cost_usd = total_gas_cost_matic * matic_price_usd
            logging.info(f"Estimated gas cost for arbitrage: ${total_gas_cost_usd:.4f}")

            try:
                active_markets = client.get_markets()
                
                if not active_markets or not active_markets.get('data'):
                    logging.warning("No active markets found.")
                    time.sleep(60)
                    continue

                logging.info(f"Found {len(active_markets['data'])} active markets.")
                
                for market in active_markets['data']:
                    if market.get('accepting_orders') and len(market.get('tokens', [])) == 2:
                        tokens = market.get('tokens')
                        
                        token0_id = tokens[0].get('clobTokenId')
                        token1_id = tokens[1].get('clobTokenId')

                        if not token0_id or not token1_id:
                            continue

                        try:
                            orderbook0 = client.get_order_book(token0_id)
                            orderbook1 = client.get_order_book(token1_id)
                            
                            asks0 = sorted(orderbook0.get('asks', []), key=lambda x: Decimal(x['price']))
                            asks1 = sorted(orderbook1.get('asks', []), key=lambda x: Decimal(x['price']))

                            if not asks0 or not asks1:
                                continue

                            for ask0 in asks0:
                                for ask1 in asks1:
                                    price0 = Decimal(ask0['price'])
                                    price1 = Decimal(ask1['price'])
                                    size0 = Decimal(ask0['size'])
                                    size1 = Decimal(ask1['size'])

                                    price_sum = price0 + price1
                                    if price_sum < (Decimal('1.0') - threshold):
                                        tradable_volume = min(size0, size1)
                                        
                                        investment = tradable_volume * price_sum
                                        returns = tradable_volume
                                        gross_profit = returns - investment
                                        net_profit = gross_profit - total_gas_cost_usd

                                        if investment >= min_trade_size_usd and net_profit > 0:
                                            logging.warning(f"ARBITRAGE FOUND: {market.get('question')}")
                                            logging.warning(f"  Outcome: {tokens[0].get('outcome')} @ {price0} & {tokens[1].get('outcome')} @ {price1}")
                                            logging.warning(f"  Tradable Volume: {tradable_volume}")
                                            logging.warning(f"  Investment: ${investment:.2f}")
                                            logging.warning(f"  Gross Profit: ${gross_profit:.2f}")
                                            logging.warning(f"  Net Profit (after gas): ${net_profit:.2f}")
                                            break
                                else:
                                    continue
                                break
                        except (InvalidOperation, KeyError, Exception) as e:
                            logging.debug(f"Could not process market {market.get('question')}: {e}")
            except Exception as e:
                logging.error(f"Error in polling cycle: {e}")

            time.sleep(10)

    except KeyboardInterrupt:
        logging.info("Scanner stopped by user.")

if __name__ == "__main__":
    main()
