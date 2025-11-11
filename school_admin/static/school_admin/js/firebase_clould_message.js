
  // Import the functions you need from the SDKs you need
  import { initializeApp } from "https://www.gstatic.com/firebasejs/12.5.0/firebase-app.js";
  import { getAnalytics } from "https://www.gstatic.com/firebasejs/12.5.0/firebase-analytics.js";
  // TODO: Add SDKs for Firebase products that you want to use
  // https://firebase.google.com/docs/web/setup#available-libraries

  // Your web app's Firebase configuration
  // For Firebase JS SDK v7.20.0 and later, measurementId is optional
  const firebaseConfig = {
    apiKey: "AIzaSyCSvm0VNdvnLqdIFPdDs4DPYDjHvDsO4_Q",
    authDomain: "gestion-scolaire-6945a.firebaseapp.com",
    projectId: "gestion-scolaire-6945a",
    storageBucket: "gestion-scolaire-6945a.firebasestorage.app",
    messagingSenderId: "983006440407",
    appId: "1:983006440407:web:8cbfc916f43b745a7e7992",
    measurementId: "G-1SHG5PC5T7"
  };

  // Initialize Firebase
  const app = initializeApp(firebaseConfig);
  const analytics = getAnalytics(app);