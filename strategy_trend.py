import pandas as pd
from datetime import datetime, timedelta
import config
from indicators import is_strong_candle, is_doji, get_candle_props

class TrendPullbackStrategy:
    VERSION = "OTC_EMA_RSI_V1"
    
    def __init__(self):
        self.consecutive_losses = 0
        self.signals_this_session = 0
        self.active_zones = []
        self.last_signal_time = None
        self.last_signal_asset = None
        
        # Dynamic Settings (Defaults from config)
        self.expiry_minutes = config.EXPIRY_MINUTES
        self.stop_loss_limit = config.STOP_LOSS_LIMIT
        self.signal_cooldown = config.SIGNAL_COOLDOWN_CANDLES

    def detect_zones(self, df):
        """
        No zones needed for this OTC strategy (EMA acts as dynamic S/R).
        """
        return []

    def update_outcomes(self, df, signals, current_asset=None):
        for sig in signals:
            if current_asset and sig.get('asset') != current_asset:
                continue
            
            if 'outcome' in sig: 
                # Already processed
                continue
                
            entry_time = sig['time']
            expiry_minutes = self.expiry_minutes
            target_time = entry_time + timedelta(minutes=expiry_minutes)
            
            if target_time in df.index and target_time < df.index[-1]:
                expiry_price = df.loc[target_time]['close']
                entry_price = sig['price']
                
                outcome = 'TIE'
                if sig['type'] == 'CALL':
                    if expiry_price > entry_price: outcome = 'WIN'
                    elif expiry_price < entry_price: outcome = 'LOSS'
                else:
                    if expiry_price < entry_price: outcome = 'WIN'
                    elif expiry_price > entry_price: outcome = 'LOSS'
                
                sig['outcome'] = outcome
                
                # Update stats
                if outcome == 'LOSS':
                    self.consecutive_losses += 1
                elif outcome == 'WIN':
                    self.consecutive_losses = 0 # Reset on win
                    
                # We count signals when they are generated, outcome updates help stop-loss logic

    def detect_market_mode(self, df, idx):
        if idx < 0: idx = len(df) + idx
        
        if 'ema_fast' not in df.columns or 'ema_slow' not in df.columns:
            return "NEUTRAL"
            
        ema_fast = df['ema_fast'].iloc[idx]
        ema_slow = df['ema_slow'].iloc[idx]
        
        if pd.isna(ema_fast) or pd.isna(ema_slow):
            return "NEUTRAL"
            
        # Basic trend
        if ema_fast > ema_slow:
            return "UPTREND"
        elif ema_fast < ema_slow:
            return "DOWNTREND"
            
        return "NEUTRAL"

    def analyze_1m(self, df_1m, symbol="EURUSD"):
        """
        OTC Strategy: EMA Pullback + RSI + Candle Confirmation.
        """
        if len(df_1m) < 55: return None
        
        # 1. Validation (Check forming candle)
        last_idx = -1
        last_time = df_1m.index[last_idx]
        current_time_utc = datetime.now(last_time.tzinfo)
        
        # Ignore forming candle for analysis, look at the just closed one
        if (current_time_utc - last_time).total_seconds() < 60:
            last_idx = -2
            if len(df_1m) < 56: return None
            
        idx = len(df_1m) + last_idx
        timestamp = df_1m.index[idx]
        
        # 2. Risk Checks
        if self.consecutive_losses >= self.stop_loss_limit: return None
        if self.last_signal_time:
             if (timestamp - self.last_signal_time).total_seconds() / 60 < self.signal_cooldown:
                 return None

        # 3. Strategy Variables
        row = df_1m.iloc[idx]
        ema_fast = row['ema_fast']
        ema_slow = row['ema_slow']
        rsi = row['rsi']
        close = row['close']
        open_p = row['open']
        high = row['high']
        low = row['low']
        
        if pd.isna(ema_fast) or pd.isna(ema_slow) or pd.isna(rsi):
            return None
            
        # 4. Filter: Doji Check
        if is_doji(row):
            return None
            
        # 5. Logic
        
        # --- CALL SETUP ---
        # 1. Trend UP (EMA 20 > EMA 50)
        if ema_fast > ema_slow:
            
            # 2. RSI Check (45 - 60)
            if config.RSI_CALL_MIN <= rsi <= config.RSI_CALL_MAX:
                
                # 3. Pullback Condition:
                # "Price pulls back to EMA 20 or slightly above EMA 50"
                # This implies the LOW of the candle touched or went below EMA 20.
                if low <= ema_fast:
                    
                    # 4. Rejection/Confirmation Condition:
                    # "A strong bullish candle closes rejecting EMA"
                    # Must be Green (Bullish)
                    if close > open_p:
                        
                        # Strong Candle (Body Size)
                        if is_strong_candle(row):
                            
                            # Close MUST be above EMA 20 (Reclaimed the level)
                            if close > ema_fast:
                                
                                # Visible lower wick (Rejection)
                                props = get_candle_props(row)
                                if props['lower_wick'] > 0:
                                    
                                    # Valid CALL
                                    self.last_signal_time = timestamp
                                    return {
                                        'type': 'CALL',
                                        'asset': symbol,
                                        'time': timestamp,
                                        'expiry': f"{config.EXPIRY_MINUTES} min",
                                        'confidence': 85,
                                        'price': close,
                                        'pattern': "EMA 20 Pullback Rejection",
                                        'mode': "UPTREND"
                                    }

        # --- PUT SETUP ---
        # 1. Trend DOWN (EMA 20 < EMA 50)
        elif ema_fast < ema_slow:
            
            # 2. RSI Check (40 - 55)
            if config.RSI_PUT_MIN <= rsi <= config.RSI_PUT_MAX:
                
                # 3. Pullback Condition:
                # "Price pulls back to EMA 20 or slightly below EMA 50"
                # High touched or went above EMA 20
                if high >= ema_fast:
                    
                    # 4. Rejection/Confirmation
                    # Must be Red (Bearish)
                    if close < open_p:
                        
                        # Strong Candle
                        if is_strong_candle(row):
                            
                            # Close MUST be below EMA 20
                            if close < ema_fast:
                                
                                # Visible upper wick
                                props = get_candle_props(row)
                                if props['upper_wick'] > 0:
                                    
                                    # Valid PUT
                                    self.last_signal_time = timestamp
                                    return {
                                        'type': 'PUT',
                                        'asset': symbol,
                                        'time': timestamp,
                                        'expiry': f"{config.EXPIRY_MINUTES} min",
                                        'confidence': 85,
                                        'price': close,
                                        'pattern': "EMA 20 Pullback Rejection",
                                        'mode': "DOWNTREND"
                                    }
                                    
        return None

    def check_early_warnings(self, df_1m):
        # Optional: Warn if price is nearing EMA 20 in a trend
        if len(df_1m) < 50: return []
        
        last_idx = -1
        # Check forming candle
        row = df_1m.iloc[last_idx]
        ema_fast = row['ema_fast']
        ema_slow = row['ema_slow']
        close = row['close']
        
        if pd.isna(ema_fast) or pd.isna(ema_slow): return []
        
        alerts = []
        
        # Approaching Pullback Zone?
        dist_to_ema = abs(close - ema_fast)
        threshold = row['atr'] * 0.5 if 'atr' in df_1m.columns else 0.0001
        
        if ema_fast > ema_slow and close > ema_fast:
            if dist_to_ema < threshold:
                alerts.append({'level': 'TEST', 'message': "Price nearing EMA 20 (Pullback Zone)"})
        elif ema_fast < ema_slow and close < ema_fast:
            if dist_to_ema < threshold:
                alerts.append({'level': 'TEST', 'message': "Price nearing EMA 20 (Pullback Zone)"})
                
        return alerts
