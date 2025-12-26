
import React, { useState, useEffect } from 'react';
import { StyleSheet, Text, View, TextInput, TouchableOpacity, ScrollView, Switch, Alert, Dimensions, Modal } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { StatusBar } from 'expo-status-bar';
import { LineChart } from 'react-native-gifted-charts';
import { Ionicons } from '@expo/vector-icons'; // Assuming Expo

export default function App() {
  const [serverIp, setServerIp] = useState('iqbot-mobile.onrender.com'); // Default example
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [accountType, setAccountType] = useState('PRACTICE');
  const [currency, setCurrency] = useState('USD');
  const [connected, setConnected] = useState(false);
  const [botRunning, setBotRunning] = useState(false);
  const [autoTrade, setAutoTrade] = useState(false);
  const [tradeAmount, setTradeAmount] = useState('1.0');
  
  // Advanced Settings State
  const [expiry, setExpiry] = useState('2');
  const [stopLoss, setStopLoss] = useState('2');
  const [profitGoal, setProfitGoal] = useState('5.0');
  const [showSettings, setShowSettings] = useState(false);

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

  const CURRENCY_SYMBOLS: {[key: string]: string} = {
    'USD': '$',
    'NGN': '₦',
    'EUR': '€',
    'GBP': '£'
  };

  // --- API Functions ---
  const connectToIq = async () => {
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
    newProfitGoal?: string
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
          active_pairs: ["EURUSD-OTC", "GBPUSD-OTC", "USDJPY-OTC"]
        })
      });
    } catch (error) {
      console.error(error);
    }
  };

  const saveSettings = () => {
      updateConfig(autoTrade, tradeAmount, currency, expiry, stopLoss, profitGoal);
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

  // --- Polling Loop ---
  useEffect(() => {
    const interval = setInterval(async () => {
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
           const chartRes = await fetch(`${API_URL}/chart_data`);
           const chartJson = await chartRes.json();
           if (chartJson.data && chartJson.data.length > 0) {
             const formattedData = chartJson.data.map((item: any) => ({
                value: item.close,
                label: new Date(item.timestamp).toLocaleTimeString([], {hour: '2-digit', minute:'2-digit'}),
             }));
             setChartData(formattedData);
             setCurrentPrice(chartJson.data[chartJson.data.length - 1].close);
           }
        }

      } catch (error) {
        // Silently fail on poll error
      }
    }, 2000); // Poll every 2 seconds

    return () => clearInterval(interval);
  }, [serverIp]); // Restart poll if IP changes

  return (
    <SafeAreaView style={styles.container}>
      <StatusBar style="light" />
      
      {/* Header */}
      <View style={styles.header}>
        <View style={{flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center'}}>
            <Text style={styles.title}>IQ Bot Mobile</Text>
            <TouchableOpacity onPress={() => setShowSettings(true)}>
                <Ionicons name="settings-sharp" size={24} color="white" />
            </TouchableOpacity>
        </View>
        <View style={styles.ipContainer}>
          <Text style={styles.label}>Server IP:</Text>
          <TextInput 
            style={styles.inputIp} 
            value={serverIp} 
            onChangeText={setServerIp}
            placeholder="192.168.X.X" 
            placeholderTextColor="#94a3b8"
          />
        </View>
      </View>

      <ScrollView style={styles.content}>

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

          <TextInput 
            style={styles.input} 
            placeholder="Email" 
            placeholderTextColor="#64748b"
            value={email} 
            onChangeText={setEmail} 
          />
          <TextInput 
            style={styles.input} 
            placeholder="Password" 
            placeholderTextColor="#64748b"
            secureTextEntry 
            value={password} 
            onChangeText={setPassword} 
          />
          <TouchableOpacity style={[styles.button, connected ? styles.btnSuccess : styles.btnPrimary]} onPress={connectToIq}>
            <Text style={styles.btnText}>{connected ? "CONNECTED" : "CONNECT TO IQ OPTION"}</Text>
          </TouchableOpacity>
          {connected && (
            <View>
                <Text style={styles.balance}>
                Balance: {CURRENCY_SYMBOLS[currency]}{balance.toFixed(2)}
                </Text>
                <TouchableOpacity style={[styles.button, styles.btnDanger, {marginTop: 10}]} onPress={disconnectFromIq}>
                    <Text style={styles.btnText}>DISCONNECT</Text>
                </TouchableOpacity>
            </View>
          )}
        </View>

        {/* Chart Section */}
        {connected && (
          <View style={styles.card}>
            <Text style={styles.cardTitle}>Live Market (EURUSD-OTC)</Text>
            <Text style={styles.priceText}>{currentPrice.toFixed(5)}</Text>
            <View style={{ height: 200, overflow: 'hidden', backgroundColor: '#0f172a', borderRadius: 10 }}>
                <LineChart
                    data={chartData}
                    height={180}
                    width={Dimensions.get('window').width - 60}
                    color="#00ff83"
                    thickness={2}
                    startFillColor="rgba(0, 255, 131, 0.3)"
                    endFillColor="rgba(0, 255, 131, 0.01)"
                    startOpacity={0.9}
                    endOpacity={0.2}
                    initialSpacing={0}
                    noOfSections={4}
                    yAxisColor="transparent"
                    yAxisThickness={0}
                    rulesType="solid"
                    rulesColor="#334155"
                    yAxisTextStyle={{color: '#94a3b8'}}
                    xAxisColor="transparent"
                    hideDataPoints
                    curved
                />
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
  header: {
    padding: 20,
    backgroundColor: '#1e293b',
    borderBottomWidth: 1,
    borderBottomColor: '#334155',
  },
  title: {
    fontSize: 24,
    fontWeight: 'bold',
    color: '#f8fafc',
    marginBottom: 10,
  },
  ipContainer: {
    flexDirection: 'row',
    alignItems: 'center',
    backgroundColor: '#334155',
    padding: 5,
    borderRadius: 8,
  },
  label: {
    color: '#94a3b8',
    marginRight: 10,
    marginLeft: 5,
    fontWeight: 'bold',
  },
  inputIp: {
    color: 'white',
    padding: 5,
    width: 150,
    fontWeight: 'bold',
  },
  content: {
    padding: 15,
  },
  card: {
    backgroundColor: '#1e293b',
    borderRadius: 12,
    padding: 15,
    marginBottom: 15,
    borderWidth: 1,
    borderColor: '#334155',
  },
  cardTitle: {
    fontSize: 18,
    fontWeight: 'bold',
    marginBottom: 15,
    color: '#f1f5f9',
  },
  input: {
    backgroundColor: '#334155',
    borderRadius: 8,
    padding: 12,
    marginBottom: 10,
    color: 'white',
    fontSize: 16,
  },
  button: {
    padding: 16,
    borderRadius: 8,
    alignItems: 'center',
    marginTop: 10,
  },
  btnPrimary: {
    backgroundColor: '#3b82f6',
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
  },
  balance: {
    marginTop: 15,
    textAlign: 'center',
    fontWeight: 'bold',
    color: '#10b981',
    fontSize: 20,
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
    fontWeight: '500',
  },
  inputSmall: {
    backgroundColor: '#334155',
    borderRadius: 8,
    padding: 8,
    width: 100,
    textAlign: 'center',
    color: 'white',
    fontSize: 16,
    fontWeight: 'bold',
  },
  signalRow: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    paddingVertical: 10,
    borderBottomWidth: 1,
    borderBottomColor: '#334155',
  },
  sigTime: { color: '#94a3b8' },
  sigAsset: { fontWeight: 'bold', color: 'white' },
  sigType: { fontWeight: 'bold' },
  green: { color: '#22c55e' },
  red: { color: '#ef4444' },
  sigStatus: {
    fontWeight: 'bold',
    color: '#94a3b8',
  },
  logText: {
    fontSize: 12,
    color: '#94a3b8',
    marginBottom: 4,
  },
  priceText: {
    fontSize: 28,
    fontWeight: 'bold',
    color: '#00ff83',
    marginBottom: 10,
    textAlign: 'center',
  },
  toggleContainer: {
    flexDirection: 'row',
    backgroundColor: '#334155',
    borderRadius: 8,
    padding: 2,
  },
  toggleBtn: {
    paddingVertical: 6,
    paddingHorizontal: 12,
    borderRadius: 6,
  },
  toggleBtnActive: {
    backgroundColor: '#3b82f6',
  },
  toggleText: {
    color: '#94a3b8',
    fontWeight: 'bold',
  },
  textActive: {
    color: 'white',
  },
  currencyContainer: {
    flexDirection: 'row',
    gap: 5,
  },
  currBtn: {
    backgroundColor: '#334155',
    paddingVertical: 5,
    paddingHorizontal: 8,
    borderRadius: 6,
    borderWidth: 1,
    borderColor: '#475569',
  },
  currBtnActive: {
    backgroundColor: '#3b82f6',
    borderColor: '#3b82f6',
  },
  currText: {
    color: '#94a3b8',
    fontWeight: 'bold',
    fontSize: 12,
  },
  modalOverlay: {
    flex: 1,
    backgroundColor: 'rgba(0,0,0,0.5)',
    justifyContent: 'center',
    padding: 20,
  },
  modalContent: {
    backgroundColor: '#1e293b',
    borderRadius: 12,
    padding: 20,
    borderWidth: 1,
    borderColor: '#334155',
  },
  modalTitle: {
    fontSize: 20,
    fontWeight: 'bold',
    color: 'white',
    marginBottom: 20,
    textAlign: 'center',
  },
  modalLabel: {
    color: '#cbd5e1',
    marginBottom: 5,
    marginTop: 10,
    fontWeight: 'bold',
  },
  modalInput: {
    backgroundColor: '#334155',
    color: 'white',
    padding: 12,
    borderRadius: 8,
    fontSize: 16,
  },
  modalButtons: {
    flexDirection: 'row',
    marginTop: 20,
  },
});
