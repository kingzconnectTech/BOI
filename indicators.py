# indicators.py
import pandas as pd
import pandas_ta as ta

class Indicators:
    @staticmethod
    def add_indicators(df: pd.DataFrame):
        """Adds technical indicators to the dataframe."""
        if df is None or df.empty:
            return df
            
        # Ensure correct types
        df['open'] = df['open'].astype(float)
        df['high'] = df['high'].astype(float)
        df['low'] = df['low'].astype(float)
        df['close'] = df['close'].astype(float)
        df['volume'] = df['volume'].astype(float)
        
        # Simple Moving Averages
        df['SMA_20'] = ta.sma(df['close'], length=20)
        df['SMA_50'] = ta.sma(df['close'], length=50)
        
        # RSI
        df['RSI'] = ta.rsi(df['close'], length=14)
        
        return df

    @staticmethod
    def get_last_candle_color(df: pd.DataFrame):
        if df is None or len(df) < 1:
            return None
        last = df.iloc[-1]
        if last['close'] > last['open']:
            return "GREEN"
        elif last['close'] < last['open']:
            return "RED"
        else:
            return "DOJI"
