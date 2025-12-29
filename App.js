import React, { useState, useEffect } from 'react';
import { StyleSheet, Text, View, TextInput, TouchableOpacity, ScrollView, Platform } from 'react-native';
import { StatusBar } from 'expo-status-bar';
import axios from 'axios';

// Backend URL - Use local IP for device testing, localhost for web/simulator
// For Android Emulator use 'http://10.0.2.2:8001'
// For iOS Simulator / Web use 'http://localhost:8001'
const API_URL = 'http://192.168.43.76:8001'; 
// NOTE: If you are running on a real device, change 'localhost' to your computer's IP address (e.g., http://192.168.1.5:8001)
 

export default function App() {
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [mode, setMode] = useState('PRACTICE'); // PRACTICE or REAL
  const [amount, setAmount] = useState('1');
  const [duration, setDuration] = useState('1');
  const [stopLoss, setStopLoss] = useState('10');
  const [takeProfit, setTakeProfit] = useState('20');
  const [stats, setStats] = useState({ profit: 0, wins: 0, losses: 0, win_rate: 0 });
  const [backendStatus, setBackendStatus] = useState('Checking...');
  const [logs, setLogs] = useState([]);
  const [isRunning, setIsRunning] = useState(false);

  useEffect(() => {
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
        amount: parseFloat(amount),
        duration: parseInt(duration),
        stop_loss: parseFloat(stopLoss),
        take_profit: parseFloat(takeProfit)
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

  return (
    <View style={styles.container}>
      <StatusBar style="light" />
      
      {/* Header */}
      <View style={styles.header}>
        <Text style={styles.title}>IQ Option Bot</Text>
        <View style={styles.statusContainer}>
          <View style={[styles.statusDot, { backgroundColor: backendStatus === 'Connected' ? '#4ade80' : '#ef4444' }]} />
          <Text style={styles.statusText}>{backendStatus}</Text>
        </View>
      </View>

      {/* Stats Board */}
      {isRunning && (
        <View style={styles.statsContainer}>
          <View style={styles.statBox}>
             <Text style={styles.statLabel}>Profit</Text>
             <Text style={[styles.statValue, { color: stats.profit >= 0 ? '#4ade80' : '#ef4444' }]}>
               ${stats.profit}
             </Text>
          </View>
          <View style={styles.statBox}>
             <Text style={styles.statLabel}>Win Rate</Text>
             <Text style={styles.statValue}>{stats.win_rate}%</Text>
          </View>
          <View style={styles.statBox}>
             <Text style={styles.statLabel}>W/L</Text>
             <Text style={styles.statValue}>{stats.wins}/{stats.losses}</Text>
          </View>
        </View>
      )}

      {/* Main Content */}
      <View style={styles.content}>
        <View style={styles.inputGroup}>
          <Text style={styles.label}>Email</Text>
          <TextInput
            style={styles.input}
            placeholder="email@example.com"
            placeholderTextColor="#666"
            value={email}
            onChangeText={setEmail}
            autoCapitalize="none"
            keyboardType="email-address"
          />
        </View>

        <View style={styles.inputGroup}>
          <Text style={styles.label}>Password</Text>
          <TextInput
            style={styles.input}
            placeholder="Password"
            placeholderTextColor="#666"
            value={password}
            onChangeText={setPassword}
            secureTextEntry
          />
        </View>

        <View style={styles.inputGroup}>
          <Text style={styles.label}>Account Mode</Text>
          <View style={styles.modeContainer}>
            <TouchableOpacity 
              style={[styles.modeButton, mode === 'PRACTICE' && styles.modeButtonActive]}
              onPress={() => setMode('PRACTICE')}
            >
              <Text style={[styles.modeText, mode === 'PRACTICE' && styles.modeTextActive]}>Demo</Text>
            </TouchableOpacity>
            <TouchableOpacity 
              style={[styles.modeButton, mode === 'REAL' && styles.modeButtonActive]}
              onPress={() => setMode('REAL')}
            >
              <Text style={[styles.modeText, mode === 'REAL' && styles.modeTextActive]}>Real</Text>
            </TouchableOpacity>
          </View>
        </View>

        <View style={styles.rowContainer}>
          <View style={[styles.inputGroup, { flex: 1, marginRight: 8 }]}>
            <Text style={styles.label}>Amount ($)</Text>
            <TextInput
              style={styles.input}
              placeholder="1"
              placeholderTextColor="#666"
              value={amount}
              onChangeText={setAmount}
              keyboardType="numeric"
            />
          </View>
          <View style={[styles.inputGroup, { flex: 1 }]}>
            <Text style={styles.label}>Time (min)</Text>
            <TextInput
              style={styles.input}
              placeholder="1"
              placeholderTextColor="#666"
              value={duration}
              onChangeText={setDuration}
              keyboardType="numeric"
            />
          </View>
        </View>

        <View style={styles.rowContainer}>
          <View style={[styles.inputGroup, { flex: 1, marginRight: 8 }]}>
            <Text style={styles.label}>Stop Loss ($)</Text>
            <TextInput
              style={styles.input}
              placeholder="10"
              placeholderTextColor="#666"
              value={stopLoss}
              onChangeText={setStopLoss}
              keyboardType="numeric"
            />
          </View>
          <View style={[styles.inputGroup, { flex: 1 }]}>
            <Text style={styles.label}>Take Profit ($)</Text>
            <TextInput
              style={styles.input}
              placeholder="20"
              placeholderTextColor="#666"
              value={takeProfit}
              onChangeText={setTakeProfit}
              keyboardType="numeric"
            />
          </View>
        </View>

        <TouchableOpacity 
          style={[styles.button, isRunning ? styles.stopButton : styles.startButton]}
          onPress={isRunning ? handleStop : handleStart}
        >
          <Text style={styles.buttonText}>
            {isRunning ? 'STOP BOT' : 'START BOT'}
          </Text>
        </TouchableOpacity>
      </View>

      {/* Logs Area */}
      <View style={styles.logsContainer}>
        <Text style={styles.logsTitle}>System Logs</Text>
        <ScrollView style={styles.logsScrollView}>
          {logs.map((log, index) => (
            <Text key={index} style={styles.logText}>{log}</Text>
          ))}
          {logs.length === 0 && (
            <Text style={styles.emptyLogText}>Waiting for activity...</Text>
          )}
        </ScrollView>
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: '#111827',
  },
  header: {
    paddingTop: 60,
    paddingBottom: 20,
    paddingHorizontal: 20,
    backgroundColor: '#1f2937',
    borderBottomWidth: 1,
    borderBottomColor: '#374151',
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
  },
  statsContainer: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    padding: 15,
    backgroundColor: '#1f2937',
    marginBottom: 10,
    marginHorizontal: 20,
    borderRadius: 8,
  },
  statBox: {
    alignItems: 'center',
  },
  statLabel: {
    color: '#9ca3af',
    fontSize: 12,
    marginBottom: 4,
  },
  statValue: {
    color: '#fff',
    fontSize: 18,
    fontWeight: 'bold',
  },
  title: {
    fontSize: 24,
    fontWeight: 'bold',
    color: '#fff',
  },
  statusContainer: {
    flexDirection: 'row',
    alignItems: 'center',
    backgroundColor: '#374151',
    paddingHorizontal: 12,
    paddingVertical: 6,
    borderRadius: 20,
  },
  statusDot: {
    width: 8,
    height: 8,
    borderRadius: 4,
    marginRight: 8,
  },
  statusText: {
    color: '#e5e7eb',
    fontSize: 12,
    fontWeight: '600',
  },
  content: {
    flex: 1,
    padding: 20,
  },
  rowContainer: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    marginBottom: 10,
  },
  inputGroup: {
    marginBottom: 20,
  },
  label: {
    color: '#9ca3af',
    marginBottom: 8,
    fontSize: 14,
    fontWeight: '500',
  },
  modeContainer: {
    flexDirection: 'row',
    backgroundColor: '#1f2937',
    borderRadius: 8,
    padding: 4,
    borderWidth: 1,
    borderColor: '#374151',
  },
  modeButton: {
    flex: 1,
    paddingVertical: 8,
    alignItems: 'center',
    borderRadius: 6,
  },
  modeButtonActive: {
    backgroundColor: '#2563eb',
  },
  modeText: {
    color: '#9ca3af',
    fontWeight: '600',
  },
  modeTextActive: {
    color: '#fff',
  },
  input: {
    backgroundColor: '#1f2937',
    borderRadius: 8,
    padding: 12,
    color: '#fff',
    borderWidth: 1,
    borderColor: '#374151',
    fontSize: 16,
  },
  button: {
    padding: 16,
    borderRadius: 8,
    alignItems: 'center',
    marginTop: 10,
  },
  startButton: {
    backgroundColor: '#2563eb',
  },
  stopButton: {
    backgroundColor: '#dc2626',
  },
  buttonText: {
    color: '#fff',
    fontSize: 16,
    fontWeight: 'bold',
  },
  logsContainer: {
    height: 200, // Fixed height for logs
    backgroundColor: '#000',
    margin: 20,
    marginTop: 0,
    borderRadius: 8,
    borderWidth: 1,
    borderColor: '#374151',
    overflow: 'hidden',
  },
  logsTitle: {
    color: '#9ca3af',
    fontSize: 12,
    fontWeight: '600',
    padding: 10,
    backgroundColor: '#1f2937',
  },
  logsScrollView: {
    flex: 1,
    padding: 10,
  },
  logText: {
    color: '#4ade80',
    fontFamily: Platform.OS === 'ios' ? 'Menlo' : 'monospace',
    fontSize: 12,
    marginBottom: 4,
  },
  emptyLogText: {
    color: '#4b5563',
    fontStyle: 'italic',
    textAlign: 'center',
    marginTop: 20,
  },
});
