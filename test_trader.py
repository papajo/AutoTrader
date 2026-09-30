import logging
from trader_engine import TraderEngine, ExchangeAPI, Strategy

# Setup logging
logging.basicConfig(level=logging.INFO, format='%(message)s')
logger = logging.getLogger('TestTrader')

class SampleDataExchange(ExchangeAPI):
    def __init__(self, prices):
        self.prices = prices
        self.index = 0
        self.orders = []

    def get_price(self, symbol):
        if self.index >= len(self.prices):
            return self.prices[-1]
        price = self.prices[self.index]
        self.index += 1
        return price

    def place_order(self, symbol, side, quantity):
        self.orders.append({'side': side, 'qty': quantity, 'symbol': symbol})
        return True

    def cancel_order(self, order_id):
        return True

class PoCStrategy(Strategy):
    def generate_signal(self, price):
        if price < 45: return 'buy'
        if price > 55: return 'sell'
        return ''

def run_poc_test():
    # Sample price data: Dip -> Peak -> Dip
    sample_prices = [40.0, 42.0, 60.0, 58.0, 30.0]
    config = {
        'poll_interval': 0,
        'trade_quantity': 0.1,
        'max_daily_loss': 1000.0
    }

    exchange = SampleDataExchange(sample_prices)
    strategy = PoCStrategy()
    engine = TraderEngine(exchange, strategy, 'BTC-USD', config)

    logger.info("Starting PoC Test with prices: %s", sample_prices)

    # Run for exactly 5 iterations
    for i in range(5):
        price = exchange.get_price('BTC-USD')
        logger.info(f"Cycle {i+1}: Price = {price}")

        signal = strategy.generate_signal(price)
        if signal:
            engine.execute_trade(signal)

    logger.info("Test Complete. Orders placed: %s", exchange.orders)

    # Validations
    assert any(o['side'] == 'buy' for o in exchange.orders), "Should have bought at 40/42"
    assert any(o['side'] == 'sell' for o in exchange.orders), "Should have sold at 60/58"
    logger.info("SUCCESS: Strategy executed correctly on sample data.")

if __name__ == '__main__':
    run_poc_test()
