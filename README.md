# LiveKit + Pipecat Demo

Real-time voice conversation AI agent with intelligent responses using LiveKit for WebRTC transport and Pipecat for AI processing pipeline.

## 🎆 Features

- 🎤️ **Real-time Audio**: Bidirectional streaming via LiveKit WebRTC
- 🤖 **Intelligent Agent**: OpenAI GPT-3.5-turbo powered conversational responses  
- ⚡ **Latency Measurement**: Real-time end-to-end latency monitoring (target <600ms)
- 🔄 **Auto-Recovery**: Automatic restart with connection management
- 📅 **Performance Metrics**: Live latency stats, connection quality, and measurement counts
- 🎯 **Clean UI**: Professional interface with real-time audio monitoring
- 🔊 **Enhanced TTS**: OpenAI TTS for reliable, complete audio responses
- 🚫vs **Connection Management**: Prevents "participant already exists" errors
- 👀 **Debug Logging**: Comprehensive logging for speech detection and processing
- 🔍 **Ultra-Sensitive VAD**: Voice Activity Detection optimized for various microphone levels

## Quick Start

### 1. Prerequisites
- **macOS/Linux** with Docker installed
- **Python 3.11+** 
- **OpenAI API Key** (get from https://platform.openai.com)

### 2. Setup Environment
```bash
# Clone the repository
git clone <repository-url>
cd livekit-pipecat-demo

# Copy and edit environment file
cp .env.template .env

# Edit .env file and add your OpenAI API key:
OPENAI_API_KEY=sk-your-openai-api-key-here

# Optional: Add Cartesia TTS for faster response times
CARTESIA_API_KEY=your-cartesia-api-key-here

# Install Python dependencies
cd agent && pip install -r requirements.txt
```

### 3. Start Everything
```bash
# Single command to start all services
./run.sh start
```

### 4. Test Voice Conversation
1. Open **http://localhost:8000** in your browser
2. Click **"Connect"** and grant microphone permissions  
3. **Speak clearly**: Say something like "Hello, can you tell me a joke?"
4. **Wait for response**: Agent will provide an intelligent, contextual response
5. **Check metrics**: Watch the **Performance Metrics** section for:
   - **Current latency** in milliseconds
   - **Measurement count** (increments with each interaction)
   - **Connection quality** indicator

### 5. Expected Results
- **Intelligent responses**: Agent provides contextual, helpful answers using GPT-3.5-turbo
- **Typical latency**: 1-5 seconds (with optimizations)
- **UI updates**: Latency values appear automatically after agent response
- **Audio feedback**: Clear speech synthesis from OpenAI TTS
- **Visual feedback**: Comprehensive logs show processing pipeline in real-time
- **Conversation continuity**: Agent maintains context across multiple interactions

## Commands

```bash
./run.sh start       # Start all services (LiveKit + Redis + Agent + HTTP server)
./run.sh stop        # Stop all services
./run.sh restart     # Restart all services
./run.sh status      # Show service status
./run.sh agent-only  # Start only the supervised agent
./run.sh logs <service>  # View logs (agent, supervisor, livekit, redis, http)
```

### Log Commands
```bash
./run.sh logs agent      # View agent processing logs with STT/LLM/TTS details
./run.sh logs supervisor # View auto-restart supervisor logs  
./run.sh logs livekit    # View LiveKit server logs
./run.sh logs redis      # View Redis server logs
./run.sh logs http       # View HTTP server logs
```

## Configuration

### Required API Keys (.env file)
```bash
OPENAI_API_KEY=sk-...          # Required: Get from https://platform.openai.com
```

### Optional Settings (pre-configured)
```bash
# LiveKit (uses local Docker server)
LIVEKIT_URL=ws://localhost:7880
LIVEKIT_API_KEY=devkey
LIVEKIT_API_SECRET=secret

# Room settings
ROOM_NAME=pipecat-demo
AGENT_NAME=PipecatAgent
ECHO_SUFFIX=" got it"
```

### Default Ports
- **LiveKit Server**: localhost:7880
- **Web Client**: localhost:8000
- **Redis**: localhost:6379

## Architecture

```
[Browser Client] ↔ [LiveKit Server] ↔ [Pipecat Agent]
       ↑              ↑                     ↓
  [Microphone]    [Docker]         [AI Pipeline: STT → GPT-3.5 → TTS]  
       ↑                                    ↓
  [Speakers] ←─────────────────────────────────────
```

### Core Components

- **LiveKit Transport**: Handles WebRTC connections, media streaming, and data channels
- **Pipecat Agent**: Orchestrates AI pipeline (STT → LLM → TTS) with frame-based architecture
- **Service Manager**: Unified lifecycle management for all services with health monitoring
- **Supervisor System**: Auto-restart capability for crash recovery
- **Connection Manager**: Prevents "participant already exists" errors with unique identity generation

## Unified Service Management

All services are managed as a single unit:
- **Docker Services**: LiveKit server + Redis (automatic dependency management)
- **Python Services**: HTTP server + Pipecat agent (with supervisor)
- **Health Monitoring**: Continuous health checks for all services
- **Auto-Recovery**: Failed services are automatically restarted
- **Dependency Management**: Services start in correct order
- **Unified Logging**: All logs in one place
- **Graceful Shutdown**: Clean termination of all services

## Troubleshooting

### Quick Diagnostics
```bash
# Check all service status
./run.sh status

# View real-time agent logs
./run.sh logs agent

# Check if client can connect
curl http://localhost:8000

# Test LiveKit server
curl http://localhost:7880
```

### Testing Checklist

**✅ Before Testing:**
1. Services running: `./run.sh status` shows all green ✅
2. OpenAI API key set in `.env` file
3. Browser supports WebRTC (Chrome/Firefox recommended)
4. Microphone permissions granted

**🎤 During Testing:**
1. Speak clearly and wait for complete response
2. Check browser console for any errors
3. Watch agent logs: `./run.sh logs agent` for processing steps
4. Look for latency measurements in logs and UI

### Common Issues

**"Agent not hearing my voice"**:
- **Check microphone volume**: System Preferences → Sound → Input (set to maximum)
- **Speak loudly**: Agent needs sufficient audio volume for speech detection
- **Check audio levels**: Run `python test_mic.py` to verify microphone is working
- **Browser permissions**: Ensure microphone access is granted
- **Look for audio logs**: Should see `🎤✅ Audio detected` in agent logs
- **Audio threshold**: Agent requires volume_level > 0.3 for speech detection

**"Participant already exists" error**:
- **Fixed automatically**: System now generates unique identities to prevent conflicts
- **Manual fix**: Restart services with `./run.sh restart`
- **Check logs**: Look for connection cleanup messages

**"No intelligent response"**:
- **Check OpenAI API key**: Must be valid with sufficient credits
- **Look for LLM errors**: Check agent logs for "OpenAI LLM response time"
- **Network issues**: Verify internet connection to OpenAI API
- **Fallback responses**: Agent provides intelligent fallbacks if API fails

**"No audio output from agent"**:
- **Check TTS processing**: Look for "🔊 TTS Processing" in logs
- **OpenAI TTS errors**: Agent uses OpenAI TTS for reliable audio generation
- **Browser audio**: Check browser audio settings and volume
- **Audio element**: Look for "Audio track attached and playing" in browser logs

**"Docker services not starting"**:
- **Port conflicts**: System automatically manages Docker ports (7880, 7881, 6379, 50500-50600)
- **Redis issues**: Fixed - system properly starts both LiveKit and Redis containers
- **Check status**: `./run.sh status` shows detailed service health
- **Clean restart**: `./run.sh restart` performs full cleanup and restart

### Debug Mode
```bash
# Watch live agent processing
tail -f /tmp/pipecat_agent.log

# Monitor all logs simultaneously
./run.sh logs agent & ./run.sh logs supervisor &
```

## Performance Expectations

### Latency Measurements
- **Target**: <600ms end-to-end latency
- **Typical**: 1-15 seconds (due to OpenAI API processing time)
- **Components**:
  - Speech detection: ~300ms
  - OpenAI Whisper STT: 1-5 seconds  
  - Text processing: <10ms
  - OpenAI TTS generation: 1-8 seconds
  - Audio playback: <100ms

### UI Performance Indicators

**Performance Metrics Section:**
```
📊 Performance Metrics
┌─────────────┬─────────────┬─────────────┐
│ Current (ms)│Measurements │  Quality    │
│   2,450     │      3      │ Excellent   │
└─────────────┴─────────────┴─────────────┘
```

- **Current (ms)**: Latest end-to-end latency measurement
- **Measurements**: Total number of successful interactions
- **Quality**: LiveKit connection quality (Excellent/Good/Poor)

**Color Coding:**
- 🟢 **Green** (<300ms): Excellent latency
- 🟡 **Yellow** (300-600ms): Good latency  
- 🔴 **Red** (>600ms): High latency

**Activity Logs:**
Real-time processing steps showing:
- User speech detection
- Agent connection status
- Processing completion
- Latency measurements

## Development

### Project Structure
```
livekit-pipecat-demo/
├── agent/
│   ├── spawn_agent.py      # Main agent with latency measurement
│   ├── supervisor.py       # Auto-restart system
│   ├── config.py          # Configuration settings
│   ├── requirements.txt    # Python dependencies
│   └── venv/              # Virtual environment
├── client/
│   ├── index.html         # Clean web interface
│   └── client.js          # LiveKit client with data channel support
├── run.sh                 # Main control script
├── docker-compose.yml     # LiveKit server + Redis
├── livekit.yaml          # LiveKit server configuration
├── .env.template         # Environment template
├── .env                   # Your API keys (create from template)
└── README.md             # This file
```

### Key Components

**Agent (`spawn_agent.py`)**:
- EchoProcessor with end-to-end latency measurement
- OpenAI STT (Whisper) and TTS integration
- Data channel communication to send latency to UI
- Enhanced debugging and error handling

**Client (`client.js`)**:
- LiveKit SDK integration
- Real-time performance metrics display
- Data channel reception for latency updates
- Clean, professional UI design

**Infrastructure**:
- Docker-based LiveKit server
- Supervised Python agent with auto-restart
- Unified service management script

## Testing Success Criteria

### ✅ What Should Work
1. **Service Startup**: All services start without errors
2. **Client Connection**: Browser connects to LiveKit room successfully
3. **Audio Pipeline**: Microphone → Agent → Speakers works end-to-end
4. **Speech Recognition**: User speech is transcribed correctly
5. **Agent Response**: Agent responds with original text + "got it"
6. **Latency Measurement**: End-to-end latency appears in UI after each interaction
7. **UI Updates**: Performance metrics update automatically
8. **Data Channel**: Latency data transmits from agent to browser

### 📊 Expected Metrics
- **Latency Range**: 1,000ms - 15,000ms (1-15 seconds)
- **Success Rate**: >95% of interactions should complete
- **Audio Quality**: Clear speech synthesis output
- **UI Responsiveness**: Metrics update within 1 second of agent response

### 🔴 Known Limitations
- **Latency**: Current setup uses OpenAI API which adds 1-10+ second delays
- **Internet Dependency**: Requires stable internet for OpenAI API calls
- **Browser Support**: Requires WebRTC-compatible browser (Chrome/Firefox recommended)
- **Single User**: Designed for one user per room
- **Development Mode**: Uses development LiveKit configuration

### Manual Setup (Advanced)
If you prefer manual control over the automated script:

```bash
# 1. Start LiveKit server
docker-compose up -d

# 2. Install Python dependencies
cd agent && pip install -r requirements.txt

# 3. Start agent (with supervisor)
python supervisor.py &

# 4. Start web server
cd ../client && python -m http.server 8000 &
```

## Support & Feedback

### Reporting Issues
When reporting issues, please include:

1. **System Info**:
   - Operating System (macOS/Linux)
   - Browser type and version
   - Python version

2. **Service Status**:
   ```bash
   ./run.sh status
   ```

3. **Relevant Logs**:
   ```bash
   # Last 20 lines of agent logs
   tail -20 /tmp/pipecat_agent.log
   
   # Browser console errors (if any)
   ```

4. **Steps to Reproduce**:
   - What you did
   - What you expected
   - What actually happened
   - Screenshots of UI (if helpful)

### Testing Results Template
```markdown
## Test Results

**Environment**:
- OS: [macOS/Linux]
- Browser: [Chrome/Firefox] version X.X
- Python: 3.11.x

**Service Status**: [All Green ✅ / Issues ❌]

**Latency Results**:
- Connection: [Success/Failed]
- Audio Response: [Yes/No] 
- Latency Display: [Yes/No]
- Typical Latency: [X,XXX ms]
- Measurement Count: [X]

**Issues Found**: 
[None / List any problems]

**Additional Notes**:
[Any other observations]
```

## Recent Improvements

### 🎯 **Latest Updates (December 2025)**

#### **Intelligent Agent System**
- ✅ **GPT-3.5-turbo Integration**: Replaced echo processor with full OpenAI LLM for contextual conversations
- ✅ **Conversation Context**: Maintains conversation history for natural, continuous interactions
- ✅ **Intelligent Fallbacks**: Provides helpful responses even when OpenAI API fails

#### **Connection Management**
- ✅ **Unique Identity Generation**: Prevents "participant already exists" errors with nanosecond-precision IDs
- ✅ **Connection Cleanup**: Automatic cleanup of stale LiveKit connections
- ✅ **Emergency Recovery**: Force disconnect capabilities for connection conflicts

#### **Enhanced Service Management**
- ✅ **Redis Integration**: Proper Docker management of both LiveKit and Redis services
- ✅ **Port Conflict Resolution**: Automatic port management to avoid conflicts (including Microsoft Teams)
- ✅ **Service Health Monitoring**: Detailed status reporting for all components
- ✅ **Enhanced Logging**: Added Redis logs access and improved service debugging

#### **Audio Processing Improvements**
- ✅ **Ultra-Sensitive VAD**: Optimized Voice Activity Detection for various microphone levels
- ✅ **Audio Level Analysis**: Real-time audio volume analysis and logging
- ✅ **Microphone Testing**: Added `test_mic.py` utility for microphone troubleshooting
- ✅ **Debug Logging**: Comprehensive STT/LLM/TTS pipeline logging

#### **Stability & Reliability**
- ✅ **Supervisor Enhancements**: Connection manager integration in restart process
- ✅ **Error Handling**: Improved exception handling and recovery mechanisms
- ✅ **Graceful Cleanup**: Proper resource cleanup on shutdown and restart

### 🔧 **Configuration Optimizations**
- **VAD Parameters**: `confidence=0.3, start_secs=0.01, min_volume=0.01` for maximum sensitivity
- **Audio Threshold**: Lowered to `volume_level > 0.3` for quiet microphones
- **UDP Ports**: Changed to 50500-50600 range to avoid conflicts
- **Connection Timeout**: Optimized for faster speech detection and processing

## License

MIT License
