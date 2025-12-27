import { Ionicons } from '@expo/vector-icons';
import AsyncStorage from '@react-native-async-storage/async-storage';
import * as BackgroundFetch from 'expo-background-fetch';
import Constants from 'expo-constants';
import * as Device from 'expo-device';
import { useKeepAwake } from 'expo-keep-awake';
import * as Notifications from 'expo-notifications';
import { StatusBar } from 'expo-status-bar';
import * as TaskManager from 'expo-task-manager';
import React, { useEffect, useState } from 'react';
import { ActivityIndicator, Alert, Dimensions, Modal, Platform, RefreshControl, ScrollView, StyleSheet, Switch, Text, TextInput, TouchableOpacity, View } from 'react-native';
import { LineChart } from 'react-native-gifted-charts';
import { SafeAreaView } from 'react-native-safe-area-context';

const BACKGROUND_FETCH_TASK = 'background-fetch-task';

// Define the background task
TaskManager.defineTask(BACKGROUND_FETCH_TASK, async () => {
  try {
    const serverIp = await AsyncStorage.getItem('SERVER_IP');
    const ip = serverIp || 'https://iqbot-mobile.onrender.com';
    
    // Helper to resolve URL (duplicated logic, but necessary outside component)
    const getApiUrl = (rawIp: string) => {
        if (rawIp.startsWith("http")) return rawIp;
        if (rawIp.includes("render.com") || rawIp.includes("herokuapp.com")) {
           return `https://${rawIp}`; 
        }
        return `http://${rawIp}:8000`;
    };

    const API_URL = getApiUrl(ip);
    
    // Ping the server status endpoint to keep it alive
    const response = await fetch(`${API_URL}/status`);
    const data = await response.json();
    
    // Optional: You could check if bot is running and notify if stopped
    // console.log(`Background fetch executed. Bot running: ${data.is_running}`);

    return BackgroundFetch.BackgroundFetchResult.NewData;
  } catch (error) {
    return BackgroundFetch.BackgroundFetchResult.Failed;
  }
});

Notifications.setNotificationHandler({
  handleNotification: async () => ({
    shouldShowAlert: true,
    shouldPlaySound: true,
    shouldSetBadge: false,
    shouldShowBanner: true,
    shouldShowList: true,
  }),
});

const AVAILABLE_PAIRS = [
    "EURUSD-OTC", "GBPUSD-OTC", "USDJPY-OTC", 
    "EURGBP-OTC"
];

async function registerForPushNotificationsAsync() {
  let token;

  if (Platform.OS === 'android') {
    await Notifications.setNotificationChannelAsync('default', {
      name: 'default',
      importance: Notifications.AndroidImportance.MAX,
      vibrationPattern: [0, 250, 250, 250],
      lightColor: '#FF231F7C',
    });
  }

  if (Device.isDevice) {
    const { status: existingStatus } = await Notifications.getPermissionsAsync();
    let finalStatus = existingStatus;
    if (existingStatus !== 'granted') {
      const { status } = await Notifications.requestPermissionsAsync();
      finalStatus = status;
    }
    if (finalStatus !== 'granted') {
      return;
    }
    try {
        const projectId = Constants?.expoConfig?.extra?.eas?.projectId ?? Constants?.easConfig?.projectId;
        token = (await Notifications.getExpoPushTokenAsync({ projectId })).data;
    } catch (e) {
        token = (await Notifications.getExpoPushTokenAsync()).data;
    }
  }

  return token;
}

export default function App() {
  useKeepAwake();
  const [serverIp, setServerIp] = useState('https://iqbot-mobile.onrender.com'); // Default to Remote Server

  useEffect(() => {
    // Load persisted IP on startup
    AsyncStorage.getItem('SERVER_IP').then(ip => {
        if (ip) setServerIp(ip);
    });

    // Register Background Fetch
    registerBackgroundFetchAsync();
  }, []);

  useEffect(() => {
    // Save IP whenever it changes
    AsyncStorage.setItem('SERVER_IP', serverIp);
  }, [serverIp]);

  async function registerBackgroundFetchAsync() {
    try {
        await BackgroundFetch.registerTaskAsync(BACKGROUND_FETCH_TASK, {
            minimumInterval: 15 * 60, // 15 minutes
            stopOnTerminate: false,   // Android only
            startOnBoot: true,        // Android only
        });
    } catch (err) {
        console.log("Background Task Register Failed:", err);
    }
  }
  
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [accountType, setAccountType] = useState('PRACTICE');
  const [currency, setCurrency] = useState('USD');
  const [connected, setConnected] = useState(false);
  const [isConnecting, setIsConnecting] = useState(false);
  const [botRunning, setBotRunning] = useState(false);
  const [autoTrade, setAutoTrade] = useState(false);
  const [tradeAmount, setTradeAmount] = useState('1.0');
  
  // Advanced Settings State
  const [expiry, setExpiry] = useState('2');
  const [stopLoss, setStopLoss] = useState('2');
  const [profitGoal, setProfitGoal] = useState('5.0');
  const [showSettings, setShowSettings] = useState(false);
  const [showAdvice, setShowAdvice] = useState(false);
  
  // Chart & Pairs State
  const [activePairs, setActivePairs] = useState<string[]>(["EURUSD-OTC", "GBPUSD-OTC", "USDJPY-OTC"]);
  const [selectedChartPair, setSelectedChartPair] = useState("EURUSD-OTC");
  const [chartType, setChartType] = useState('AREA'); // 'LINE' or 'AREA'
  const [expoPushToken, setExpoPushToken] = useState('');
  const [refreshing, setRefreshing] = useState(false);

  const [rates, setRates] = useState<{[key: string]: number}>({'USD': 1.0, 'NGN': 1650.0, 'EUR': 0.92, 'GBP': 0.77});
  const [logs, setLogs] = useState<string[]>([]);
  const [signals, setSignals] = useState<any[]>([]);
  const [balance, setBalance] = useState(0);
  const [chartData, setChartData] = useState<any[]>([]);
  const [currentPrice, setCurrentPrice] = useState(0);

  const getApiUrl = (ip: string) => {
    // If user pasted a full URL, use it
    if (ip.startsWith("http")) return ip;
    // If it's a cloud domain (Render/Heroku), assume HTTPS and no port 8000
    if (ip.includes("render.com") || ip.includes("herokuapp.com")) {
       return `https://${ip}`; 
    }
    // Default to local development
    return `http://${ip}:8000`;
  };

  const API_URL = getApiUrl(serverIp);

  useEffect(() => {
    registerForPushNotificationsAsync().then(token => {
      if (token) {
        setExpoPushToken(token);
        fetch(`${API_URL}/register_push`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ token })
        }).catch(err => console.log("Push Reg Error", err));
      }
    });
    
    // Listener for foreground notifications
    const notificationListener = Notifications.addNotificationReceivedListener(notification => {
      // Optional: handle foreground notification
    });

    return () => {
      notificationListener.remove();
    };
  }, [serverIp]);

  const CURRENCY_SYMBOLS: {[key: string]: string} = {
    'USD': '$',
    'NGN': '₦',
    'EUR': '€',
    'GBP': '£'
  };

  // --- API Functions ---
  const connectToIq = async () => {
    setIsConnecting(true);
    try {
      const response = await fetch(`${API_URL}/connect`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ email, password, account_type: accountType })
      });
      const data = await response.json();
      if (data.success) {
        Alert.alert("Success", `Connected to ${accountType} Account!`);
        setConnected(true);
      } else {
        Alert.alert("Error", data.message);
      }
    } catch (error) {
      Alert.alert("Network Error", "Could not reach server. Check IP.");
    } finally {
      setIsConnecting(false);
    }
  };

  const disconnectFromIq = async () => {
    try {
      await fetch(`${API_URL}/disconnect`, { method: 'POST' });
      setConnected(false);
      setBotRunning(false); // Stop bot if disconnected
      setBalance(0);
    } catch (error) {
      console.error(error);
    }
  };

  const toggleBot = async () => {
    const endpoint = botRunning ? '/stop' : '/start';
    try {
      await fetch(`${API_URL}${endpoint}`, { method: 'POST' });
      setBotRunning(!botRunning);
    } catch (error) {
      console.error(error);
    }
  };

  const updateConfig = async (
    newAutoTrade: boolean, 
    newAmount: string, 
    newCurrency?: string,
    newExpiry?: string,
    newStopLoss?: string,
    newProfitGoal?: string,
    newPairs?: string[]
  ) => {
    try {
      await fetch(`${API_URL}/config`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ 
          auto_trade: newAutoTrade, 
          trade_amount: parseFloat(newAmount),
          currency: newCurrency || currency,
          expiry_minutes: parseInt(newExpiry || expiry),
          stop_loss: parseInt(newStopLoss || stopLoss),
          profit_goal: parseFloat(newProfitGoal || profitGoal),
          active_pairs: newPairs || activePairs
        })
      });
    } catch (error) {
      console.error(error);
    }
  };

  const togglePair = (pair: string) => {
    let newPairs;
    if (activePairs.includes(pair)) {
        newPairs = activePairs.filter(p => p !== pair);
        if (newPairs.length === 0) newPairs = [pair]; // Prevent empty list
    } else {
        newPairs = [...activePairs, pair];
    }
    setActivePairs(newPairs);
    // If the currently viewed pair is removed, switch view to the first available one
    if (!newPairs.includes(selectedChartPair)) {
        setSelectedChartPair(newPairs[0]);
    }
    updateConfig(autoTrade, tradeAmount, currency, expiry, stopLoss, profitGoal, newPairs);
  };

  const saveSettings = () => {
      updateConfig(autoTrade, tradeAmount, currency, expiry, stopLoss, profitGoal, activePairs);
      setShowSettings(false);
  };

  const changeCurrency = (newCurrency: string) => {
    const currentRate = rates[currency] || 1.0;
    const newRate = rates[newCurrency] || 1.0;
    
    const amountVal = parseFloat(tradeAmount);
    if (!isNaN(amountVal)) {
        const amountUSD = amountVal / currentRate;
        const newAmountVal = amountUSD * newRate;
        
        const decimals = newCurrency === 'NGN' ? 0 : 2;
        const newAmountStr = newAmountVal.toFixed(decimals);
        
        setTradeAmount(newAmountStr);
        updateConfig(autoTrade, newAmountStr, newCurrency);
    }
    setCurrency(newCurrency);
  };

  useEffect(() => {
    const fetchRates = async () => {
        try {
            const res = await fetch(`${API_URL}/rates`);
            const data = await res.json();
            if (data && data.USD) {
                setRates(data);
            }
        } catch (e) {
            console.log("Rates fetch failed");
        }
    };
    if (connected) fetchRates();
  }, [connected, serverIp]);

  const fetchData = async () => {
    try {
      // Fetch Status
      const statusRes = await fetch(`${API_URL}/status`);
      const statusData = await statusRes.json();
      
      setBotRunning(statusData.is_running);
      setConnected(statusData.is_connected);
      setAutoTrade(statusData.auto_trade);
      setBalance(statusData.balance);
      setLogs(statusData.logs.reverse()); // Newest first
      
      if (statusData.config) {
           // Only update if not editing settings
           if (!showSettings) {
               setExpiry(statusData.config.expiry.toString());
               setStopLoss(statusData.config.stop_loss.toString());
               setProfitGoal(statusData.config.profit_goal.toString());
           }
      }

      // Fetch Signals
      const sigRes = await fetch(`${API_URL}/signals`);
      const sigData = await sigRes.json();
      setSignals(sigData.reverse());

      // Fetch Chart Data
      if (statusData.is_connected) {
         const chartRes = await fetch(`${API_URL}/chart_data?symbol=${selectedChartPair}`);
         const chartJson = await chartRes.json();
         if (chartJson.data && chartJson.data.length > 0) {
           const formattedData = chartJson.data.map((item: any) => ({
              timestamp: item.timestamp,
              value: item.close,
              open: item.open,
              high: item.high,
              low: item.low,
              label: new Date(item.timestamp).toLocaleTimeString([], {hour: '2-digit', minute:'2-digit'}),
           }));
           setChartData(formattedData);
           setCurrentPrice(chartJson.data[chartJson.data.length - 1].close);
         }
      }

    } catch (error) {
      // Silently fail on poll error
    }
  };

  const onRefresh = React.useCallback(async () => {
    setRefreshing(true);
    await fetchData();
    setRefreshing(false);
  }, [serverIp, selectedChartPair, showSettings]);

  // --- Polling Loop ---
  useEffect(() => {
    const interval = setInterval(fetchData, 2000); // Poll every 2 seconds
    return () => clearInterval(interval);
  }, [serverIp, selectedChartPair, showSettings]); // Restart poll if key deps change

  // --- Render ---
  if (!connected) {
    return (
      <View style={styles.loginContainer}>
        <StatusBar style="light" />
        <View style={styles.loginCard}>
          <Text style={styles.loginTitle}>BOI Login</Text>
          
          <TextInput
            style={styles.input}
            placeholder="IQ Option Email"
            placeholderTextColor="#94a3b8"
            value={email}
            onChangeText={setEmail}
            autoCapitalize="none"
          />
          <TextInput
            style={styles.input}
            placeholder="IQ Option Password"
            placeholderTextColor="#94a3b8"
            value={password}
            onChangeText={setPassword}
            secureTextEntry
          />
          
          <View style={styles.switchContainer}>
            <Text style={styles.label}>Real Account</Text>
            <Switch
              trackColor={{ false: "#767577", true: "#00ff83" }}
              thumbColor={accountType === 'REAL' ? "#f4f3f4" : "#f4f3f4"}
              onValueChange={() => setAccountType(prev => prev === 'PRACTICE' ? 'REAL' : 'PRACTICE')}
              value={accountType === 'REAL'}
            />
          </View>
          
          <TouchableOpacity style={styles.btnPrimary} onPress={connectToIq} disabled={isConnecting}>
            {isConnecting ? (
                <ActivityIndicator size="small" color="#0f172a" />
            ) : (
                <Text style={styles.btnTextPrimary}>Connect</Text>
            )}
          </TouchableOpacity>
        </View>
      </View>
    );
  }

  return (
    <SafeAreaView style={styles.container}>
      <StatusBar style="light" />
      <ScrollView 
        contentContainerStyle={styles.scrollContent}
        refreshControl={
          <RefreshControl refreshing={refreshing} onRefresh={onRefresh} tintColor="#fff" colors={['#00ff83']} />
        }
      >
        {/* HEADER */}
        <View style={styles.header}>
          <View>
            <Text style={styles.headerTitle}>BOI</Text>
            <View style={styles.statusBadge}>
              <View style={[styles.statusDot, { backgroundColor: '#00ff83' }]} />
              <Text style={styles.statusText}>{accountType}</Text>
            </View>
          </View>
          <View style={{flexDirection: 'row', gap: 10}}>
            <TouchableOpacity onPress={() => setShowAdvice(true)} style={styles.iconButton}>
              <Ionicons name="information-circle-outline" size={24} color="#e2e8f0" />
            </TouchableOpacity>
            <TouchableOpacity onPress={() => setShowSettings(true)} style={styles.iconButton}>
              <Ionicons name="settings-outline" size={24} color="#e2e8f0" />
            </TouchableOpacity>
            <TouchableOpacity onPress={disconnectFromIq} style={styles.logoutBtn}>
              <Ionicons name="log-out-outline" size={24} color="#ef4444" />
            </TouchableOpacity>
          </View>
        </View>

        <Modal
          animationType="slide"
          transparent={true}
          visible={showSettings}
          onRequestClose={() => setShowSettings(false)}
        >
            <View style={styles.modalOverlay}>
                <View style={styles.modalContent}>
                    <Text style={styles.modalTitle}>Bot Strategy Settings</Text>
                    
                    <Text style={styles.modalLabel}>Expiry (Minutes):</Text>
                    <TextInput 
                        style={styles.modalInput} 
                        value={expiry} 
                        onChangeText={setExpiry}
                        keyboardType="numeric"
                    />

                    <Text style={styles.modalLabel}>Stop Loss (Consecutive):</Text>
                    <TextInput 
                        style={styles.modalInput} 
                        value={stopLoss} 
                        onChangeText={setStopLoss}
                        keyboardType="numeric"
                    />

                    <Text style={styles.modalLabel}>Profit Goal ($):</Text>
                    <TextInput 
                        style={styles.modalInput} 
                        value={profitGoal} 
                        onChangeText={setProfitGoal}
                        keyboardType="numeric"
                    />

                    <View style={styles.modalButtons}>
                        <TouchableOpacity style={[styles.button, styles.btnDanger, {flex:1, marginRight:5}]} onPress={() => setShowSettings(false)}>
                            <Text style={styles.btnText}>Cancel</Text>
                        </TouchableOpacity>
                        <TouchableOpacity style={[styles.button, styles.btnSuccess, {flex:1, marginLeft:5}]} onPress={saveSettings}>
                            <Text style={styles.btnText}>Save</Text>
                        </TouchableOpacity>
                    </View>
                </View>
            </View>
        </Modal>
        
        <Modal
          animationType="fade"
          transparent={true}
          visible={showAdvice}
          onRequestClose={() => setShowAdvice(false)}
        >
            <View style={styles.modalOverlay}>
                <View style={[styles.modalContent, {maxHeight: '85%'}]}>
                    <ScrollView showsVerticalScrollIndicator={false}>
                        <View style={{flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', marginBottom: 15}}>
                            <Text style={[styles.modalTitle, {marginBottom: 0, fontSize: 18}]}>Best Time to Trade OTC</Text>
                            <TouchableOpacity onPress={() => setShowAdvice(false)}>
                                <Ionicons name="close-circle" size={26} color="#94a3b8" />
                            </TouchableOpacity>
                        </View>
                        
                        {/* Best Window */}
                        <View style={{backgroundColor: 'rgba(34, 197, 94, 0.1)', padding: 15, borderRadius: 12, marginBottom: 15, borderWidth: 1, borderColor: 'rgba(34, 197, 94, 0.3)'}}>
                            <View style={{flexDirection: 'row', alignItems: 'center', marginBottom: 8}}>
                                <Ionicons name="checkmark-circle" size={20} color="#22c55e" style={{marginRight: 8}} />
                                <Text style={{color: '#22c55e', fontWeight: 'bold', fontSize: 15}}>BEST WINDOW (MOST STABLE)</Text>
                            </View>
                            <Text style={{color: 'white', fontWeight: 'bold', fontSize: 20, marginBottom: 8, textAlign: 'center'}}>22:00 – 02:00 WAT</Text>
                            <Text style={{color: '#94a3b8', fontSize: 12, marginBottom: 5, fontWeight: 'bold'}}>Why this works:</Text>
                            {['Lower global retail activity', 'Less algorithm aggression', 'Cleaner ranges', 'Fewer fake spikes'].map((item, i) => (
                                <View key={i} style={{flexDirection: 'row', alignItems: 'center', marginBottom: 4}}>
                                    <View style={{width: 4, height: 4, borderRadius: 2, backgroundColor: '#cbd5e1', marginRight: 8}} />
                                    <Text style={{color: '#cbd5e1', fontSize: 13}}>{item}</Text>
                                </View>
                            ))}
                            <Text style={{color: '#94a3b8', fontSize: 12, marginTop: 8, fontStyle: 'italic', borderTopWidth: 1, borderTopColor: 'rgba(255,255,255,0.1)', paddingTop: 5}}>
                                *OTC behaves most range-like here.
                            </Text>
                        </View>

                        {/* Secondary Window */}
                        <View style={{backgroundColor: 'rgba(234, 179, 8, 0.1)', padding: 15, borderRadius: 12, marginBottom: 15, borderWidth: 1, borderColor: 'rgba(234, 179, 8, 0.3)'}}>
                            <View style={{flexDirection: 'row', alignItems: 'center', marginBottom: 8}}>
                                <Ionicons name="warning" size={20} color="#eab308" style={{marginRight: 8}} />
                                <Text style={{color: '#eab308', fontWeight: 'bold', fontSize: 14}}>SECONDARY WINDOW (STRICT)</Text>
                            </View>
                            <Text style={{color: 'white', fontWeight: 'bold', fontSize: 18, marginBottom: 8, textAlign: 'center'}}>06:00 – 08:00 WAT</Text>
                            <Text style={{color: '#94a3b8', fontSize: 12, marginBottom: 5, fontWeight: 'bold'}}>Use ONLY if:</Text>
                            {['Market is clearly ranging', 'No sudden long candles', 'Trade S/R reversals only'].map((item, i) => (
                                <View key={i} style={{flexDirection: 'row', alignItems: 'center', marginBottom: 4}}>
                                    <View style={{width: 4, height: 4, borderRadius: 2, backgroundColor: '#cbd5e1', marginRight: 8}} />
                                    <Text style={{color: '#cbd5e1', fontSize: 13}}>{item}</Text>
                                </View>
                            ))}
                        </View>

                        <TouchableOpacity 
                            style={[styles.button, styles.btnPrimary, styles.shadowBtn]} 
                            onPress={() => setShowAdvice(false)}
                        >
                            <Text style={styles.btnText}>Got it</Text>
                        </TouchableOpacity>
                    </ScrollView>
                </View>
            </View>
        </Modal>
        
        {/* Connection Panel */}
        <View style={styles.card}>
          <Text style={styles.cardTitle}>Account Settings</Text>
          
          <View style={styles.row}>
            <Text style={styles.rowLabel}>Type:</Text>
            <View style={styles.toggleContainer}>
              <TouchableOpacity 
                style={[styles.toggleBtn, accountType === 'PRACTICE' && styles.toggleBtnActive]} 
                onPress={() => setAccountType('PRACTICE')}
              >
                <Text style={[styles.toggleText, accountType === 'PRACTICE' && styles.textActive]}>Demo</Text>
              </TouchableOpacity>
              <TouchableOpacity 
                style={[styles.toggleBtn, accountType === 'REAL' && styles.toggleBtnActive]} 
                onPress={() => setAccountType('REAL')}
              >
                <Text style={[styles.toggleText, accountType === 'REAL' && styles.textActive]}>Real</Text>
              </TouchableOpacity>
            </View>
          </View>

          <View style={styles.row}>
            <Text style={styles.rowLabel}>Currency:</Text>
            <View style={styles.currencyContainer}>
               {Object.keys(CURRENCY_SYMBOLS).map((curr) => (
                 <TouchableOpacity 
                    key={curr}
                    style={[styles.currBtn, currency === curr && styles.currBtnActive]}
                    onPress={() => changeCurrency(curr)}
                 >
                   <Text style={[styles.currText, currency === curr && styles.textActive]}>{curr}</Text>
                 </TouchableOpacity>
               ))}
            </View>
          </View>

          <View style={styles.inputContainer}>
            <Ionicons name="mail-outline" size={20} color="#94a3b8" style={styles.inputIcon} />
            <TextInput 
                style={styles.inputField} 
                placeholder="Email Address" 
                placeholderTextColor="#64748b"
                value={email} 
                onChangeText={setEmail} 
                autoCapitalize="none"
                keyboardType="email-address"
            />
          </View>

          <View style={styles.inputContainer}>
            <Ionicons name="lock-closed-outline" size={20} color="#94a3b8" style={styles.inputIcon} />
            <TextInput 
                style={styles.inputField} 
                placeholder="Password" 
                placeholderTextColor="#64748b"
                secureTextEntry 
                value={password} 
                onChangeText={setPassword} 
            />
          </View>

          <TouchableOpacity 
            style={[styles.button, connected ? styles.btnSuccess : styles.btnPrimary, styles.shadowBtn, isConnecting && {opacity: 0.7}]} 
            onPress={connectToIq}
            activeOpacity={0.8}
            disabled={isConnecting}
          >
            {isConnecting ? (
                <View style={{flexDirection: 'row', alignItems: 'center'}}>
                    <ActivityIndicator size="small" color="white" style={{marginRight: 8}} />
                    <Text style={styles.btnText}>Connecting...</Text>
                </View>
            ) : (
                <>
                    <Ionicons name={connected ? "checkmark-circle" : "log-in-outline"} size={20} color="white" style={{marginRight: 8}} />
                    <Text style={styles.btnText}>{connected ? "Connected" : "Connect Account"}</Text>
                </>
            )}
          </TouchableOpacity>
          {connected && (
            <View>
                <Text style={styles.balance}>
                Balance: {CURRENCY_SYMBOLS[currency]}{balance.toFixed(2)}
                </Text>
                <TouchableOpacity style={[styles.button, styles.btnDanger, {marginTop: 10}, styles.shadowBtn]} onPress={disconnectFromIq}>
                    <Ionicons name="log-out-outline" size={20} color="white" style={{marginRight: 8}} />
                    <Text style={styles.btnText}>Disconnect</Text>
                </TouchableOpacity>
            </View>
          )}
        </View>

        {/* Chart Section */}
        {connected && (
          <View style={styles.card}>
            <View style={{flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', marginBottom: 5}}>
                <Text style={styles.cardTitle}>Live Market</Text>
                <TouchableOpacity 
                    onPress={() => setChartType(prev => prev === 'LINE' ? 'AREA' : 'LINE')} 
                    style={styles.smBtn}
                >
                     <Ionicons name={chartType === 'LINE' ? "stats-chart-outline" : "trending-up-outline"} size={16} color="#cbd5e1" />
                     <Text style={{color: '#cbd5e1', fontSize: 12, marginLeft: 4}}>{chartType === 'LINE' ? 'Area' : 'Line'}</Text>
                </TouchableOpacity>
            </View>

            {/* Chart Pair Selector */}
            <ScrollView horizontal showsHorizontalScrollIndicator={false} style={{marginBottom: 10}}>
                {AVAILABLE_PAIRS.map(pair => (
                    <TouchableOpacity 
                        key={pair} 
                        style={[styles.chip, selectedChartPair === pair && styles.chipActive]}
                        onPress={() => setSelectedChartPair(pair)}
                    >
                        <Text style={[styles.chipText, selectedChartPair === pair && styles.chipTextActive]}>{pair}</Text>
                    </TouchableOpacity>
                ))}
            </ScrollView>

            <View style={{flexDirection: 'row', justifyContent: 'space-between', alignItems: 'flex-end'}}>
                 <Text style={styles.priceText}>{currentPrice.toFixed(5)}</Text>
                 <Text style={{color: '#94a3b8', fontSize: 12, marginBottom: 5}}>
                    {selectedChartPair} • {chartType === 'AREA' ? 'Area' : 'Line'}
                 </Text>
            </View>

            <View style={{ height: 220, overflow: 'hidden', backgroundColor: '#0f172a', borderRadius: 10, paddingTop: 10 }}>
                {chartType === 'AREA' ? (
                    <LineChart
                        data={chartData}
                        height={180}
                        width={Dimensions.get('window').width - 60}
                        color="#22c55e"
                        thickness={2}
                        startFillColor="rgba(34, 197, 94, 0.3)"
                        endFillColor="rgba(34, 197, 94, 0.01)"
                        startOpacity={0.9}
                        endOpacity={0.2}
                        initialSpacing={0}
                        noOfSections={4}
                        yAxisColor="transparent"
                        yAxisThickness={0}
                        rulesType="solid"
                        rulesColor="#334155"
                        yAxisTextStyle={{color: '#64748b', fontSize: 10}}
                        xAxisColor="transparent"
                        hideDataPoints
                        curved
                        areaChart
                    />
                ) : (
                    <LineChart
                        data={chartData}
                        height={180}
                        width={Dimensions.get('window').width - 60}
                        color="#3b82f6"
                        thickness={3}
                        initialSpacing={0}
                        noOfSections={4}
                        yAxisColor="transparent"
                        yAxisThickness={0}
                        rulesType="solid"
                        rulesColor="#334155"
                        yAxisTextStyle={{color: '#64748b', fontSize: 10}}
                        xAxisColor="transparent"
                        hideDataPoints
                        curved
                    />
                )}
            </View>
          </View>
        )}

        {/* Control Panel */}
        <View style={styles.card}>
          <Text style={styles.cardTitle}>Bot Controls</Text>
          
          <View style={styles.row}>
            <Text style={styles.rowLabel}>Auto-Trade</Text>
            <Switch 
              value={autoTrade} 
              trackColor={{ false: "#334155", true: "#059669" }}
              thumbColor={autoTrade ? "#34d399" : "#94a3b8"}
              onValueChange={(val) => {
                setAutoTrade(val);
                updateConfig(val, tradeAmount, currency);
              }} 
            />
          </View>

          {/* Active Pairs Selector */}
          <Text style={[styles.rowLabel, {marginTop: 5, marginBottom: 8}]}>Active Pairs (Trading):</Text>
          <ScrollView horizontal showsHorizontalScrollIndicator={false} style={{marginBottom: 20}}>
                {AVAILABLE_PAIRS.map(pair => (
                    <TouchableOpacity 
                        key={pair} 
                        style={[styles.chip, activePairs.includes(pair) && styles.chipActive]}
                        onPress={() => togglePair(pair)}
                    >
                        <Text style={[styles.chipText, activePairs.includes(pair) && styles.chipTextActive]}>
                            {pair} {activePairs.includes(pair) && "✓"}
                        </Text>
                    </TouchableOpacity>
                ))}
          </ScrollView>
          
          <View style={styles.row}>
            <Text style={styles.rowLabel}>Amount ({CURRENCY_SYMBOLS[currency]})</Text>
            <TextInput 
              style={styles.inputSmall} 
              value={tradeAmount} 
              keyboardType="numeric"
              placeholderTextColor="#64748b"
              onChangeText={(val) => {
                setTradeAmount(val);
                updateConfig(autoTrade, val, currency);
              }}
            />
          </View>

          <TouchableOpacity 
            style={[styles.button, botRunning ? styles.btnDanger : styles.btnPrimary]} 
            onPress={toggleBot}
          >
            <Text style={styles.btnText}>{botRunning ? "STOP BOT" : "START BOT"}</Text>
          </TouchableOpacity>
        </View>

        {/* Signals */}
        <View style={styles.card}>
          <Text style={styles.cardTitle}>Recent Signals</Text>
          {signals.slice(0, 5).map((sig, index) => (
            <View key={index} style={styles.signalRow}>
              <Text style={styles.sigTime}>{sig.time_str.split(' ')[1].substring(0,5)}</Text>
              <Text style={styles.sigAsset}>{sig.asset}</Text>
              <Text style={[styles.sigType, sig.type === 'CALL' ? styles.green : styles.red]}>{sig.type}</Text>
              <Text style={[
                styles.sigStatus,
                sig.outcome === 'WIN' ? styles.green :
                sig.outcome === 'LOSS' ? styles.red :
                null
              ]}>
                {sig.outcome ? sig.outcome : sig.status}
              </Text>
            </View>
          ))}
        </View>

        {/* Logs */}
        <View style={styles.card}>
          <Text style={styles.cardTitle}>System Logs</Text>
          {logs.slice(0, 5).map((log, index) => (
            <Text key={index} style={styles.logText}>{log}</Text>
          ))}
        </View>

      </ScrollView>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: '#0f172a',
    paddingTop: 40,
  },
  scrollContent: {
    paddingBottom: 40,
  },
  header: {
    paddingHorizontal: 20,
    paddingVertical: 15,
    backgroundColor: '#0f172a',
    borderBottomWidth: 1,
    borderBottomColor: '#1e293b',
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    marginBottom: 20,
  },
  title: {
    fontSize: 22,
    fontWeight: '800',
    color: '#f8fafc',
    letterSpacing: 0.5,
  },
  statusOnline: {
    backgroundColor: '#22c55e',
    shadowColor: '#22c55e',
    shadowOffset: { width: 0, height: 0 },
    shadowOpacity: 0.8,
    shadowRadius: 5,
  },
  statusOffline: {
    backgroundColor: '#64748b',
  },
  content: {
    padding: 15,
  },
  card: {
    backgroundColor: '#1e293b',
    borderRadius: 16,
    padding: 20,
    marginBottom: 20,
    borderWidth: 1,
    borderColor: '#334155',
    shadowColor: '#000',
    shadowOffset: { width: 0, height: 4 },
    shadowOpacity: 0.3,
    shadowRadius: 4.65,
    elevation: 8,
  },
  cardTitle: {
    fontSize: 18,
    fontWeight: '700',
    marginBottom: 20,
    color: '#f1f5f9',
  },
  inputContainer: {
    flexDirection: 'row',
    alignItems: 'center',
    backgroundColor: '#334155',
    borderRadius: 12,
    marginBottom: 15,
    paddingHorizontal: 12,
    borderWidth: 1,
    borderColor: '#475569',
  },
  inputIcon: {
    marginRight: 10,
  },
  inputField: {
    flex: 1,
    paddingVertical: 14,
    color: 'white',
    fontSize: 16,
    fontWeight: '500',
  },
  button: {
    paddingVertical: 16,
    borderRadius: 12,
    flexDirection: 'row',
    justifyContent: 'center',
    alignItems: 'center',
    marginTop: 10,
  },
  shadowBtn: {
    shadowColor: '#000',
    shadowOffset: { width: 0, height: 2 },
    shadowOpacity: 0.25,
    shadowRadius: 3.84,
    elevation: 5,
  },
  loginContainer: {
    flex: 1,
    backgroundColor: '#0f172a',
    justifyContent: 'center',
    padding: 20,
  },
  loginCard: {
    backgroundColor: '#1e293b',
    borderRadius: 20,
    padding: 25,
    borderWidth: 1,
    borderColor: '#334155',
    shadowColor: '#000',
    shadowOffset: { width: 0, height: 10 },
    shadowOpacity: 0.5,
    shadowRadius: 20,
    elevation: 10,
  },
  loginTitle: {
    fontSize: 28,
    fontWeight: '800',
    color: 'white',
    textAlign: 'center',
    marginBottom: 30,
    letterSpacing: 1,
  },
  input: {
    backgroundColor: '#334155',
    color: 'white',
    padding: 16,
    borderRadius: 12,
    fontSize: 16,
    marginBottom: 16,
    borderWidth: 1,
    borderColor: '#475569',
  },
  switchContainer: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    marginBottom: 25,
    paddingHorizontal: 5,
  },
  label: {
    color: '#cbd5e1',
    fontSize: 16,
    fontWeight: '600',
  },
  btnTextPrimary: {
    color: '#0f172a',
    fontWeight: 'bold',
    fontSize: 18,
  },
  headerTitle: {
    fontSize: 24,
    fontWeight: '800',
    color: 'white',
    letterSpacing: 1,
  },
  statusBadge: {
    flexDirection: 'row',
    alignItems: 'center',
    backgroundColor: 'rgba(0, 255, 131, 0.1)',
    paddingHorizontal: 8,
    paddingVertical: 4,
    borderRadius: 12,
    marginTop: 4,
    alignSelf: 'flex-start',
  },
  statusDot: {
    width: 6,
    height: 6,
    borderRadius: 3,
    marginRight: 6,
  },
  statusText: {
    color: '#00ff83',
    fontSize: 12,
    fontWeight: '700',
  },
  logoutBtn: {
    padding: 8,
    backgroundColor: 'rgba(239, 68, 68, 0.1)',
    borderRadius: 12,
  },
  iconButton: {
    padding: 8,
    backgroundColor: '#334155',
    borderRadius: 12,
  },
  btnPrimary: {
    backgroundColor: '#00ff83',
    paddingVertical: 16,
    borderRadius: 12,
    alignItems: 'center',
    shadowColor: '#00ff83',
    shadowOffset: { width: 0, height: 4 },
    shadowOpacity: 0.3,
    shadowRadius: 10,
    elevation: 5,
  },
  btnSuccess: {
    backgroundColor: '#10b981',
  },
  btnDanger: {
    backgroundColor: '#ef4444',
  },
  btnText: {
    color: 'white',
    fontWeight: 'bold',
    fontSize: 16,
    letterSpacing: 0.5,
  },
  balance: {
    marginTop: 20,
    textAlign: 'center',
    fontWeight: '800',
    color: '#10b981',
    fontSize: 24,
    textShadowColor: 'rgba(16, 185, 129, 0.3)',
    textShadowOffset: { width: 0, height: 0 },
    textShadowRadius: 10,
  },
  row: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    marginBottom: 15,
  },
  rowLabel: {
    color: '#cbd5e1',
    fontSize: 16,
    fontWeight: '600',
  },
  inputSmall: {
    backgroundColor: '#334155',
    borderRadius: 8,
    padding: 10,
    width: 100,
    textAlign: 'center',
    color: 'white',
    fontSize: 16,
    fontWeight: 'bold',
    borderWidth: 1,
    borderColor: '#475569',
  },
  signalRow: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    paddingVertical: 12,
    borderBottomWidth: 1,
    borderBottomColor: '#334155',
  },
  sigTime: { color: '#94a3b8', fontSize: 13 },
  sigAsset: { fontWeight: '700', color: 'white' },
  sigType: { fontWeight: '700' },
  green: { color: '#22c55e' },
  red: { color: '#ef4444' },
  sigStatus: {
    fontWeight: '700',
    fontSize: 13,
  },
  logText: {
    fontSize: 12,
    color: '#94a3b8',
    marginBottom: 6,
    fontFamily: 'monospace',
  },
  priceText: {
    fontSize: 32,
    fontWeight: '800',
    color: '#00ff83',
    marginBottom: 20,
    textAlign: 'center',
  },
  toggleContainer: {
    flexDirection: 'row',
    backgroundColor: '#0f172a',
    borderRadius: 8,
    padding: 3,
    borderWidth: 1,
    borderColor: '#334155',
  },
  toggleBtn: {
    paddingVertical: 8,
    paddingHorizontal: 16,
    borderRadius: 6,
  },
  toggleBtnActive: {
    backgroundColor: '#00ff83',
  },
  toggleText: {
    color: '#94a3b8',
    fontWeight: 'bold',
    fontSize: 14,
  },
  textActive: {
    color: '#0f172a',
  },
  currencyContainer: {
    flexDirection: 'row',
    gap: 8,
  },
  currBtn: {
    backgroundColor: '#1e293b',
    paddingVertical: 6,
    paddingHorizontal: 10,
    borderRadius: 8,
    borderWidth: 1,
    borderColor: '#475569',
  },
  currBtnActive: {
    backgroundColor: '#00ff83',
    borderColor: '#00ff83',
  },
  currText: {
    color: '#94a3b8',
    fontWeight: 'bold',
    fontSize: 12,
  },
  modalOverlay: {
    flex: 1,
    backgroundColor: 'rgba(0,0,0,0.7)',
    justifyContent: 'center',
    padding: 20,
  },
  modalContent: {
    backgroundColor: '#1e293b',
    borderRadius: 20,
    padding: 25,
    borderWidth: 1,
    borderColor: '#334155',
    shadowColor: '#000',
    shadowOffset: { width: 0, height: 10 },
    shadowOpacity: 0.5,
    shadowRadius: 20,
    elevation: 10,
  },
  modalTitle: {
    fontSize: 22,
    fontWeight: 'bold',
    color: 'white',
    marginBottom: 25,
    textAlign: 'center',
  },
  modalLabel: {
    color: '#cbd5e1',
    marginBottom: 8,
    marginTop: 15,
    fontWeight: '600',
  },
  modalInput: {
    backgroundColor: '#334155',
    color: 'white',
    padding: 14,
    borderRadius: 10,
    fontSize: 16,
    borderWidth: 1,
    borderColor: '#475569',
  },
  modalButtons: {
    flexDirection: 'row',
    marginTop: 30,
  },
  chip: {
    paddingVertical: 8,
    paddingHorizontal: 14,
    backgroundColor: '#334155',
    borderRadius: 20,
    marginRight: 8,
    borderWidth: 1,
    borderColor: '#475569',
  },
  chipActive: {
    backgroundColor: '#00ff83',
    borderColor: '#00ff83',
  },
  chipText: {
    color: '#94a3b8',
    fontSize: 13,
    fontWeight: '600',
  },
  chipTextActive: {
    color: '#0f172a',
  },
  smBtn: {
    backgroundColor: '#334155',
    paddingVertical: 6,
    paddingHorizontal: 12,
    borderRadius: 8,
    flexDirection: 'row',
    alignItems: 'center',
  },
});
