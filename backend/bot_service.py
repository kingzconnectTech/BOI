import multiprocessing
import threading
import time
import queue
from iq_bot import IQBot

# ============================================================================
# BotProcess Function - Runs in a separate process
# ============================================================================

def run_bot_process(email, password, mode, shared_dict, command_queue):
    """
    Target function for the bot process.
    Manages the IQBot instance and synchronizes state with shared_dict.
    """
    try:
        bot = IQBot()
        
        # Initial connection
        print(f"[BotProcess-{email}] Process started. PID: {multiprocessing.current_process().pid}")
        success, message = bot.connect(email, password, mode)
        
        # Update initial state
        if success:
            shared_dict['connected'] = True
            shared_dict['is_running'] = False
            shared_dict['balance'] = bot.balance
            shared_dict['currency'] = bot.currency
            shared_dict['min_amount'] = bot.trade_amount # Send min amount
            shared_dict['logs'] = bot.get_logs()
            shared_dict['stats'] = {
                "profit": bot.total_profit,
                "wins": bot.wins,
                "losses": bot.losses,
                "win_rate": 0
            }
        else:
            shared_dict['connected'] = False
            shared_dict['logs'] = [message]
            print(f"[BotProcess-{email}] Connection failed: {message}")
            return  # Exit process on connection failure

        # Main Loop
        while True:
            try:
                # Check for commands
                try:
                    cmd = command_queue.get_nowait()
                    if cmd['type'] == 'STOP':
                        bot.stop()
                    elif cmd['type'] == 'START':
                         # Set config if provided
                        if 'config' in cmd:
                            c = cmd['config']
                            bot.set_config(
                                c.get('amount', 1),
                                c.get('duration', 1),
                                c.get('stop_loss', 0),
                                c.get('take_profit', 0),
                                c.get('max_consecutive_losses', 0),
                                c.get('max_trades', 0),
                                c.get('auto_trading', True),
                                c.get('strategy', 'Momentum')
                            )
                        if 'push_token' in cmd:
                            bot.set_push_token(cmd['push_token'])
                            
                        bot.start_trading()

                    elif cmd['type'] == 'UPDATE':
                        if 'config' in cmd:
                            c = cmd['config']
                            bot.set_config(
                                c.get('amount', bot.trade_amount),
                                c.get('duration', bot.trade_duration),
                                c.get('stop_loss', bot.stop_loss),
                                c.get('take_profit', bot.take_profit),
                                c.get('max_consecutive_losses', bot.max_consecutive_losses),
                                c.get('max_trades', bot.max_trades),
                                c.get('auto_trading', bot.auto_trading),
                                c.get('strategy', bot.strategy)
                            )
                            bot.add_log(f"Config updated. Strategy: {bot.strategy}")

                    elif cmd['type'] == 'DISCONNECT':
                        bot.disconnect()
                        shared_dict['connected'] = False
                        break # Exit loop and process
                except queue.Empty:
                    pass
                
                # Sync State
                shared_dict['is_running'] = bot.is_running
                shared_dict['balance'] = bot.balance
                shared_dict['currency'] = bot.currency
                shared_dict['min_amount'] = bot.trade_amount
                shared_dict['next_trading_time'] = bot.next_trading_time
                shared_dict['logs'] = bot.get_logs()
                shared_dict['signals'] = bot.get_signals()
                
                win_rate = 0
                if bot.trades_taken > 0:
                    win_rate = (bot.wins / bot.trades_taken) * 100
                    
                shared_dict['stats'] = {
                    "profit": round(bot.total_profit, 2),
                    "wins": bot.wins,
                    "losses": bot.losses,
                    "win_rate": round(win_rate, 1)
                }
                
                if not bot.connected:
                     shared_dict['connected'] = False
                     break

                time.sleep(1) # Sync every second
                
            except (EOFError, BrokenPipeError, OSError) as e:
                # Handle broken pipe specifically (often Errno 32)
                if isinstance(e, OSError) and e.errno != 32:
                     # If it's an OSError but NOT broken pipe, print it. 
                     # If it IS broken pipe, we fall through to break.
                     print(f"[BotProcess-{email}] OS Error: {e}")
                else:
                     print(f"[BotProcess-{email}] Parent connection lost (Broken Pipe). Terminating.")
                break
                
            except Exception as e:
                print(f"[BotProcess-{email}] Error: {e}")
                time.sleep(1)
                
    except Exception as e:
        err_msg = f"Critical Error in BotProcess: {e}"
        print(f"[BotProcess-{email}] {err_msg}")
        shared_dict['logs'] = [err_msg]
        shared_dict['connected'] = False

# ============================================================================
# IsolatedBot Class - Wrapper for the process
# ============================================================================

class IsolatedBot:
    def __init__(self, manager):
        self.manager = manager # Multiprocessing Manager
        self.process = None
        self.command_queue = manager.Queue()
        self.shared_dict = manager.dict()
        
        # Initialize default state
        self.shared_dict['connected'] = False
        self.shared_dict['is_running'] = False
        self.shared_dict['balance'] = 0
        self.shared_dict['currency'] = ""
        self.shared_dict['logs'] = []
        self.shared_dict['stats'] = {"profit": 0, "wins": 0, "losses": 0, "win_rate": 0}
        self.email = None

    def connect(self, email, password, mode="PRACTICE"):
        self.email = email
        
        try:
            # If process exists, kill it first
            if self.process and self.process.is_alive():
                self.process.terminate()
                self.process.join()
                
            # Spawn new process
            self.process = multiprocessing.Process(
                target=run_bot_process,
                args=(email, password, mode, self.shared_dict, self.command_queue)
            )
            self.process.daemon = True # Ensure process dies if parent dies
            self.process.start()
            
            # Wait for connection result (timeout 60s to allow for retries)
            for _ in range(60):
                time.sleep(1)
                if self.shared_dict.get('connected'):
                    return True, "Connected successfully"
                # If process died, it failed
                if not self.process.is_alive():
                    logs = self.shared_dict.get('logs', [])
                    reason = logs[-1] if logs else "Unknown error (Process died)"
                    return False, reason
                    
            return False, "Connection timeout (Backend)"
            
        except Exception as e:
            print(f"Error in BotService.connect: {e}")
            return False, f"System Error: {str(e)}"

    def set_config(self, amount, duration, stop_loss, take_profit, max_consecutive_losses, max_trades, auto_trading=True, strategy="Momentum"):
        self.config = {
            'amount': amount,
            'duration': duration,
            'stop_loss': stop_loss,
            'take_profit': take_profit,
            'max_consecutive_losses': max_consecutive_losses,
            'max_trades': max_trades,
            'auto_trading': auto_trading,
            'strategy': strategy
        }

    def set_push_token(self, token):
        self.push_token = token

    def start_trading(self):
        self.command_queue.put({
            'type': 'START',
            'config': getattr(self, 'config', {}),
            'push_token': getattr(self, 'push_token', None)
        })

    def update_config(self, config):
        # Merge with existing config
        if not hasattr(self, 'config'):
            self.config = {}
        self.config.update(config)
        
        self.command_queue.put({
            'type': 'UPDATE',
            'config': config
        })

    def stop(self):
        self.command_queue.put({'type': 'STOP'})
        return True, "Bot stopped"

    def disconnect(self):
        self.command_queue.put({'type': 'DISCONNECT'})
        if self.process:
            self.process.join(timeout=5)
            if self.process.is_alive():
                self.process.terminate()
        return True, "Disconnected"

    def get_status(self):
        # Read from shared dict
        return {
            "connected": self.shared_dict.get('connected', False),
            "running": self.shared_dict.get('is_running', False),
            "balance": self.shared_dict.get('balance', 0),
            "currency": self.shared_dict.get('currency', ""),
            "email": self.email,
            "stats": self.shared_dict.get('stats', {}),
            "signals": self.shared_dict.get('signals', [])
        }

    def get_logs(self):
        return self.shared_dict.get('logs', [])
        
    def clear_logs(self):
        self.shared_dict['logs'] = []
        



# ============================================================================
# BotManager Class
# ============================================================================

class BotManager:
    def __init__(self):
        self.bots = {}
        self.mp_manager = None # Initialized on first use or explicitly
        
    def _ensure_manager(self):
        if self.mp_manager is None:
            print("[BotManager] Starting Multiprocessing Manager...")
            self.mp_manager = multiprocessing.Manager()

    def connect_bot(self, email, password, mode):
        self._ensure_manager()
        email = email.lower().strip()
        
        if email not in self.bots:
            print(f"[BotManager] Creating NEW IsolatedBot for {email}")
            self.bots[email] = IsolatedBot(self.mp_manager)
        
        return self.bots[email].connect(email, password, mode)

    def get_bot(self, email):
        email = email.lower().strip()
        return self.bots.get(email)

    def remove_bot(self, email):
        email = email.lower().strip()
        if email in self.bots:
            self.bots[email].disconnect()
            del self.bots[email]

bot_manager = BotManager()
