# LiveKit + Pipecat Demo

Real-time voice conversation with AI agent using LiveKit for transport and Pipecat for AI processing.

## Features

- 🎙️ **Real-time Audio**: Bidirectional streaming via LiveKit
- 🤖 **AI Agent**: Echo agent that responds with your words + "got it"
- ⚡ **Latency Measurement**: Real-time end-to-end latency monitoring displayed in UI
- 🔄 **Auto-Recovery**: Automatic restart on crashes
- 📊 **Performance Metrics**: Live latency stats, connection quality, and measurement counts
- 🎯 **Clean UI**: Simple, professional interface optimized for latency testing

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
```

### 3. Start Everything
```bash
# Single command to start all services
./run.sh start
```

### 4. Test Latency Measurement
1. Open **http://localhost:8000** in your browser
2. Click **"Join Room"** and grant microphone permissions  
3. **Speak clearly**: Say something like "Hello, can you hear me?"
4. **Wait for response**: Agent will echo back with "+ got it"
5. **Check metrics**: Watch the **Performance Metrics** section for:
   - **Current latency** in milliseconds
   - **Measurement count** (increments with each interaction)
   - **Connection quality** indicator

### 5. Expected Results
- **Typical latency**: 1-15 seconds (depends on OpenAI API response time)
- **UI updates**: Latency values appear automatically after agent response
- **Audio feedback**: You should hear the agent's voice response
- **Visual feedback**: Logs show processing steps in real-time

## Commands

```bash
./run.sh start       # Start all services (LiveKit + Agent + HTTP server)
./run.sh stop        # Stop all services
./run.sh restart     # Restart all services
./run.sh status      # Show service status
./run.sh agent-only  # Start only the supervised agent
./run.sh logs <service>  # View logs (agent, supervisor, livekit, http)
```

### Log Commands
```bash
./run.sh logs agent      # View agent processing logs
./run.sh logs supervisor # View auto-restart supervisor logs  
./run.sh logs livekit    # View LiveKit server logs
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
[Browser] ↔ [LiveKit Server] ↔ [Pipecat Agent]
    ↑             ↑                    ↓
[Microphone]  [Docker]         [AI Pipeline: STT → Echo → TTS]
    ↑                                  ↓
[Speakers] ←────────────────────────────────────
```

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

**"Latency not showing in UI"**:
- Check browser console for data reception logs
- Look for "TransportMessageFrame" in agent logs
- Verify agent is processing: look for "END-TO-END LATENCY" in logs
- Try refreshing the page and rejoining

**"No audio response"**:
- Check OpenAI API key is valid and has credits
- Look for TTS errors in agent logs
- Verify audio permissions in browser
- Check if agent shows "Bot started speaking" in logs

**"Connection failed"**:
- Ensure Docker is running: `docker ps`
- Restart services: `./run.sh restart`
- Check port availability (7880, 8000)
- Look for "Connected to pipecat-demo" in agent logs

**"High latency (>15 seconds)**":
- Normal for OpenAI API during high load
- Check internet connection
- Monitor OpenAI API status page

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

## License

MIT License