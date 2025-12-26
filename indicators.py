import pandas as pd
import pandas_ta as ta
import config

def calculate_indicators(df):
    """
    Calculates OTC Strategy Indicators:
    - EMA 20 (Fast)
    - EMA 50 (Slow)
    - RSI 14
    """
    # EMAs
    df['ema_fast'] = df.ta.ema(length=config.EMA_FAST_PERIOD)
    df['ema_slow'] = df.ta.ema(length=config.EMA_SLOW_PERIOD)
    
    # RSI
    df['rsi'] = df.ta.rsi(length=config.RSI_PERIOD)
    
    # ATR (Optional, for volatility context if needed later)
    df['atr'] = df.ta.atr(length=14)
    
    return df

def is_doji(row):
    """
    Returns True if candle is a Doji (small body relative to range).
    """
    props = get_candle_props(row)
    if props['total_range'] == 0: return True
    ratio = props['body'] / props['total_range']
    return ratio < config.DOJI_THRESHOLD

def is_strong_candle(row):
    """
    Returns True if candle has a clear body.
    """
    props = get_candle_props(row)
    if props['total_range'] == 0: return False
    ratio = props['body'] / props['total_range']
    return ratio >= config.MIN_BODY_SIZE_RATIO

def get_candle_props(row):
    open_p = row['open']
    close_p = row['close']
    high_p = row['high']
    low_p = row['low']
    
    body = abs(close_p - open_p)
    total_range = high_p - low_p
    
    if total_range == 0: total_range = 0.00001
    
    color = 'green' if close_p >= open_p else 'red'
    
    if color == 'green':
        upper_wick = high_p - close_p
        lower_wick = open_p - low_p
    else:
        upper_wick = high_p - open_p
        lower_wick = close_p - low_p
    
    return {
        'body': body,
        'upper_wick': upper_wick,
        'lower_wick': lower_wick,
        'total_range': total_range,
        'color': color
    }
