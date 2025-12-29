import React, { useState, useEffect } from 'react';
import { StyleSheet, Text, View, TextInput, TouchableOpacity, ScrollView, Platform, Switch, SafeAreaView, Dimensions } from 'react-native';
import { StatusBar } from 'expo-status-bar';
import axios from 'axios';
import { MaterialCommunityIcons } from '@expo/vector-icons';
import * as Device from 'expo-device';
import * as Notifications from 'expo-notifications';
import Constants from 'expo-constants';

// Backend URL
const API_URL = 'https://boi-lgdy.onrender.com'; 
const { width } = Dimensions.get('window');

Notifications.setNotificationHandler({
  handleNotification: async () => ({
    shouldShowAlert: true,
    shouldPlaySound: true,
    shouldSetBadge: false,
  }),
});

export default function App() {
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [mode, setMode] = useState('PRACTICE'); // PRACTICE or REAL
  const [amount, setAmount] = useState('1');
  const [duration, setDuration] = useState('1');
  const [stopLoss, setStopLoss] = useState('10');
  const [takeProfit, setTakeProfit] = useState('20');
  const [maxConsecutiveLosses, setMaxConsecutiveLosses] = useState('2');
  const [maxTrades, setMaxTrades] = useState('0'); // 0 = unlimited
  const [autoTrading, setAutoTrading] = useState(true);
  const [stats, setStats] = useState({ profit: 0, wins: 0, losses: 0, win_rate: 0 });
  const [backendStatus, setBackendStatus] = useState('Checking...');
  const [logs, setLogs] = useState([]);
  const [isRunning, setIsRunning] = useState(false);
  const [expoPushToken, setExpoPushToken] = useState('');

  useEffect(() => {
    registerForPushNotificationsAsync().then(token => setExpoPushToken(token));
    checkBackend();
  }, []);

  // Poll for logs and stats when bot is running
  useEffect(() => {
    let interval;
    if (isRunning) {
      interval = setInterval(async () => {
        try {
          // Get Logs
          const logsResponse = await axios.get(`${API_URL}/logs`);
          if (logsResponse.data.logs && logsResponse.data.logs.length > 0) {
            setLogs(logsResponse.data.logs.reverse());
          }
          
          // Get Stats (Status)
          const statusResponse = await axios.get(`${API_URL}/status`);
          if (statusResponse.data.stats) {
            setStats(statusResponse.data.stats);
          }
        } catch (error) {
          console.log("Error fetching data:", error.message);
        }
      }, 2000);
    }
    return () => clearInterval(interval);
  }, [isRunning]);

  const addLog = (message) => {
    const timestamp = new Date().toLocaleTimeString();
    setLogs(prev => [`[${timestamp}] ${message}`, ...prev]);
  };

  const checkBackend = async () => {
    try {
      const response = await axios.get(API_URL);
      if (response.data.status === 'ok') {
        setBackendStatus('Connected');
        addLog('Backend connected successfully');
      }
    } catch (error) {
      setBackendStatus('Disconnected');
      addLog(`Backend connection failed: ${error.message}`);
    }
  };

  const handleStart = async () => {
    if (!email || !password) {
      addLog('Error: Please enter email and password');
      return;
    }
    
    setIsRunning(true);
    addLog('Connecting to IQ Option...');
    
    try {
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
        push_token: expoPushToken // Send push token
      });
      
      if (response.data.status === 'started') {
        addLog(`Success: ${response.data.message}`);
        addLog(`Balance: ${response.data.data.currency} ${response.data.data.balance}`);
      }
    } catch (error) {
      setIsRunning(false);
      const errorMsg = error.response?.data?.detail || error.message;
      addLog(`Error: ${errorMsg}`);
    }
  };

  const handleStop = async () => {
    try {
      addLog('Stopping bot...');
      const response = await axios.post(`${API_URL}/stop`);
      if (response.data.status === 'stopped') {
        setIsRunning(false);
        addLog('Bot stopped successfully');
      }
    } catch (error) {
      addLog(`Error stopping bot: ${error.message}`);
    }
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
      // Learn more about projectId:
      // https://docs.expo.dev/push-notifications/push-notifications-setup/#configure-projectid
      // For bare workflow:
      // token = (await Notifications.getExpoPushTokenAsync({ projectId: 'YOUR_PROJECT_ID' })).data;
      // For managed workflow (like this):
      try {
        const projectId = Constants?.expoConfig?.extra?.eas?.projectId ?? Constants?.easConfig?.projectId;
        if (!projectId) {
           // Fallback if projectId not found (development)
           token = (await Notifications.getExpoPushTokenAsync()).data;
        } else {
           token = (await Notifications.getExpoPushTokenAsync({ projectId })).data;
        }
      } catch (e) {
         token = (await Notifications.getExpoPushTokenAsync()).data;
      }
      console.log("Push Token:", token);
    } else {
      alert('Must use physical device for Push Notifications');
    }
  
    return token;
  }

  return (
    <SafeAreaView style={styles.container}>
      <StatusBar style="light" backgroundColor="#0f172a" />
      
      {/* Header */}
      <View style={styles.header}>
        <View>
          <Text style={styles.headerTitle}>QUANTUM<Text style={styles.headerTitleAccent}>BOT</Text></Text>
          <Text style={styles.headerSubtitle}>IQ Option Automated Trader</Text>
        </View>
        <View style={styles.statusBadge}>
          <View style={[styles.statusDot, { backgroundColor: backendStatus === 'Connected' ? '#10b981' : '#ef4444' }]} />
          <Text style={styles.statusText}>{backendStatus === 'Connected' ? 'ONLINE' : 'OFFLINE'}</Text>
        </View>
      </View>

      <ScrollView style={styles.mainScrollView} contentContainerStyle={styles.scrollContent}>
        
        {/* Stats Dashboard */}
        <View style={styles.dashboardContainer}>
          <View style={styles.statCard}>
            <MaterialCommunityIcons name="finance" size={24} color="#10b981" />
            <Text style={styles.statLabel}>Profit</Text>
            <Text style={[styles.statValue, { color: stats.profit >= 0 ? '#10b981' : '#ef4444' }]}>
              ${stats.profit}
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
          <Text style={styles.sectionTitle}>CONFIGURATION</Text>
          
          {/* Account Mode */}
          <View style={styles.modeSelector}>
            <TouchableOpacity 
              style={[styles.modeOption, mode === 'PRACTICE' && styles.modeOptionActive]}
              onPress={() => setMode('PRACTICE')}
            >
              <Text style={[styles.modeText, mode === 'PRACTICE' && styles.modeTextActive]}>DEMO ACCOUNT</Text>
            </TouchableOpacity>
            <TouchableOpacity 
              style={[styles.modeOption, mode === 'REAL' && styles.modeOptionActive]}
              onPress={() => setMode('REAL')}
            >
              <Text style={[styles.modeText, mode === 'REAL' && styles.modeTextActive]}>REAL ACCOUNT</Text>
            </TouchableOpacity>
          </View>

          {/* Credentials */}
          <View style={styles.inputContainer}>
            <MaterialCommunityIcons name="email-outline" size={20} color="#94a3b8" style={styles.inputIcon} />
            <TextInput
              style={styles.input}
              placeholder="Email Address"
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
              placeholder="Password"
              placeholderTextColor="#64748b"
              value={password}
              onChangeText={setPassword}
              secureTextEntry
            />
          </View>

          {/* Trading Settings Grid */}
          <View style={styles.gridContainer}>
            <View style={styles.gridItem}>
              <Text style={styles.gridLabel}>Amount ($)</Text>
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
              <Text style={styles.gridLabel}>Stop Loss ($)</Text>
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
              <Text style={styles.gridLabel}>Take Profit ($)</Text>
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
                <Text style={styles.settingSubLabel}>{autoTrading ? 'Active Trading' : 'Signal Mode Only'}</Text>
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
          onPress={isRunning ? handleStop : handleStart}
          activeOpacity={0.8}
        >
          <MaterialCommunityIcons name={isRunning ? "stop-circle-outline" : "play-circle-outline"} size={28} color="#fff" />
          <Text style={styles.mainButtonText}>
            {isRunning ? 'TERMINATE SESSION' : 'INITIATE TRADING'}
          </Text>
        </TouchableOpacity>

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
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: '#0f172a', // Slate 900
    paddingTop: Platform.OS === 'android' ? 40 : 0,
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
  dashboardContainer: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    marginBottom: 24,
  },
  statCard: {
    flex: 1,
    backgroundColor: '#1e293b', // Slate 800
    padding: 12,
    borderRadius: 12,
    marginHorizontal: 4,
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
    backgroundColor: '#1e293b',
    borderRadius: 16,
    padding: 20,
    marginBottom: 24,
    borderWidth: 1,
    borderColor: '#334155',
  },
  sectionTitle: {
    color: '#64748b',
    fontSize: 12,
    fontWeight: '700',
    marginBottom: 16,
    letterSpacing: 1,
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
    fontSize: 16,
    fontWeight: '600',
  },

  // Settings Row
  settingRow: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    paddingVertical: 12,
    borderTopWidth: 1,
    borderTopColor: '#334155',
  },
  settingLabel: {
    color: '#e2e8f0',
    fontSize: 15,
    fontWeight: '500',
  },
  settingSubLabel: {
    color: '#64748b',
    fontSize: 12,
    marginTop: 2,
  },
  smallInput: {
    backgroundColor: '#0f172a',
    color: '#fff',
    paddingVertical: 8,
    paddingHorizontal: 16,
    borderRadius: 6,
    borderWidth: 1,
    borderColor: '#334155',
    textAlign: 'center',
    width: 60,
  },

  // Buttons
  mainButton: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    padding: 18,
    borderRadius: 16,
    marginBottom: 24,
    shadowColor: '#3b82f6',
    shadowOffset: { width: 0, height: 4 },
    shadowOpacity: 0.3,
    shadowRadius: 8,
    elevation: 4,
  },
  startButton: {
    backgroundColor: '#2563eb', // Blue 600
  },
  stopButton: {
    backgroundColor: '#dc2626', // Red 600
    shadowColor: '#dc2626',
  },
  mainButtonText: {
    color: '#fff',
    fontSize: 16,
    fontWeight: 'bold',
    marginLeft: 10,
    letterSpacing: 1,
  },

  // Logs
  logsSection: {
    backgroundColor: '#000',
    borderRadius: 12,
    borderWidth: 1,
    borderColor: '#334155',
    overflow: 'hidden',
  },
  logsHeader: {
    flexDirection: 'row',
    alignItems: 'center',
    padding: 12,
    backgroundColor: '#1e293b',
    borderBottomWidth: 1,
    borderBottomColor: '#334155',
  },
  logsTitle: {
    color: '#94a3b8',
    fontSize: 11,
    fontWeight: '700',
    marginLeft: 8,
  },
  logsConsole: {
    height: 180,
    padding: 12,
  },
  logLine: {
    marginBottom: 4,
  },
  logTimestamp: {
    color: '#64748b',
    fontFamily: Platform.OS === 'ios' ? 'Menlo' : 'monospace',
    fontSize: 11,
  },
  logContent: {
    color: '#4ade80', // Green 400
    fontFamily: Platform.OS === 'ios' ? 'Menlo' : 'monospace',
    fontSize: 11,
  },
  logPlaceholder: {
    color: '#334155',
    textAlign: 'center',
    marginTop: 60,
    fontStyle: 'italic',
  },
});
