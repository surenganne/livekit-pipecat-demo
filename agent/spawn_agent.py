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
    """Generate a LiveKit access token for the agent"""
    from livekit import api

    # Create access token
    token = api.AccessToken(config.LIVEKIT_API_KEY, config.LIVEKIT_API_SECRET) \
        .with_identity(config.AGENT_NAME) \
        .with_name(config.AGENT_NAME) \
        .with_grants(api.VideoGrants(
            room_join=True,
            room=config.ROOM_NAME,
            can_publish=True,
            can_subscribe=True
        ))

    return token.to_jwt()


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
            logger.info(f"🎵 TTS processing TextFrame: '{frame.text}' (length: {len(frame.text)})")
            logger.debug(f"🔍 Frame direction: {direction}")
            logger.debug(f"🔍 _aggregate_sentences: {self._aggregate_sentences}")
        
        try:
            # Call the parent process_frame method
            result = await super().process_frame(frame, direction)
            
            if isinstance(frame, TextFrame):
                logger.info(f"🎵 TTS completed processing TextFrame: '{frame.text}'")
            
            return result
        except Exception as e:
            if isinstance(frame, TextFrame):
                logger.error(f"❌ TTS process_frame failed for TextFrame: '{frame.text}' - {e}")
            else:
                logger.error(f"❌ TTS process_frame failed for {frame_type} - {e}")
            raise
    
    async def _process_text_frame(self, frame: TextFrame):
        """Override _process_text_frame to add debugging"""
        logger.debug(f"🔍 _process_text_frame called with: '{frame.text}'")
        logger.debug(f"🔍 _aggregate_sentences: {self._aggregate_sentences}")
        
        text = None
        if not self._aggregate_sentences:
            text = frame.text
            logger.debug(f"🔍 Direct text assignment: '{text}'")
        else:
            text = await self._text_aggregator.aggregate(frame.text)
            logger.debug(f"🔍 Aggregated text: '{text}'")
        
        logger.debug(f"🔍 Final text for TTS: '{text}'")
        if text:
            logger.info(f"🎵 Calling _push_tts_frames with: '{text}'")
            await self._push_tts_frames(text)
        else:
            logger.warning(f"⚠️ Text is empty, not calling _push_tts_frames")
    
    async def _push_tts_frames(self, text: str):
        """Override _push_tts_frames to add debugging"""
        logger.info(f"🎵 _push_tts_frames called with: '{text}' (length: {len(text)})")
        
        # Call parent method
        await super()._push_tts_frames(text)
    
    async def run_tts(self, text: str):
        """Override run_tts to add debugging"""
        logger.info(f"🎵 TTS run_tts called with text: '{text}' (length: {len(text)})")
        try:
            result = super().run_tts(text)  # This returns an async generator
            logger.info(f"🎵 TTS run_tts returned generator successfully")
            return result
        except Exception as e:
            logger.error(f"❌ TTS run_tts failed: {e}")
            raise


class EchoProcessor(FrameProcessor):
    """Simple processor that adds 'got it' to user input"""

    def __init__(self):
        super().__init__()
        self.response_suffix = config.ECHO_SUFFIX
        self.speech_start_time = None
        self.waiting_for_tts_audio = False  # Flag to know when we're expecting TTS audio
        self.tts_text_sent = None  # Track what text was sent to TTS
        self.latency_measurements = []  # Store latency measurements
        self.max_measurements = 20  # Keep last 20 measurements for averaging



    async def process_frame(self, frame: Frame, direction: FrameDirection):
        """Process incoming frames"""
        # Log important frames only (not continuous audio frames)
        frame_type = frame.__class__.__name__
        if frame_type not in ['UserAudioRawFrame', 'AudioRawFrame']:
            logger.debug(f"🔄 EchoProcessor received: {frame_type}")
        elif frame_type == 'AudioRawFrame':
            logger.debug(f"🎵 AudioRawFrame received in EchoProcessor")

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
            logger.info(f"📝 Received TextFrame: '{user_text}' (length: {len(user_text)})")

            if user_text:
                # Calculate latency if we have a start time
                if self.speech_start_time:
                    latency_ms = (time.time() - self.speech_start_time) * 1000
                    logger.info(f"⏱️  STT Latency: {latency_ms:.1f}ms")

                # Create response with suffix - remove problematic punctuation for TTS
                # Replace sentence-ending punctuation to avoid TTS splitting
                clean_text = user_text.replace('?', '').replace('!', '').replace('.', '')
                response_text = f"{clean_text} got it"
                logger.info(f"💬 User: '{user_text}' -> Agent: '{response_text}'")

                # Send text to TTS service for speech synthesis
                logger.info(f"🎵 Sending to TTS: '{response_text}' (length: {len(response_text)})")
                logger.debug(f"🔍 About to create TextFrame with text: '{response_text}'")

                # Create TextFrame and send to TTS pipeline
                response_frame = TextFrame(response_text)
                logger.debug(f"🔍 TextFrame created: {type(response_frame)} with text: '{response_frame.text}'")
                
                # Mark that we're waiting for TTS audio generation
                self.waiting_for_tts_audio = True
                self.tts_text_sent = response_text
                logger.info(f"🎙️ Now waiting for TTS audio for: '{response_text}'")
                
                await self.push_frame(response_frame, FrameDirection.DOWNSTREAM)
                logger.info(f"✅ TextFrame sent to TTS pipeline (frame id: {id(response_frame)})")
                logger.debug(f"🔍 Frame pushed downstream to TTS service")

                # Note: Latency will be measured when TTS completes audio generation
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


async def main():
    """Main function to start the agent"""
    logger.info("🤖 Starting LiveKit + Pipecat Demo Agent")

    # Validate configuration
    if not config.OPENAI_API_KEY or config.OPENAI_API_KEY == "your-openai-api-key":
        logger.error("❌ Please set your OpenAI API key in config.py")
        return

    if not config.LIVEKIT_URL or not config.LIVEKIT_API_KEY or not config.LIVEKIT_API_SECRET:
        logger.error("❌ Please set your LiveKit credentials in config.py")
        return

    try:
        # Generate access token
        token = generate_access_token()

        # Initialize transport with VAD
        transport = LiveKitTransport(
            url=config.LIVEKIT_URL,
            token=token,
            room_name=config.ROOM_NAME,
            params=LiveKitParams(
                participant_name=config.AGENT_NAME,
                audio_in_enabled=True,
                audio_out_enabled=True,
                vad_analyzer=SileroVADAnalyzer(
                    params=VADParams(
                        stop_secs=1.5,   # Wait longer before considering speech ended (allows natural pauses)
                        start_secs=0.3,   # Slightly longer to avoid false starts
                        min_volume=0.6    # Lower threshold for voice detection
                    )
                ),
            )
        )

        # Initialize STT service
        stt = OpenAISTTService(
            api_key=config.OPENAI_API_KEY,
            model="whisper-1",
        )

        # Initialize OpenAI TTS service (fixed configuration)
        logger.info("🎤 Initializing OpenAI TTS service")
        try:
            tts = OpenAITTSService(
                api_key=config.OPENAI_API_KEY,
                voice="alloy",  # Clear, natural voice
                model="tts-1",  # Explicitly specify model
                aggregate_sentences=False,  # CRITICAL: Disable sentence aggregation for direct text
            )
            logger.info("✅ OpenAI TTS service initialized successfully")
        except Exception as e:
            logger.error(f"❌ Failed to initialize OpenAI TTS service: {e}")
            raise

        # Initialize our echo processor
        echo_processor = EchoProcessor()

        # Create pipeline with TTS service
        pipeline = Pipeline([
            transport.input(),   # Audio input from LiveKit
            stt,                # Speech to text
            echo_processor,     # Our echo logic (generates TextFrames)
            tts,                # Text to speech (OpenAI)
            transport.output(), # Audio output to LiveKit
        ])

        logger.info("🔗 Pipeline created successfully")

        # Create and run the task
        task = PipelineTask(pipeline)

        logger.info(f"🚀 Agent connecting to room: {config.ROOM_NAME}")
        logger.info("💬 Ready to receive audio and respond with echo + 'got it'")

        # Run the pipeline
        runner = PipelineRunner()
        await runner.run(task)

    except KeyboardInterrupt:
        logger.info("👋 Agent stopped by user")
    except Exception as e:
        logger.error(f"❌ Agent failed: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    # Handle graceful shutdown
    def signal_handler(signum, frame):
        logger.info("Received shutdown signal, cleaning up...")
        sys.exit(0)

    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    # Run the async main function
    asyncio.run(main())
