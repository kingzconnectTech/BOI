from iqoptionapi.stable_api import IQ_Option
import time
import threading
import random
import os
import glob
import traceback

import talib
import numpy as np
from datetime import datetime, timedelta
from exponent_server_sdk import PushClient, PushMessage

class IQBot:
    def __init__(self):
        self.api = None
        self.email = None
        self.password = None
        self.connected = False
        self.is_running = False
        self.balance = 0
        self.currency = ""
        self.logs = [] # Store logs for frontend
        
        # Trade Config
        self.trade_amount = 1
        self.trade_duration = 1 # minutes
        self.stop_loss = 0
        self.take_profit = 0
        self.max_consecutive_losses = 0
        self.max_trades = 0 # 0 means unlimited
        self.auto_trading = True
        self.push_token = None # Expo Push Token
        
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

    def reset_stats(self):
        self.total_profit = 0
        self.wins = 0
        self.losses = 0
        self.trades_taken = 0
        self.current_consecutive_losses = 0
        self.logs = []
        self.balance = 0
        self.currency = ""

    def connect(self, email, password, mode="PRACTICE"):
        # Force cleanup before connecting to ensure no stale session
        if self.api:
            try:
                self.api.api.close()
                del self.api
            except:
                pass
            self.api = None
            
        self.reset_stats() # FORCE RESET ALL STATS AND VARIABLES
        
        self.email = email
        self.password = password
        
        # 1. Initialize API
        try:
            # We use a global lock here just in case the library has thread-safety issues during init
            with bot_manager.lock:
                # CRITICAL: Remove any existing session file to prevent reusing old credentials
                self._clear_session_file()
                
                print(f"Initializing IQ_Option for {email}")
                self.api = IQ_Option(email, password)
                
                # Clear logs and stats on new connection to prevent data leak
                self.clear_logs() 
                self.reset_stats()
                
                # Attempt connection
                print("Connecting to IQ Option API...")
                check, reason = self.api.connect()
        except Exception as e:
            print(f"CRITICAL ERROR during connection initialization: {e}")
            traceback.print_exc()
            return False, f"Internal Error during connection: {str(e)}"
        
        if check:
            self.connected = True
            print("API Connected. Verifying identity...")
            
            # 2. Identity Verification
            # We must verify that the connected account matches the requested email
            try:
                # Wait for profile data to be populated (timeout 30s)
                # In iqoptionapi, profile is usually in self.api.profile.msg
                profile_email = None
                
                # Force a profile update request
                self.api.get_profile_ansyc()
                
                start_time = time.time()
                while time.time() - start_time < 30: # 30 seconds timeout
                     if hasattr(self.api, 'profile') and self.api.profile and hasattr(self.api.profile, 'msg') and self.api.profile.msg:
                         # Depending on library version, msg might be the dict or msg['result']
                         msg = self.api.profile.msg
                         if isinstance(msg, dict):
                             profile_email = msg.get('email')
                         
                         if profile_email:
                             print(f"Profile email found: {profile_email}")
                             break
                     
                     # Re-trigger profile fetch every 5 seconds if still waiting
                     if int(time.time() - start_time) % 5 == 0:
                         self.api.get_profile_ansyc()
                         
                     time.sleep(0.5)
                
                # STRICT EMAIL CHECK
                if profile_email:
                    if profile_email.lower().strip() != email.lower().strip():
                        self.add_log(f"CRITICAL: Session mismatch! Requested {email}, but connected to {profile_email}. Disconnecting.")
                        self.disconnect() 
                        return False, f"Session Error: Connected to {profile_email} instead of {email}."
                else:
                    # If we can't verify, we log a warning but PROCEED if balance check works
                    # We assume _clear_session_file handled the "wrong account" risk
                    self.add_log("Warning: Email verification timed out. Proceeding based on clean session.")
                    print("Warning: Email verification timed out.")

                # Check balance to ensure it's fresh
                self.api.change_balance(mode)
                time.sleep(1) # Wait for mode change to propagate
                self.balance = self.api.get_balance()
                self.currency = self.api.get_currency()
                
            except Exception as e:
                print(f"Profile/Balance check error: {e}")
                traceback.print_exc()
                self.disconnect()
                return False, f"Error verifying account: {str(e)}"

            self.update_balance()
            self.add_log(f"Connected to {email} ({mode}). Balance: {self.currency}{self.balance}")
            return True, f"Connected successfully ({mode})"
            self.add_log(f"Connected to {email} ({mode}). Balance: {self.currency}{self.balance}")
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
        threading.Thread(target=self._trading_loop).start()

    def _trading_loop(self):
        while self.is_running and self.connected:
            try:
                # 1. Skip Open Check for now to avoid 'underlying' error
                # We will just try to trade and let the API reject if closed
                
                # For now, let's just pick a few popular pairs to scan
                pairs_to_scan = ["EURUSD-OTC", "GBPUSD-OTC", "AUDCAD-OTC", "USDCHF-OTC", "NZDUSD-OTC", "USDJPY-OTC"]
                # Remove restricted pairs if any were accidentally added or just filter strictly
                # User requested: "usdjyo-otc, nzdusd-otc do not trade them"
                # So we keep the list safe:
                pairs_to_scan = ["EURUSD-OTC", "GBPUSD-OTC", "AUDCAD-OTC", "USDCHF-OTC", "EURJPY-OTC"]
                
                # Scan pairs sequentially to ensure deterministic behavior
                # random.shuffle(pairs_to_scan) - Removed as per request
                
                self.add_log("Starting market scan...")

                for pair in pairs_to_scan:
                    if not self.is_running: break
                    
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
                        # traceback.print_exc()
                        
                self.add_log("Scan complete. Waiting...")
                time.sleep(2) # Wait a bit before next scan cycle
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
            # self.add_log(f"Outside trading hours (WAT). Current: {current_time.strftime('%H:%M')}")
            return False # Just skip quietly or log once (too noisy if logged every loop)
            
        # Analyze Strategy
        action = self.analyze_strategy(pair)
        
        if action:
            direction = action
            
            # Expiry Rule: Use User Defined Duration
            # STRATEGY OVERRIDE: 1 min chart -> 2 min expiry
            expiry_duration = 2 
            
            # Money Management: Risk 1-2% per trade
            # Cap trade amount at 2% of balance
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
                threading.Thread(target=self._check_trade_result, args=(id, expiry_duration)).start()
                self.update_balance()
                return True
            else:
                self.add_log(f"Trade failed: {pair} {direction}")
                return False
                
        return False

    def analyze_strategy(self, pair):
        try:
            # 1. Fetch Candles (1 min timeframe = 60s)
            # Need enough for EMA 50 -> fetch 100 candles
            candles = self.api.get_candles(pair, 60, 100, time.time())
            
            if not candles or len(candles) < 60:
                return None
                
            # Convert to numpy arrays
            # candles is a list of dicts: [{'open': 1.1, 'close': 1.2, ...}, ...]
            close_prices = np.array([c['close'] for c in candles], dtype=float)
            open_prices = np.array([c['open'] for c in candles], dtype=float)
            high_prices = np.array([c['max'] for c in candles], dtype=float)
            low_prices = np.array([c['min'] for c in candles], dtype=float)
            
            # 2. Indicators
            ema20 = talib.EMA(close_prices, timeperiod=20)
            ema50 = talib.EMA(close_prices, timeperiod=50)
            upper_bb, middle_bb, lower_bb = talib.BBANDS(close_prices, timeperiod=20, nbdevup=2.0, nbdevdn=2.0, matype=0)
            rsi = talib.RSI(close_prices, timeperiod=14)
            
            # Indices: -1 is current (forming), -2 is last closed
            last_idx = -2
            prev_idx = -3 # For checking previous candle context if needed
            
            c_close = close_prices[last_idx]
            c_open = open_prices[last_idx]
            c_high = high_prices[last_idx]
            c_low = low_prices[last_idx]
            
            c_rsi = rsi[last_idx]
            c_ema20 = ema20[last_idx]
            c_ema50 = ema50[last_idx]
            
            # Step 1: Trend Filter
            is_uptrend = c_ema20 > c_ema50 and c_rsi > 50
            is_downtrend = c_ema20 < c_ema50 and c_rsi < 50
            
            # EMA Separation Check (Avoid flat/crossing)
            # Threshold: 0.005% of price
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
            # Calculate average body size of last 10 candles
            last_bodies = np.abs(close_prices[-12:-2] - open_prices[-12:-2])
            avg_body = np.mean(last_bodies)
            
            # Current (forming) body size
            # For confirmation, we look at last CLOSED candle (idx -2)
            c_body_size = abs(c_close - c_open)
            
            # 1. Low Volatility (Doji/Small)
            if c_body_size < avg_body * 0.2:
                return None
                
            # 2. Impulse Candle (Huge) -> Avoid Exhaustion
            if c_body_size > avg_body * 3.0:
                return None

            # Step 2 & 3: Pullback + Confirmation
            
            # CALL SCENARIO
            if is_uptrend:
                # Rule: Pullback to EMA 20 OR Lower/Middle BB
                # Check if Low of last closed candle touched EMA20 or Lower BB
                # Or if previous candle touched it.
                
                # Simplified Pullback Logic:
                # We want to enter ON confirmation.
                # So the Confirmation Candle (last closed) should be GREEN (Bullish).
                is_bullish = c_close > c_open
                if not is_bullish: return None
                
                # Check for Pullback context:
                # Did this candle or the previous one touch the zone?
                # Zone: EMA20, LowerBB, MiddleBB
                # We check if Low <= EMA20 (or close to it)
                
                # Let's check if the Low of the confirmation candle OR the previous candle dipped near EMA20
                touched_zone = False
                
                # Check current candle (Confirmation) Low
                if c_low <= c_ema20 * 1.0002 or c_low <= middle_bb[last_idx] * 1.0002: # Small buffer
                     touched_zone = True
                
                # Check previous candle Low
                if not touched_zone:
                    p_low = low_prices[prev_idx]
                    if p_low <= ema20[prev_idx] * 1.0002 or p_low <= middle_bb[prev_idx] * 1.0002:
                        touched_zone = True
                        
                if not touched_zone:
                    return None
                    
                # Confirmation types:
                # 1. Bullish Engulfing
                is_engulfing = c_open <= close_prices[prev_idx] and c_close >= open_prices[prev_idx] and (close_prices[prev_idx] < open_prices[prev_idx])
                # 2. Strong Bullish (Body size)
                is_strong = c_body_size > avg_body
                # 3. Rejection (Long lower wick)
                lower_wick = c_open - c_low if is_bullish else c_close - c_low
                is_rejection = lower_wick > c_body_size * 0.5 # Wick is significant
                
                if is_engulfing or is_strong or is_rejection:
                    return "call"

            # PUT SCENARIO
            elif is_downtrend:
                # Rule: Pullback to EMA 20 OR Upper/Middle BB
                
                # Confirmation Candle must be RED (Bearish)
                is_bearish = c_close < c_open
                if not is_bearish: return None
                
                touched_zone = False
                
                # Check current candle High (touched from below?)
                if c_high >= c_ema20 * 0.9998 or c_high >= middle_bb[last_idx] * 0.9998:
                    touched_zone = True
                    
                if not touched_zone:
                    p_high = high_prices[prev_idx]
                    if p_high >= ema20[prev_idx] * 0.9998 or p_high >= middle_bb[prev_idx] * 0.9998:
                        touched_zone = True
                        
                if not touched_zone:
                    return None
                    
                # Confirmation types:
                # 1. Bearish Engulfing
                is_engulfing = c_open >= close_prices[prev_idx] and c_close <= open_prices[prev_idx] and (close_prices[prev_idx] > open_prices[prev_idx])
                # 2. Strong Bearish
                is_strong = c_body_size > avg_body
                # 3. Rejection (Long upper wick)
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
            # Wait for duration + buffer
            # We add a bit more buffer to ensure IQ Option has processed it
            wait_time = (duration * 60) if duration else (self.trade_duration * 60)
            time.sleep(wait_time + 5)
            
            result = None
            
            # Try check_win_v4 first
            try:
                result = self.api.check_win_v4(order_id)
            except:
                pass

            # Fallback to check_win_v3 if v4 fails or returns nothing
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
                
                # Check limits immediately after result
                if self.stop_loss > 0 and self.total_profit <= -self.stop_loss:
                     self.add_log(f"Stop Loss reached (-${self.stop_loss}). Stopping bot.")
                     self.send_push("Bot Stopped 🛑", f"Stop Loss reached (-${self.stop_loss})")
                     self.stop()
                elif self.take_profit > 0 and self.total_profit >= self.take_profit:
                     self.add_log(f"Take Profit reached (+${self.take_profit}). Stopping bot.")
                     self.send_push("Bot Stopped 🛑", f"Take Profit reached (+${self.take_profit})")
                     self.stop()
                else:
                    # Enforce Strategy Rule: 2 consecutive losses -> STOP (Default if not set)
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
        if self.api:
            # self.api.close() # Close connection might be too aggressive if we just want to stop trading
            pass
        return True, "Bot stopped"

    def _clear_session_file(self):
        """Attempts to remove session files created by iqoptionapi"""
        try:
            cwd = os.getcwd()
            print(f"Clearing session files. CWD: {cwd}")
            
            # Potential locations for session.json
            paths_to_check = [
                cwd,
                os.path.join(cwd, "backend"),
                os.path.dirname(os.path.abspath(__file__)) # The directory where bot_service.py is
            ]
            
            files = ["session.json", "auth.json"]
            
            for path in paths_to_check:
                for fname in files:
                    full_path = os.path.join(path, fname)
                    if os.path.exists(full_path):
                        try:
                            os.remove(full_path)
                            print(f"Removed session file: {full_path}")
                        except Exception as e:
                            print(f"Error removing {full_path}: {e}")
                            
        except Exception as e:
            print(f"Error clearing session file: {e}")

    def disconnect(self):
        self.stop()
        
        # Explicitly close the API connection to prevent zombie threads
        if self.api:
            try:
                self.api.api.close()
                del self.api
            except Exception as e:
                print(f"Error closing API: {e}")
                
        self.connected = False
        self.api = None
        self.email = None
        self.password = None
        
        # Clear persistent session files
        self._clear_session_file()
        
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
            "stats": {
                "profit": round(self.total_profit, 2),
                "wins": self.wins,
                "losses": self.losses,
                "win_rate": round(win_rate, 1)
            }
        }

class BotManager:
    def __init__(self):
        self.bots = {} # {email: IQBot()}
        self.lock = threading.Lock()
    
    def get_bot(self, email):
        email = email.lower().strip()
        with self.lock:
            # Note: We do NOT reuse the existing bot object if the user is reconnecting.
            # We want a fresh start. But if we just replace it, we might leave a thread running?
            # The 'disconnect' logic should handle stopping threads.
            if email not in self.bots:
                self.bots[email] = IQBot()
            return self.bots[email]
    
    def force_new_bot(self, email):
        """Destroys existing bot and creates a brand new instance"""
        email = email.lower().strip()
        with self.lock:
            if email in self.bots:
                print(f"Destroying old bot instance for {email}")
                try:
                    self.bots[email].disconnect() # Stop threads, close socket
                except:
                    pass
                del self.bots[email]
            
            print(f"Creating fresh bot instance for {email}")
            self.bots[email] = IQBot()
            return self.bots[email]
    
    def remove_bot(self, email):
        email = email.lower().strip()
        with self.lock:
            if email in self.bots:
                self.bots[email].disconnect()
                del self.bots[email]

# Global instance manager
bot_manager = BotManager()
