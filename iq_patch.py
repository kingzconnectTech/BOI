from iqoptionapi.api import IQOptionAPI
from iqoptionapi.ws.objects.timesync import TimeSync
from iqoptionapi.ws.objects.profile import Profile
from iqoptionapi.ws.objects.candles import Candles
from iqoptionapi.ws.objects.listinfodata import ListInfoData
from iqoptionapi.ws.objects.betinfo import Game_betinfo_data
from collections import defaultdict, deque

def nested_dict(n, type):
    if n == 1:
        return defaultdict(type)
    else:
        return defaultdict(lambda: nested_dict(n-1, type))

# Save original init
_original_init = IQOptionAPI.__init__

def patched_init(self, host, username, password, proxies=None):
    # Call original init to set up session, url, etc.
    _original_init(self, host, username, password, proxies)
    
    # Re-initialize all class attributes as instance attributes
    self.socket_option_opened = {}
    self.timesync = TimeSync()
    self.profile = Profile()
    self.candles = Candles()
    self.listinfodata = ListInfoData()
    self.api_option_init_all_result = []
    self.api_option_init_all_result_v2 = []
    
    self.underlying_list_data = None
    self.position_changed = None
    self.instrument_quites_generated_data = nested_dict(2, dict)
    self.instrument_quotes_generated_raw_data = nested_dict(2, dict)
    self.instrument_quites_generated_timestamp = nested_dict(2, dict)
    self.strike_list = None
    self.leaderboard_deals_client = None
    
    self.order_async = nested_dict(2, dict)
    self.game_betinfo = Game_betinfo_data()
    self.instruments = None
    self.financial_information = None
    self.buy_id = None
    self.buy_order_id = None
    self.traders_mood = {}
    self.order_data = None
    self.positions = None
    self.position = None
    self.deferred_orders = None
    self.position_history = None
    self.position_history_v2 = None
    self.available_leverages = None
    self.order_canceled = None
    self.close_position_data = None
    self.overnight_fee = None
    
    self.digital_option_placed_id = None
    self.live_deal_data = nested_dict(3, deque)
    
    self.subscribe_commission_changed_data = nested_dict(2, dict)
    self.real_time_candles = nested_dict(3, dict)
    self.real_time_candles_maxdict_table = nested_dict(2, dict)
    self.candle_generated_check = nested_dict(2, dict)
    self.candle_generated_all_size_check = nested_dict(1, dict)
    
    self.api_game_getoptions_result = None
    self.sold_options_respond = None
    self.tpsl_changed_respond = None
    self.auto_margin_call_changed_respond = None
    self.top_assets_updated_data = {}
    self.get_options_v2_data = None
    
    self.buy_multi_result = None
    self.buy_multi_option = {}
    
    self.result = None
    self.training_balance_reset_request = None
    self.balances_raw = None
    self.user_profile_client = None
    self.leaderboard_userinfo_deals_client = None
    self.users_availability = None

# Apply Patch
IQOptionAPI.__init__ = patched_init
print("IQOptionAPI Patched for Multi-User Support")
