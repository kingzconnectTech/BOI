from iqoptionapi.stable_api import IQ_Option
import time
import threading
import traceback
import talib
import numpy as np
import uuid
from datetime import datetime, timedelta
from exponent_server_sdk import PushClient, PushMessage

# ============================================================================
# IQBot Class - Single User Bot Instance (Logic only)
# ============================================================================

class IQBot:
    def __init__(self):
        self.api = None
        self.email = None
        self.password = None
        self.connected = False
        self.is_running = False
        self.balance = 0
        self.currency = ""
        self.logs = []  # Store logs for frontend
        self.signals = [] # Store simulated signals
        self.active_simulations = {} # Track active simulations to prevent duplicates
        
        # Trade Config - Instance specific
        self.pairs_to_scan = ["EURUSD-OTC", "GBPUSD-OTC", "AUDCAD-OTC", "USDCHF-OTC", "EURJPY-OTC"]
        self.trade_amount = 1
        self.trade_duration = 1  # minutes
        self.stop_loss = 0
        self.take_profit = 0
        self.max_consecutive_losses = 0
        self.max_trades = 1  # 0 means unlimited
        self.auto_trading = True
        self.push_token = None  # Expo Push Token
        self.strategy = "Momentum"
        
        self.initial_balance = 0
        self.total_profit = 0
        self.wins = 0
        self.losses = 0
        self.trades_taken = 0
        self.trade_in_progress = False
        self.current_consecutive_losses = 0
        self.next_trading_time = 0

    def set_config(self, amount, duration, stop_loss, take_profit, max_consecutive_losses, max_trades, auto_trading=True, strategy="Momentum"):
        self.trade_amount = amount
        self.trade_duration = duration
        self.stop_loss = stop_loss
        self.take_profit = take_profit
        self.max_consecutive_losses = max_consecutive_losses
        self.max_trades = max_trades
        self.auto_trading = auto_trading
        self.strategy = strategy
        
    def set_push_token(self, token):
        self.push_token = token
        self.add_log(f"Push token set: {token[:10]}...")

    def send_push(self, title, body):
        if not self.push_token:
            return
        try:
            response = PushClient().publish(
                PushMessage(to=self.push_token,
                            title=title,
                            body=body)
            )
        except Exception as e:
            print(f"Push notification failed: {e}")

    def reset_stats(self):
        self.total_profit = 0
        self.wins = 0
        self.losses = 0
        self.trades_taken = 0
        self.initial_balance = self.balance

    def add_log(self, message):
        timestamp = time.strftime("%H:%M:%S")
        log_entry = f"[{timestamp}] {message}"
        print(log_entry)
        self.logs.append(log_entry)
        # Keep only last 100 logs to avoid memory issues
        if len(self.logs) > 100:
            self.logs.pop(0)

    def get_logs(self):
        return self.logs

    def get_signals(self):
        return self.signals

    def clear_logs(self):
        self.logs = []

    def connect(self, email, password, mode="PRACTICE"):
        # Force cleanup before connecting to ensure no stale session
        if self.api:
            try:
                self.api.api.close()
                del self.api
            except:
                pass
            self.api = None
            time.sleep(1)  # Wait for full disconnect
            
        self.email = email
        self.password = password
        
        # Create NEW instance - This acts as a separate "machine" for this user
        self.api = IQ_Option(email, password)
        print(f"[IQBot] Initializing separate bot instance {id(self.api)} for {email}")
        
        # Clear logs and stats on new connection to prevent data leak
        self.clear_logs()
        self.reset_stats()
        
        # Attempt connection
        check, reason = self.api.connect()
        
        if check:
            self.connected = True
            
            # Change account mode
            self.api.change_balance(mode)
            
            self.update_balance()
            
            # VERIFICATION: Log which account we're actually connected to
            self.add_log(f"✓ Connected as: {email}")
            self.add_log(f"✓ Balance: {self.currency}{self.balance}")
            self.add_log(f"✓ Mode: {mode}")
            
            return True, f"Connected successfully ({mode})"
        else:
            self.connected = False
            self.is_running = False
            
            # Clean up failed instance
            try:
                self.api.api.close()
                del self.api
                self.api = None
            except: 
                pass
                
            if reason == "[{'code': 'invalid_credentials', 'message': 'You entered the wrong credentials. Please check that the login and password is correct.'}]":
                 return False, "Invalid Credentials"
            
            return False, f"Connection failed: {reason}"

    def update_balance(self):
        if self.connected:
            self.balance = self.api.get_balance()
            self.currency = self.api.get_currency()

    def start_trading(self):
        if self.is_running:
            self.add_log("Bot is already running.")
            return
            
        self.is_running = True
        self.add_log("Starting trading loop...")
        threading.Thread(target=self._trading_loop, daemon=True).start()

    def _trading_loop(self):
        self.add_log("Trading loop started.")
        while self.is_running and self.connected:
            try:
                self.add_log("Starting market scan...")

                for pair in self.pairs_to_scan:
                    if not self.is_running: 
                        break
                    
                    # Double check if trade started during loop
                    if self.trade_in_progress: 
                        self.add_log("Trade in progress. Pausing analysis.")
                        break

                    try:
                        self.add_log(f"Analysing {pair}...")
                        if self._process_pair(pair):
                            # Trade placed, break loop to wait for it to finish
                            break
                    except Exception as e:
                        print(f"Error processing {pair}: {e}")
                        self.add_log(f"Error analysing {pair}: {str(e)}")
                        
                self.add_log("Scan complete. Waiting...")
                self.next_trading_time = time.time() + 2
                time.sleep(2)  # Wait a bit before next scan cycle
            except Exception as e:
                print(f"Error in trading loop: {e}")
                traceback.print_exc()
                time.sleep(5)

    def _process_pair(self, pair):
        if not self.is_running:
            return False

        # Check for active simulation on this pair to prevent duplicates
        if not self.auto_trading and pair in self.active_simulations:
            if time.time() < self.active_simulations[pair]:
                # self.add_log(f"Skipping {pair}: Active simulation in progress.") # Optional log
                return False
            else:
                # Cleanup expired
                del self.active_simulations[pair]
            
        # Analyze Strategy
        action, reason = self.analyze_strategy(pair)
        
        # Log analysis (optional: restrict to errors or important status to avoid spam)
        # But user requested "show pair being analysed", so we log it.
        self.add_log(f"Analysis {pair}: {reason}")
        
        if action:
            direction = action
            
            # Expiry Rule: Use configured duration
            expiry_duration = self.trade_duration 
            
            # Money Management: Use configured amount directly
            actual_amount = self.trade_amount
            
            # Check Auto Trading
            if not self.auto_trading:
                # Simulation Logic
                try:
                    # Get current price for entry
                    candle = self.api.get_candles(pair, 60, 1, time.time())
                    entry_price = float(candle[-1]['close'])
                except:
                    entry_price = 0
                
                signal_id = str(uuid.uuid4())[:8]
                timestamp_str = time.strftime("%H:%M:%S")
                
                signal = {
                    "id": signal_id,
                    "pair": pair,
                    "direction": direction,
                    "entry": entry_price,
                    "exit": 0,
                    "status": "Running",
                    "time": timestamp_str,
                    "timestamp": time.time()
                }
                
                self.signals.insert(0, signal) # Add to top
                self.signals = self.signals[:50] # Keep last 50
                
                # Register active simulation
                self.active_simulations[pair] = time.time() + (expiry_duration * 60)
                
                self.add_log(f"SIMULATION: {pair} {direction} @ {entry_price}")
                
                threading.Thread(target=self._monitor_simulation, args=(signal_id, pair, direction, expiry_duration, entry_price), daemon=True).start()
                return True 
            
            # Place Trade
            check, id = self.api.buy(actual_amount, pair, direction, expiry_duration)
            if check:
                self.trade_in_progress = True
                self.add_log(f"Trade placed: {pair} {direction} ${actual_amount:.2f} ({expiry_duration}m)")
                threading.Thread(target=self._check_trade_result, args=(id, expiry_duration), daemon=True).start()
                self.update_balance()
                return True
            else:
                self.add_log(f"Trade failed: {pair} {direction}")
                return False
                
        return False

    def _monitor_simulation(self, signal_id, pair, direction, duration, entry_price):
        # Wait for expiry
        time.sleep(duration * 60)
        
        try:
            # Get exit price
            candle = self.api.get_candles(pair, 60, 1, time.time())
            exit_price = float(candle[-1]['close'])
            
            # Find and update signal
            for s in self.signals:
                if s['id'] == signal_id:
                    s['exit'] = exit_price
                    
                    status = 'TIE'
                    if direction == 'call':
                        if exit_price > entry_price: status = 'WIN'
                        elif exit_price < entry_price: status = 'LOSS'
                    else: # put
                        if exit_price < entry_price: status = 'WIN'
                        elif exit_price > entry_price: status = 'LOSS'
                    
                    s['status'] = status
                    self.add_log(f"SIM RESULT: {pair} {status} ({entry_price} -> {exit_price})")
                    break
        except Exception as e:
            print(f"Sim error: {e}")
            self.add_log(f"Error checking simulation result: {e}")

    def analyze_strategy(self, pair):
        if self.strategy == "RSI Reversal":
             return self.strategy_rsi_reversal(pair)
        elif self.strategy == "EMA Trend Pullback":
             return self.strategy_ema_trend_pullback(pair)
        elif self.strategy == "Support & Resistance":
             return self.strategy_support_resistance(pair)
        else:
             return self.strategy_momentum(pair)

    def strategy_support_resistance(self, pair):
        try:
            # Fetch Candles (1 min timeframe = 60s)
            # Need slightly more history for S/R zones
            candles = self.api.get_candles(pair, 60, 150, time.time())
            
            if not candles or len(candles) < 100:
                return None, "Not enough candles"
                
            # Convert to numpy arrays
            close_prices = np.array([c['close'] for c in candles], dtype=float)
            open_prices = np.array([c['open'] for c in candles], dtype=float)
            high_prices = np.array([c['max'] for c in candles], dtype=float)
            low_prices = np.array([c['min'] for c in candles], dtype=float)
            
            # Indicators
            rsi = talib.RSI(close_prices, timeperiod=14)
            
            # Indices: 
            # -1 is current incomplete candle (ignore)
            # -2 is confirmation candle (must be bullish/bearish close)
            # -3 is rejection candle (must be pinbar/rejection at zone)
            
            idx_conf = -2
            idx_rej = -3
            
            # Confirmation Candle Data
            conf_close = close_prices[idx_conf]
            conf_open = open_prices[idx_conf]
            
            # Rejection Candle Data
            rej_close = close_prices[idx_rej]
            rej_open = open_prices[idx_rej]
            rej_high = high_prices[idx_rej]
            rej_low = low_prices[idx_rej]
            rej_body_size = abs(rej_close - rej_open)
            rej_total_size = rej_high - rej_low
            
            # RSI at rejection moment (using idx_rej is safer as per instructions)
            rej_rsi = rsi[idx_rej]
            
            if rej_total_size == 0:
                return None, "Doji (Zero Size)"

            # --- HELPER: Find S/R Zones ---
            # We look at past 60 candles before rejection candle
            past_lows = low_prices[idx_rej-60 : idx_rej]
            past_highs = high_prices[idx_rej-60 : idx_rej]
            
            # Function to check if price is near a level with >= 3 touches
            def is_near_level(price, levels, threshold=0.0003, min_touches=3):
                # Simple clustering
                # Count how many levels are within threshold of price
                count = 0
                for lvl in levels:
                    if abs(price - lvl) < threshold:
                        count += 1
                return count >= min_touches

            # CALL SCENARIO
            # 1. Price touches support (Rejection candle Low is near support zone)
            # 2. Rejection candle (Long lower wick)
            # 3. RSI 25-40
            # 4. Confirmation candle is Bullish
            
            is_call_rsi = 25 <= rej_rsi <= 40
            is_call_rejection = False
            
            # Calculate Lower Wick
            lower_wick = min(rej_open, rej_close) - rej_low
            # Wick should be significant (e.g., > 40% of total candle size or > body)
            if lower_wick > rej_total_size * 0.4:
                is_call_rejection = True
                
            # Check Support Zone
            # We check if 'rej_low' is near previous lows
            is_support_zone = is_near_level(rej_low, past_lows)
            
            # Check Confirmation
            is_conf_bullish = conf_close > conf_open
            
            if is_call_rsi and is_call_rejection and is_support_zone and is_conf_bullish:
                return "call", f"S&R Call (RSI: {rej_rsi:.1f}, RejWick: {lower_wick:.5f})"
                
            # PUT SCENARIO
            # 1. Price touches resistance (Rejection candle High is near resistance zone)
            # 2. Rejection candle (Long upper wick)
            # 3. RSI 60-75
            # 4. Confirmation candle is Bearish
            
            is_put_rsi = 60 <= rej_rsi <= 75
            is_put_rejection = False
            
            # Calculate Upper Wick
            upper_wick = rej_high - max(rej_open, rej_close)
            if upper_wick > rej_total_size * 0.4:
                is_put_rejection = True
                
            # Check Resistance Zone
            is_resistance_zone = is_near_level(rej_high, past_highs)
            
            # Check Confirmation
            is_conf_bearish = conf_close < conf_open
            
            if is_put_rsi and is_put_rejection and is_resistance_zone and is_conf_bearish:
                return "put", f"S&R Put (RSI: {rej_rsi:.1f}, RejWick: {upper_wick:.5f})"

            # Debugging / Reason
            reason = []
            if is_call_rsi: reason.append("RSI Call OK")
            if is_put_rsi: reason.append("RSI Put OK")
            if is_call_rejection: reason.append("Call Rej OK")
            if is_put_rejection: reason.append("Put Rej OK")
            if is_support_zone: reason.append("Supp Zone OK")
            if is_resistance_zone: reason.append("Res Zone OK")
            
            return None, f"No Setup. Matches: {', '.join(reason) if reason else 'None'}"

        except Exception as e:
            return None, f"Error S&R: {e}"


    def strategy_ema_trend_pullback(self, pair):
        try:
            # Fetch Candles (1 min timeframe = 60s)
            candles = self.api.get_candles(pair, 60, 100, time.time())
            
            if not candles or len(candles) < 60:
                return None, "Not enough candles"
                
            # Convert to numpy arrays
            close_prices = np.array([c['close'] for c in candles], dtype=float)
            open_prices = np.array([c['open'] for c in candles], dtype=float)
            low_prices = np.array([c['min'] for c in candles], dtype=float)
            high_prices = np.array([c['max'] for c in candles], dtype=float)
            
            # Indicators: EMA 9, EMA 21, RSI 14
            ema9 = talib.EMA(close_prices, timeperiod=9)
            ema21 = talib.EMA(close_prices, timeperiod=21)
            rsi = talib.RSI(close_prices, timeperiod=14)
            
            # Analysis on the last completed candle (index -2)
            last_idx = -2
            
            c_close = close_prices[last_idx]
            c_open = open_prices[last_idx]
            c_low = low_prices[last_idx]
            c_high = high_prices[last_idx]
            
            c_ema9 = ema9[last_idx]
            c_ema21 = ema21[last_idx]
            c_rsi = rsi[last_idx]
            
            # Trend Identification
            # UP Trend: EMA 9 > EMA 21
            # DOWN Trend: EMA 9 < EMA 21
            is_uptrend = c_ema9 > c_ema21
            is_downtrend = c_ema9 < c_ema21
            
            # Avoid Flat EMAs / Crossovers (ensure some separation)
            ema_dist = abs(c_ema9 - c_ema21)
            min_dist = c_close * 0.0001 # Minimum separation threshold
            if ema_dist < min_dist:
                 return None, f"Flat/Crossing EMAs (Dist: {ema_dist:.5f})"

            # CALL Entry Logic
            if is_uptrend:
                # Price pulls back and touches or nearly touches EMA 21
                # We check if the Low of the candle touched EMA 21 region
                # Touching region: Low <= EMA21 * 1.0002 (slightly above allowed) AND High >= EMA21
                
                touched_ema21 = c_low <= c_ema21 * 1.0002 and c_high >= c_ema21 * 0.9998
                
                # RSI stays above 50
                rsi_ok = c_rsi > 50
                
                # Entry candle closes bullish (Close > Open)
                is_bullish = c_close > c_open
                
                if touched_ema21 and rsi_ok and is_bullish:
                     return "call", f"EMA Pullback UP (RSI: {c_rsi:.1f})"
                else:
                     return None, f"No Call Setup (Trend UP, RSI: {c_rsi:.1f}, Bullish: {is_bullish})"

            # PUT Entry Logic
            elif is_downtrend:
                # Price pulls back to EMA 21
                # Touching region: High >= EMA21 * 0.9998 AND Low <= EMA21
                
                touched_ema21 = c_high >= c_ema21 * 0.9998 and c_low <= c_ema21 * 1.0002
                
                # RSI stays below 50
                rsi_ok = c_rsi < 50
                
                # Entry candle closes bearish (Close < Open)
                is_bearish = c_close < c_open
                
                if touched_ema21 and rsi_ok and is_bearish:
                     return "put", f"EMA Pullback DOWN (RSI: {c_rsi:.1f})"
                else:
                     return None, f"No Put Setup (Trend DOWN, RSI: {c_rsi:.1f}, Bearish: {is_bearish})"
            
            return None, "No Trend"

        except Exception as e:
            return None, f"Error: {e}"

    def strategy_rsi_reversal(self, pair):
        try:
            # Fetch Candles (1 min timeframe = 60s)
            candles = self.api.get_candles(pair, 60, 100, time.time())
            if not candles or len(candles) < 60:
                return None, "Not enough candles"
                
            close_prices = np.array([c['close'] for c in candles], dtype=float)
            rsi = talib.RSI(close_prices, timeperiod=14)
            
            last_idx = -2
            c_rsi = rsi[last_idx]
            
            # Simple Reversal Logic
            if c_rsi > 70:
                return "put", f"RSI Overbought ({c_rsi:.1f})"
            elif c_rsi < 30:
                return "call", f"RSI Oversold ({c_rsi:.1f})"
                
            return None, f"RSI Neutral ({c_rsi:.1f})"
        except Exception as e:
            return None, f"Error: {e}"

    def strategy_momentum(self, pair):
        try:
            # Fetch Candles (1 min timeframe = 60s)
            candles = self.api.get_candles(pair, 60, 100, time.time())
            
            if not candles or len(candles) < 60:
                return None, "Not enough candles"
                
            # Convert to numpy arrays
            close_prices = np.array([c['close'] for c in candles], dtype=float)
            open_prices = np.array([c['open'] for c in candles], dtype=float)
            high_prices = np.array([c['max'] for c in candles], dtype=float)
            low_prices = np.array([c['min'] for c in candles], dtype=float)
            
            # Indicators
            ema20 = talib.EMA(close_prices, timeperiod=20)
            ema50 = talib.EMA(close_prices, timeperiod=50)
            upper_bb, middle_bb, lower_bb = talib.BBANDS(close_prices, timeperiod=20, nbdevup=2.0, nbdevdn=2.0, matype=0)
            rsi = talib.RSI(close_prices, timeperiod=14)
            
            last_idx = -2
            prev_idx = -3
            
            c_close = close_prices[last_idx]
            c_open = open_prices[last_idx]
            c_high = high_prices[last_idx]
            c_low = low_prices[last_idx]
            
            c_rsi = rsi[last_idx]
            c_ema20 = ema20[last_idx]
            c_ema50 = ema50[last_idx]
            
            # Trend Filter
            is_uptrend = c_ema20 > c_ema50 and c_rsi > 50
            is_downtrend = c_ema20 < c_ema50 and c_rsi < 50
            
            # EMA Separation Check
            ema_dist = abs(c_ema20 - c_ema50)
            min_dist = c_close * 0.00005 
            if ema_dist < min_dist:
                return None, f"Low EMA Dist ({ema_dist:.5f}<{min_dist:.5f})"
            
            if not is_uptrend and not is_downtrend:
                return None, f"No Trend (RSI={c_rsi:.1f})"
                
            # RSI Filter (45-55 NO TRADE)
            if 45 <= c_rsi <= 55:
                return None, f"RSI Neutral ({c_rsi:.1f})"

            # Volatility Check
            last_bodies = np.abs(close_prices[-12:-2] - open_prices[-12:-2])
            avg_body = np.mean(last_bodies)
            
            c_body_size = abs(c_close - c_open)
            
            # Low Volatility (Doji/Small)
            if c_body_size < avg_body * 0.2:
                return None, "Low Volatility (Doji)"
                
            # Impulse Candle (Huge) -> Avoid Exhaustion
            if c_body_size > avg_body * 3.0:
                return None, "High Volatility (Impulse)"

            # CALL SCENARIO
            if is_uptrend:
                is_bullish = c_close > c_open
                if not is_bullish: 
                    return None, "Uptrend but Bearish Candle"
                
                touched_zone = False
                
                if c_low <= c_ema20 * 1.0002 or c_low <= middle_bb[last_idx] * 1.0002:
                     touched_zone = True
                
                if not touched_zone:
                    p_low = low_prices[prev_idx]
                    if p_low <= ema20[prev_idx] * 1.0002 or p_low <= middle_bb[prev_idx] * 1.0002:
                        touched_zone = True
                        
                if not touched_zone:
                    return None, "Uptrend but No Pullback"
                    
                # Confirmation types
                is_engulfing = c_open <= close_prices[prev_idx] and c_close >= open_prices[prev_idx] and (close_prices[prev_idx] < open_prices[prev_idx])
                is_strong = c_body_size > avg_body
                lower_wick = c_open - c_low if is_bullish else c_close - c_low
                is_rejection = lower_wick > c_body_size * 0.5
                
                if is_engulfing or is_strong or is_rejection:
                    return "call", f"CALL Signal (RSI={c_rsi:.1f})"
                
                return None, "Uptrend but Weak Candle"

            # PUT SCENARIO
            elif is_downtrend:
                is_bearish = c_close < c_open
                if not is_bearish: 
                    return None, "Downtrend but Bullish Candle"
                
                touched_zone = False
                
                if c_high >= c_ema20 * 0.9998 or c_high >= middle_bb[last_idx] * 0.9998:
                    touched_zone = True
                    
                if not touched_zone:
                    p_high = high_prices[prev_idx]
                    if p_high >= ema20[prev_idx] * 0.9998 or p_high >= middle_bb[prev_idx] * 0.9998:
                        touched_zone = True
                        
                if not touched_zone:
                    return None, "Downtrend but No Pullback"
                    
                # Confirmation types
                is_engulfing = c_open >= close_prices[prev_idx] and c_close <= open_prices[prev_idx] and (close_prices[prev_idx] > open_prices[prev_idx])
                is_strong = c_body_size > avg_body
                upper_wick = c_high - c_open if is_bearish else c_high - c_close
                is_rejection = upper_wick > c_body_size * 0.5
                
                if is_engulfing or is_strong or is_rejection:
                    return "put", f"PUT Signal (RSI={c_rsi:.1f})"
                    
                return None, "Downtrend but Weak Candle"
                    
            return None, "Unknown State"
            
        except Exception as e:
            print(f"Error in analysis: {e}")
            return None, f"Error: {e}"

    def _check_trade_result(self, order_id, duration=None):
        try:
            wait_time = (duration * 60) if duration else (self.trade_duration * 60)
            time.sleep(wait_time + 5)
            
            result = None
            
            try:
                result = self.api.check_win_v4(order_id)
            except:
                pass

            if result is None:
                 try:
                     result = self.api.check_win_v3(order_id)
                 except:
                     pass

            if result is not None:
                profit = float(result)
                if profit > 0:
                    self.wins += 1
                    self.current_consecutive_losses = 0
                    msg = f"WIN: +${profit:.2f}"
                    self.add_log(msg)
                    self.send_push("Trade Won 💰", f"{self.currency} {profit:.2f}")
                elif profit < 0:
                    self.losses += 1
                    self.current_consecutive_losses += 1
                    msg = f"LOSS: ${profit:.2f}"
                    self.add_log(msg)
                    self.send_push("Trade Lost 🔻", f"{self.currency} {profit:.2f}")
                else:
                    msg = f"TIE: $0.00"
                    self.add_log(msg)
                    
                self.total_profit += profit
                self.trades_taken += 1
                self.update_balance()
                
                # Check limits
                if self.stop_loss > 0 and self.total_profit <= -self.stop_loss:
                     self.add_log(f"Stop Loss reached (-${self.stop_loss}). Stopping bot.")
                     self.send_push("Bot Stopped 🛑", f"Stop Loss reached (-${self.stop_loss})")
                     self.stop()
                elif self.take_profit > 0 and self.total_profit >= self.take_profit:
                     self.add_log(f"Take Profit reached (+${self.take_profit}). Stopping bot.")
                     self.send_push("Bot Stopped 🛑", f"Take Profit reached (+${self.take_profit})")
                     self.stop()
                else:
                    limit_consecutive = self.max_consecutive_losses if self.max_consecutive_losses > 0 else 2
                    
                    if self.current_consecutive_losses >= limit_consecutive:
                        self.add_log(f"Max consecutive losses reached ({self.current_consecutive_losses}). Stopping bot.")
                        self.send_push("Bot Stopped 🛑", f"Max consecutive losses reached ({self.current_consecutive_losses})")
                        self.stop()
                    elif self.max_trades > 0 and self.trades_taken >= self.max_trades:
                        self.add_log(f"Max trades limit reached ({self.trades_taken}). Stopping bot.")
                        self.send_push("Bot Stopped 🛑", f"Max trades limit reached")
                        self.stop()

            else:
                self.add_log(f"Warning: Could not fetch result for trade {order_id}")
                
        except Exception as e:
            print(f"Error checking trade result: {e}")
            self.add_log(f"Error checking trade result: {e}")

        finally:
            self.trade_in_progress = False

    def stop(self):
        self.add_log("Stopping bot...")
        self.is_running = False
        return True, "Bot stopped"

    def disconnect(self):
        self.stop()
        
        if self.api:
            try:
                self.api.api.close()
                del self.api
            except Exception as e:
                print(f"Error closing API: {e}")
        
        time.sleep(1)
        
        self.connected = False
        self.api = None
        self.email = None
        self.password = None
        
        self.balance = 0
        self.currency = ""
        self.logs = []
        self.reset_stats()
        
        return True, "Disconnected"
