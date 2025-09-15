#!/usr/bin/env python3

"""
Agent Process Supervisor

This script monitors the Pipecat agent and automatically restarts it when:
- The process crashes or stops
- The process becomes unresponsive
- Connection errors occur
- Memory usage gets too high

Features:
- Automatic restart with exponential backoff
- Health checks and monitoring
- Detailed logging
- Graceful shutdown handling
"""

import asyncio
import subprocess
import signal
import sys
import os
import time
import logging
import psutil
from pathlib import Path

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('/tmp/agent_supervisor.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

class AgentSupervisor:
    def __init__(self):
        self.agent_process = None
        self.restart_count = 0
        self.max_restarts = 10
        self.restart_delay = 1  # Start with 1 second delay
        self.max_restart_delay = 60  # Maximum 60 seconds delay
        self.last_restart_time = 0
        self.is_shutting_down = False
        
        # Agent configuration
        self.agent_script = Path(__file__).parent / "spawn_agent.py"
        self.log_file = "/tmp/pipecat_agent.log"
        self.env_file = Path(__file__).parent.parent / ".env"
        
        # Health check parameters
        self.health_check_interval = 30  # Check every 30 seconds
        self.max_memory_mb = 500  # Restart if memory usage > 500MB
        self.max_silent_time = 120  # Restart if no log activity for 2 minutes
        
    def load_environment(self):
        """Load environment variables from .env file"""
        if self.env_file.exists():
            with open(self.env_file) as f:
                for line in f:
                    if line.strip() and not line.startswith('#'):
                        key, value = line.strip().split('=', 1)
                        os.environ[key] = value
            logger.info(f"✅ Environment loaded from {self.env_file}")
        else:
            logger.warning(f"⚠️ Environment file not found: {self.env_file}")
    
    def start_agent(self):
        """Start the Pipecat agent process"""
        try:
            # Load environment variables
            self.load_environment()
            
            # Kill any existing agent processes
            self.kill_existing_agents()
            
            # Start new agent process
            logger.info(f"🚀 Starting agent: {self.agent_script}")
            
            self.agent_process = subprocess.Popen(
                [sys.executable, str(self.agent_script)],
                stdout=open(self.log_file, 'w'),
                stderr=subprocess.STDOUT,
                cwd=str(self.agent_script.parent),
                env=os.environ.copy()
            )
            
            logger.info(f"✅ Agent started with PID: {self.agent_process.pid}")
            self.last_restart_time = time.time()
            return True
            
        except Exception as e:
            logger.error(f"❌ Failed to start agent: {e}")
            return False
    
    def kill_existing_agents(self):
        """Kill any existing agent processes"""
        try:
            # Find and kill existing spawn_agent.py processes
            for proc in psutil.process_iter(['pid', 'name', 'cmdline']):
                try:
                    if proc.info['cmdline'] and 'spawn_agent.py' in ' '.join(proc.info['cmdline']):
                        logger.info(f"🔧 Killing existing agent process: {proc.info['pid']}")
                        proc.kill()
                        proc.wait(timeout=5)
                except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.TimeoutExpired):
                    pass
        except Exception as e:
            logger.warning(f"⚠️ Error killing existing agents: {e}")
    
    def is_agent_healthy(self):
        """Check if the agent process is healthy"""
        if not self.agent_process:
            return False
            
        # Check if process is still running
        if self.agent_process.poll() is not None:
            logger.warning("⚠️ Agent process has terminated")
            return False
        
        try:
            # Check memory usage
            process = psutil.Process(self.agent_process.pid)
            memory_mb = process.memory_info().rss / 1024 / 1024
            
            if memory_mb > self.max_memory_mb:
                logger.warning(f"⚠️ Agent memory usage too high: {memory_mb:.1f}MB > {self.max_memory_mb}MB")
                return False
            
            # Check log file activity
            if os.path.exists(self.log_file):
                log_age = time.time() - os.path.getmtime(self.log_file)
                if log_age > self.max_silent_time:
                    logger.warning(f"⚠️ Agent log inactive for {log_age:.1f}s > {self.max_silent_time}s")
                    return False
            
            logger.debug(f"✅ Agent healthy - PID: {self.agent_process.pid}, Memory: {memory_mb:.1f}MB")
            return True
            
        except psutil.NoSuchProcess:
            logger.warning("⚠️ Agent process not found")
            return False
        except Exception as e:
            logger.warning(f"⚠️ Health check error: {e}")
            return False
    
    def restart_agent(self):
        """Restart the agent with exponential backoff"""
        if self.is_shutting_down:
            return False
            
        self.restart_count += 1
        
        if self.restart_count > self.max_restarts:
            logger.error(f"❌ Maximum restarts ({self.max_restarts}) reached. Stopping supervisor.")
            return False
        
        # Emergency cleanup of any stale LiveKit connections
        try:
            logger.info("🧹 Performing emergency cleanup of LiveKit connections...")
            import sys
            sys.path.append(str(Path(__file__).parent))
            from connection_manager import connection_manager
            
            # Run emergency cleanup in a new event loop (since supervisor runs sync)
            import asyncio
            try:
                loop = asyncio.get_event_loop()
            except RuntimeError:
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
            
            loop.run_until_complete(connection_manager.emergency_cleanup())
            logger.info("✅ Emergency cleanup completed")
        except Exception as e:
            logger.warning(f"⚠️ Emergency cleanup failed: {e}")
        
        # Stop current agent
        if self.agent_process:
            try:
                logger.info(f"🛑 Stopping agent process: {self.agent_process.pid}")
                self.agent_process.terminate()
                self.agent_process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                logger.warning("⚠️ Agent didn't stop gracefully, killing...")
                self.agent_process.kill()
            except Exception as e:
                logger.warning(f"⚠️ Error stopping agent: {e}")
        
        # Wait with exponential backoff
        logger.info(f"⏳ Waiting {self.restart_delay}s before restart {self.restart_count}/{self.max_restarts}")
        time.sleep(self.restart_delay)
        
        # Increase delay for next restart (exponential backoff)
        self.restart_delay = min(self.restart_delay * 2, self.max_restart_delay)
        
        # Start new agent
        success = self.start_agent()
        
        if success:
            # Reset delay on successful start
            self.restart_delay = 1
            logger.info(f"✅ Agent restarted successfully (restart #{self.restart_count})")
        else:
            logger.error(f"❌ Agent restart failed (attempt #{self.restart_count})")
            
        return success
    
    async def monitor_loop(self):
        """Main monitoring loop"""
        logger.info("🎯 Agent supervisor started")
        
        # Initial agent start
        if not self.start_agent():
            logger.error("❌ Failed to start agent initially")
            return
        
        while not self.is_shutting_down:
            try:
                await asyncio.sleep(self.health_check_interval)
                
                if not self.is_agent_healthy():
                    logger.warning("🔄 Agent unhealthy, restarting...")
                    if not self.restart_agent():
                        break
                        
            except asyncio.CancelledError:
                logger.info("🛑 Monitor loop cancelled")
                break
            except Exception as e:
                logger.error(f"❌ Monitor loop error: {e}")
                await asyncio.sleep(5)  # Brief pause before continuing
    
    def shutdown(self):
        """Graceful shutdown"""
        logger.info("🛑 Shutting down supervisor...")
        self.is_shutting_down = True
        
        if self.agent_process:
            try:
                logger.info("🛑 Stopping agent process...")
                self.agent_process.terminate()
                self.agent_process.wait(timeout=10)
                logger.info("✅ Agent stopped gracefully")
            except subprocess.TimeoutExpired:
                logger.warning("⚠️ Force killing agent...")
                self.agent_process.kill()
            except Exception as e:
                logger.error(f"❌ Error stopping agent: {e}")

# Signal handlers
supervisor = None

def signal_handler(signum, frame):
    """Handle shutdown signals"""
    global supervisor
    logger.info(f"📡 Received signal {signum}, shutting down...")
    if supervisor:
        supervisor.shutdown()
    sys.exit(0)

async def main():
    """Main function"""
    global supervisor
    
    # Setup signal handlers
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    # Create and run supervisor
    supervisor = AgentSupervisor()
    
    try:
        await supervisor.monitor_loop()
    except KeyboardInterrupt:
        logger.info("👋 Supervisor interrupted by user")
    except Exception as e:
        logger.error(f"❌ Supervisor error: {e}")
    finally:
        supervisor.shutdown()

if __name__ == "__main__":
    asyncio.run(main())