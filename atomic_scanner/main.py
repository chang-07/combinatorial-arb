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
    host = "https://clob.polymarket.com"
    chain_id = 137 # Polygon Mainnet

    # --- Client Initialization ---
    try:
        # Initializing for read-only access as per requirements
        client = ClobClient(host, chain_id=chain_id, creds=None)
        logging.info("Successfully connected to the CLOB API.")
    except Exception as e:
        logging.error(f"Failed to connect to the CLOB API: {e}")
        return

    # Arbitrage threshold defined in project context
    threshold = Decimal('0.01') 
    logging.info(f"Arbitrage threshold set to: {threshold}")

    try:
        while True:
            logging.info("Fetching active markets...")
            try:
                # Fetches first page of active markets
                active_markets = client.get_markets()
                
                if not active_markets or not active_markets.get('data'):
                    logging.warning("No active markets found.")
                    time.sleep(60)
                    continue

                logging.info(f"Found {len(active_markets['data'])} active markets.")
                
                for market in active_markets['data']:
                    # Ensure the market is active and has exactly two tokens (binary)
                    if market.get('accepting_orders') and len(market.get('tokens', [])) == 2:
                        tokens = market.get('tokens')
                        
                        # FIX: Use 'clobTokenId' instead of 'token_id'
                        token0_id = tokens[0].get('clobTokenId')
                        token1_id = tokens[1].get('clobTokenId')

                        # Skip markets that are not supported on the CLOB
                        if not token0_id or not token1_id:
                            continue

                        try:
                            # The get_order_book method now uses the correct CLOB-specific ID
                            orderbook0 = client.get_order_book(token0_id)
                            orderbook1 = client.get_order_book(token1_id)
                            
                            # Extract best ask prices to calculate total cost
                            # Using .get('asks') assumes dict-style response; check library version if issues persist
                            asks0 = orderbook0.get('asks', []) if isinstance(orderbook0, dict) else orderbook0.asks
                            asks1 = orderbook1.get('asks', []) if isinstance(orderbook1, dict) else orderbook1.asks

                            best_ask_0 = min([Decimal(ask['price']) for ask in asks0], default=None)
                            best_ask_1 = min([Decimal(ask['price']) for ask in asks1], default=None)

                            if best_ask_0 is not None and best_ask_1 is not None:
                                price_sum = best_ask_0 + best_ask_1
                                
                                # Logic: P(Yes) + P(No) < (1.0 - threshold)
                                if price_sum < (Decimal('1.0') - threshold):
                                    logging.warning(f"ARBITRAGE FOUND: {market.get('question')}")
                                    logging.warning(f"  {tokens[0].get('outcome')}: {best_ask_0} | {tokens[1].get('outcome')}: {best_ask_1}")
                                    logging.warning(f"  Total Cost: {price_sum} | Expected Profit: {Decimal('1.0') - price_sum}")

                        except (InvalidOperation, Exception) as e:
                            logging.debug(f"Could not process market {market.get('question')}: {e}")

            except Exception as e:
                logging.error(f"Error in polling cycle: {e}")

            time.sleep(10) # Wait for next poll

    except KeyboardInterrupt:
        logging.info("Scanner stopped by user.")

if __name__ == "__main__":
    main()
