import time
import pandas as pd
from datetime import datetime, timezone
import yfinance as yf
from iqoptionapi.stable_api import IQ_Option
import os
import threading

class DataFeed:
    def __init__(self, session_id=None):
        self.session_id = session_id
        self.iq_api = None
        self.is_connected = False
        self.use_iq = False
        self.symbol = "EURUSD"
        self.session_file = f"session_{session_id}.json" if session_id else "session.json"
        
        # Credentials storage for re-init
        self.email = None
        self.password = None
        self.account_type = "PRACTICE"
        self.last_balance = 0.0
        self.conn_lock = threading.Lock()
        self.last_trade_ts = 0
        self.grace_seconds = 6
        self.fail_count = 0
        self.iq_cooldown_until = 0

    def disconnect(self):
        print("Disconnect called.") # Debug log
        self.is_connected = False
        if self.iq_api:
            try:
                self.iq_api.close()
            except:
                pass
            self.iq_api = None
        return True, "Disconnected"

    def ensure_connection(self, mode="soft"):
        """
        Centralized reconnection with locking to avoid race conditions.
        mode: "soft" tries reconnect; "hard" closes and full reconnect.
        """
        if not self.email or not self.password:
            return False
        with self.conn_lock:
            try:
                if mode == "hard":
                    try:
                        if self.iq_api:
                            self.iq_api.close()
                        self.iq_api = None
                    except:
                        pass
                    time.sleep(1)
                if self.iq_api is None:
                    self.iq_api = IQ_Option(self.email, self.password)
                check, reason = self.iq_api.connect()
                if check:
                    self.is_connected = True
                    try:
                        self.iq_api.change_balance(self.account_type.upper())
                    except:
                        pass
                    return True
                else:
                    print(f"Reconnect failed: {reason}")
                    return False
            except Exception as e:
                print(f"Reconnect Exception: {e}")
                return False

    def connect_iq(self, email, password, account_type="PRACTICE"):
        """
        Connects to IQ Option API.
        account_type: "PRACTICE" or "REAL"
        """
        # Store credentials for potential re-connection/re-initialization
        self.email = email
        self.password = password
        self.account_type = account_type

        # Ensure previous session is cleared
        self.disconnect()

        try:
            print(f"Connecting with email: {email}")
            
            # Extra cleanup before new connection
            if os.path.exists(self.session_file):
                try:
                    os.remove(self.session_file)
                except: pass
            
            # Initialize API
            self.iq_api = IQ_Option(email, password)
            
            # Retry logic for connection
            max_retries = 3
            for attempt in range(max_retries):
                try:
                    print(f"Attempting connection {attempt+1}/{max_retries}...")
                    check, reason = self.iq_api.connect()
                    
                    if check:
                        print("Connection Check: Success")
                        
                        # Ensure account type is valid and switch
                        target_account = account_type.upper()
                        print(f"Switching to {target_account} account...")
                        self.iq_api.change_balance(target_account) 
                        
                        # Verify balance type (optional, just logging)
                        current_balance = self.iq_api.get_balance()
                        print(f"Connected. Balance: {current_balance}")
                        
                        self.is_connected = True
                        self.use_iq = True
                        return True, f"Connected to {target_account} account."
                    else:
                        print(f"Connection Check: Failed ({reason})")
                        if attempt < max_retries - 1:
                            time.sleep(2)
                            continue
                        return False, f"Connection failed: {reason}"
                except Exception as e:
                    print(f"Connection Exception: {e}")
                    if attempt < max_retries - 1:
                        time.sleep(2)
                        continue
                    return False, f"Connection Error: {str(e)}"
            
            return False, "Connection failed after retries."
            
        except Exception as e:
            return False, str(e)

    def get_balance(self):
        """
        Safely gets the balance, handling reconnection if needed.
        """
        if not self.use_iq:
            return 0.0
            
        # If not connected but we have a last balance, return it to prevent UI flicker
        if not self.is_connected:
            return self.last_balance

        try:
            bal = self.iq_api.get_balance()
            self.last_balance = bal
            return bal
        except Exception as e:
            print(f"Get Balance Error: {e}")
            # Force Reconnect Logic
            try:
                print("Connection issue detected in get_balance. Reconnecting...")
                # Always try to connect if we hit an error, regardless of check_connect()
                if self.ensure_connection(mode="soft"):
                    bal = self.iq_api.get_balance()
                    self.last_balance = bal
                    return bal
                else:
                    if self.ensure_connection(mode="hard"):
                        bal = self.iq_api.get_balance()
                        self.last_balance = bal
                        return bal
            except Exception as re_err:
                print(f"Reconnection in get_balance failed: {re_err}")
            
            # If all fails, return last known balance instead of 0.0
            # This prevents "Account Removed"
            return self.last_balance

    def fetch_data(self, symbol=None, period="5d", interval="1m"):
        """
        Fetches data with resilient fallback:
        - Try IQ Option first if connected.
        - If IQ returns None/empty, fallback to yfinance to keep UI and strategy alive.
        """
        target_symbol = symbol if symbol else self.symbol
        
        df = None
        now = time.time()
        # Respect IQ cooldown window if set
        if self.iq_cooldown_until and now < self.iq_cooldown_until:
            return self._fetch_yf_data(target_symbol, period, interval)
        
        if self.use_iq and self.is_connected:
            df = self._fetch_iq_data(target_symbol, interval)
            if df is not None and not df.empty:
                return df
            # If IQ failed, try to recover softly once
            self.ensure_connection(mode="soft")
            df = self._fetch_iq_data(target_symbol, interval)
            if df is not None and not df.empty:
                return df
        
        # If we were in cooldown and it's over, try IQ again next time
        if self.iq_cooldown_until and now >= self.iq_cooldown_until:
            self.iq_cooldown_until = 0
            self.fail_count = 0
        # Final fallback to yfinance
        return self._fetch_yf_data(target_symbol, period, interval)

    def _fetch_iq_data(self, symbol, interval):
        """
        Fetches candles from IQ Option with aggressive reconnection logic.
        """
        # Grace period after a trade to avoid immediate ws churn
        if self.last_trade_ts and (time.time() - self.last_trade_ts) < self.grace_seconds:
            return None
        
        iq_symbol = symbol.replace("=X", "").replace("/", "")
        
        # Interval map
        size = 60 # 1m
        if interval == "5m": size = 300
        elif interval == "15m": size = 900
        
        try:
            endtime = int(time.time())
            max_retries = 3
            candles = []
            
            for attempt in range(max_retries):
                try:
                    # Avoid racing with reconnect by sharing the conn lock
                    with self.conn_lock:
                        candles = self.iq_api.get_candles(iq_symbol, size, 300, endtime)
                    if candles:
                        self.fail_count = 0
                        break
                    
                    # If candles is empty, it means internal state is bad.
                    print(f"Warning: Empty candles received on attempt {attempt}. forcing reconnect.")
                    raise Exception("Force reconnect: Empty candles received")

                except Exception as e:
                    print(f"IQ Option Data Error (Attempt {attempt}): {e}")
                    
                    # Check for specific "need reconnect" or similar hard failures
                    err_str = str(e).lower()
                    if "reconnect" in err_str or "closed" in err_str or "ssl" in err_str:
                        print("Critical Connection Error Detected. Forcing Reset.")
                        self.is_connected = False
                        self.fail_count += 1
                        if self.ensure_connection(mode="hard"):
                            print("Re-init success after critical error.")
                            continue
                        else:
                            print("Re-init failed after critical error.")
                            if self.fail_count >= 2:
                                # Back off IQ for 60 seconds
                                self.iq_cooldown_until = time.time() + 60
                                return None
                    
                    if attempt < max_retries - 1:
                        time.sleep(2) # Increased sleep
                        if self.iq_api:
                            reconnect_success = False
                            self.is_connected = False 
                            
                            # Strategy:
                            # Attempt 0: Try simple reconnect
                            # Attempt > 0: Force FULL re-initialization
                            
                            if attempt == 0:
                                try:
                                    if self.ensure_connection(mode="soft"):
                                        print("Simple reconnection successful.")
                                        reconnect_success = True
                                        self.is_connected = True
                                except Exception as conn_err:
                                    print(f"Simple reconnection failed: {conn_err}")
                            
                            if reconnect_success:
                                continue

                            # Fallback to Reconnection (Avoid creating new instance if possible)
                            try:
                                print("Attempting reconnection...")
                                # Try to close and reconnect
                                try: self.iq_api.close() 
                                except: pass # close() might clear data?
                                
                                # Just call connect() - it handles reconnection
                                if self.ensure_connection(mode="soft"):
                                    print("Reconnection success.")
                                    reconnect_success = True
                                else:
                                    print(f"Reconnection failed.")
                                    
                                    # Only if simple reconnect fails, try full re-init (Nuclear option)
                                    # But ONLY if we don't have active trades? 
                                    # Actually, if connection is dead, we have to re-init.
                                    if attempt > 1: # Only on last attempt
                                        print("Reconnection failed. Attempting full re-initialization...")
                                        if self.ensure_connection(mode="hard"):
                                            reconnect_success = True
                            except Exception as reinit_err:
                                print(f"Reconnection exception: {reinit_err}")
                        continue
                    print(f"IQ Option Data Error (Retried): {e}")
                    return None
            
            if not candles:
                return None
                
            # Convert to DataFrame
            data = []
            for c in candles:
                dt = datetime.fromtimestamp(c['from'], tz=timezone.utc)
                data.append({
                    'time': dt,
                    'open': c['open'],
                    'high': c['max'],
                    'low': c['min'],
                    'close': c['close'],
                    'volume': c['volume']
                })
            
            df = pd.DataFrame(data)
            df.set_index('time', inplace=True)
            return df
            
        except Exception as e:
            print(f"IQ Option Data Error: {e}")
            return None

    def _fetch_yf_data(self, symbol, period, interval):
        target = symbol
        if "OTC" in target:
            target = target.replace("-OTC", "")
            if "=X" not in target:
                target += "=X"
                
        try:
            df = yf.download(target, period=period, interval=interval, progress=False, auto_adjust=False)
            if df.empty:
                print(f"YFinance: No data for {target}")
                return None
            
            if isinstance(df.columns, pd.MultiIndex):
                df.columns = df.columns.droplevel(1)
                
            df = df.reset_index()
            df.columns = [c.lower() for c in df.columns]
            df.rename(columns={'datetime': 'time', 'date': 'time'}, inplace=True)
            
            if df['time'].dt.tz is None:
                df['time'] = df['time'].dt.tz_localize('UTC')
            else:
                df['time'] = df['time'].dt.tz_convert('UTC')
                
            df.set_index('time', inplace=True)
            return df
        except Exception as e:
            print(f"Error fetching data: {e}")
            return None

    def check_asset_open(self, symbol):
        """
        Checks if asset is open for Binary or Digital.
        """
        if not self.use_iq or not self.is_connected:
            return {'binary': False, 'digital': False, 'reason': "Not Connected"}
        
        iq_symbol = symbol.replace("=X", "").replace("/", "").upper()
        
        is_binary = False
        is_digital = False
        
        try:
            # Check if asset is in 'all profit' list (basic check)
            all_profit = self.iq_api.get_all_profit()
            if iq_symbol in all_profit:
                is_binary = True
            
            # For digital, it's tricker, assume open if binary is open or check digital specific
            # Just returning binary status for now as it's the primary mode
            return {'binary': is_binary, 'digital': is_binary, 'reason': "OK"}
        except:
            return {'binary': False, 'digital': False, 'reason': "Error checking status"}

    def execute_trade(self, symbol, action, amount, duration, trade_mode="BINARY"):
        """
        Executes a trade.
        """
        if not self.is_connected:
            return False, None, "Not Connected"
            
        iq_symbol = symbol.replace("=X", "").replace("/", "").upper()
        direction = action.lower() # call/put
        
        try:
            # Binary Option
            check, id = self.iq_api.buy(amount, iq_symbol, direction, duration)
            
            if check:
                time.sleep(2)  # small pause to let ws stabilize post-trade
                self.last_trade_ts = time.time()
                return True, {'id': id, 'type': 'BINARY'}, "Trade Placed"
            else:
                return False, None, "Trade Failed (API returned False)"
        except Exception as e:
            print(f"Execution Error: {e}")
            self.is_connected = False # Mark as disconnected to trigger reconnect
            return False, None, f"Execution Error: {e}"

    def check_trade_result(self, trade_id, trade_type="BINARY"):
        """
        Checks the result of a trade (Non-blocking).
        """
        if not self.is_connected:
            return 'PENDING'
            
        try:
            # Method 1: Check if trade is in 'socket_option_opened' (Real-time updates)
            if hasattr(self.iq_api, 'socket_option_opened'):
                trades = self.iq_api.socket_option_opened
                if trades:
                    tid = int(trade_id)
                    # Check if we can find it directly
                    trade_data = trades.get(tid) or trades.get(str(tid))
                    
                    if trade_data:
                         win_amount = trade_data.get('win_amount')
                         if win_amount is not None and str(win_amount).lower() != 'null':
                             profit = float(win_amount) - float(trade_data.get('amount', 0))
                             if profit > 0: return 'WIN'
                             elif profit < 0: return 'LOSS'
                             else: return 'TIE'

            # Method 2: Check Open Options (To see if it's still running)
            # This helps if socket_option_opened is empty (e.g. after reconnect)
            try:
                open_options = self.iq_api.get_option_open_by_other_pc()
                if open_options and isinstance(open_options, dict):
                    tid = int(trade_id)
                    for k, v in open_options.items():
                        try:
                            if int(k) == tid:
                                # Found in open options
                                win_amount = v.get('win_amount')
                                if win_amount is not None and str(win_amount).lower() != 'null':
                                    profit = float(win_amount) - float(v.get('amount', 0))
                                    if profit > 0: return 'WIN'
                                    elif profit < 0: return 'LOSS'
                                    else: return 'TIE'
                                # If found but no result, it is PENDING
                                return 'PENDING' 
                        except: continue
            except: pass

            return 'PENDING'

        except Exception as e:
            # print(f"Check Trade Error: {e}")
            return 'PENDING'
