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






class IntelligentProcessor(FrameProcessor):
    """Intelligent processor with OpenAI GPT-3.5-turbo and latency measurement"""

    def __init__(self, openai_api_key, transport):
        super().__init__()
        self.openai_api_key = openai_api_key
        self.transport = transport
        self.speech_start_time = None
        self.waiting_for_tts_audio = False
        self.conversation_history = []
        self.response_count = 0
        
        # Add system prompt for intelligent conversation
        system_prompt = (
            "You are a helpful, friendly AI assistant having a natural conversation. "
            "Keep your responses concise (1-2 sentences), engaging, and contextually relevant. "
            "Be conversational and helpful."
        )
        self.conversation_history.append({"role": "system", "content": system_prompt})
        
        logger.info("🧠 IntelligentProcessor initialized with direct GPT-3.5-turbo calls")
        logger.info("📊 Latency measurement enabled")

    async def process_frame(self, frame: Frame, direction: FrameDirection):
        """Process incoming frames with intelligent LLM responses and latency measurement"""
        frame_type = frame.__class__.__name__
        
        # Let parent handle the frame first
        await super().process_frame(frame, direction)
        
        # Track when user starts speaking for latency measurement
        if 'UserStartedSpeaking' in frame_type:
            self.speech_start_time = time.time()
            self.waiting_for_tts_audio = True
            logger.info("🎤🔥 USER STARTED SPEAKING - latency timer started")
        
        # Process text input from STT
        if isinstance(frame, TextFrame):
            user_text = frame.text.strip()
            logger.info(f"🎤📝 USER SPOKE: '{user_text}'")
            
            if user_text:
                await self._generate_intelligent_response(user_text)
            else:
                # Handle empty input
                response_frame = TextFrame("I didn't catch that. Could you repeat?")
                await self.push_frame(response_frame, FrameDirection.DOWNSTREAM)
        
        # Measure latency when TTS audio starts playing
        elif isinstance(frame, AudioRawFrame) and self.waiting_for_tts_audio and self.speech_start_time:
            end_time = time.time()
            latency_ms = (end_time - self.speech_start_time) * 1000
            
            logger.info(f"📊 LATENCY MEASURED: {latency_ms:.0f}ms (mouth-to-ear)")
            
            # Send latency data to UI via data channel
            await self._send_latency_to_ui(latency_ms)
            
            # Reset latency tracking
            self.waiting_for_tts_audio = False
            self.speech_start_time = None
        
        # Pass all other frames downstream
        elif not isinstance(frame, TextFrame):
            await self.push_frame(frame, direction)
    
    async def _generate_intelligent_response(self, user_text: str):
        """Generate intelligent response using direct OpenAI GPT-3.5-turbo API call"""
        try:
            self.response_count += 1
            
            # Add user message to conversation history
            self.conversation_history.append({"role": "user", "content": user_text})
            
            # Keep conversation history manageable (last 10 messages)
            if len(self.conversation_history) > 11:  # 1 system + 10 conversation messages
                # Keep system message and last 8 messages
                self.conversation_history = [self.conversation_history[0]] + self.conversation_history[-8:]
            
            logger.info(f"🧠⚙️ Generating intelligent response with direct GPT-3.5-turbo call...")
            
            # Make direct OpenAI API call
            from openai import AsyncOpenAI
            client = AsyncOpenAI(api_key=self.openai_api_key)
            
            response = await client.chat.completions.create(
                model="gpt-3.5-turbo",
                messages=self.conversation_history,
                max_tokens=100,
                temperature=0.7
            )
            
            ai_response = response.choices[0].message.content.strip()
            
            # Add AI response to conversation history
            self.conversation_history.append({"role": "assistant", "content": ai_response})
            
            logger.info(f"🧠✅ GPT Response: '{ai_response}'")
            
            # Send the intelligent response to TTS
            response_frame = TextFrame(ai_response)
            await self.push_frame(response_frame, FrameDirection.DOWNSTREAM)
            
        except Exception as e:
            logger.error(f"❌ Failed to generate intelligent response: {e}")
            # Fallback to simple response
            fallback_response = f"I understand you said '{user_text}'. Could you tell me more?"
            response_frame = TextFrame(fallback_response)
            await self.push_frame(response_frame, FrameDirection.DOWNSTREAM)
    
    async def _send_latency_to_ui(self, latency_ms: float):
        """Send latency metrics to the UI via LiveKit data channel"""
        try:
            from pipecat.frames.frames import TransportMessageFrame
            import json
            
            latency_data = {
                "type": "latency_update",
                "latency_ms": round(latency_ms, 1),
                "timestamp": time.time(),
                "response_count": self.response_count
            }
            
            # Convert to JSON string for transport
            message_json = json.dumps(latency_data)
            
            # Send via transport message frame (data channel)
            message_frame = TransportMessageFrame(message=message_json)
            await self.push_frame(message_frame, FrameDirection.DOWNSTREAM)
            
            logger.info(f"📊 Latency data sent to UI: {latency_ms:.1f}ms")
            
        except Exception as e:
            logger.warning(f"⚠️ Failed to send latency data to UI: {e}")



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
                        stop_secs=1.0,   # Normal speech completion detection  
                        start_secs=0.2,   # Normal speech detection
                        min_volume=0.6,   # Normal volume detection
                        confidence=0.6    # Normal confidence threshold
                    )
                ),
            )
        )
        
        # Register the transport with connection manager
        connection_manager.register_connection(unique_identity, transport)

        # Initialize STT service
        logger.info("🎤 Initializing OpenAI STT service...")
        stt = OpenAISTTService(
            api_key=config.OPENAI_API_KEY,
            model="whisper-1",
        )
        logger.info("✅ OpenAI STT service initialized")

        # Initialize OpenAI TTS service with complete response processing
        logger.info("🔊 Initializing OpenAI TTS service...")
        tts = OpenAITTSService(
            api_key=config.OPENAI_API_KEY,
            voice="alloy",
            model="tts-1",
            aggregate_sentences=False  # Process complete text without sentence splitting
        )
        logger.info("✅ OpenAI TTS service initialized")

        # Initialize our intelligent processor with direct OpenAI API calls
        intelligent_processor = IntelligentProcessor(config.OPENAI_API_KEY, transport)

        # Create simplified pipeline - IntelligentProcessor handles GPT directly
        pipeline = Pipeline([
            transport.input(),       # Audio input from LiveKit
            stt,                    # Speech to text (Whisper)
            intelligent_processor,  # Intelligent processor with direct GPT calls
            tts,                    # Text to speech (OpenAI)
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
