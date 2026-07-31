"""
Minimal mic stream test - bypasses the entire pipeline.
Opens the mic ONCE using sounddevice.InputStream at the native sample rate 
and prints RMS levels every 0.5 seconds for 10 seconds.

Run: .\venv\Scripts\python.exe test_mic_stream.py
"""
import sounddevice as sd
import numpy as np
import time
import threading

print("=" * 60)
print("MINIMAL MIC STREAM TEST")
print("=" * 60)

# Find the Realtek mic
devices = sd.query_devices()
mic_idx = None
for idx, dev in enumerate(devices):
    if dev["max_input_channels"] > 0 and "microphone" in dev["name"].lower():
        mic_idx = idx
        break

if mic_idx is None:
    mic_idx = sd.default.device[0]

dev_info = sd.query_devices(mic_idx)
native_rate = int(dev_info.get("default_samplerate", 44100))

print(f"Device #{mic_idx}: {dev_info['name']}")
print(f"Native sample rate: {native_rate}Hz")
print(f"Max input channels: {dev_info['max_input_channels']}")
print()

# Shared state
rms_value = 0.0
peak_value = 0.0
callback_count = 0
error_count = 0
lock = threading.Lock()

GAIN = 150.0

def audio_callback(indata, frames, time_info, status):
    global rms_value, peak_value, callback_count, error_count
    if status:
        error_count += 1
        print(f"  [CALLBACK STATUS]: {status}")
    
    raw = indata[:, 0].copy()
    amplified = np.clip(raw * GAIN, -1.0, 1.0)
    rms = float(np.sqrt(np.mean(amplified ** 2)))
    peak = float(np.max(np.abs(amplified)))
    
    with lock:
        rms_value = rms
        peak_value = peak
        callback_count += 1

print(f"Opening InputStream at {native_rate}Hz with {GAIN}x gain...")
print(">>> SPEAK NOW — watching for 15 seconds <<<")
print()

try:
    stream = sd.InputStream(
        samplerate=native_rate,
        blocksize=2048,
        device=mic_idx,
        channels=1,
        dtype="float32",
        callback=audio_callback,
    )
    stream.start()
    print(f"Stream opened! Active={stream.active}")
    print()
    
    start_time = time.time()
    while time.time() - start_time < 15:
        time.sleep(0.5)
        with lock:
            r = rms_value
            p = peak_value
            c = callback_count
            e = error_count
        
        # Visual bar
        bar_len = int(min(r * 200, 50))
        bar = "█" * bar_len + "░" * (50 - bar_len)
        
        status_icon = "🔴" if r < 0.001 else "🟡" if r < 0.01 else "🟢"
        
        elapsed = time.time() - start_time
        print(
            f"  [{elapsed:5.1f}s] {status_icon} RMS={r:.6f} Peak={p:.6f} "
            f"|{bar}| callbacks={c} errors={e} active={stream.active}"
        )
    
    stream.stop()
    stream.close()
    print()
    print(f"Stream closed normally. Total callbacks: {callback_count}, errors: {error_count}")
    
    if callback_count == 0:
        print("\n❌ ZERO callbacks received — sounddevice is NOT getting audio from this device!")
        print("   Try: Control Panel > Sound > Recording > right-click Mic > Enable")
    elif rms_value < 0.001:
        print(f"\n⚠️  Signal very weak even with {GAIN}x gain.")
        print("   Windows Settings > System > Sound > Input Volume → drag to 100")
        print("   Control Panel > Sound > Recording > Microphone > Properties > Levels")
        print("   → Set Microphone to 100, Mic Boost to +20dB or +30dB")
    else:
        print(f"\n✅ Mic is working! Peak signal: {peak_value:.4f}")

except Exception as e:
    print(f"\n❌ STREAM FAILED: {e}")
    print(f"   Type: {type(e).__name__}")
    print()
    print("Trying alternate rates...")
    for alt_rate in [44100, 48000, 16000, 22050, 8000]:
        try:
            test = sd.rec(int(0.2 * alt_rate), samplerate=alt_rate, channels=1, 
                         device=mic_idx, dtype='float32')
            sd.wait()
            r = float(np.sqrt(np.mean(test ** 2)))
            print(f"  Rate {alt_rate}Hz: RMS={r:.7f} {'✓ works' if r > 0 else '✗ silent'}")
        except Exception as e2:
            print(f"  Rate {alt_rate}Hz: FAILED ({e2})")
