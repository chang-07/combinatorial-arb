import time
import logging
from decimal import Decimal, InvalidOperation
from py_clob_client.client import ClobClient

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

def main():
    """
    Main function to monitor Polymarket for atomic arbitrage opportunities.
    """
    logging.info("Starting atomic scanner...")

    # --- Configuration ---
    # For read-only access, API credentials are not required.
    # For trading, you would need to provide your private key, API key, and API secret.
    
    # Mainnet configuration
    host = "https://clob.polymarket.com"
    chain_id = 137 

    # --- Client Initialization ---
    try:
        client = ClobClient(host, chain_id=chain_id, creds=None)
        logging.info("Successfully connected to the CLOB API.")
    except Exception as e:
        logging.error(f"Failed to connect to the CLOB API: {e}")
        return

    # Arbitrage threshold
    threshold = Decimal('0.01')
    logging.info(f"Arbitrage threshold set to: {threshold}")

    # --- Market Monitoring Loop ---
    try:
        while True:
            logging.info("Fetching active markets...")
            
            try:
                active_markets = client.get_markets()
                
                if not active_markets or not active_markets.get('data'):
                    logging.warning("No active markets found.")
                    time.sleep(60)
                    continue

                logging.info(f"Found {len(active_markets['data'])} active markets.")
                
                for market in active_markets['data']:
                    if market.get('accepting_orders') and len(market.get('tokens', [])) == 2:
                        condition_id = market.get('condition_id')
                        tokens = market.get('tokens')
                        token0_id = tokens[0].get('token_id')
                        token1_id = tokens[1].get('token_id')

                        try:
                            # Get order book for both tokens
                            orderbook0 = client.get_orderbook(f"{condition_id}-{token0_id}")
                            orderbook1 = client.get_orderbook(f"{condition_id}-{token1_id}")

                            # Find the best ask price for each token
                            best_ask_0 = min([Decimal(ask['price']) for ask in orderbook0.get('asks', [])], default=None)
                            best_ask_1 = min([Decimal(ask['price']) for ask in orderbook1.get('asks', [])], default=None)

                            if best_ask_0 is not None and best_ask_1 is not None:
                                price_sum = best_ask_0 + best_ask_1
                                if price_sum < (Decimal('1.0') - threshold):
                                    logging.warning(f"Arbitrage opportunity found in market: {market.get('question')}")
                                    logging.warning(f"  Condition ID: {condition_id}")
                                    logging.warning(f"  Token 0 ({tokens[0].get('outcome')}): Best Ask = {best_ask_0}")
                                    logging.warning(f"  Token 1 ({tokens[1].get('outcome')}): Best Ask = {best_ask_1}")
                                    logging.warning(f"  Sum of prices: {price_sum}")

                        except (InvalidOperation, Exception) as e:
                            logging.error(f"Error processing market {market.get('question')}: {e}")

            except Exception as e:
                logging.error(f"An error occurred while fetching or processing markets: {e}")

            logging.info("Scanner finished a cycle. Waiting for 10 seconds before next poll...")
            time.sleep(10)

    except KeyboardInterrupt:
        logging.info("Scanner stopped by user.")
    except Exception as e:
        logging.error(f"An unexpected error occurred: {e}")

if __name__ == "__main__":
    main()
