from iqoptionapi.stable_api import IQ_Option
import time
import threading
import traceback
import talib
import numpy as np
from datetime import datetime, timedelta
from exponent_server_sdk import PushClient, PushMessage

# ============================================================================
# IQBot Class - Single User Bot Instance
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
        
        # Trade Config
        self.trade_amount = 1
        self.trade_duration = 1  # minutes
        self.stop_loss = 0
        self.take_profit = 0
        self.max_consecutive_losses = 0
        self.max_trades = 0  # 0 means unlimited
        self.auto_trading = True
        self.push_token = None  # Expo Push Token
        
        self.initial_balance = 0
        self.total_profit = 0
        self.wins = 0
        self.losses = 0
        self.trades_taken = 0
        self.trade_in_progress = False
        self.current_consecutive_losses = 0

    def set_config(self, amount, duration, stop_loss, take_profit, max_consecutive_losses, max_trades, auto_trading=True):
        self.trade_amount = amount
        self.trade_duration = duration
        self.stop_loss = stop_loss
        self.take_profit = take_profit
        self.max_consecutive_losses = max_consecutive_losses
        self.max_trades = max_trades
        self.auto_trading = auto_trading
        
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
        self.is_running = True
        threading.Thread(target=self._trading_loop, daemon=True).start()

    def _trading_loop(self):
        while self.is_running and self.connected:
            try:
                pairs_to_scan = ["EURUSD-OTC", "GBPUSD-OTC", "AUDCAD-OTC", "USDCHF-OTC", "EURJPY-OTC"]
                
                self.add_log("Starting market scan...")

                for pair in pairs_to_scan:
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
                time.sleep(2)  # Wait a bit before next scan cycle
            except Exception as e:
                print(f"Error in trading loop: {e}")
                traceback.print_exc()
                time.sleep(5)

    def _process_pair(self, pair):
        # Time Check (WAT: UTC+1)
        utc_now = datetime.utcnow()
        wat_now = utc_now + timedelta(hours=1)
        
        # Ranges: 9:00-11:30, 14:00-16:30, 19:00-21:00
        current_time = wat_now.time()
        
        can_trade = False
        ranges = [
            ("09:00", "11:30"),
            ("14:00", "16:30"),
            ("19:00", "21:00")
        ]
        
        for start, end in ranges:
            s = datetime.strptime(start, "%H:%M").time()
            e = datetime.strptime(end, "%H:%M").time()
            if s <= current_time <= e:
                can_trade = True
                break
        
        if not can_trade:
            return False
            
        # Analyze Strategy
        action = self.analyze_strategy(pair)
        
        if action:
            direction = action
            
            # Expiry Rule: 2 min expiry
            expiry_duration = 2 
            
            # Money Management: Risk 1-2% per trade
            safe_max = max(1.0, self.balance * 0.02)
            actual_amount = min(self.trade_amount, safe_max)
            
            # Check Auto Trading
            if not self.auto_trading:
                self.add_log(f"SIGNAL: {pair} {direction.upper()} (Simulation)")
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

    def analyze_strategy(self, pair):
        try:
            # Fetch Candles (1 min timeframe = 60s)
            candles = self.api.get_candles(pair, 60, 100, time.time())
            
            if not candles or len(candles) < 60:
                return None
                
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
                return None
            
            if not is_uptrend and not is_downtrend:
                return None
                
            # RSI Filter (45-55 NO TRADE)
            if 45 <= c_rsi <= 55:
                return None

            # Volatility Check
            last_bodies = np.abs(close_prices[-12:-2] - open_prices[-12:-2])
            avg_body = np.mean(last_bodies)
            
            c_body_size = abs(c_close - c_open)
            
            # Low Volatility (Doji/Small)
            if c_body_size < avg_body * 0.2:
                return None
                
            # Impulse Candle (Huge) -> Avoid Exhaustion
            if c_body_size > avg_body * 3.0:
                return None

            # CALL SCENARIO
            if is_uptrend:
                is_bullish = c_close > c_open
                if not is_bullish: 
                    return None
                
                touched_zone = False
                
                if c_low <= c_ema20 * 1.0002 or c_low <= middle_bb[last_idx] * 1.0002:
                     touched_zone = True
                
                if not touched_zone:
                    p_low = low_prices[prev_idx]
                    if p_low <= ema20[prev_idx] * 1.0002 or p_low <= middle_bb[prev_idx] * 1.0002:
                        touched_zone = True
                        
                if not touched_zone:
                    return None
                    
                # Confirmation types
                is_engulfing = c_open <= close_prices[prev_idx] and c_close >= open_prices[prev_idx] and (close_prices[prev_idx] < open_prices[prev_idx])
                is_strong = c_body_size > avg_body
                lower_wick = c_open - c_low if is_bullish else c_close - c_low
                is_rejection = lower_wick > c_body_size * 0.5
                
                if is_engulfing or is_strong or is_rejection:
                    return "call"

            # PUT SCENARIO
            elif is_downtrend:
                is_bearish = c_close < c_open
                if not is_bearish: 
                    return None
                
                touched_zone = False
                
                if c_high >= c_ema20 * 0.9998 or c_high >= middle_bb[last_idx] * 0.9998:
                    touched_zone = True
                    
                if not touched_zone:
                    p_high = high_prices[prev_idx]
                    if p_high >= ema20[prev_idx] * 0.9998 or p_high >= middle_bb[prev_idx] * 0.9998:
                        touched_zone = True
                        
                if not touched_zone:
                    return None
                    
                # Confirmation types
                is_engulfing = c_open >= close_prices[prev_idx] and c_close <= open_prices[prev_idx] and (close_prices[prev_idx] > open_prices[prev_idx])
                is_strong = c_body_size > avg_body
                upper_wick = c_high - c_open if is_bearish else c_high - c_close
                is_rejection = upper_wick > c_body_size * 0.5
                
                if is_engulfing or is_strong or is_rejection:
                    return "put"
                    
            return None
            
        except Exception as e:
            print(f"Error in analysis: {e}")
            return None

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

    def get_status(self):
        win_rate = 0
        if self.trades_taken > 0:
            win_rate = (self.wins / self.trades_taken) * 100
            
        return {
            "connected": self.connected,
            "running": self.is_running,
            "balance": self.balance,
            "currency": self.currency,
            "email": self.email,  # Added for verification
            "stats": {
                "profit": round(self.total_profit, 2),
                "wins": self.wins,
                "losses": self.losses,
                "win_rate": round(win_rate, 1)
            }
        }


# ============================================================================
# BotManager Class - Manages Multiple User Bots
# ============================================================================

class BotManager:
    def __init__(self):
        self.bots = {}  # {email: IQBot()}
        self.locks = {}  # {email: threading.Lock()}
        self.global_lock = threading.Lock()
    
    def get_lock(self, email):
        with self.global_lock:
            if email not in self.locks:
                self.locks[email] = threading.Lock()
            return self.locks[email]

    def connect_bot(self, email, password, mode):
        email = email.lower().strip()
        user_lock = self.get_lock(email)
        
        with user_lock:
            if email not in self.bots:
                print(f"[BotManager] Creating NEW bot for {email}")
                self.bots[email] = IQBot()
            else:
                print(f"[BotManager] Using EXISTING bot for {email}")
            
            bot = self.bots[email]
            return bot.connect(email, password, mode)
            
    def get_bot(self, email):
        email = email.lower().strip()
        if email in self.bots:
            return self.bots[email]
        return None
    
    def remove_bot(self, email):
        email = email.lower().strip()
        user_lock = self.get_lock(email)
        
        with user_lock:
            if email in self.bots:
                self.bots[email].disconnect()
                del self.bots[email]
                print(f"[BotManager] Removed bot for {email}")


# Global bot manager instance
bot_manager = BotManager()