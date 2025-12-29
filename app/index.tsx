import React, { useEffect, useRef, useState } from "react";
import {
    ActivityIndicator,
    Platform,
    ScrollView,
    StyleSheet,
    Switch,
    Text,
    TextInput,
    TouchableOpacity,
    View,
} from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";

// Determine API URL
// For Web: localhost is fine
// For Android Emulator: 10.0.2.2
// For Physical Device: Your PC IP
const API_URL = Platform.OS === "android" ? "http://10.0.2.2:8001" : "http://localhost:8001";

export default function Index() {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [mode, setMode] = useState("PRACTICE"); // PRACTICE or REAL
  const [logs, setLogs] = useState<string[]>([]);
  const [status, setStatus] = useState<any>(null);
  const [loading, setLoading] = useState(false);
  const scrollViewRef = useRef<ScrollView>(null);

  useEffect(() => {
    const interval = setInterval(fetchStatus, 1000);
    return () => clearInterval(interval);
  }, []);

  const fetchStatus = async () => {
    try {
      const res = await fetch(`${API_URL}/status`);
      if (res.ok) {
        const data = await res.json();
        setStatus(data);
        if (data.logs) {
          setLogs(data.logs);
        }
      }
    } catch (e) {
      // console.log("Connection error", e);
    }
  };

  const handleStart = async () => {
    if (!email || !password) {
      alert("Please enter email and password");
      return;
    }
    setLoading(true);
    try {
      const res = await fetch(`${API_URL}/start`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ email, password, mode }),
      });
      const data = await res.json();
      if (!res.ok) {
        alert("Error: " + (data.detail || "Failed to start"));
      }
    } catch (e) {
      alert("Network Error");
    } finally {
      setLoading(false);
    }
  };

  const handleStop = async () => {
    try {
      await fetch(`${API_URL}/stop`, { method: "POST" });
    } catch (e) {
      alert("Error stopping");
    }
  };

  return (
    <SafeAreaView style={styles.container}>
      <View style={styles.header}>
        <Text style={styles.title}>IQ Bot Auto-Trader</Text>
        <View style={styles.statusBadge}>
          <View
            style={[
              styles.dot,
              { backgroundColor: status?.connected ? "#4ade80" : "#ef4444" },
            ]}
          />
          <Text style={styles.statusText}>
            {status?.connected ? "Connected" : "Disconnected"}
          </Text>
        </View>
      </View>

      <ScrollView style={styles.content}>
        {/* Stats Card */}
        <View style={styles.card}>
          <View style={styles.row}>
            <View>
              <Text style={styles.label}>Balance</Text>
              <Text style={styles.value}>${status?.balance?.toFixed(2) || "0.00"}</Text>
            </View>
            <View>
              <Text style={styles.label}>Profit</Text>
              <Text
                style={[
                  styles.value,
                  { color: (status?.session_profit || 0) >= 0 ? "#4ade80" : "#ef4444" },
                ]}
              >
                ${status?.session_profit?.toFixed(2) || "0.00"}
              </Text>
            </View>
          </View>
        </View>

        {/* Login / Controls */}
        {!status?.running ? (
          <View style={styles.card}>
            <TextInput
              style={styles.input}
              placeholder="Email"
              placeholderTextColor="#64748b"
              value={email}
              onChangeText={setEmail}
              autoCapitalize="none"
            />
            <TextInput
              style={styles.input}
              placeholder="Password"
              placeholderTextColor="#64748b"
              value={password}
              onChangeText={setPassword}
              secureTextEntry
            />
            
            <View style={styles.modeRow}>
                <Text style={styles.label}>Mode: {mode}</Text>
                <Switch 
                    value={mode === "REAL"}
                    onValueChange={(v) => setMode(v ? "REAL" : "PRACTICE")}
                />
            </View>

            <TouchableOpacity
              style={[styles.button, styles.startButton]}
              onPress={handleStart}
              disabled={loading}
            >
              {loading ? (
                <ActivityIndicator color="white" />
              ) : (
                <Text style={styles.buttonText}>Start Bot</Text>
              )}
            </TouchableOpacity>
          </View>
        ) : (
          <View style={styles.card}>
            <Text style={styles.runningText}>Bot is Running...</Text>
            <TouchableOpacity
              style={[styles.button, styles.stopButton]}
              onPress={handleStop}
            >
              <Text style={styles.buttonText}>Stop Bot</Text>
            </TouchableOpacity>
          </View>
        )}

        {/* Logs */}
        <View style={[styles.card, styles.logsCard]}>
          <Text style={styles.label}>Logs</Text>
          <ScrollView
            style={styles.logsScroll}
            ref={scrollViewRef}
            onContentSizeChange={() =>
              scrollViewRef.current?.scrollToEnd({ animated: true })
            }
          >
            {logs.map((log, index) => (
              <Text key={index} style={styles.logText}>
                {log}
              </Text>
            ))}
            {logs.length === 0 && (
                <Text style={styles.logText}>Waiting for logs...</Text>
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
    backgroundColor: "#0f172a",
  },
  header: {
    padding: 20,
    flexDirection: "row",
    justifyContent: "space-between",
    alignItems: "center",
    borderBottomWidth: 1,
    borderBottomColor: "#1e293b",
  },
  title: {
    fontSize: 20,
    fontWeight: "bold",
    color: "white",
  },
  statusBadge: {
    flexDirection: "row",
    alignItems: "center",
    backgroundColor: "#1e293b",
    paddingHorizontal: 10,
    paddingVertical: 5,
    borderRadius: 20,
  },
  dot: {
    width: 8,
    height: 8,
    borderRadius: 4,
    marginRight: 6,
  },
  statusText: {
    color: "#94a3b8",
    fontSize: 12,
  },
  content: {
    flex: 1,
    padding: 20,
  },
  card: {
    backgroundColor: "#1e293b",
    borderRadius: 12,
    padding: 20,
    marginBottom: 20,
  },
  row: {
    flexDirection: "row",
    justifyContent: "space-around",
  },
  label: {
    color: "#94a3b8",
    fontSize: 14,
    marginBottom: 4,
  },
  value: {
    color: "white",
    fontSize: 24,
    fontWeight: "bold",
  },
  input: {
    backgroundColor: "#0f172a",
    color: "white",
    padding: 15,
    borderRadius: 8,
    marginBottom: 15,
    fontSize: 16,
  },
  button: {
    padding: 16,
    borderRadius: 8,
    alignItems: "center",
  },
  startButton: {
    backgroundColor: "#3b82f6",
  },
  stopButton: {
    backgroundColor: "#ef4444",
  },
  buttonText: {
    color: "white",
    fontWeight: "bold",
    fontSize: 16,
  },
  runningText: {
    color: "#4ade80",
    textAlign: "center",
    marginBottom: 15,
    fontSize: 16,
    fontWeight: "bold",
  },
  logsCard: {
    flex: 1,
    minHeight: 300,
  },
  logsScroll: {
    marginTop: 10,
    maxHeight: 250,
  },
  logText: {
    color: "#cbd5e1",
    fontSize: 12,
    marginBottom: 4,
    fontFamily: Platform.OS === "ios" ? "Courier" : "monospace",
  },
  modeRow: {
      flexDirection: 'row',
      justifyContent: 'space-between',
      alignItems: 'center',
      marginBottom: 15
  }
});
