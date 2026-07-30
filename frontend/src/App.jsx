import React, { useState, useEffect, useRef } from 'react';

const API_BASE = "http://127.0.0.1:8000/api/v1";

function App() {
  // Auth state
  const [token, setToken] = useState(localStorage.getItem('token') || '');
  const [sessionId, setSessionId] = useState(localStorage.getItem('sessionId') || '');
  const [username, setUsername] = useState(localStorage.getItem('username') || '');
  const [authLevel, setAuthLevel] = useState(parseInt(localStorage.getItem('authLevel')) || 0);

  // Form states
  const [loginUser, setLoginUser] = useState('admin');
  const [loginPass, setLoginPass] = useState('admin123');
  const [regUser, setRegUser] = useState('');
  const [regPass, setRegPass] = useState('');
  const [regPin, setRegPin] = useState('');
  const [isRegistering, setIsRegistering] = useState(false);
  const [pinInput, setPinInput] = useState('');
  const [vaultPassword, setVaultPassword] = useState('');

  // UI state
  const [errorMsg, setErrorMsg] = useState('');
  const [infoMsg, setInfoMsg] = useState('');
  const [commands, setCommands] = useState([]);
  const [userInput, setUserInput] = useState('');
  const [auditLogs, setAuditLogs] = useState([]);
  const [isLoading, setIsLoading] = useState(false);
  
  // Simulated Biometrics & JARVIS HUD States
  const [isVoiceRecording, setIsVoiceRecording] = useState(false);
  const [isFaceScanning, setIsFaceScanning] = useState(false);
  const [faceMatchProgress, setFaceMatchProgress] = useState(0);
  const [speechSynthesisEnabled, setSpeechSynthesisEnabled] = useState(true);

  // Wake-word & Arc Reactor Core States
  const [isWakeWordListening, setIsWakeWordListening] = useState(true);
  const [wakeWordStatus, setWakeWordStatus] = useState("SAY 'HEY JARVIS' OR CLICK CORE TO ACTIVATE");
  const [arcState, setArcState] = useState("idle"); // idle, listening, thinking, speaking

  const consoleEndRef = useRef(null);
  const videoRef = useRef(null);
  const mediaStreamRef = useRef(null);
  const wakeWordRecognitionRef = useRef(null);

  // Poll audit logs and check session status
  useEffect(() => {
    fetchAuditLogs();
    const interval = setInterval(fetchAuditLogs, 3000);
    return () => clearInterval(interval);
  }, []);

  useEffect(() => {
    if (sessionId) {
      checkSessionStatus(sessionId);
    }
  }, [sessionId]);

  const fetchAuditLogs = async () => {
    try {
      const res = await fetch(`${API_BASE}/logs/audit`);
      if (res.ok) {
        const data = await res.json();
        setAuditLogs(data);
      }
    } catch (err) {
      console.error("Failed to fetch audit logs", err);
    }
  };

  const checkSessionStatus = async (sId) => {
    try {
      const res = await fetch(`${API_BASE}/auth/session/${sId}`);
      if (res.ok) {
        const data = await res.json();
        setAuthLevel(data.auth_level);
        localStorage.setItem('authLevel', data.auth_level);
      } else {
        // Session expired or invalid
        handleLogout();
      }
    } catch (err) {
      console.error("Error validating session status", err);
    }
  };

  const handleLogin = async (e) => {
    e.preventDefault();
    setErrorMsg('');
    setInfoMsg('');
    setIsLoading(true);
    try {
      const res = await fetch(`${API_BASE}/auth/login`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ username: loginUser, password: loginPass })
      });
      const data = await res.json();
      if (res.ok) {
        setToken(data.access_token);
        setSessionId(data.session_id);
        setAuthLevel(data.auth_level);
        setUsername(loginUser);
        localStorage.setItem('token', data.access_token);
        localStorage.setItem('sessionId', data.session_id);
        localStorage.setItem('authLevel', data.auth_level.toString());
        localStorage.setItem('username', loginUser);
        setInfoMsg("Authentication successful. Session initialized.");
        // Add initial greeting from JARVIS
        setCommands([{
          prompt: "[Session Initialized]",
          response: `Greetings Agent. I am JARVIS. Security clearances are set to Level 0 (Public). 
          Please complete biometrics to elevate privileges. Use "admin123" and PIN "1234" for default verification.`,
          status: "SUCCESS"
        }]);
      } else {
        setErrorMsg(data.detail || "Login failed");
      }
    } catch (err) {
      setErrorMsg("Cannot connect to backend server.");
    } finally {
      setIsLoading(false);
      fetchAuditLogs();
    }
  };

  const handleRegister = async (e) => {
    e.preventDefault();
    setErrorMsg('');
    setInfoMsg('');
    setIsLoading(true);
    try {
      const res = await fetch(`${API_BASE}/auth/register`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ username: regUser, password: regPass, pin: regPin })
      });
      const data = await res.json();
      if (res.ok) {
        setInfoMsg("User registered successfully! You can now log in.");
        setIsRegistering(false);
        setLoginUser(regUser);
        setLoginPass('');
      } else {
        setErrorMsg(data.detail || "Registration failed");
      }
    } catch (err) {
      setErrorMsg("Failed to connect to backend server.");
    } finally {
      setIsLoading(false);
      fetchAuditLogs();
    }
  };

  const handleLogout = () => {
    setToken('');
    setSessionId('');
    setAuthLevel(0);
    setUsername('');
    localStorage.clear();
    setCommands([]);
  };

  // Submit Text Command
  const handleSubmitCommand = async (e) => {
    e.preventDefault();
    if (!userInput.trim()) return;

    const userPrompt = userInput;
    setUserInput('');
    setIsLoading(true);
    setErrorMsg('');

    try {
      const res = await fetch(`${API_BASE}/commands/execute`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ session_id: sessionId, prompt: userPrompt })
      });
      const data = await res.json();
      
      setCommands(prev => [...prev, {
        prompt: userPrompt,
        response: data.response,
        status: data.status,
        requiredLevel: data.required_level
      }]);
    } catch (err) {
      setErrorMsg("Command execution error.");
    } finally {
      setIsLoading(false);
      fetchAuditLogs();
    }
  };

  // Simulated Voice Authentication (Level 1 Elevation)
  const triggerVoiceVerification = async () => {
    setIsVoiceRecording(true);
    setInfoMsg("Recording voice sample...");
    
    // Simulate recording voice for 3 seconds
    setTimeout(async () => {
      setIsVoiceRecording(false);
      try {
        const formData = new FormData();
        formData.append("session_id", sessionId);
        // Create dummy blob for audio file
        const blob = new Blob([new Uint8Array([1, 2, 3, 4, 5])], { type: 'audio/wav' });
        formData.append("file", blob, "voice_auth.wav");

        const res = await fetch(`${API_BASE}/auth/verify-voice`, {
          method: 'POST',
          body: formData
        });
        const data = await res.json();
        if (res.ok) {
          setAuthLevel(data.auth_level);
          localStorage.setItem('authLevel', data.auth_level.toString());
          setInfoMsg("Voice authentication verified! Level 1 unlocked.");
        } else {
          setErrorMsg(data.detail || "Voice match failed.");
        }
      } catch (err) {
        setErrorMsg("Failed to upload voice data.");
      } finally {
        fetchAuditLogs();
      }
    }, 2500);
  };

  // Submit PIN for Level 2 Elevation
  const submitPin = async () => {
    if (!pinInput) return;
    setIsLoading(true);
    setErrorMsg('');
    try {
      const res = await fetch(`${API_BASE}/auth/verify-pin`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ session_id: sessionId, pin: pinInput })
      });
      const data = await res.json();
      if (res.ok) {
        setAuthLevel(data.auth_level);
        localStorage.setItem('authLevel', data.auth_level.toString());
        setInfoMsg("PIN correct. Level 2 (Advanced) unlocked.");
        setPinInput('');
      } else {
        setErrorMsg(data.detail || "Invalid PIN.");
      }
    } catch (err) {
      setErrorMsg("Failed to verify PIN.");
    } finally {
      setIsLoading(false);
      fetchAuditLogs();
    }
  };

  // Helper for JARVIS audio voice output
  const speakResponse = (text, onEndCallback) => {
    if (!speechSynthesisEnabled || !('speechSynthesis' in window)) {
      if (onEndCallback) onEndCallback();
      return;
    }
    try {
      window.speechSynthesis.cancel();
      const utterance = new SpeechSynthesisUtterance(text);
      utterance.rate = 1.0;
      utterance.pitch = 0.9;
      if (onEndCallback) {
        utterance.onend = onEndCallback;
      }
      window.speechSynthesis.speak(utterance);
    } catch (e) {
      console.warn("Speech synthesis unavailable", e);
      if (onEndCallback) onEndCallback();
    }
  };

  // Continuous Wake-Word Background Listener ("Hey JARVIS" / "JARVIS")
  useEffect(() => {
    if (!token || !isWakeWordListening) return;

    const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
    if (!SpeechRecognition) return;

    let restartTimer = null;
    let recognition = null;

    const startRecognition = () => {
      try {
        if (recognition) {
          try { recognition.abort(); } catch (e) {}
        }

        recognition = new SpeechRecognition();
        recognition.continuous = true;
        recognition.interimResults = true;
        recognition.lang = 'en-US';
        wakeWordRecognitionRef.current = recognition;

        recognition.onresult = (event) => {
          const transcript = Array.from(event.results)
            .map(result => result[0].transcript.toLowerCase())
            .join(' ');

          // Match 'jarvis', 'hey jarvis', 'hello jarvis', and common STT phonetic variations
          const wakeWordRegex = /\b(jarvis|hey jarvis|hello jarvis|hi jarvis|javis|travis)\b/i;

          if (wakeWordRegex.test(transcript)) {
            try {
              recognition.stop();
            } catch (e) {}
            setIsWakeWordListening(false);
            triggerAutomatedVoiceFlow();
          }
        };

        recognition.onerror = (err) => {
          // Restart on error if still listening
          if (err.error !== 'aborted' && isWakeWordListening) {
            clearTimeout(restartTimer);
            restartTimer = setTimeout(startRecognition, 1000);
          }
        };

        recognition.onend = () => {
          // Keepalive loop: Auto-restart wake word listener if still enabled
          if (isWakeWordListening) {
            clearTimeout(restartTimer);
            restartTimer = setTimeout(startRecognition, 500);
          }
        };

        recognition.start();
      } catch (err) {
        if (isWakeWordListening) {
          clearTimeout(restartTimer);
          restartTimer = setTimeout(startRecognition, 2000);
        }
      }
    };

    startRecognition();

    return () => {
      clearTimeout(restartTimer);
      if (wakeWordRecognitionRef.current) {
        try {
          wakeWordRecognitionRef.current.abort();
        } catch (e) {}
      }
    };
  }, [token, isWakeWordListening]);

  // AUTOMATED PIPELINE: Wake-Word -> Face ID -> Voice Prompt -> Gemini Execution -> TTS Output
  const triggerAutomatedVoiceFlow = async () => {
    setArcState("thinking");
    setWakeWordStatus("WAKE WORD RECOGNIZED: VERIFYING BIOMETRICS...");
    setInfoMsg("Wake phrase detected! Initializing facial scanner...");

    speakResponse("Wake phrase recognized. Verifying biometric identity...", async () => {
      // Step 1: Run Face Verification
      await triggerFaceVerification(async (success) => {
        if (!success) {
          setArcState("idle");
          setWakeWordStatus("BIOMETRIC SCAN FAILED");
          setIsWakeWordListening(true);
          return;
        }

        // Step 2: Face Verified, start voice command capture
        setArcState("listening");
        setWakeWordStatus("FACE VERIFIED (LEVEL 3 ADMIN). LISTENING FOR COMMAND...");
        setInfoMsg("Face biometrics match 98.4%! Listening for your prompt...");
        
        speakResponse("Biometrics confirmed. Clearance Level 3 active. State your command, Agent.", () => {
          startLiveVoiceInput(true); // autoExecute = true
        });
      });
    });
  };

  // Real Browser Speech Recognition for Voice Commands
  const startLiveVoiceInput = (autoExecute = false) => {
    const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
    if (!SpeechRecognition) {
      triggerVoiceCommandSimulate('general');
      return;
    }

    try {
      const recognition = new SpeechRecognition();
      recognition.continuous = false;
      recognition.interimResults = true;
      recognition.lang = 'en-US';

      setIsVoiceRecording(true);
      setArcState("listening");
      setInfoMsg("Listening to command...");

      let finalCapturedText = "";

      recognition.onresult = (event) => {
        const transcript = Array.from(event.results)
          .map(result => result[0].transcript)
          .join('');
        setUserInput(transcript);
        finalCapturedText = transcript;
      };

      recognition.onerror = () => {
        setIsVoiceRecording(false);
        setArcState("idle");
        setWakeWordStatus("VOICE INPUT CANCELED");
        setIsWakeWordListening(true);
      };

      recognition.onend = async () => {
        setIsVoiceRecording(false);
        if (autoExecute && finalCapturedText.trim()) {
          executeCommandDirect(finalCapturedText);
        } else {
          setArcState("idle");
          setWakeWordStatus("COMMAND CAPTURED. SAY 'HEY JARVIS' TO START AGAIN");
          setIsWakeWordListening(true);
        }
      };

      recognition.start();
    } catch (err) {
      setIsVoiceRecording(false);
      setArcState("idle");
      setIsWakeWordListening(true);
    }
  };

  // Direct Execution helper for Automated Pipeline
  const executeCommandDirect = async (promptText) => {
    setUserInput('');
    setIsLoading(true);
    setArcState("thinking");
    setWakeWordStatus("PROCESSING COMMAND WITH GEMINI AI...");

    try {
      const res = await fetch(`${API_BASE}/commands/execute`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ session_id: sessionId, prompt: promptText })
      });
      const data = await res.json();
      
      setCommands(prev => [...prev, {
        prompt: promptText,
        response: data.response,
        status: data.status,
        requiredLevel: data.required_level
      }]);

      setArcState("speaking");
      setWakeWordStatus("JARVIS RESPONDING...");
      speakResponse(data.response, () => {
        setArcState("idle");
        setWakeWordStatus("SAY 'HEY JARVIS' OR CLICK CORE TO ACTIVATE");
        setIsWakeWordListening(true);
      });
    } catch (err) {
      setErrorMsg("Command execution error.");
      setArcState("idle");
      setIsWakeWordListening(true);
    } finally {
      setIsLoading(false);
      fetchAuditLogs();
    }
  };

  // Facial Recognition with callback
  const triggerFaceVerification = async (callback) => {
    setIsFaceScanning(true);
    setFaceMatchProgress(10);
    setInfoMsg("Initializing biometric camera feed...");

    try {
      if (navigator.mediaDevices && navigator.mediaDevices.getUserMedia) {
        const stream = await navigator.mediaDevices.getUserMedia({ video: true });
        mediaStreamRef.current = stream;
        if (videoRef.current) {
          videoRef.current.srcObject = stream;
        }
      }
    } catch (err) {
      console.log("Webcam access restricted, using cyber scanner fallback.", err);
    }

    const interval = setInterval(() => {
      setFaceMatchProgress(prev => Math.min(prev + 22, 98));
    }, 400);

    setTimeout(async () => {
      clearInterval(interval);
      if (mediaStreamRef.current) {
        mediaStreamRef.current.getTracks().forEach(track => track.stop());
        mediaStreamRef.current = null;
      }
      setIsFaceScanning(false);
      setFaceMatchProgress(0);

      try {
        const formData = new FormData();
        formData.append("session_id", sessionId);
        const blob = new Blob([new Uint8Array([5, 4, 3, 2, 1])], { type: 'image/jpeg' });
        formData.append("file", blob, "face_capture.jpg");

        const res = await fetch(`${API_BASE}/auth/verify-face`, {
          method: 'POST',
          body: formData
        });
        const data = await res.json();
        if (res.ok) {
          setAuthLevel(data.auth_level);
          localStorage.setItem('authLevel', data.auth_level.toString());
          setInfoMsg("Face authentication match: 98.4% similarity. Level 3 Admin granted.");
          if (callback) callback(true);
        } else {
          setErrorMsg(data.detail || "Face recognition verification failed.");
          if (callback) callback(false);
        }
      } catch (err) {
        setErrorMsg("Failed to verify facial markers.");
        if (callback) callback(false);
      } finally {
        fetchAuditLogs();
      }
    }, 2800);
  };

  // Submit Vault Password for Level 4 Elevation
  const submitVaultPassword = async () => {
    if (!vaultPassword) return;
    setIsLoading(true);
    setErrorMsg('');
    try {
      const res = await fetch(`${API_BASE}/auth/verify-vault`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ session_id: sessionId, password: vaultPassword })
      });
      const data = await res.json();
      if (res.ok) {
        setAuthLevel(data.auth_level);
        localStorage.setItem('authLevel', data.auth_level.toString());
        setInfoMsg("Vault decrypted successfully! Level 4 clearance granted.");
        setVaultPassword('');
      } else {
        setErrorMsg(data.detail || "Incorrect Vault Master Password.");
      }
    } catch (err) {
      setErrorMsg("Vault validation failed.");
    } finally {
      setIsLoading(false);
      fetchAuditLogs();
    }
  };

  // Simulated Voice Command triggers
  const triggerVoiceCommandSimulate = async (type) => {
    setIsVoiceRecording(true);
    setInfoMsg(`Recording command voice note...`);
    
    setTimeout(async () => {
      setIsVoiceRecording(false);
      try {
        const formData = new FormData();
        formData.append("session_id", sessionId);
        const blob = new Blob([new Uint8Array([9, 9, 9])], { type: 'audio/wav' });
        
        let filename = "general.wav";
        if (type === 'vault') filename = "vault_secrets.wav";
        if (type === 'delete') filename = "delete_file.wav";
        if (type === 'read') filename = "read_file.wav";
        
        formData.append("file", blob, filename);

        const res = await fetch(`${API_BASE}/commands/execute-voice`, {
          method: 'POST',
          body: formData
        });
        const data = await res.json();
        
        setCommands(prev => [...prev, {
          prompt: `[Simulated Voice Input: ${filename}]`,
          response: data.response,
          status: data.status,
          requiredLevel: data.required_level
        }]);
      } catch (err) {
        setErrorMsg("Failed to execute voice command.");
      } finally {
        fetchAuditLogs();
      }
    }, 2000);
  };

  // Scroll terminal logs to bottom when they update
  useEffect(() => {
    if (consoleEndRef.current) {
      consoleEndRef.current.scrollIntoView({ behavior: 'smooth' });
    }
  }, [auditLogs, commands]);

  // Auth screen layout
  if (!token) {
    return (
      <div style={{ display: 'flex', minHeight: '100vh', justifyContent: 'center', alignItems: 'center', padding: '20px' }}>
        <div className="glass-panel" style={{ width: '420px', padding: '30px' }}>
          <div style={{ textAlign: 'center', marginBottom: '24px' }}>
            <div className="logo-dot" style={{ margin: '0 auto 12px' }}></div>
            <h1 className="app-title">PROJECT AEGIS</h1>
            <p style={{ color: 'var(--text-secondary)', fontSize: '14px', margin: '4px 0' }}>Secure Personal AI Operating System</p>
          </div>

          {errorMsg && (
            <div style={{ backgroundColor: 'rgba(239, 108, 108, 0.1)', color: 'var(--accent-red)', padding: '12px', borderRadius: '8px', fontSize: '14px', marginBottom: '16px', border: '1px solid rgba(239, 108, 108, 0.2)' }}>
              {errorMsg}
            </div>
          )}

          {isRegistering ? (
            <form onSubmit={handleRegister}>
              <div style={{ marginBottom: '16px' }}>
                <label style={{ display: 'block', marginBottom: '6px', fontSize: '14px', color: 'var(--text-secondary)' }}>Username</label>
                <input className="input-field" type="text" value={regUser} onChange={e => setRegUser(e.target.value)} required placeholder="e.g. jarvis_agent" />
              </div>
              <div style={{ marginBottom: '16px' }}>
                <label style={{ display: 'block', marginBottom: '6px', fontSize: '14px', color: 'var(--text-secondary)' }}>Master Password</label>
                <input className="input-field" type="password" value={regPass} onChange={e => setRegPass(e.target.value)} required placeholder="Master access key" />
              </div>
              <div style={{ marginBottom: '20px' }}>
                <label style={{ display: 'block', marginBottom: '6px', fontSize: '14px', color: 'var(--text-secondary)' }}>Security PIN (Level 2)</label>
                <input className="input-field" type="text" value={regPin} onChange={e => setRegPin(e.target.value)} required placeholder="4 digit code (e.g. 1234)" maxLength={6} minLength={4} />
              </div>
              <button className="btn" type="submit" disabled={isLoading} style={{ width: '100%', marginBottom: '12px' }}>
                {isLoading ? 'Registering...' : 'REGISTER AGENT'}
              </button>
              <button className="btn btn-secondary" type="button" onClick={() => setIsRegistering(false)} style={{ width: '100%' }}>
                BACK TO LOGIN
              </button>
            </form>
          ) : (
            <form onSubmit={handleLogin}>
              <div style={{ marginBottom: '16px' }}>
                <label style={{ display: 'block', marginBottom: '6px', fontSize: '14px', color: 'var(--text-secondary)' }}>Username</label>
                <input className="input-field" type="text" value={loginUser} onChange={e => setLoginUser(e.target.value)} required />
              </div>
              <div style={{ marginBottom: '24px' }}>
                <label style={{ display: 'block', marginBottom: '6px', fontSize: '14px', color: 'var(--text-secondary)' }}>Password</label>
                <input className="input-field" type="password" value={loginPass} onChange={e => setLoginPass(e.target.value)} required />
              </div>
              <button className="btn" type="submit" disabled={isLoading} style={{ width: '100%', marginBottom: '12px' }}>
                {isLoading ? 'Authenticating...' : 'INITIALIZE SYSTEM'}
              </button>
              <button className="btn btn-secondary" type="button" onClick={() => setIsRegistering(true)} style={{ width: '100%' }}>
                REGISTER NEW USER
              </button>
            </form>
          )}
        </div>
      </div>
    );
  }

  // Dashboard layout
  return (
    <div className="app-container">
      {/* Top Header */}
      <header className="glass-panel app-header">
        <div className="logo-container">
          <div className="logo-dot"></div>
          <div>
            <h1 className="app-title">PROJECT AEGIS</h1>
            <span style={{ fontSize: '11px', color: 'var(--text-secondary)' }}>ASSISTANT CODED AS: <strong>JARVIS v1.0</strong></span>
          </div>
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: '16px', fontSize: '14px' }}>
          <div style={{ textAlign: 'right' }}>
            <div>USER: <span className="glow-text-cyan"><strong>{username}</strong></span></div>
            <div style={{ fontSize: '11px', color: 'var(--text-muted)' }}>Session: {sessionId.substring(0, 8)}...</div>
          </div>
          <button className="btn btn-secondary" style={{ padding: '6px 12px', fontSize: '12px' }} onClick={handleLogout}>
            TERMINATE
          </button>
        </div>
      </header>

      {/* Main Grid: Left Auth, Right Controls */}
      <main className="dashboard-grid">
        
        {/* Left Side: Security Gateway Dashboard */}
        <section className="glass-panel" style={{ display: 'flex', flexDirection: 'column' }}>
          <div className="panel-header">
            <h2 className="panel-title">
              <span className="logo-dot" style={{ display: 'inline-block', width: '8px', height: '8px' }}></span>
              Security Gateway
            </h2>
            <span style={{ fontSize: '12px', padding: '2px 8px', borderRadius: '20px', background: 'rgba(0, 242, 254, 0.1)', color: 'var(--accent-cyan)', border: '1px solid rgba(0, 242, 254, 0.3)' }}>
              Clearance: L{authLevel}
            </span>
          </div>

          <div style={{ padding: '20px', flex: 1, overflowY: 'auto' }}>
            
            {/* Display message status */}
            {infoMsg && (
              <div style={{ backgroundColor: 'rgba(16, 185, 129, 0.1)', color: 'var(--accent-green)', padding: '10px', borderRadius: '8px', fontSize: '13px', marginBottom: '16px', border: '1px solid rgba(16, 185, 129, 0.2)' }}>
                {infoMsg}
              </div>
            )}
            
            {/* Level 0: Public */}
            <div className={`security-level-item ${authLevel >= 0 ? 'unlocked' : 'locked'}`}>
              <div>
                <strong>Level 0: Public</strong>
                <div style={{ fontSize: '11px', color: 'var(--text-secondary)' }}>General conversation / Web search</div>
              </div>
              <span className="glow-text-green">✔ UNLOCKED</span>
            </div>

            {/* Level 1: Standard (Voice Match) */}
            <div className={`security-level-item ${authLevel === 1 ? 'active' : authLevel > 1 ? 'unlocked' : 'locked'}`}>
              <div style={{ flex: 1 }}>
                <strong>Level 1: Standard</strong>
                <div style={{ fontSize: '11px', color: 'var(--text-secondary)' }}>Read files & draft emails</div>
                {authLevel === 0 && (
                  <div style={{ marginTop: '8px' }}>
                    {isVoiceRecording ? (
                      <div className="wave-container" style={{ margin: '4px 0' }}>
                        <div className="wave-bar"></div>
                        <div className="wave-bar"></div>
                        <div className="wave-bar"></div>
                        <div className="wave-bar"></div>
                        <div className="wave-bar"></div>
                      </div>
                    ) : (
                      <button className="btn" onClick={triggerVoiceVerification} style={{ width: '100%', fontSize: '12px', padding: '6px 12px' }}>
                        🎙 START VOICE VERIFICATION
                      </button>
                    )}
                  </div>
                )}
              </div>
              <div>
                {authLevel >= 1 ? (
                  <span className="glow-text-green">✔ UNLOCKED</span>
                ) : (
                  <span className="glow-text-purple">🔒 LOCKED</span>
                )}
              </div>
            </div>

            {/* Level 2: Advanced (Voice + PIN) */}
            <div className={`security-level-item ${authLevel === 2 ? 'active' : authLevel > 2 ? 'unlocked' : 'locked'}`}>
              <div style={{ flex: 1 }}>
                <strong>Level 2: Advanced</strong>
                <div style={{ fontSize: '11px', color: 'var(--text-secondary)' }}>Write local files & run custom scripts</div>
                {authLevel === 1 && (
                  <div style={{ display: 'flex', gap: '8px', marginTop: '8px' }}>
                    <input className="input-field" type="password" placeholder="Enter Security PIN" value={pinInput} onChange={e => setPinInput(e.target.value)} maxLength={6} style={{ padding: '6px 10px', fontSize: '12px' }} />
                    <button className="btn" onClick={submitPin} style={{ padding: '6px 12px', fontSize: '12px' }}>VERIFY</button>
                  </div>
                )}
              </div>
              <div>
                {authLevel >= 2 ? (
                  <span className="glow-text-green">✔ UNLOCKED</span>
                ) : (
                  <span className="glow-text-purple">🔒 LOCKED</span>
                )}
              </div>
            </div>

            {/* Level 3: Admin (Face Authentication) */}
            <div className={`security-level-item ${authLevel === 3 ? 'active' : authLevel > 3 ? 'unlocked' : 'locked'}`}>
              <div style={{ flex: 1 }}>
                <strong>Level 3: Admin</strong>
                <div style={{ fontSize: '11px', color: 'var(--text-secondary)' }}>Configure system settings</div>
                {authLevel === 2 && (
                  <div style={{ marginTop: '8px' }}>
                    {isFaceScanning ? (
                      <div className="webcam-container">
                        <video ref={videoRef} autoPlay playsInline muted className="webcam-video" />
                        <div className="scan-laser" />
                        <div className="face-reticle" />
                        <div className="corner-bracket corner-tl" />
                        <div className="corner-bracket corner-tr" />
                        <div className="corner-bracket corner-bl" />
                        <div className="corner-bracket corner-br" />
                        <div style={{ position: 'absolute', bottom: '6px', width: '100%', textAlign: 'center', color: 'var(--accent-cyan)', fontSize: '11px', fontWeight: 'bold', background: 'rgba(0,0,0,0.6)', padding: '2px 0', zIndex: 6 }}>
                          BIOMETRIC SCANNING: {faceMatchProgress}% MATCH
                        </div>
                      </div>
                    ) : (
                      <button className="btn" onClick={triggerFaceVerification} style={{ width: '100%', fontSize: '12px', padding: '6px 12px' }}>
                        📷 SCAN CAMERA (FACE AUTH)
                      </button>
                    )}
                  </div>
                )}
              </div>
              <div>
                {authLevel >= 3 ? (
                  <span className="glow-text-green">✔ UNLOCKED</span>
                ) : (
                  <span className="glow-text-purple">🔒 LOCKED</span>
                )}
              </div>
            </div>

            {/* Level 4: Vault (Face Auth + Password) */}
            <div className={`security-level-item ${authLevel === 4 ? 'unlocked' : 'locked'}`}>
              <div style={{ flex: 1 }}>
                <strong>Level 4: Vault (Full Cryptographic)</strong>
                <div style={{ fontSize: '11px', color: 'var(--text-secondary)' }}>Access encrypted passwords & credentials</div>
                {authLevel === 3 && (
                  <div style={{ display: 'flex', gap: '8px', marginTop: '8px' }}>
                    <input className="input-field" type="password" placeholder="Master Password" value={vaultPassword} onChange={e => setVaultPassword(e.target.value)} style={{ padding: '6px 10px', fontSize: '12px' }} />
                    <button className="btn" onClick={submitVaultPassword} style={{ padding: '6px 12px', fontSize: '12px' }}>UNLOCK</button>
                  </div>
                )}
              </div>
              <div>
                {authLevel >= 4 ? (
                  <span className="glow-text-green">✔ UNLOCKED</span>
                ) : (
                  <span className="glow-text-purple">🔒 LOCKED</span>
                )}
              </div>
            </div>

          </div>
        </section>

        {/* Right Side: Chat & Commands Core */}
        <section className="glass-panel" style={{ display: 'grid', gridTemplateRows: 'auto auto 1fr auto', height: '620px' }}>
          <div className="panel-header">
            <h2 className="panel-title">
              <span className="logo-dot" style={{ display: 'inline-block', width: '8px', height: '8px', background: 'var(--accent-purple)' }}></span>
              JARVIS Neural Voice Core
            </h2>
            <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
              <button
                className="btn btn-secondary"
                style={{ padding: '2px 8px', fontSize: '11px' }}
                onClick={() => setSpeechSynthesisEnabled(!speechSynthesisEnabled)}
              >
                {speechSynthesisEnabled ? '🔊 VOICE OUTPUT: ON' : '🔇 VOICE OUTPUT: OFF'}
              </button>
              <span style={{ fontSize: '11px', color: 'var(--accent-cyan)', background: 'rgba(0,242,254,0.1)', padding: '2px 8px', borderRadius: '12px', border: '1px solid rgba(0,242,254,0.3)' }}>
                {isWakeWordListening ? '👂 LISTENING FOR "JARVIS"' : '🤖 ACTIVE PROCESSING'}
              </span>
            </div>
          </div>

          {/* Holographic Arc Reactor AI Core HUD */}
          <div style={{ padding: '16px 20px', borderBottom: '1px solid var(--border-color)', background: 'rgba(0,0,0,0.15)', textAlign: 'center' }}>
            <div
              className={`arc-reactor-wrapper arc-state-${arcState}`}
              onClick={triggerAutomatedVoiceFlow}
              title="Click Arc Reactor to initiate voice command flow"
            >
              <div className="arc-reactor-ring-outer" />
              <div className="arc-reactor-ring-inner" />
              <div className="arc-reactor-core-orb">
                {arcState === 'listening' ? '🎙️' : arcState === 'thinking' ? '⚡' : arcState === 'speaking' ? '🗣️' : '💎'}
              </div>
            </div>
            
            <div style={{ marginTop: '12px', fontSize: '12px', fontWeight: '600', letterSpacing: '1px', color: arcState === 'listening' ? 'var(--accent-cyan)' : arcState === 'thinking' ? 'var(--accent-purple)' : 'var(--text-secondary)' }}>
              {wakeWordStatus}
            </div>
            <div style={{ fontSize: '10px', color: 'var(--text-muted)', marginTop: '4px' }}>
              [Automated Pipeline: Wake Phrase ("Hey JARVIS") → Camera Face ID → Voice Command → Gemini AI]
            </div>
          </div>

          {/* Chat Messages Panel */}
          <div style={{ padding: '20px', overflowY: 'auto', display: 'flex', flexDirection: 'column', gap: '16px' }}>
            {commands.map((cmd, idx) => (
              <div key={idx} style={{ display: 'flex', flexDirection: 'column', gap: '6px' }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '12px' }}>
                  <span style={{ color: 'var(--accent-cyan)' }}><strong>👤 USER:</strong> {cmd.prompt}</span>
                  {cmd.status && (
                    <span style={{
                      color: cmd.status === 'SUCCESS' ? 'var(--accent-green)' : cmd.status === 'UPGRADE_REQUIRED' ? 'var(--accent-yellow)' : 'var(--accent-red)',
                      fontWeight: 'bold'
                    }}>{cmd.status}</span>
                  )}
                </div>
                <div style={{
                  padding: '12px 16px',
                  borderRadius: '10px',
                  background: 'rgba(255, 255, 255, 0.03)',
                  borderLeft: `3px solid ${
                    cmd.status === 'SUCCESS' ? 'var(--accent-green)' : cmd.status === 'UPGRADE_REQUIRED' ? 'var(--accent-yellow)' : 'var(--accent-red)'
                  }`,
                  fontSize: '14px',
                  whiteSpace: 'pre-wrap',
                  lineHeight: '1.5'
                }}>
                  {cmd.response}
                </div>
              </div>
            ))}
            <div ref={consoleEndRef} />
          </div>

          {/* Action inputs */}
          <div style={{ padding: '20px', borderTop: '1px solid var(--border-color)', background: 'rgba(0,0,0,0.1)' }}>
            
            {/* Quick simulated Voice Commands for testing */}
            <div style={{ display: 'flex', gap: '10px', marginBottom: '12px', overflowX: 'auto', paddingBottom: '4px' }}>
              <span style={{ fontSize: '11px', color: 'var(--text-muted)', alignSelf: 'center', whiteSpace: 'nowrap' }}>Mock Voice Cmd:</span>
              <button className="btn btn-secondary" style={{ padding: '4px 8px', fontSize: '10px', whiteSpace: 'nowrap' }} onClick={() => triggerVoiceCommandSimulate('weather')} disabled={isVoiceRecording}>
                ☁ General: "What is the weather?"
              </button>
              <button className="btn btn-secondary" style={{ padding: '4px 8px', fontSize: '10px', whiteSpace: 'nowrap' }} onClick={() => triggerVoiceCommandSimulate('read')} disabled={isVoiceRecording}>
                📄 L1 Read: "Read file system_config.txt"
              </button>
              <button className="btn btn-secondary" style={{ padding: '4px 8px', fontSize: '10px', whiteSpace: 'nowrap' }} onClick={() => triggerVoiceCommandSimulate('delete')} disabled={isVoiceRecording}>
                🔥 L2 Write: "Delete file old_report.txt"
              </button>
              <button className="btn btn-secondary" style={{ padding: '4px 8px', fontSize: '10px', whiteSpace: 'nowrap' }} onClick={() => triggerVoiceCommandSimulate('vault')} disabled={isVoiceRecording}>
                🔑 L4 Secrets: "Vault secrets display"
              </button>
            </div>

            <form onSubmit={handleSubmitCommand} style={{ display: 'flex', gap: '12px' }}>
              <input
                className="input-field"
                type="text"
                value={userInput}
                onChange={e => setUserInput(e.target.value)}
                placeholder={isVoiceRecording ? "Listening... Speak your command..." : "Instruct JARVIS (e.g. Read file system_config.txt, Weather update...)"}
                disabled={isLoading}
              />
              <button
                className="btn btn-secondary"
                type="button"
                onClick={startLiveVoiceInput}
                disabled={isLoading || isVoiceRecording}
                title="Speak command using microphone"
                style={{ padding: '0 14px', fontSize: '16px', display: 'flex', alignItems: 'center', justifyContent: 'center' }}
              >
                {isVoiceRecording ? '🔴' : '🎙️'}
              </button>
              <button className="btn" type="submit" disabled={isLoading || !userInput}>
                {isLoading ? 'PROCESSING...' : 'EXECUTE'}
              </button>
            </form>
          </div>
        </section>
      </main>

      {/* Bottom Side: Real-time Audit Logs Console */}
      <section className="glass-panel">
        <div className="panel-header" style={{ padding: '10px 20px' }}>
          <h2 className="panel-title" style={{ fontSize: '14px' }}>
            <span className="logo-dot" style={{ display: 'inline-block', width: '6px', height: '6px', background: 'var(--accent-red)', animation: 'pulse 1s infinite' }}></span>
            Immutable Audit Trail
          </h2>
          <span style={{ fontSize: '11px', color: 'var(--text-muted)' }}>Status: CONNECTED</span>
        </div>
        <div style={{ padding: '15px' }}>
          <div className="terminal-window" style={{ height: '140px' }}>
            {auditLogs.length === 0 ? (
              <div className="terminal-line"><span style={{ color: 'var(--text-muted)' }}>[System initialized. Awaiting gateway audits...]</span><span className="terminal-cursor"></span></div>
            ) : (
              auditLogs.map((log) => {
                const isoUtc = log.timestamp && !log.timestamp.endsWith('Z') && !log.timestamp.includes('+') ? `${log.timestamp}Z` : log.timestamp;
                const dateStr = new Date(isoUtc).toLocaleTimeString();
                const isBlocked = log.status === 'BLOCKED' || log.status === 'FAILURE' || log.status === 'BLOCKED_BY_RBAC';
                const statusColor = log.threat_flag ? 'var(--accent-red)' : isBlocked ? 'var(--accent-yellow)' : 'var(--accent-green)';
                
                return (
                  <div key={log.id} className="terminal-line">
                    <span style={{ color: 'var(--text-muted)' }}>[{dateStr}]</span>{' '}
                    <span style={{ color: 'var(--accent-purple)' }}>{log.action}</span> -{' '}
                    <span style={{ color: statusColor, fontWeight: 'bold' }}>{log.status}</span>:{' '}
                    <span>{log.details}</span>
                    {log.threat_flag && <span style={{ color: '#fff', background: 'var(--accent-red)', padding: '2px 6px', borderRadius: '4px', marginLeft: '8px', fontSize: '10px', boxShadow: '0 0 8px rgba(239, 68, 68, 0.4)' }}>THREAT DETECTED</span>}
                  </div>
                );
              })
            )}
            <div ref={consoleEndRef} />
          </div>
        </div>
      </section>
    </div>
  );
}

export default App;
