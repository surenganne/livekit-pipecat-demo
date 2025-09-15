#!/usr/bin/env python3

"""
LiveKit + Pipecat Integration Demo Agent

This agent:
1. Connects to a LiveKit room as a participant
2. Listens for user audio input
3. Converts speech to text (STT)
4. Adds "...got it" suffix to the text
5. Converts back to speech (TTS)
6. Publishes audio response to the room

Features:
- Real-time audio processing
- Barge-in support (user can interrupt)
- Latency optimization
- Error handling and reconnection
"""

import asyncio
import logging
import signal
import sys
import os
import time
import jwt
from typing import Optional

# Add current directory to path for config import
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

try:
    import config
except ImportError:
    print("❌ config.py not found. Please copy config.py.template to config.py and configure your credentials.")
    sys.exit(1)

# Configure logging
logging.basicConfig(
    level=getattr(logging, config.LOG_LEVEL),
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Check if we have the required packages
try:
    from pipecat.frames.frames import Frame, AudioRawFrame, TextFrame, StartFrame
    from pipecat.pipeline.pipeline import Pipeline
    from pipecat.pipeline.runner import PipelineRunner
    from pipecat.pipeline.task import PipelineTask
    from pipecat.services.openai.stt import OpenAISTTService
    from pipecat.services.openai.tts import OpenAITTSService
    from pipecat.frames.frames import AudioRawFrame
    from pipecat.transports.livekit.transport import LiveKitTransport, LiveKitParams
    from pipecat.processors.aggregators.openai_llm_context import OpenAILLMContext
    from pipecat.processors.frame_processor import FrameDirection, FrameProcessor
    from pipecat.audio.vad.silero import SileroVADAnalyzer
    from pipecat.audio.vad.vad_analyzer import VADParams

    logger.info("✅ Pipecat imports successful")

except ImportError as e:
    logger.error(f"❌ Failed to import Pipecat: {e}")
    logger.error("Please install Pipecat: pip install pipecat-ai")
    sys.exit(1)


def generate_access_token():
    """Generate a LiveKit access token for the agent with unique identity"""
    from livekit import api
    from connection_manager import connection_manager
    
    # Use connection manager to generate truly unique identity
    unique_identity = connection_manager.generate_unique_identity("PipecatAgent")
    
    logger.info(f"🆔 Generating token for unique agent identity: {unique_identity}")
    
    # Create access token with unique identity
    token = api.AccessToken(config.LIVEKIT_API_KEY, config.LIVEKIT_API_SECRET) \
        .with_identity(unique_identity) \
        .with_name(unique_identity) \
        .with_grants(api.VideoGrants(
            room_join=True,
            room=config.ROOM_NAME,
            can_publish=True,
            can_subscribe=True
        ))

    return token.to_jwt(), unique_identity


class DummyTTSService(FrameProcessor):
    """Dummy TTS service for testing pipeline flow"""
    
    async def process_frame(self, frame: Frame, direction: FrameDirection):
        """Process frames - convert TextFrame to dummy audio"""
        # Handle start frame and other setup frames first
        await super().process_frame(frame, direction)
        
        if isinstance(frame, TextFrame):
            logger.info(f"🎵 DummyTTS received text: '{frame.text}'")
            
            # Create dummy audio data (silence)
            sample_rate = 16000
            duration_seconds = len(frame.text) * 0.1  # 0.1 seconds per character
            num_samples = int(sample_rate * duration_seconds)
            dummy_audio = bytes(num_samples * 2)  # 16-bit silence
            
            # Create AudioRawFrame
            audio_frame = AudioRawFrame(dummy_audio, sample_rate, 1)
            logger.info(f"🎵 DummyTTS generated {len(dummy_audio)} bytes of audio")
            
            # Send audio frame downstream
            await self.push_frame(audio_frame, direction)


class DebuggingTTSService(OpenAITTSService):
    """TTS service wrapper with debug logging"""
    
    async def process_frame(self, frame: Frame, direction: FrameDirection):
        """Override process_frame to add debugging"""
        frame_type = frame.__class__.__name__
        logger.debug(f"🎵 TTS Service received frame: {frame_type}")
        
        if isinstance(frame, TextFrame):
            logger.info(f"🔊 TTS Processing: '{frame.text}' (length: {len(frame.text)})")
            logger.debug(f"🔍 Frame direction: {direction}")
        
        try:
            # Call the parent process_frame method
            result = await super().process_frame(frame, direction)
            
            if isinstance(frame, TextFrame):
                logger.info(f"✅ TTS completed processing: '{frame.text}'")
            
            return result
        except Exception as e:
            if isinstance(frame, TextFrame):
                logger.error(f"❌ TTS process_frame failed for: '{frame.text}' - {e}")
            else:
                logger.error(f"❌ TTS process_frame failed for {frame_type} - {e}")
            raise
    
    async def _push_tts_frames(self, text: str):
        """Override _push_tts_frames to add debugging"""
        logger.info(f"🎤➡️🔊 TTS generating audio for: '{text}' (length: {len(text)})")
        
        try:
            # Call parent method which handles the async generator properly
            await super()._push_tts_frames(text)
            logger.info(f"🔊✅ TTS audio generation completed for: '{text[:50]}...'")
        except Exception as e:
            logger.error(f"❌ TTS _push_tts_frames failed for '{text}': {e}")
            raise


class IntelligentProcessor(FrameProcessor):
    """Intelligent processor that uses OpenAI to generate contextual responses"""

    def __init__(self):
        super().__init__()
        self.speech_start_time = None
        self.waiting_for_tts_audio = False
        self.tts_text_sent = None
        self.latency_measurements = []
        self.max_measurements = 20
        
        # Initialize OpenAI client for real LLM responses
        import openai
        self.openai_client = openai.OpenAI(
            api_key=config.OPENAI_API_KEY,
            timeout=8.0  # Reasonable timeout for quality responses
        )
        
        # Conversation history for context
        self.conversation_history = [
            {"role": "system", "content": "You are a helpful AI assistant. Provide natural, conversational responses. Be informative and engaging while keeping responses reasonably concise."}
        ]
        
        logger.info("🧠 IntelligentProcessor initialized with real OpenAI GPT-3.5-turbo")



    async def process_frame(self, frame: Frame, direction: FrameDirection):
        """Process incoming frames"""
        # Log important frames to debug audio flow
        frame_type = frame.__class__.__name__
        
        # Log ALL frame types for debugging
        if frame_type not in ['UserAudioRawFrame', 'AudioRawFrame']:
            logger.info(f"🔄 IntelligentProcessor received: {frame_type}")
        elif frame_type == 'UserAudioRawFrame':
            # Log every user audio frame with more details
            if hasattr(frame, 'audio') and frame.audio:
                logger.info(f"🎤🔊 User audio frame: {len(frame.audio)} bytes, sample_rate: {getattr(frame, 'sample_rate', 'unknown')}")
            else:
                logger.info(f"🎤⚠️ User audio frame with no audio data")
        elif frame_type == 'AudioRawFrame':
            # More detailed logging for audio frames
            if hasattr(frame, 'audio') and frame.audio:
                logger.info(f"🎵 AudioRawFrame: {len(frame.audio)} bytes, direction: {direction}")
            else:
                logger.debug(f"🎵 Empty AudioRawFrame, direction: {direction}")

        # Let parent handle the frame first (including StartFrame validation)
        await super().process_frame(frame, direction)

        # Track when user starts speaking for conversation latency measurement
        if 'UserStartedSpeaking' in frame_type:
            self.speech_start_time = time.time()
            self.waiting_for_tts_audio = False
            self.tts_text_sent = None
            logger.info(f"🎤 🔥 USER STARTED SPEAKING at {self.speech_start_time:.3f}")
            logger.info(f"🎤 Ready to measure latency for next complete interaction")

            # Send processing start notification to client
            await self.send_processing_data({
                'type': 'processing_start',
                'timestamp': self.speech_start_time
            })

        # Process text input from STT
        if isinstance(frame, TextFrame):
            user_text = frame.text.strip()
            logger.info(f"🎤📝 USER SPOKE: '{user_text}' (length: {len(user_text)})")

            if user_text:
                # Calculate latency if we have a start time
                if self.speech_start_time:
                    latency_ms = (time.time() - self.speech_start_time) * 1000
                    logger.info(f"⏱️  STT Latency: {latency_ms:.1f}ms")

                # Generate intelligent response using OpenAI
                response_text = await self.generate_response(user_text)
                
                logger.info(f"👥 USER INPUT: '{user_text}'")
                logger.info(f"🤖 AGENT RESPONSE: '{response_text}'")
                logger.info(f"🎵 SENDING TO TTS: '{response_text}' (length: {len(response_text)})")

                # Create TextFrame and send to TTS pipeline
                response_frame = TextFrame(response_text)
                logger.info(f"📝 TTS TextFrame content: '{response_frame.text}'")
                
                # Mark that we're waiting for TTS audio generation
                self.waiting_for_tts_audio = True
                self.tts_text_sent = response_text
                logger.info(f"⏳ WAITING FOR TTS AUDIO: '{response_text}'")
                
                await self.push_frame(response_frame, FrameDirection.DOWNSTREAM)
                logger.info(f"✅ TTS FRAME SENT: '{response_text}'")
                # The TextFrame is now sent to TTS service for speech synthesis
            else:
                # Handle empty input
                logger.info("🔇 Empty text received, sending fallback response")
                response_frame = TextFrame("I didn't catch that. Could you repeat?")
                await self.push_frame(response_frame, FrameDirection.DOWNSTREAM)

        # Process audio frames from TTS (for latency measurement)
        elif isinstance(frame, AudioRawFrame):
            # Check frame direction to distinguish input from output audio
            is_downstream = direction == FrameDirection.DOWNSTREAM
            
            if hasattr(frame, 'audio') and len(frame.audio) > 0:
                # Only measure latency for TTS-generated audio (downstream frames when we're waiting)
                if (self.waiting_for_tts_audio and self.speech_start_time and 
                    is_downstream and len(frame.audio) > 1000):  # Substantial audio chunk
                    
                    response_time = time.time()
                    latency_ms = (response_time - self.speech_start_time) * 1000
                    
                    logger.info(f"🎙️ TTS Audio received for: '{self.tts_text_sent}' (audio length: {len(frame.audio)} bytes)")
                    
                    # Store measurement for averaging
                    self.latency_measurements.append(latency_ms)
                    if len(self.latency_measurements) > self.max_measurements:
                        self.latency_measurements.pop(0)
                    
                    # Calculate average latency
                    avg_latency = sum(self.latency_measurements) / len(self.latency_measurements)
                    
                    # Enhanced latency reporting
                    logger.info(f"🚀 ⚡ END-TO-END LATENCY: {latency_ms:.1f}ms (Average: {avg_latency:.1f}ms over {len(self.latency_measurements)} measurements)")
                    
                    # Highlight when we achieve <600ms target
                    if latency_ms < 600:
                        logger.info(f"✅ 🏆 LATENCY TARGET MET: {latency_ms:.1f}ms < 600ms target!")
                    
                    # Send processing complete notification to client
                    await self.send_processing_data({
                        'type': 'processing_complete',
                        'timestamp': response_time,
                        'latency_ms': latency_ms,
                        'average_latency_ms': avg_latency,
                        'measurement_count': len(self.latency_measurements),
                        'tts_text': self.tts_text_sent
                    })

                    # Reset for next measurement
                    self.speech_start_time = None
                    self.waiting_for_tts_audio = False
                    self.tts_text_sent = None

            # Pass audio frame downstream
            await self.push_frame(frame, FrameDirection.DOWNSTREAM)
        else:
            # Pass all other frames downstream
            await self.push_frame(frame, FrameDirection.DOWNSTREAM)

    def get_latency_summary(self):
        """Get latency statistics summary"""
        if not self.latency_measurements:
            return "No latency measurements yet"
        
        avg = sum(self.latency_measurements) / len(self.latency_measurements)
        min_latency = min(self.latency_measurements)
        max_latency = max(self.latency_measurements)
        
        sub_600_count = sum(1 for l in self.latency_measurements if l < 600)
        sub_600_percentage = (sub_600_count / len(self.latency_measurements)) * 100
        
        return (f"Latency Summary: Avg={avg:.1f}ms, Min={min_latency:.1f}ms, Max={max_latency:.1f}ms, "
                f"<600ms: {sub_600_count}/{len(self.latency_measurements)} ({sub_600_percentage:.1f}%)")
    
    async def send_processing_data(self, data):
        """Send processing state data to client via data channel"""
        try:
            import json
            from pipecat.frames.frames import TransportMessageFrame

            # Send data to client via data channel
            json_data = json.dumps(data)
            logger.info(f"📱 Processing data: {json_data}")
            
            # Create transport message frame and send to client
            message_frame = TransportMessageFrame(message=json_data)
            logger.info(f"📶 Sending TransportMessageFrame to client: {data['type']}")
            await self.push_frame(message_frame, FrameDirection.DOWNSTREAM)
            logger.info(f"✅ TransportMessageFrame successfully sent to client")
            
            # Every 5th measurement, log summary
            if 'latency_ms' in data and len(self.latency_measurements) % 5 == 0:
                logger.info(f"📈 LATENCY SUMMARY: {self.get_latency_summary()}")

        except Exception as e:
            logger.error(f"❌ Failed to send processing data: {e}")
            logger.error(f"🔍 Exception details: {type(e).__name__}: {str(e)}")
            # Fallback to just logging
            logger.info(f"📱 Processing data (log only): {json.dumps(data)}")
            
            # Try alternative approach with TextFrame as fallback
            try:
                from pipecat.frames.frames import TextFrame
                fallback_frame = TextFrame(f"LATENCY_DATA: {json.dumps(data)}")
                await self.push_frame(fallback_frame, FrameDirection.DOWNSTREAM)
                logger.info(f"🔄 Sent as TextFrame fallback")
            except Exception as fallback_error:
                logger.error(f"❌ Fallback also failed: {fallback_error}")
    
    async def generate_response(self, user_text: str) -> str:
        """Generate intelligent response using OpenAI GPT-3.5-turbo"""
        try:
            logger.info(f"🧠 Generating intelligent response for: '{user_text}'")
            start_time = time.time()
            
            # Add user message to conversation history
            self.conversation_history.append({"role": "user", "content": user_text})
            
            # Keep conversation history manageable (last 6 messages)
            if len(self.conversation_history) > 7:  # 1 system + 6 messages
                self.conversation_history = [self.conversation_history[0]] + self.conversation_history[-6:]
            
            # Generate intelligent response using OpenAI
            response = self.openai_client.chat.completions.create(
                model="gpt-3.5-turbo",
                messages=self.conversation_history,
                max_tokens=150,  # Allow for complete, helpful responses
                temperature=0.7,  # Natural conversation
                timeout=8.0  # Reasonable timeout for quality
            )
            
            llm_time = (time.time() - start_time) * 1000
            logger.info(f"⚡ OpenAI LLM response time: {llm_time:.1f}ms")
            
            response_text = response.choices[0].message.content.strip()
            
            # Add assistant response to conversation history
            self.conversation_history.append({"role": "assistant", "content": response_text})
            
            # Clean up response for TTS (remove quotes that might cause issues)
            response_text = response_text.replace('"', '').replace("'", "")
            
            logger.info(f"💬 Generated intelligent response: '{response_text}'")
            return response_text
            
        except Exception as e:
            logger.error(f"❌ Failed to generate OpenAI response: {e}")
            # Intelligent fallback based on user input
            if "weather" in user_text.lower():
                return "I don't have access to current weather data. You can check a weather app or website for accurate forecasts."
            elif "joke" in user_text.lower():
                return "Here's one: Why don't scientists trust atoms? Because they make up everything!"
            elif "help" in user_text.lower():
                return "I'm here to help! I can answer questions, have conversations, explain topics, or assist with various tasks. What would you like to know?"
            else:
                return f"That's interesting! I'd be happy to discuss {user_text} with you. Could you tell me more about what specifically interests you?"


async def main():
    """Main function to start the agent"""
    logger.info("🤖 Starting LiveKit + Pipecat Demo Agent")
    
    from connection_manager import connection_manager

    # Validate configuration
    if not config.OPENAI_API_KEY or config.OPENAI_API_KEY == "your-openai-api-key":
        logger.error("❌ Please set your OpenAI API key in config.py")
        return

    if not config.LIVEKIT_URL or not config.LIVEKIT_API_KEY or not config.LIVEKIT_API_SECRET:
        logger.error("❌ Please set your LiveKit credentials in config.py")
        return

    transport = None
    unique_identity = None
    
    try:
        # Clean up any stale connections first
        await connection_manager.cleanup_stale_connections()
        
        # Generate access token with unique identity
        token, unique_identity = generate_access_token()
        
        logger.info(f"🔗 Connecting with identity: {unique_identity}")
        
        # Initialize transport with VAD and unique identity
        transport = LiveKitTransport(
            url=config.LIVEKIT_URL,
            token=token,
            room_name=config.ROOM_NAME,
            params=LiveKitParams(
                participant_name=unique_identity,  # Use unique identity
                audio_in_enabled=True,
                audio_out_enabled=True,
                vad_analyzer=SileroVADAnalyzer(
                    params=VADParams(
                        stop_secs=0.5,   # Faster speech completion detection  
                        start_secs=0.01,  # Ultra-fast speech detection
                        min_volume=0.01,  # Extremely sensitive volume detection
                        confidence=0.3    # Very low confidence threshold
                    )
                ),
            )
        )
        
        # Register the transport with connection manager
        connection_manager.register_connection(unique_identity, transport)

        # Initialize STT service with detailed debugging
        logger.info("🎤 Initializing OpenAI STT service with debugging...")
        
        class DebuggingSTTService(OpenAISTTService):
            """STT service wrapper with debug logging"""
            
            async def process_frame(self, frame: Frame, direction: FrameDirection):
                """Override process_frame to add debugging"""
                frame_type = frame.__class__.__name__
                
                if frame_type == 'UserAudioRawFrame' and hasattr(frame, 'audio'):
                    logger.info(f"📝 STT received UserAudioRawFrame: {len(frame.audio)} bytes")
                    
                    # Check if audio has any volume/content
                    import numpy as np
                    try:
                        # Convert audio bytes to numpy array for analysis
                        audio_data = np.frombuffer(frame.audio, dtype=np.int16)
                        volume_level = np.sqrt(np.mean(audio_data**2))
                        max_amplitude = np.max(np.abs(audio_data))
                        logger.info(f"📊 Audio analysis: volume_level={volume_level:.1f}, max_amplitude={max_amplitude}, samples={len(audio_data)}")
                        
                        # Check if audio is likely speech (lowered threshold for low-volume mics)
                        if volume_level > 0.3:  # Very low threshold for quiet microphones
                            logger.info(f"🎤✅ Audio detected: volume={volume_level:.1f}, amplitude={max_amplitude}")
                        else:
                            logger.warning(f"🎤⚠️ Audio volume extremely low: {volume_level:.1f}")
                            
                    except Exception as e:
                        logger.error(f"❌ Audio analysis failed: {e}")
                
                elif isinstance(frame, TextFrame):
                    logger.info(f"📝✅ STT produced TextFrame: '{frame.text}' (length: {len(frame.text)})")
                
                try:
                    # Call parent process_frame
                    result = await super().process_frame(frame, direction)
                    return result
                except Exception as e:
                    logger.error(f"❌ STT process_frame failed: {e}")
                    raise
        
        stt = DebuggingSTTService(
            api_key=config.OPENAI_API_KEY,
            model="whisper-1",
        )
        logger.info("✅ OpenAI STT service initialized with debugging")

        # Initialize OpenAI TTS service for reliable, complete audio
        logger.info("🎤 Initializing OpenAI TTS service for reliable audio...")
        tts = DebuggingTTSService(
            api_key=config.OPENAI_API_KEY,
            voice="alloy",  # Clear, natural voice
            model="tts-1",  # Reliable model with good quality
            aggregate_sentences=False  # Process text directly without aggregation
        )
        logger.info("✅ OpenAI TTS service initialized - reliable complete audio with debugging")

        # Initialize our intelligent processor
        intelligent_processor = IntelligentProcessor()

        # Create pipeline with intelligent processor
        pipeline = Pipeline([
            transport.input(),       # Audio input from LiveKit
            stt,                    # Speech to text (Whisper)
            intelligent_processor,   # Our intelligent AI processor
            tts,                    # Text to speech (Cartesia/OpenAI)
            transport.output(),     # Audio output to LiveKit
        ])

        logger.info("🔗 Pipeline created successfully")

        # Create and run the task
        task = PipelineTask(pipeline)

        logger.info(f"🚀 Agent connecting to room: {config.ROOM_NAME} as {unique_identity}")
        logger.info("🧠 Ready for intelligent conversation with OpenAI GPT-3.5-turbo")
        logger.info("🎵 Using OpenAI TTS for reliable, complete audio responses")
        logger.info("🎯 Target: Intelligent responses with complete audio playback")

        # Run the pipeline
        runner = PipelineRunner()
        await runner.run(task)

    except KeyboardInterrupt:
        logger.info("👋 Agent stopped by user")
        await cleanup_transport(transport, unique_identity)
    except Exception as e:
        logger.error(f"❌ Agent failed: {e}")
        import traceback
        traceback.print_exc()
        await cleanup_transport(transport, unique_identity)
        sys.exit(1)


async def cleanup_transport(transport, unique_identity=None):
    """Clean up LiveKit transport connection"""
    from connection_manager import connection_manager
    
    if transport:
        try:
            logger.info("🧹 Cleaning up LiveKit transport...")
            
            # Unregister from connection manager first
            if unique_identity:
                connection_manager.unregister_connection(unique_identity)
            
            # Disconnect from room
            if hasattr(transport, 'disconnect'):
                await transport.disconnect()
            
            logger.info("✅ Transport cleanup completed")
            
        except Exception as e:
            logger.warning(f"⚠️ Transport cleanup failed: {e}")
            
            # Emergency cleanup if normal cleanup fails
            if unique_identity:
                try:
                    await connection_manager.force_disconnect(unique_identity)
                except Exception as cleanup_error:
                    logger.error(f"❌ Emergency cleanup failed: {cleanup_error}")


if __name__ == "__main__":
    # Handle graceful shutdown
    def signal_handler(signum, frame):
        logger.info("Received shutdown signal, cleaning up...")
        sys.exit(0)

    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    # Run the async main function
    asyncio.run(main())
