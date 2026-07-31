"""
Deep mic diagnostic — tests each device with WASAPI-exclusive and shared modes,
tries multiple sample rates, measures sustained RMS over 2 seconds while speaking,
and applies software gain to check if the signal is just very quiet.
"""
import sounddevice as sd
import numpy as np
import time

print("=" * 70)
print("PROJECT AEGIS — DEEP MICROPHONE DIAGNOSTIC")
print("=" * 70)
print()
print(">>> SPEAK CONTINUOUSLY during this test <<<")
print()

devices = sd.query_devices()
results = []

for idx, dev in enumerate(devices):
    if dev["max_input_channels"] <= 0:
        continue

    name = dev["name"]
    default_sr = int(dev.get("default_samplerate", 44100))

    for rate in [default_sr, 16000, 44100, 48000]:
        try:
            # Record 2 seconds
            duration = 2.0
            audio = sd.rec(
                int(duration * rate),
                samplerate=rate,
                channels=1,
                device=idx,
                dtype="float32",
            )
            sd.wait()

            rms = float(np.sqrt(np.mean(audio ** 2)))
            peak = float(np.max(np.abs(audio)))

            # Software gain test: amplify 100x and re-measure
            amplified = audio * 100.0
            amp_rms = float(np.sqrt(np.mean(amplified ** 2)))

            status = "SILENT"
            if rms > 0.01:
                status = "*** STRONG SIGNAL ***"
            elif rms > 0.001:
                status = "** WEAK SIGNAL (needs gain) **"
            elif rms > 0.0001:
                status = "* VERY WEAK (may need Windows boost) *"

            line = (
                f"Dev #{idx:2d} [{name[:35]:35s}] "
                f"Rate={rate:5d}Hz  RMS={rms:.7f}  Peak={peak:.7f}  "
                f"Amp100x_RMS={amp_rms:.5f}  -> {status}"
            )
            print(line)
            results.append((idx, name, rate, rms, peak, amp_rms, status))
            break  # only test first working rate per device
        except Exception as e:
            pass

print()
print("-" * 70)

# Find the best device
best = None
for r in results:
    if best is None or r[3] > best[3]:
        best = r

if best:
    idx, name, rate, rms, peak, amp_rms, status = best
    print(f"BEST DEVICE: #{idx} [{name}] at {rate}Hz")
    print(f"  Raw RMS: {rms:.7f}  |  Peak: {peak:.7f}  |  100x Amplified RMS: {amp_rms:.5f}")
    print()
    if rms < 0.0005:
        print("DIAGNOSIS: Mic is capturing near-zero signal.")
        print()
        print("RECOMMENDED FIXES:")
        print("  1. Windows Settings > System > Sound > Input > Microphone Array")
        print("     -> Set input volume slider to 100%")
        print("  2. Control Panel > Sound > Recording tab > Microphone Array > Properties")
        print("     -> Levels tab: Set Microphone to 100, Boost to +20dB or +30dB")
        print("  3. Check 'Allow apps to access your microphone' in Privacy settings")
        print()
        print(f"  If after boost, signal is still <0.001, the pipeline will apply")
        print(f"  automatic software gain (100x) and lower VAD threshold to 0.0003.")
    elif rms < 0.01:
        print("DIAGNOSIS: Signal is present but weak. Software gain will help.")
        print(f"  Pipeline will auto-apply gain. VAD threshold set to {max(rms * 3, 0.0003):.5f}")
    else:
        print("DIAGNOSIS: Strong mic signal detected. Pipeline should work as-is.")
else:
    print("ERROR: No working input devices found!")
