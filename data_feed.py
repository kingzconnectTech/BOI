# data_feed.py
import time
import logging
from iqoptionapi.stable_api import IQ_Option
from config import config
import threading

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class DataFeed:
    def __init__(self):
        self.api = None
        self.email = None
        self.password = None
        self.connected = False
        self.lock = threading.Lock()

    def set_credentials(self, email, password):
        self.email = email
        self.password = password

    def connect(self):
        with self.lock:
            if not self.email or not self.password:
                logger.error("Credentials not set")
                return False

            logger.info(f"Connecting to IQ Option as {self.email}...")
            try:
                # Close existing API connection if it exists to prevent multiple active sockets
                if self.api:
                    try:
                        self.api.api.close()
                    except:
                        pass
                
                self.api = IQ_Option(self.email, self.password)
                check, reason = self.api.connect()
                
                if check:
                    logger.info("Successfully connected to IQ Option")
                    self.api.change_balance(config.MODE)  # PRACTICE or REAL
                    self.connected = True
                    return True
                else:
                    logger.error(f"Connection failed: {reason}")
                    self.connected = False
                    return False
            except Exception as e:
                logger.error(f"Error during connection: {e}")
                self.connected = False
                return False

    def check_connection(self):
        """
        Checks connection and attempts tiered reconnection.
        """
        if self.api is None:
            return self.connect()

        if self.api.check_connect():
            return True

        logger.warning("Connection lost. Attempting simple reconnect...")
        try:
            if self.api.reconnect():
                logger.info("Simple reconnect successful")
                return True
        except Exception as e:
            logger.error(f"Simple reconnect failed: {e}")

        logger.warning("Simple reconnect failed. Performing full re-initialization...")
        return self.connect() # Create new instance

    def get_candles(self, asset, timeframe, limit=10):
        """
        Fetches candles for a given asset.
        """
        if not self.check_connection():
            return None

        try:
            candles = self.api.get_candles(asset, timeframe, limit, time.time())
            if not candles:
                logger.warning(f"No candles received for {asset}")
                # Force reconnect if candles are empty repeatedly?
                return None
            
            # Convert to DataFrame-friendly format or just list
            return candles
        except Exception as e:
            logger.error(f"Error fetching candles for {asset}: {e}")
            # If error is 'NoneType' object has no attribute 'is_ssl', it implies websocket is dead.
            if "is_ssl" in str(e) or "NoneType" in str(e):
                logger.critical("Critical connection error detected. Forcing full re-connect.")
                self.connect()
            return None

    def get_balance(self):
        if not self.check_connection():
            return 0
        try:
            return self.api.get_balance()
        except Exception as e:
            logger.error(f"Error getting balance: {e}")
            return 0

    def get_open_pairs(self):
        """
        Returns a list of currently open pairs (binary options) based on PAYOUTS.
        We prioritize get_all_profit() because if an asset is paying, it is tradeable.
        """
        if not self.check_connection():
            return []
        
        try:
            logger.info("Fetching all profits to determine active assets...")
            all_profits = self.api.get_all_profit()
            
            open_paying_pairs = []
            
            if isinstance(all_profits, dict):
                for pair, profit_data in all_profits.items():
                    is_paying = False
                    
                    # profit_data can be a dict {'turbo': 0.85, 'binary': 0.80} 
                    # or sometimes a float directly depending on API version/state
                    if isinstance(profit_data, dict):
                        if profit_data.get('turbo', 0) > 0.01 or profit_data.get('binary', 0) > 0.01:
                            is_paying = True
                    elif isinstance(profit_data, (int, float)) and profit_data > 0.01:
                         is_paying = True
                    
                    if is_paying:
                        open_paying_pairs.append(pair)
            
            # Filter out non-pairs (sometimes stocks/commodities appear if not filtered?)
            # Usually IQ Option API pairs are like "EURUSD", "EURUSD-OTC", "USDJPY", etc.
            # We might want to filter for length > 3 or contains uppercase.
            
            if open_paying_pairs:
                logger.info(f"Found {len(open_paying_pairs)} active paying pairs via get_all_profit.")
                return open_paying_pairs
            
            # Fallback to schedule if profit check fails completely (unexpected)
            logger.warning("get_all_profit returned no paying pairs. Falling back to schedule check...")
            
            all_assets = self.api.get_all_open_time()
            scheduled_open = set()
            if 'turbo' in all_assets:
                for pair, data in all_assets['turbo'].items():
                    if data['open']:
                        scheduled_open.add(pair)
            if 'binary' in all_assets:
                 for pair, data in all_assets['binary'].items():
                    if data['open']:
                        scheduled_open.add(pair)
            
            return list(scheduled_open)

        except Exception as e:
            logger.error(f"Error fetching open pairs: {e}")
            return []

    def place_trade(self, asset, amount, action, duration):
        """
        Places a trade.
        action: "CALL" or "PUT"
        """
        if not self.check_connection():
            return False, "Not connected"

        try:
            logger.info(f"Placing trade: {asset}, {action}, {amount}, {duration}min")
            check, id = self.api.buy(amount, asset, action, duration)
            
            if check:
                logger.info(f"Trade placed successfully. ID: {id}")
                return True, id
            else:
                logger.error(f"Trade failed. ID (Error): {id}")
                return False, id # id contains error message usually if check is False
        except Exception as e:
            logger.error(f"Exception placing trade: {e}")
            return False, str(e)

data_feed = DataFeed()
