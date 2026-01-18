from decimal import Decimal

class InferenceCore:
    """
    A pure, I/O-free core for arbitrage calculations.
    """

    def calculate_weighted_average_price(self, target_size: Decimal, order_book: list[dict]) -> tuple[Decimal, Decimal] | None:
        """
        Calculates the weighted average price to fill a target size.
        """
        cumulative_size = Decimal('0')
        cumulative_cost = Decimal('0')
        
        for order in order_book:
            price = Decimal(order['price'])
            size = Decimal(order['size'])
            
            if cumulative_size + size >= target_size:
                remaining_size = target_size - cumulative_size
                cumulative_cost += remaining_size * price
                cumulative_size += remaining_size
                break
            else:
                cumulative_cost += size * price
                cumulative_size += size
        
        if cumulative_size < target_size:
            return None # Not enough depth

        wap = cumulative_cost / target_size
        return wap, cumulative_cost

    def calculate_net_profit(self, target_size: Decimal, book_yes: list[dict], book_no: list[dict], gas_usd: Decimal, exchange_fee_percent: Decimal) -> tuple[Decimal, Decimal, Decimal, Decimal] | None:
        """
        Calculates the net profit for a potential arbitrage opportunity.
        """
        wap_yes_result = self.calculate_weighted_average_price(target_size, book_yes)
        wap_no_result = self.calculate_weighted_average_price(target_size, book_no)

        if not wap_yes_result or not wap_no_result:
            return None

        wap_yes, cost_yes = wap_yes_result
        wap_no, cost_no = wap_no_result

        total_investment = cost_yes + cost_no
        gross_returns = target_size * 2 # Assuming binary market, one side pays out
        
        # This is incorrect, the return is 1 per share, so target_size * 1 for each side.
        # The total return is target_size if we buy `target_size` of each.
        # Let's rethink the profit calculation.
        # If we buy `target_size` of YES and `target_size` of NO, we have `target_size` complete sets.
        # Each set costs `wap_yes + wap_no` and pays out 1.
        # So, total investment is `(wap_yes + wap_no) * target_size`.
        # Total return is `target_size * 1`.
        # Gross profit is `target_size - (wap_yes + wap_no) * target_size`.
        
        price_sum = wap_yes + wap_no
        if price_sum >= 1:
            return None

        gross_profit = (Decimal('1.0') - price_sum) * target_size
        
        total_investment = price_sum * target_size
        exchange_fees = total_investment * exchange_fee_percent
        net_profit = gross_profit - gas_usd - exchange_fees

        return net_profit, gross_profit, wap_yes, wap_no
