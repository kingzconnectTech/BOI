import { initializeApp } from 'firebase/app';
import { initializeAuth, getReactNativePersistence, getAuth } from 'firebase/auth';
import ReactNativeAsyncStorage from '@react-native-async-storage/async-storage';

// Configuration from your Service Account "boi-e8449"
// NOTE: You must provide the "apiKey" from Firebase Console -> Project Settings -> General
const firebaseConfig = {
  apiKey: "AIzaSyAnqL1H6jozpwB-ykhfYVQe2Ne3Sr_a2O4", 
   authDomain: "boi-e8449.firebaseapp.com",
  projectId: "boi-e8449",
  storageBucket: "boi-e8449.firebasestorage.app",
  messagingSenderId: "705703904910", 
  appId: "1:705703904910:web:cd0933cd2c8f825a2babdf" 
};

const app = initializeApp(firebaseConfig);

// Initialize Auth with persistence
const auth = initializeAuth(app, {
  persistence: getReactNativePersistence(ReactNativeAsyncStorage)
});

export { auth };
