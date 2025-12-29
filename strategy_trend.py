# strategy_trend.py
import pandas as pd
from indicators import Indicators
from config import config

class TrendStrategy:
    def __init__(self):
        self.name = "Easy Trend Follow"

    def check_signal(self, df: pd.DataFrame):
        """
        Generates a signal based on a simplified trend strategy.
        Returns: "CALL", "PUT", or None
        """
        if df is None or len(df) < 3:
            return None

        # Add indicators (handles type conversion too)
        df = Indicators.add_indicators(df)

        # Get the last completed candle (index -1 is the current forming candle usually, 
        # but in many IQ APIs, get_candles returns completed candles or includes current.
        # We'll assume the last row is the most recent completed or current.
        # Safest is to look at the last fully closed candle. 
        # If we are polling, we might just look at the last row.
        
        last_candle = df.iloc[-1]
        prev_candle = df.iloc[-2]

        # Logic: "Easy trades" - Follow the color of the previous candle
        # If previous candle was GREEN, assume trend is UP -> CALL
        # If previous candle was RED, assume trend is DOWN -> PUT
        
        prev_open = prev_candle['open']
        prev_close = prev_candle['close']
        
        if prev_close > prev_open:
            return "CALL"
        elif prev_close < prev_open:
            return "PUT"
            
        return None
