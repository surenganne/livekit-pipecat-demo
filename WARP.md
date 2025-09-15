# WARP.md

This file provides guidance to WARP (warp.dev) when working with code in this repository.

## Project Overview

This is a real-time voice conversation AI agent demo that integrates **LiveKit** (WebRTC transport) with **Pipecat** (AI processing pipeline). The system demonstrates end-to-end latency measurement for voice AI applications with an intelligent agent that provides contextual responses using OpenAI GPT-3.5-turbo and optimized TTS processing.

## Architecture

The system follows a **separated transport + AI processing** architecture:

```
[Browser Client] ↔ [LiveKit Server] ↔ [Pipecat Agent]
       ↑              ↑                     ↓
  [Microphone]    [Docker]         [AI Pipeline: STT → Echo → TTS]  
       ↑                                    ↓
  [Speakers] ←─────────────────────────────────
```

### Core Components

- **LiveKit Transport**: Handles WebRTC connections, media streaming, and data channels
- **Pipecat Agent**: Orchestrates AI pipeline (STT → Processing → TTS) with frame-based architecture
- **Service Manager**: Unified lifecycle management for all services with health monitoring
- **Supervisor System**: Auto-restart capability for crash recovery

### Key Integration Points

1. **Frame Processing Pipeline**: `spawn_agent.py` contains the core `IntelligentProcessor` with GPT-3.5-turbo integration and latency measurement
2. **Data Channel Communication**: Latency metrics are sent to UI via `TransportMessageFrame`
3. **Service Dependencies**: Agent depends on LiveKit server being healthy
4. **TTS Optimization**: Automatic fallback from Cartesia (fast) to OpenAI TTS

## Common Development Commands

### Service Management
```bash
# Start all services (recommended)
./run.sh start

# Stop all services
./run.sh stop

# Restart all services
./run.sh restart

# Check service status
./run.sh status

# Start only the supervised agent (if LiveKit already running)
./run.sh agent-only
```

### Log Monitoring
```bash
# View real-time agent processing logs
./run.sh logs agent

# View supervisor auto-restart logs
./run.sh logs supervisor

# View LiveKit server logs
./run.sh logs livekit

# View HTTP server logs
./run.sh logs http

# Direct log file access
tail -f /tmp/pipecat_agent.log
tail -f /tmp/agent_supervisor.log
```

### Development Workflow
```bash
# Setup environment
cp .env.example .env
# Edit .env with your OpenAI and Cartesia API keys

# Install Python dependencies
cd agent && pip install -r requirements.txt

# Test improvements
python test_improvements.py

# Start Docker services only
docker-compose up -d

# Manual agent development (bypasses supervisor)
cd agent && python spawn_agent.py
```

### Testing & Debugging
```bash
# Quick health check
curl http://localhost:8000  # Client
curl http://localhost:7880  # LiveKit server

# Check Docker services
docker-compose ps

# Test web client
open http://localhost:8000

# Debug agent without supervisor
cd agent && python -c "import config; print('Config loaded successfully')"
```

## Configuration

### Environment Variables (.env)
```bash
# Required
OPENAI_API_KEY=sk-your-openai-api-key
CARTESIA_API_KEY=your-cartesia-api-key

# Optional (pre-configured for local development)
LIVEKIT_URL=ws://localhost:7880
LIVEKIT_API_KEY=devkey
LIVEKIT_API_SECRET=secret
ROOM_NAME=pipecat-demo
```

### Key Configuration Files
- `agent/config.py`: Main configuration with API keys, room settings, agent behavior
- `livekit.yaml`: LiveKit server configuration for Docker
- `docker-compose.yml`: Infrastructure services (LiveKit + Redis)
- `agent/requirements.txt`: Python dependencies with specific Pipecat version

## Development Guidelines

### Working with the Agent Pipeline

The agent uses a **frame-based processing model**:
1. Audio input flows through `transport.input()`
2. STT converts to `TextFrame` (Whisper)
3. `IntelligentProcessor` generates contextual response using GPT-3.5-turbo
4. TTS converts back to `AudioRawFrame` (Cartesia for speed, OpenAI fallback)
5. Audio output flows through `transport.output()`

### Latency Measurement System

The system tracks **mouth-to-ear latency** in `IntelligentProcessor`:
- `speech_start_time`: Set when user starts speaking
- `waiting_for_tts_audio`: Flag to track processing state  
- End-to-end measurement: From speech detection to TTS audio generation
- Includes LLM processing time in measurements
- Data sent to UI via `TransportMessageFrame`

### Performance Optimizations

**TTS Speed Enhancement**:
- Primary: Cartesia TTS (~200-500ms latency)
- Fallback: OpenAI TTS (~1-8s latency)
- Automatic service selection based on API key availability

**VAD (Voice Activity Detection) Tuning**:
- Speech start: 0.2s (33% faster detection)
- Speech end: 1.0s (33% faster processing)
- Voice sensitivity: 0.5 (more responsive)

**LLM Response Optimization**:
- Model: GPT-3.5-turbo (fast, cost-effective)
- Max tokens: 100 (concise responses)
- Timeout: 10s (fail-fast for better UX)
- Conversation context maintained

### Service Architecture Patterns

**Three-tier service management**:
1. **Docker Services**: LiveKit + Redis (infrastructure)
2. **Python Services**: HTTP server + Pipecat agent
3. **Supervision Layer**: Automatic restart and health monitoring

### Error Handling

The system implements **multi-layer error recovery**:
- **Transport Level**: LiveKit connection retries
- **Agent Level**: Frame processing error handling in `spawn_agent.py`
- **Process Level**: Automatic restart via `supervisor.py`
- **Service Level**: Health checks and dependency management

### Common Issues & Solutions

**"Agent not processing audio"**:
- Check OpenAI API key validity and credits
- Verify LiveKit server is running: `docker-compose ps`
- Check agent logs for STT/TTS errors

**"High latency (>15 seconds)"**:
- Normal for OpenAI API during high load
- Consider switching to Cartesia TTS for lower latency
- Check internet connection stability

**"Connection failed"**:
- Ensure Docker is running
- Check port availability (7880, 8000, 6379)
- Restart services: `./run.sh restart`

## File Structure Context

```
livekit-pipecat-demo/
├── agent/
│   ├── spawn_agent.py      # Main agent with IntelligentProcessor and GPT-3.5-turbo
│   ├── supervisor.py       # Auto-restart system with health checks
│   ├── config.py          # Configuration with API keys and settings
│   └── requirements.txt    # Python dependencies (Pipecat, LiveKit, OpenAI, Cartesia)
├── client/
│   ├── index.html         # Web UI with real-time metrics display
│   └── client.js          # LiveKit client with data channel support
├── run.sh                 # Main service management script
├── test_improvements.py   # Test script for performance improvements
├── docker-compose.yml     # LiveKit server + Redis infrastructure
├── livekit.yaml          # LiveKit server configuration
└── .env                   # API keys (OpenAI + Cartesia) and environment variables
```

## Performance Expectations

### Optimized Performance (with Cartesia TTS)
- **Target Latency**: <600ms end-to-end (achievable with optimizations)
- **Typical Latency**: 1-3 seconds (significant improvement from 1-15s)
- **Component Breakdown**:
  - Speech detection: ~200ms (VAD optimized)
  - OpenAI Whisper STT: 1-5s
  - GPT-3.5-turbo LLM: 0.5-2s
  - Cartesia TTS: 200-500ms (3-5x faster than OpenAI)
  - Audio playback: <100ms

### Fallback Performance (OpenAI TTS only)
- **Typical Latency**: 3-10 seconds
- **TTS bottleneck**: OpenAI TTS (1-8s)

### Key Improvements
- **50-70% latency reduction** with Cartesia TTS
- **Intelligent responses** replace simple echo
- **33% faster** speech detection with optimized VAD
- **Contextual conversation** with maintained history

The demo now balances **measurement accuracy** with **production-ready performance**, making it suitable for real-world voice AI applications.
