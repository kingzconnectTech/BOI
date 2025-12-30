import React, { useState, useEffect } from 'react';
import { StyleSheet, Text, View, TextInput, TouchableOpacity, ScrollView, Platform, Switch, Dimensions, ActivityIndicator, Modal } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { StatusBar } from 'expo-status-bar';
import axios from 'axios';
import { MaterialCommunityIcons } from '@expo/vector-icons';
import * as Device from 'expo-device';
import * as Notifications from 'expo-notifications';
import Constants from 'expo-constants';
import { useKeepAwake } from 'expo-keep-awake';
import { auth } from './firebaseConfig';
import { onAuthStateChanged, signInWithEmailAndPassword, createUserWithEmailAndPassword, signOut } from 'firebase/auth';

// Backend URL
const API_URL = 'http://192.168.43.76:8000'; 
// const API_URL = 'https://boi-lgdy.onrender.com'; 
const { width } = Dimensions.get('window');

Notifications.setNotificationHandler({
  handleNotification: async () => ({
    shouldShowAlert: true,
    shouldPlaySound: true,
    shouldSetBadge: false,
  }),
});

export default function App() {
  useKeepAwake(); // Keep screen on while app is open

  // Auth State
  const [user, setUser] = useState(null);
  const [firebaseEmail, setFirebaseEmail] = useState('');
  const [firebasePassword, setFirebasePassword] = useState('');
  const [isRegistering, setIsRegistering] = useState(false);

  // App State
  const [page, setPage] = useState('bot_connect'); // 'bot_connect' or 'dashboard'
  const [email, setEmail] = useState(''); // IQ Option Email
  const [password, setPassword] = useState(''); // IQ Option Password
  const [mode, setMode] = useState('PRACTICE'); // PRACTICE or REAL
  const [amount, setAmount] = useState('1');
  const [duration, setDuration] = useState('2');
  const [stopLoss, setStopLoss] = useState('2');
  const [takeProfit, setTakeProfit] = useState('5');
  const [maxConsecutiveLosses, setMaxConsecutiveLosses] = useState('2');
  const [maxTrades, setMaxTrades] = useState('4'); // 0 = unlimited
  const [autoTrading, setAutoTrading] = useState(true);
  const [currency, setCurrency] = useState('$'); // Default to $
  const [strategy, setStrategy] = useState('Momentum'); // Momentum, RSI Reversal
  const [stats, setStats] = useState({ profit: 0, wins: 0, losses: 0, win_rate: 0 });
  const [signals, setSignals] = useState([]); // Simulated signals
  const [backendStatus, setBackendStatus] = useState('Checking...');
  const [logs, setLogs] = useState([]);
  const [isRunning, setIsRunning] = useState(false);
  const [expoPushToken, setExpoPushToken] = useState('');
  const [nextTradingTime, setNextTradingTime] = useState(null); // New state for market status
  const [isLoading, setIsLoading] = useState(false);
  const [showAdvice, setShowAdvice] = useState(false);

  useEffect(() => {
    registerForPushNotificationsAsync().then(token => setExpoPushToken(token));
    checkBackend();
    
    const unsubscribe = onAuthStateChanged(auth, (u) => {
      setUser(u);
      if (!u) {
        // Reset bot state if user logs out
        setPage('bot_connect');
        setIsRunning(false);
        setLogs([]);
        setEmail('');
        setPassword('');
      }
    });
    return unsubscribe;
  }, []);

  // Poll for logs and stats when dashboard is active
  useEffect(() => {
    let interval;
    if (user && page === 'dashboard') {
      interval = setInterval(async () => {
        try {
          if (!email) return;

          // Get Logs
          const logsResponse = await axios.get(`${API_URL}/logs?email=${email}`);
          if (logsResponse.data.logs && logsResponse.data.logs.length > 0) {
            // Only update if we have logs to avoid clearing "Starting bot..." message prematurely
            // Or better: Append backend logs to local logs, avoiding duplicates?
            // Simple approach: Backend logs are authoritative. 
            // If backend logs are empty, do nothing (keep local logs).
            setLogs(logsResponse.data.logs.reverse());
          } else if (logsResponse.data.logs && logsResponse.data.logs.length === 0) {
             // If backend explicitly returns empty logs, do we clear local?
             // Only if we just started (to clear old session logs).
             // But if we just added "Starting bot...", we don't want to clear it.
             // So, do nothing here.
          }
          
          // Get Stats (Status)
          const statusResponse = await axios.get(`${API_URL}/status?email=${email}`);
          if (statusResponse.data) {
            setStats(statusResponse.data.stats || { profit: 0, wins: 0, losses: 0, win_rate: 0 });
            setIsRunning(statusResponse.data.running);
            setSignals(statusResponse.data.signals || []);
            if (statusResponse.data.currency) {
                setCurrency(statusResponse.data.currency);
            }
            if (statusResponse.data.min_amount) {
                // Only update if amount is default '1' or empty, to avoid overwriting user input
                if (amount === '1' || amount === '') {
                     setAmount(statusResponse.data.min_amount.toString());
                }
            }
            if (statusResponse.data.next_trading_time) {
                 setNextTradingTime(statusResponse.data.next_trading_time);
            } else {
                 setNextTradingTime(null);
            }
          }
        } catch (error) {
          console.log("Error fetching data:", error.message);
        }
      }, 2000);
    }
    return () => clearInterval(interval);
  }, [page, email, user]);

  const addLog = (message) => {
    const timestamp = new Date().toLocaleTimeString();
    setLogs(prev => [`[${timestamp}] ${message}`, ...prev]);
  };

  const checkBackend = async () => {
    try {
      const response = await axios.get(API_URL);
      if (response.data.status === 'ok') {
        setBackendStatus('Connected');
      }
    } catch (error) {
      setBackendStatus('Disconnected');
    }
  };

  // Firebase Handlers
  const handleFirebaseLogin = async () => {
    if (!firebaseEmail || !firebasePassword) {
      alert('Please enter email and password');
      return;
    }
    setIsLoading(true);
    try {
      await signInWithEmailAndPassword(auth, firebaseEmail, firebasePassword);
    } catch (error) {
      alert(`Login Failed: ${error.message}`);
    } finally {
      setIsLoading(false);
    }
  };

  const handleFirebaseRegister = async () => {
    if (!firebaseEmail || !firebasePassword) {
      alert('Please enter email and password');
      return;
    }
    setIsLoading(true);
    try {
      await createUserWithEmailAndPassword(auth, firebaseEmail, firebasePassword);
    } catch (error) {
      alert(`Registration Failed: ${error.message}`);
    } finally {
      setIsLoading(false);
    }
  };

  const handleAppLogout = async () => {
    try {
        if (email) {
            // Ensure we disconnect the bot from backend before logging out
            try {
                await axios.post(`${API_URL}/disconnect`, { email });
            } catch (e) {
                console.log("Error disconnecting bot:", e);
            }
        }
        await signOut(auth);
    } catch (error) {
        alert(error.message);
    }
  };

  // Bot Handlers
  const handleBotConnect = async () => {
    if (!email || !password) {
      alert('Please enter IQ Option email and password');
      return;
    }
    
    setIsLoading(true);
    // Switch to dashboard immediately to show logs
    setPage('dashboard');
    addLog('Connecting to IQ Option...'); 

    try {
        const response = await axios.post(`${API_URL}/connect`, {
            email,
            password,
            mode
        }, { timeout: 60000 }); // 60s timeout
        
        if (response.data.status === 'connected') {
            // setPage('dashboard'); // Already there
            setIsRunning(false);
            addLog(`Success: ${response.data.message}`);
            if (response.data.data && response.data.data.stats) {
                 setStats(response.data.data.stats);
            }
            if (response.data.data && response.data.data.currency) {
                 setCurrency(response.data.data.currency);
            }
            if (response.data.data && response.data.data.min_amount) {
                 setAmount(response.data.data.min_amount.toString());
            }
        }
    } catch (error) {
        // Go back to connect page on failure
        // setPage('bot_connect'); // Optional: stay on dashboard to see logs?
        // Let's stay on dashboard but allow retry via logout or back button if we had one.
        // Actually, if we fail, we should probably go back so they can fix credentials.
        setPage('bot_connect');
        const errorMsg = error.response?.data?.detail || error.message;
        alert(`Connection Failed: ${errorMsg}`);
    } finally {
        setIsLoading(false);
    }
  };

  const startBot = async () => {
    try {
      addLog('Starting bot...'); // Immediate feedback
      const response = await axios.post(`${API_URL}/start`, {
        email: email,
        password: password,
        mode: mode,
        amount: parseFloat(amount) || 1,
        duration: parseInt(duration) || 1,
        stop_loss: parseFloat(stopLoss) || 0,
        take_profit: parseFloat(takeProfit) || 0,
        max_consecutive_losses: parseInt(maxConsecutiveLosses) || 0,
        max_trades: parseInt(maxTrades) || 0,
        auto_trading: autoTrading,
        push_token: expoPushToken,
        strategy: strategy
      }, { timeout: 60000 }); // 60s timeout
      
      if (response.data.status === 'started') {
        setPage('dashboard');
        setIsRunning(true);
        addLog(`Success: ${response.data.message}`);
      }
    } catch (error) {
      setIsRunning(false);
      const errorMsg = error.response?.data?.detail || error.message;
      alert(`Connect/Start Failed: ${errorMsg}`);
      addLog(`Start Failed: ${errorMsg}`);
    }
  };

  const handleUpdateStrategy = async (newStrategy) => {
    setStrategy(newStrategy);
    if (isRunning) {
        try {
            addLog(`Updating strategy to ${newStrategy}...`);
            await axios.post(`${API_URL}/update`, {
                email: email,
                strategy: newStrategy
            });
            addLog(`Strategy updated to ${newStrategy}`);
        } catch (error) {
            addLog(`Error updating strategy: ${error.message}`);
        }
    }
  };

  const handleStop = async () => {
    try {
      addLog('Stopping bot...');
      const response = await axios.post(`${API_URL}/stop`, { email: email });
      if (response.data.status === 'stopped') {
        setIsRunning(false);
        addLog('Bot stopped successfully');
      }
    } catch (error) {
      addLog(`Error stopping bot: ${error.message}`);
    }
  };

  const handleBotDisconnect = () => {
      handleStop();
      setPage('bot_connect');
      setLogs([]);
      setStats({ profit: 0, wins: 0, losses: 0, win_rate: 0 });
      setCurrency('$');
      setEmail('');
      setPassword('');
  };

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
        alert('Failed to get push token for push notification!');
        return;
      }
      try {
        const projectId = Constants?.expoConfig?.extra?.eas?.projectId ?? Constants?.easConfig?.projectId;
        if (!projectId) {
           token = (await Notifications.getExpoPushTokenAsync()).data;
        } else {
           token = (await Notifications.getExpoPushTokenAsync({ projectId })).data;
        }
      } catch (e) {
         token = (await Notifications.getExpoPushTokenAsync()).data;
      }
      console.log("Push Token:", token);
    } else {
      // alert('Must use physical device for Push Notifications');
    }
  
    return token;
  }

  const handleScheduleNotification = async () => {
    if (!nextTradingTime) return;
    
    // Parse time string (e.g., "14:00")
    const timeParts = nextTradingTime.split(' ')[0].split(':');
    const hour = parseInt(timeParts[0]);
    const minute = parseInt(timeParts[1]);
    
    const now = new Date();
    const trigger = new Date();
    trigger.setHours(hour);
    trigger.setMinutes(minute);
    trigger.setSeconds(0);
    
    // If time is in past, assume tomorrow (though backend handles "Tomorrow" label, simple check here)
    if (trigger <= now) {
        trigger.setDate(trigger.getDate() + 1);
    }
    
    // Schedule notification 5 mins before
    trigger.setMinutes(trigger.getMinutes() - 5);

    try {
        await Notifications.scheduleNotificationAsync({
            content: {
                title: "Trading Session Starting Soon!",
                body: `Market opens at ${nextTradingTime}. Get ready!`,
            },
            trigger: trigger,
        });
        alert(`Reminder set for ${trigger.toLocaleTimeString()}!`);
    } catch (e) {
        alert("Failed to schedule reminder");
    }
  };

  const renderAuth = () => (
    <View style={styles.loginContainer}>
        <Text style={styles.loginTitle}>BOI</Text>
        <Text style={styles.loginSubtitle}>{isRegistering ? 'Create Account' : 'Welcome Back'}</Text>
        
        <View style={styles.loginCard}>
           <View style={styles.inputContainer}>
              <MaterialCommunityIcons name="email-outline" size={20} color="#94a3b8" style={styles.inputIcon} />
              <TextInput
                style={styles.input}
                placeholder="Email Address"
                placeholderTextColor="#64748b"
                value={firebaseEmail}
                onChangeText={setFirebaseEmail}
                autoCapitalize="none"
                keyboardType="email-address"
              />
            </View>
            <View style={styles.inputContainer}>
              <MaterialCommunityIcons name="lock-outline" size={20} color="#94a3b8" style={styles.inputIcon} />
              <TextInput
                style={styles.input}
                placeholder="Password"
                placeholderTextColor="#64748b"
                value={firebasePassword}
                onChangeText={setFirebasePassword}
                secureTextEntry
              />
            </View>

            <TouchableOpacity style={styles.loginButton} onPress={isRegistering ? handleFirebaseRegister : handleFirebaseLogin} disabled={isLoading}>
                {isLoading ? (
                    <ActivityIndicator size="small" color="#fff" />
                ) : (
                    <Text style={styles.loginButtonText}>{isRegistering ? 'REGISTER' : 'LOGIN'}</Text>
                )}
            </TouchableOpacity>
            
            <TouchableOpacity style={{marginTop: 20}} onPress={() => setIsRegistering(!isRegistering)}>
                <Text style={{color: '#3b82f6', textAlign: 'center', fontWeight: '600'}}>
                    {isRegistering ? 'Already have an account? Login' : 'New here? Create Account'}
                </Text>
            </TouchableOpacity>
        </View>
        <Text style={styles.backendStatus}>Server: {backendStatus}</Text>
    </View>
  );

  const renderBotConnect = () => (
      <View style={styles.loginContainer}>
          <View style={styles.authHeader}>
             <Text style={styles.authEmail}>{user?.email}</Text>
             <TouchableOpacity onPress={handleAppLogout}>
                 <Text style={{color: '#ef4444', fontWeight: 'bold'}}>Sign Out</Text>
             </TouchableOpacity>
          </View>

          <Text style={styles.loginTitle}>CONNECT<Text style={styles.headerTitleAccent}>BOT</Text></Text>
          <Text style={styles.loginSubtitle}>Enter IQ Option Credentials</Text>
          
          <View style={styles.loginCard}>
             <View style={styles.inputContainer}>
                <MaterialCommunityIcons name="email-outline" size={20} color="#94a3b8" style={styles.inputIcon} />
                <TextInput
                  style={styles.input}
                  placeholder="IQ Option Email"
                  placeholderTextColor="#64748b"
                  value={email}
                  onChangeText={setEmail}
                  autoCapitalize="none"
                  keyboardType="email-address"
                />
              </View>
              <View style={styles.inputContainer}>
                <MaterialCommunityIcons name="lock-outline" size={20} color="#94a3b8" style={styles.inputIcon} />
                <TextInput
                  style={styles.input}
                  placeholder="IQ Option Password"
                  placeholderTextColor="#64748b"
                  value={password}
                  onChangeText={setPassword}
                  secureTextEntry
                />
              </View>

              <View style={styles.modeSelector}>
                <TouchableOpacity 
                  style={[styles.modeOption, mode === 'PRACTICE' && styles.modeOptionActive]}
                  onPress={() => setMode('PRACTICE')}
                >
                  <Text style={[styles.modeText, mode === 'PRACTICE' && styles.modeTextActive]}>DEMO</Text>
                </TouchableOpacity>
                <TouchableOpacity 
                  style={[styles.modeOption, mode === 'REAL' && styles.modeOptionActive]}
                  onPress={() => setMode('REAL')}
                >
                  <Text style={[styles.modeText, mode === 'REAL' && styles.modeTextActive]}>REAL</Text>
                </TouchableOpacity>
              </View>

              <TouchableOpacity style={styles.loginButton} onPress={handleBotConnect} disabled={isLoading}>
                  {isLoading ? (
                      <ActivityIndicator size="small" color="#fff" />
                  ) : (
                      <Text style={styles.loginButtonText}>CONNECT & START</Text>
                  )}
              </TouchableOpacity>
          </View>
      </View>
  );

  const renderDashboard = () => (
      <ScrollView style={styles.mainScrollView} contentContainerStyle={styles.scrollContent}>
        {/* Header with Logout */}
        <View style={styles.dashboardHeader}>
             <View>
                <Text style={styles.headerTitle}>DASHBOARD</Text>
                <Text style={styles.headerSubtitle}>{email} ({mode})</Text>
                <Text style={{color: '#64748b', fontSize: 10, marginTop: 2}}>Runs in background</Text>
             </View>
             <View style={{flexDirection: 'row', alignItems: 'center'}}>
                 <TouchableOpacity onPress={() => setShowAdvice(true)} style={[styles.logoutButton, {marginRight: 10, borderColor: '#3b82f6'}]}>
                     <MaterialCommunityIcons name="lightbulb-on-outline" size={20} color="#3b82f6" />
                 </TouchableOpacity>
                 <TouchableOpacity onPress={handleBotDisconnect} style={[styles.logoutButton, {marginRight: 10}]}>
                     <MaterialCommunityIcons name="power" size={20} color="#f59e0b" />
                 </TouchableOpacity>
                 <TouchableOpacity onPress={handleAppLogout} style={styles.logoutButton}>
                     <MaterialCommunityIcons name="logout" size={20} color="#ef4444" />
                 </TouchableOpacity>
             </View>
        </View>
        
        {/* Advice Modal */}
        <Modal
            animationType="slide"
            transparent={true}
            visible={showAdvice}
            onRequestClose={() => setShowAdvice(false)}
        >
            <View style={{flex: 1, backgroundColor: 'rgba(0,0,0,0.8)', justifyContent: 'center', padding: 20}}>
                <View style={{backgroundColor: '#1e293b', borderRadius: 16, padding: 20, maxHeight: '80%', borderWidth: 1, borderColor: '#334155'}}>
                    <View style={{flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', marginBottom: 20}}>
                        <Text style={{color: '#fff', fontSize: 20, fontWeight: 'bold'}}>Trading Advice</Text>
                        <TouchableOpacity onPress={() => setShowAdvice(false)}>
                            <MaterialCommunityIcons name="close" size={24} color="#94a3b8" />
                        </TouchableOpacity>
                    </View>
                    <ScrollView indicatorStyle="white">
                        <Text style={{color: '#e2e8f0', fontSize: 16, marginBottom: 10, fontWeight: 'bold'}}>Daily Trading Schedule</Text>
                        
                        <Text style={{color: '#10b981', fontSize: 14, fontWeight: 'bold', marginTop: 10}}>🟢 Best Session #1: London Session</Text>
                        <Text style={{color: '#94a3b8', fontSize: 13, marginBottom: 4}}>09:00 AM – 12:00 PM</Text>
                        <Text style={{color: '#cbd5e1', fontSize: 14, lineHeight: 22}}>
                        • Why: Clean candle structure, lowest manipulation on OTC.{'\n'}
                        • What to trade: EMA Trend Pullback, Support & Resistance Rejection.{'\n'}
                        • How: Take 2–3 quality trades only. Avoid first 10 mins (09:00–09:10).
                        </Text>

                        <Text style={{color: '#f59e0b', fontSize: 14, fontWeight: 'bold', marginTop: 15}}>🟡 Best Session #2: New York Session</Text>
                        <Text style={{color: '#94a3b8', fontSize: 13, marginBottom: 4}}>02:30 PM – 05:30 PM</Text>
                        <Text style={{color: '#cbd5e1', fontSize: 14, lineHeight: 22}}>
                        • Why: Strong momentum, larger candles.{'\n'}
                        • Caution: Higher volatility. Avoid major news.{'\n'}
                        • What to trade: RSI + Candle Confirmation, Trend continuation.{'\n'}
                        • Tip: Stop after 2 losses.
                        </Text>

                        <Text style={{color: '#10b981', fontSize: 14, fontWeight: 'bold', marginTop: 15}}>🟢 Best Session #3: OTC Golden Hours (Highly Recommended)</Text>
                        <Text style={{color: '#94a3b8', fontSize: 13, marginBottom: 4}}>07:00 PM – 10:00 PM</Text>
                        <Text style={{color: '#cbd5e1', fontSize: 14, lineHeight: 22}}>
                        • Why: Most stable OTC behavior, fewer fake breakouts.{'\n'}
                        • What to trade: S&R Rejection, EMA pullbacks.{'\n'}
                        • Setup: 1-min chart, 2-min expiry. Max 3 trades.
                        </Text>

                        <Text style={{color: '#ef4444', fontSize: 14, fontWeight: 'bold', marginTop: 15}}>❌ Sessions to Avoid</Text>
                        <Text style={{color: '#cbd5e1', fontSize: 14, lineHeight: 22}}>
                        • 01:00 AM – 06:00 AM: Random movements.{'\n'}
                        • After 10:30 PM: OTC becomes unstable, sudden spikes.
                        </Text>

                        <Text style={{color: '#e2e8f0', fontSize: 16, marginTop: 20, marginBottom: 10, fontWeight: 'bold'}}>Recommended Routine</Text>
                        <Text style={{color: '#cbd5e1', fontSize: 14, lineHeight: 22}}>
                        • Option A (Conservative): 7:00 – 9:00 PM{'\n'}
                        • Option B (Active): 9:30 – 10:30 AM & 7:30 – 9:00 PM
                        </Text>

                        <Text style={{color: '#e2e8f0', fontSize: 16, marginTop: 20, marginBottom: 10, fontWeight: 'bold'}}>Golden Rules</Text>
                        <Text style={{color: '#cbd5e1', fontSize: 14, lineHeight: 22}}>
                        1. Max 5 trades per day.{'\n'}
                        2. Stop after 2 consecutive losses.{'\n'}
                        3. No martingale on 2-minute trades.{'\n'}
                        4. Trade only when candles are clean.
                        </Text>
                        <View style={{height: 20}} />
                    </ScrollView>
                </View>
            </View>
        </Modal>

        {/* Market Closed Warning */}
        {nextTradingTime && (
            <View style={styles.warningCard}>
                <MaterialCommunityIcons name="clock-alert-outline" size={24} color="#fff" />
                <View style={{flex: 1, marginLeft: 10}}>
                    <Text style={styles.warningTitle}>Market Currently Closed</Text>
                    <Text style={styles.warningText}>Next session starts at: {nextTradingTime}</Text>
                </View>
                <TouchableOpacity style={styles.reminderButton} onPress={handleScheduleNotification}>
                    <MaterialCommunityIcons name="bell-ring" size={20} color="#fff" />
                </TouchableOpacity>
            </View>
        )}

        {/* Strategy Selector */}
        <View style={styles.sectionContainer}>
            <Text style={styles.sectionTitle}>STRATEGY</Text>
            <ScrollView 
                horizontal 
                showsHorizontalScrollIndicator={false}
                contentContainerStyle={{ gap: 8, paddingRight: 20 }}
            >
                <TouchableOpacity 
                    style={[styles.strategyOption, strategy === 'Momentum' && styles.strategyOptionActive]}
                    onPress={() => handleUpdateStrategy('Momentum')}
                >
                    <Text style={[styles.strategyText, strategy === 'Momentum' && styles.strategyTextActive]}>Momentum</Text>
                </TouchableOpacity>
                <TouchableOpacity 
                    style={[styles.strategyOption, strategy === 'RSI Reversal' && styles.strategyOptionActive]}
                    onPress={() => handleUpdateStrategy('RSI Reversal')}
                >
                    <Text style={[styles.strategyText, strategy === 'RSI Reversal' && styles.strategyTextActive]}>RSI Reversal</Text>
                </TouchableOpacity>
                <TouchableOpacity 
                    style={[styles.strategyOption, strategy === 'EMA Trend Pullback' && styles.strategyOptionActive]}
                    onPress={() => handleUpdateStrategy('EMA Trend Pullback')}
                >
                    <Text style={[styles.strategyText, strategy === 'EMA Trend Pullback' && styles.strategyTextActive]}>EMA Trend</Text>
                </TouchableOpacity>
                <TouchableOpacity 
                    style={[styles.strategyOption, strategy === 'Support & Resistance' && styles.strategyOptionActive]}
                    onPress={() => handleUpdateStrategy('Support & Resistance')}
                >
                    <Text style={[styles.strategyText, strategy === 'Support & Resistance' && styles.strategyTextActive]}>Support & Res</Text>
                </TouchableOpacity>
            </ScrollView>
        </View>
        
        {/* Stats Dashboard */}
        <View style={styles.dashboardContainer}>
          <View style={styles.statCard}>
            <MaterialCommunityIcons name="finance" size={24} color="#10b981" />
            <Text style={styles.statLabel}>Profit</Text>
            <Text style={[styles.statValue, { color: stats.profit >= 0 ? '#10b981' : '#ef4444' }]}>
              {currency}{stats.profit}
            </Text>
          </View>
          <View style={styles.statCard}>
            <MaterialCommunityIcons name="target" size={24} color="#3b82f6" />
            <Text style={styles.statLabel}>Win Rate</Text>
            <Text style={styles.statValue}>{stats.win_rate}%</Text>
          </View>
          <View style={styles.statCard}>
            <MaterialCommunityIcons name="history" size={24} color="#f59e0b" />
            <Text style={styles.statLabel}>W/L</Text>
            <Text style={styles.statValue}>{stats.wins}/{stats.losses}</Text>
          </View>
        </View>

        {/* Configuration Section */}
        <View style={styles.sectionContainer}>
          <Text style={styles.sectionTitle}>SETTINGS</Text>
          
          {/* Trading Settings Grid */}
          <View style={styles.gridContainer}>
            <View style={styles.gridItem}>
              <Text style={styles.gridLabel}>Amount ({currency})</Text>
              <TextInput
                style={styles.gridInput}
                placeholder="1"
                placeholderTextColor="#64748b"
                value={amount}
                onChangeText={setAmount}
                keyboardType="numeric"
              />
            </View>
            <View style={styles.gridItem}>
              <Text style={styles.gridLabel}>Time (Min)</Text>
              <TextInput
                style={styles.gridInput}
                placeholder="1"
                placeholderTextColor="#64748b"
                value={duration}
                onChangeText={setDuration}
                keyboardType="numeric"
              />
            </View>
            <View style={styles.gridItem}>
              <Text style={styles.gridLabel}>Stop Loss ({currency})</Text>
              <TextInput
                style={styles.gridInput}
                placeholder="10"
                placeholderTextColor="#64748b"
                value={stopLoss}
                onChangeText={setStopLoss}
                keyboardType="numeric"
              />
            </View>
            <View style={styles.gridItem}>
              <Text style={styles.gridLabel}>Take Profit ({currency})</Text>
              <TextInput
                style={styles.gridInput}
                placeholder="20"
                placeholderTextColor="#64748b"
                value={takeProfit}
                onChangeText={setTakeProfit}
                keyboardType="numeric"
              />
            </View>
          </View>

          {/* Advanced Settings */}
          <View style={styles.settingRow}>
             <View style={{flex: 1}}>
                <Text style={styles.settingLabel}>Max Consecutive Losses</Text>
                <Text style={styles.settingSubLabel}>Auto-stop after N losses</Text>
             </View>
             <TextInput
                style={styles.smallInput}
                placeholder="2"
                placeholderTextColor="#64748b"
                value={maxConsecutiveLosses}
                onChangeText={setMaxConsecutiveLosses}
                keyboardType="numeric"
              />
          </View>

          <View style={styles.settingRow}>
             <View style={{flex: 1}}>
                <Text style={styles.settingLabel}>Max Trades per Session</Text>
                <Text style={styles.settingSubLabel}>Stop after N trades (0=Unlimited)</Text>
             </View>
             <TextInput
                style={styles.smallInput}
                placeholder="0"
                placeholderTextColor="#64748b"
                value={maxTrades}
                onChangeText={setMaxTrades}
                keyboardType="numeric"
              />
          </View>

          <View style={styles.settingRow}>
             <View style={{flex: 1}}>
                <Text style={styles.settingLabel}>Auto Trading</Text>
                <Text style={styles.settingSubLabel}>{autoTrading ? 'Active' : 'Signal Only'}</Text>
             </View>
             <Switch
                trackColor={{ false: "#334155", true: "#3b82f6" }}
                thumbColor={autoTrading ? "#fff" : "#cbd5e1"}
                ios_backgroundColor="#334155"
                onValueChange={setAutoTrading}
                value={autoTrading}
            />
          </View>

        </View>

        {/* Action Button */}
        <TouchableOpacity 
          style={[styles.mainButton, isRunning ? styles.stopButton : styles.startButton]}
          onPress={isRunning ? handleStop : startBot} // startBot here updates settings
          activeOpacity={0.8}
        >
          <MaterialCommunityIcons name={isRunning ? "stop-circle-outline" : "play-circle-outline"} size={28} color="#fff" />
          <Text style={styles.mainButtonText}>
            {isRunning ? 'STOP BOT' : 'UPDATE & START'}
          </Text>
        </TouchableOpacity>

        {/* Signal History (Visible when Auto Trading is OFF or always if you prefer) */}
        {!autoTrading && signals.length > 0 && (
          <View style={styles.logsSection}>
            <View style={styles.logsHeader}>
               <MaterialCommunityIcons name="history" size={16} color="#94a3b8" />
               <Text style={styles.logsTitle}>SIGNAL HISTORY (SIMULATION)</Text>
            </View>
            <View style={styles.signalTable}>
               <View style={styles.signalHeaderRow}>
                <Text style={[styles.signalHeaderCell, {flex: 2}]}>PAIR</Text>
                <Text style={[styles.signalHeaderCell, {flex: 1}]}>DIR</Text>
                <Text style={[styles.signalHeaderCell, {flex: 2}]}>ENTRY</Text>
                <Text style={[styles.signalHeaderCell, {flex: 2}]}>RESULT</Text>
              </View>
              <ScrollView style={{ flex: 1 }} nestedScrollEnabled={true}>
              {signals.map((sig) => (
                <View key={sig.id} style={styles.signalRow}>
                  <Text style={[styles.signalCell, {flex: 2, color: '#fff'}]}>
                    {sig.pair.replace('-OTC', '')}
                    <Text style={{fontSize: 10, color: '#64748b'}}>{'\n'}{sig.time}</Text>
                  </Text>
                  <Text style={[styles.signalCell, {flex: 1, color: sig.direction === 'call' ? '#10b981' : '#ef4444'}]}>
                    {sig.direction === 'call' ? '▲' : '▼'}
                  </Text>
                  <Text style={[styles.signalCell, {flex: 2, color: '#94a3b8'}]}>{sig.entry}</Text>
                  <Text style={[styles.signalCell, {flex: 2, fontWeight: 'bold', color: sig.status === 'WIN' ? '#10b981' : sig.status === 'LOSS' ? '#ef4444' : '#fbbf24'}]}>
                    {sig.status}
                  </Text>
                </View>
              ))}
              </ScrollView>
           </View>
          </View>
        )}

        {/* System Logs */}
        <View style={styles.logsSection}>
          <View style={styles.logsHeader}>
            <MaterialCommunityIcons name="console-line" size={16} color="#94a3b8" />
            <Text style={styles.logsTitle}>SYSTEM LOGS</Text>
          </View>
          <ScrollView style={styles.logsConsole} nestedScrollEnabled={true}>
            {logs.length === 0 ? (
              <Text style={styles.logPlaceholder}>Waiting for system events...</Text>
            ) : (
              logs.map((log, index) => (
                <Text key={index} style={styles.logLine}>
                  <Text style={styles.logTimestamp}>{log.split(']')[0]}]</Text>
                  <Text style={styles.logContent}>{log.split(']')[1]}</Text>
                </Text>
              ))
            )}
          </ScrollView>
        </View>

      </ScrollView>
  );

  return (
    <SafeAreaView style={styles.container}>
      <StatusBar style="light" backgroundColor="#0f172a" />
      {!user ? renderAuth() : (page === 'bot_connect' ? renderBotConnect() : renderDashboard())}
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: '#0f172a', // Slate 900
    paddingTop: Platform.OS === 'android' ? 40 : 0,
  },
  // Login Styles
  loginContainer: {
      flex: 1,
      justifyContent: 'center',
      alignItems: 'center',
      padding: 24,
  },
  loginTitle: {
      fontSize: 32,
      fontWeight: '800',
      color: '#fff',
      letterSpacing: 2,
      marginBottom: 8,
  },
  loginSubtitle: {
      color: '#64748b',
      marginBottom: 40,
      fontSize: 16,
  },
  loginCard: {
      width: '100%',
      backgroundColor: '#1e293b',
      padding: 24,
      borderRadius: 24,
      borderWidth: 1,
      borderColor: '#334155',
      shadowColor: '#000',
      shadowOffset: { width: 0, height: 10 },
      shadowOpacity: 0.3,
      shadowRadius: 20,
      elevation: 10,
  },
  loginButton: {
      backgroundColor: '#3b82f6',
      padding: 16,
      borderRadius: 12,
      alignItems: 'center',
      marginTop: 16,
  },
  loginButtonText: {
      color: '#fff',
      fontWeight: 'bold',
      fontSize: 16,
      letterSpacing: 1,
  },
  strategyOption: {
    width: 140,
    paddingVertical: 12,
    paddingHorizontal: 4,
    borderRadius: 12,
    borderWidth: 1,
    borderColor: '#334155',
    alignItems: 'center',
    justifyContent: 'center',
    backgroundColor: '#1e293b',
  },
  strategyOptionActive: {
    borderColor: '#3b82f6',
    backgroundColor: '#3b82f6',
  },
  strategyText: {
    color: '#94a3b8',
    fontWeight: '600',
    fontSize: 11,
    textAlign: 'center',
  },
  strategyTextActive: {
    color: '#fff',
  },
  backendStatus: {
      marginTop: 20,
      color: '#475569',
      fontSize: 12,
  },
  authHeader: {
      position: 'absolute',
      top: 20,
      right: 20,
      left: 20,
      flexDirection: 'row',
      justifyContent: 'space-between',
      alignItems: 'center',
  },
  authEmail: {
      color: '#94a3b8',
      fontSize: 12,
  },
  dashboardHeader: {
      flexDirection: 'row',
      justifyContent: 'space-between',
      alignItems: 'center',
      marginBottom: 24,
      paddingBottom: 16,
      borderBottomWidth: 1,
      borderBottomColor: '#1e293b',
  },
  logoutButton: {
      padding: 8,
      backgroundColor: '#1e293b',
      borderRadius: 8,
      borderWidth: 1,
      borderColor: '#334155',
  },
  mainScrollView: {
    flex: 1,
  },
  scrollContent: {
    padding: 20,
    paddingBottom: 40,
  },
  header: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    paddingHorizontal: 24,
    paddingVertical: 16,
    backgroundColor: '#0f172a',
    borderBottomWidth: 1,
    borderBottomColor: '#1e293b',
  },
  headerTitle: {
    fontSize: 24,
    fontWeight: '800',
    color: '#fff',
    letterSpacing: 1,
  },
  headerTitleAccent: {
    color: '#3b82f6', // Blue 500
  },
  headerSubtitle: {
    color: '#64748b',
    fontSize: 12,
    fontWeight: '500',
  },
  statusBadge: {
    flexDirection: 'row',
    alignItems: 'center',
    backgroundColor: '#1e293b',
    paddingHorizontal: 10,
    paddingVertical: 6,
    borderRadius: 20,
    borderWidth: 1,
    borderColor: '#334155',
  },
  statusDot: {
    width: 6,
    height: 6,
    borderRadius: 3,
    marginRight: 6,
  },
  statusText: {
    color: '#94a3b8',
    fontSize: 10,
    fontWeight: '700',
  },
  
  // Dashboard
  warningCard: {
    backgroundColor: '#f59e0b',
    margin: 20,
    marginBottom: 0,
    padding: 15,
    borderRadius: 12,
    flexDirection: 'row',
    alignItems: 'center',
    shadowColor: '#f59e0b',
    shadowOffset: { width: 0, height: 4 },
    shadowOpacity: 0.3,
    shadowRadius: 8,
    elevation: 5,
  },
  warningTitle: {
    color: '#fff',
    fontWeight: 'bold',
    fontSize: 16,
  },
  warningText: {
    color: '#fff',
    fontSize: 14,
    opacity: 0.9,
  },
  reminderButton: {
    backgroundColor: 'rgba(255,255,255,0.2)',
    padding: 8,
    borderRadius: 8,
  },
  dashboardContainer: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    marginBottom: 24,
  },
  statCard: {
    width: '31%',
    backgroundColor: '#1e293b', // Slate 800
    padding: 12,
    borderRadius: 12,
    alignItems: 'center',
    borderWidth: 1,
    borderColor: '#334155',
    elevation: 2,
    shadowColor: '#000',
    shadowOffset: { width: 0, height: 2 },
    shadowOpacity: 0.2,
    shadowRadius: 4,
  },
  statLabel: {
    color: '#94a3b8',
    fontSize: 11,
    marginTop: 8,
    fontWeight: '600',
    textTransform: 'uppercase',
  },
  statValue: {
    color: '#fff',
    fontSize: 16,
    fontWeight: 'bold',
    marginTop: 4,
  },

  // Section
  sectionContainer: {
    paddingHorizontal: 24,
    marginBottom: 24,
  },
  sectionTitle: {
    color: '#94a3b8',
    fontSize: 12,
    fontWeight: 'bold',
    letterSpacing: 1,
    marginBottom: 10,
  },
  card: {
  },

  // Mode Selector
  modeSelector: {
    flexDirection: 'row',
    backgroundColor: '#0f172a',
    borderRadius: 8,
    padding: 4,
    marginBottom: 20,
  },
  modeOption: {
    flex: 1,
    paddingVertical: 10,
    alignItems: 'center',
    borderRadius: 6,
  },
  modeOptionActive: {
    backgroundColor: '#334155',
  },
  modeText: {
    color: '#64748b',
    fontWeight: '600',
    fontSize: 12,
  },
  modeTextActive: {
    color: '#fff',
  },

  // Inputs
  inputContainer: {
    flexDirection: 'row',
    alignItems: 'center',
    backgroundColor: '#0f172a',
    borderRadius: 8,
    borderWidth: 1,
    borderColor: '#334155',
    marginBottom: 12,
    paddingHorizontal: 12,
  },
  inputIcon: {
    marginRight: 10,
  },
  input: {
    flex: 1,
    color: '#fff',
    paddingVertical: 14,
    fontSize: 15,
  },

  // Grid
  gridContainer: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    marginHorizontal: -6,
    marginBottom: 12,
  },
  gridItem: {
    width: '50%',
    paddingHorizontal: 6,
    marginBottom: 12,
  },
  gridLabel: {
    color: '#94a3b8',
    fontSize: 12,
    marginBottom: 6,
    marginLeft: 4,
  },
  gridInput: {
    backgroundColor: '#0f172a',
    color: '#fff',
    padding: 12,
    borderRadius: 8,
    borderWidth: 1,
    borderColor: '#334155',
    textAlign: 'center',
  },

  // Settings
  settingRow: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    marginBottom: 16,
    paddingBottom: 16,
    borderBottomWidth: 1,
    borderBottomColor: '#334155',
  },
  settingLabel: {
    color: '#e2e8f0',
    fontSize: 14,
    fontWeight: '600',
  },
  settingSubLabel: {
    color: '#64748b',
    fontSize: 12,
    marginTop: 2,
  },
  smallInput: {
    backgroundColor: '#0f172a',
    color: '#fff',
    padding: 10,
    borderRadius: 8,
    width: 60,
    textAlign: 'center',
    borderWidth: 1,
    borderColor: '#334155',
  },

  // Main Button
  mainButton: {
    padding: 18,
    borderRadius: 16,
    flexDirection: 'row',
    justifyContent: 'center',
    alignItems: 'center',
    shadowColor: '#000',
    shadowOffset: { width: 0, height: 4 },
    shadowOpacity: 0.3,
    shadowRadius: 8,
    elevation: 6,
    marginBottom: 24,
  },
  startButton: {
    backgroundColor: '#3b82f6', // Blue
  },
  stopButton: {
    backgroundColor: '#ef4444', // Red
  },
  mainButtonText: {
    color: '#fff',
    fontWeight: '800',
    fontSize: 16,
    letterSpacing: 1,
    marginLeft: 8,
  },

  // Logs
  logsSection: {
    backgroundColor: '#0f172a',
    borderRadius: 16,
    padding: 16,
    borderWidth: 1,
    borderColor: '#334155',
    height: 300,
    marginBottom: 24,
    overflow: 'hidden', // Ensure content stays inside
  },
  logsHeader: {
    flexDirection: 'row',
    alignItems: 'center',
    marginBottom: 12,
  },
  logsTitle: {
    color: '#64748b',
    fontSize: 12,
    fontWeight: '700',
    marginLeft: 8,
    letterSpacing: 1,
  },
  logsConsole: {
    flex: 1,
  },
  logPlaceholder: {
    color: '#334155',
    fontStyle: 'italic',
    textAlign: 'center',
    marginTop: 40,
  },
  logLine: {
    marginBottom: 6,
    fontSize: 12,
  },
  logTimestamp: {
    color: '#64748b',
    fontFamily: Platform.OS === 'ios' ? 'Courier New' : 'monospace',
    marginRight: 8,
  },
  logContent: {
    color: '#cbd5e1',
    fontFamily: Platform.OS === 'ios' ? 'Courier New' : 'monospace',
  },

  // Signal Table
  signalTable: {
    marginTop: 8,
    flex: 1, // Take remaining space
  },
  signalHeaderRow: {
    flexDirection: 'row',
    paddingBottom: 8,
    borderBottomWidth: 1,
    borderBottomColor: '#334155',
    marginBottom: 8,
  },
  signalHeaderCell: {
    color: '#64748b',
    fontSize: 10,
    fontWeight: 'bold',
    textAlign: 'center',
  },
  signalRow: {
    flexDirection: 'row',
    paddingVertical: 8,
    borderBottomWidth: 1,
    borderBottomColor: '#1e293b', // darker separator
    alignItems: 'center',
  },
  signalCell: {
    fontSize: 12,
    textAlign: 'center',
  },
});
