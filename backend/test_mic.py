import sounddevice as sd
import numpy as np
import time

print("Testing Windows Hardware Microphone...")
devices = sd.query_devices()
print(f"Total audio devices found: {len(devices)}")

default_input = sd.default.device[0]
print(f"Default input device ID: {default_input} -> {devices[default_input]['name']}")

print("Recording 2 seconds of audio...")
audio_data = sd.rec(int(2 * 16000), samplerate=16000, channels=1, dtype='float32')
sd.wait()

rms_level = float(np.sqrt(np.mean(audio_data**2)))
max_peak = float(np.max(np.abs(audio_data)))
print(f"Recorded successfully! RMS Level: {rms_level:.6f}, Max Peak: {max_peak:.6f}")
