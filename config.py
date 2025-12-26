from datetime import time

# --- Timeframe Settings ---
ZONE_TIMEFRAME = "15m"  # 5m or 15m
ENTRY_TIMEFRAME = "1m"

# --- OTC Strategy Settings (User Defined) ---
# Indicators
EMA_FAST_PERIOD = 20
EMA_SLOW_PERIOD = 50
RSI_PERIOD = 14

# RSI Thresholds
RSI_CALL_MIN = 45
RSI_CALL_MAX = 60
RSI_PUT_MIN = 40
RSI_PUT_MAX = 55

# Candle Confirmation
MIN_BODY_SIZE_RATIO = 0.2 # Body must be at least 20% of total range to be "Clear"
DOJI_THRESHOLD = 0.1 # If body is < 10% of range, it's a Doji (SKIP)

# --- S/R Settings ---
ZONE_LOOKBACK_BARS = 20
ZONE_TOUCH_TOLERANCE_ATR = 0.5

# --- Entry Filters ---
EXPIRY_MINUTES = 2 # 2 Minutes Expiry
SIGNAL_COOLDOWN_CANDLES = 3

# --- Session & Risk ---
MAX_TRADES_PER_SESSION = 6
STOP_LOSS_LIMIT = 2 # Consecutive losses to stop
SESSION_PROFIT_GOAL = 5 # Stop at $5 profit
TRADE_AMOUNT = 1.0 # $1 per trade

# --- Sessions (UTC) ---
# Best OTC Windows: 00:00-03:00 UTC & 18:00-21:00 UTC
OTC_WINDOW_1_START = time(0, 0)
OTC_WINDOW_1_END = time(3, 0)

OTC_WINDOW_2_START = time(18, 0)
OTC_WINDOW_2_END = time(21, 0)

# --- Pairs ---
PAIRS_OTC = [
    "EURUSD-OTC", 
    "GBPUSD-OTC",
    "USDJPY-OTC"
]

# (Legacy/Unused for this specific strategy but kept to avoid import errors)
PAIRS_LONDON = ["EURUSD=X", "GBPUSD=X", "USDJPY=X"]
PAIRS_NY = ["EURUSD=X", "USDJPY=X", "AUDUSD=X"]
SESSION_LONDON_START = time(8, 30)
SESSION_LONDON_END = time(11, 0)
SESSION_NY_START = time(14, 0)
SESSION_NY_END = time(16, 30)
SESSION_NY_CONT_START = time(16, 30)
SESSION_NY_CONT_END = time(20, 30)
SESSION_OTC_START_UTC = time(21, 30) # Legacy
SESSION_OTC_END_UTC = time(3, 0) # Legacy
