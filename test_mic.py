#!/usr/bin/env python3
"""
Simple microphone test to check audio levels
"""
import numpy as np
import sounddevice as sd
import time

def test_microphone():
    """Test microphone input levels"""
    print("🎤 Testing microphone levels...")
    print("📢 Please speak loudly into your microphone for 5 seconds...")
    print("⏳ Starting in 3 seconds...")
    time.sleep(3)
    
    # Record 5 seconds of audio
    duration = 5  # seconds
    sample_rate = 16000  # Same as agent
    
    print("🔴 Recording... SPEAK LOUDLY NOW!")
    audio_data = sd.rec(int(duration * sample_rate), samplerate=sample_rate, channels=1, dtype='int16')
    sd.wait()  # Wait until recording is finished
    
    # Analyze audio levels
    audio_array = audio_data.flatten()
    volume_level = np.sqrt(np.mean(audio_array**2))
    max_amplitude = np.max(np.abs(audio_array))
    
    print("\n" + "="*50)
    print("📊 MICROPHONE TEST RESULTS:")
    print(f"🔊 Volume level: {volume_level:.1f}")
    print(f"📈 Max amplitude: {max_amplitude}")
    print(f"🎵 Audio samples: {len(audio_array)}")
    print("="*50)
    
    # Compare with agent requirements
    if volume_level > 50:
        print("✅ GOOD: Volume level sufficient for speech detection")
    else:
        print("❌ PROBLEM: Volume too low for speech detection")
        print(f"   Required: > 50, Got: {volume_level:.1f}")
        print("💡 Solutions:")
        print("   - Speak MUCH louder")
        print("   - Move closer to microphone")
        print("   - Check system audio settings")
        print("   - Increase browser microphone permissions")
    
    if max_amplitude > 100:
        print("✅ GOOD: Audio signal has sufficient amplitude")
    else:
        print("❌ PROBLEM: Audio signal too weak")
        print(f"   Required: > 100, Got: {max_amplitude}")

if __name__ == "__main__":
    try:
        test_microphone()
    except Exception as e:
        print(f"❌ Error testing microphone: {e}")
        print("💡 Try: pip install sounddevice numpy")