# config.py

class Config:
    # Trading settings
    BALANCE_LIMIT = 10  # Stop trading if balance drops below this
    TRADE_AMOUNT = 1
    MARTINGALE_FACTOR = 2.0
    MAX_MARTINGALE_STEPS = 3
    TARGET_PROFIT = 100
    STOP_LOSS = 50
    
    # Strategy settings
    EXPIRY_MINUTES = 1  # 1 minute expiry
    TIMEFRAME = 60      # 1 minute candles (60 seconds)
    
    # Pairs to trade (can be updated dynamically)
    ASSETS = ["EURUSD", "GBPUSD", "USDJPY", "AUDUSD", "USDCAD"]
    
    # System settings
    RECONNECT_DELAY = 5
    CHECK_INTERVAL = 1  # Check signals every 1 second
    
    # Status
    IS_TRADING = False
    
    # Credentials (to be set at runtime)
    EMAIL = ""
    PASSWORD = ""
    MODE = "PRACTICE" # PRACTICE or REAL

config = Config()
