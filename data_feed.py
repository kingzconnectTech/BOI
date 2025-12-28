import time
import pandas as pd
from datetime import datetime, timezone
import yfinance as yf
from iqoptionapi.stable_api import IQ_Option
import os

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
        if not self.use_iq or not self.is_connected:
            return 0.0

        try:
            return self.iq_api.get_balance()
        except Exception as e:
            print(f"Get Balance Error: {e}")
            # Try to reconnect
            try:
                if self.iq_api and not self.iq_api.check_connect():
                    print("Connection lost during get_balance. Reconnecting...")
                    check, reason = self.iq_api.connect()
                    if check:
                        print("Reconnected.")
                        self.is_connected = True
                        return self.iq_api.get_balance()
                    else:
                        # Full re-init logic
                        if hasattr(self, 'email') and hasattr(self, 'password'):
                             print("Attempting full re-init in get_balance...")
                             self.iq_api = IQ_Option(self.email, self.password)
                             check, _ = self.iq_api.connect()
                             if check:
                                 self.is_connected = True
                                 if hasattr(self, 'account_type'):
                                     self.iq_api.change_balance(self.account_type.upper())
                                 return self.iq_api.get_balance()
            except Exception as re_err:
                print(f"Reconnection in get_balance failed: {re_err}")
            
            # If all fails
            self.is_connected = False
            return 0.0

    def fetch_data(self, symbol=None, period="5d", interval="1m"):
        """
        Fetches data. If connected to IQ Option, fetches from there.
        Otherwise falls back to yfinance.
        """
        target_symbol = symbol if symbol else self.symbol
        
        if self.use_iq and self.is_connected:
            return self._fetch_iq_data(target_symbol, interval)
        else:
            return self._fetch_yf_data(target_symbol, period, interval)

    def _fetch_iq_data(self, symbol, interval):
        """
        Fetches candles from IQ Option with aggressive reconnection logic.
        """
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
                    candles = self.iq_api.get_candles(iq_symbol, size, 1000, endtime)
                    if candles:
                        break
                    
                    # If candles is empty, it means internal state is bad.
                    print(f"Warning: Empty candles received on attempt {attempt}. forcing reconnect.")
                    raise Exception("Force reconnect: Empty candles received")

                except Exception as e:
                    print(f"IQ Option Data Error (Attempt {attempt}): {e}")
                    
                    if attempt < max_retries - 1:
                        time.sleep(1)
                        if self.iq_api:
                            reconnect_success = False
                            self.is_connected = False 
                            
                            # Strategy:
                            # Attempt 0: Try simple reconnect
                            # Attempt > 0: Force FULL re-initialization
                            
                            if attempt == 0:
                                try:
                                    if not self.iq_api.check_connect():
                                        print("Reconnecting (Simple)...")
                                        check, reason = self.iq_api.connect()
                                        if check:
                                            print("Simple reconnection successful.")
                                            reconnect_success = True
                                            self.is_connected = True
                                except Exception as conn_err:
                                    print(f"Simple reconnection failed: {conn_err}")
                            
                            if reconnect_success:
                                continue

                            # Fallback to Full Re-initialization
                            if hasattr(self, 'email') and hasattr(self, 'password'):
                                    try:
                                        print("Attempting full re-initialization of IQ Option instance...")
                                        try:
                                            self.iq_api.close()
                                            if os.path.exists("session.json"):
                                                try: os.remove("session.json")
                                                except: pass
                                        except: pass
                                        
                                        self.iq_api = IQ_Option(self.email, self.password)
                                        check, reason = self.iq_api.connect()
                                        if check:
                                            print("Full re-initialization success.")
                                            self.is_connected = True
                                            if hasattr(self, 'account_type'):
                                                self.iq_api.change_balance(self.account_type.upper())
                                        else:
                                            print(f"Full re-initialization failed: {reason}")
                                    except Exception as reinit_err:
                                        print(f"Full re-initialization exception: {reinit_err}")
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
                return True, {'id': id, 'type': 'BINARY'}, "Trade Placed"
            else:
                return False, None, "Trade Failed (API returned False)"
        except Exception as e:
            return False, None, f"Execution Error: {e}"

    def check_trade_result(self, trade_id, trade_type="BINARY"):
        """
        Checks the result of a trade (Non-blocking).
        """
        if not self.is_connected:
            return 'PENDING'
            
        try:
            # Method 1: Check if trade is in 'socket_option_opened' (Real-time updates)
            # This dictionary usually contains open and recently closed trades
            if hasattr(self.iq_api, 'socket_option_opened'):
                trades = self.iq_api.socket_option_opened
                if trades:
                    # IQ Option API stores trades by ID (int or str)
                    # We need to find our trade_id
                    tid = int(trade_id)
                    
                    # Check if we can find it directly
                    trade_data = trades.get(tid) or trades.get(str(tid))
                    
                    if trade_data:
                        # Check status
                        # If 'win' is present, it's closed?
                        # Or check 'msg' -> 'status'
                        
                        # Note: Structure varies by API version, but usually:
                        # trade_data = {'id': ..., 'profit_amount': ..., 'win_amount': ..., ...}
                        
                        # Let's try to interpret common fields
                        win_amount = trade_data.get('win_amount')
                        if win_amount is not None:
                            # It's likely closed
                             # If win_amount is None or 'null', it might be open
                             pass
                        
            # Method 2: Use get_option_open_by_other_pc() (which returns open options)
            # If trade is NOT in open options, it might be closed.
            # But we need the result.
            
            # Method 3: Check history (v3) - but non-blocking?
            # get_betinfo might be useful?
            
            # Let's try a safer approach:
            # 1. Check if it's still open
            # 2. If not open, check result in history
            
            # But to be safe and avoid blocking, let's just use get_balance change? No, unreliable.
            
            # Let's use the 'check_win_v3' but with a timeout logic or just try-except-pass
            # Actually, check_win_v3 IS blocking in most implementations.
            
            # Better implementation: Check P&L history
            # Fetch latest 10 trades
            
            # Check if trade is expired based on time?
            # If trade time + duration < current time, it SHOULD be closed.
            # Then we can query result.
            
            pass
            
            # Fallback to history check (which is safer than blocking)
            history = self.iq_api.get_option_open_by_other_pc()
            
            if history and isinstance(history, dict):
                tid = int(trade_id)
                for k, v in history.items():
                    try:
                        k_int = int(k)
                    except ValueError:
                        continue
                    
                    if k_int == tid:
                        # Found the trade
                        # Check if it has a result
                        # If 'win_amount' is present and not None
                        win_amount = v.get('win_amount')
                        if win_amount is not None:
                             profit = win_amount - v.get('amount', 0)
                             if profit > 0: return 'WIN'
                             elif profit < 0: return 'LOSS'
                             else: return 'TIE'
                        
                        # If close_time is passed
                        # ...
            
            return 'PENDING'

        except Exception as e:
            # print(f"Check Trade Error: {e}")
            return 'PENDING'
