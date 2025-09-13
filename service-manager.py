#!/usr/bin/env python3

"""
LiveKit + Pipecat Demo - Unified Service Manager

This script manages all services as a single unit:
- LiveKit Server (Docker)
- Redis (Docker)
- HTTP Server (Python)
- Pipecat Agent (Python with supervisor)

Features:
- Single command to start/stop everything
- Automatic dependency management
- Health checks for all services
- Auto-restart on failures
- Unified logging
- Graceful shutdown
"""

import asyncio
import subprocess
import signal
import sys
import os
import time
import logging
import json
import aiohttp
import docker
from pathlib import Path
from typing import Dict, List, Optional
import psutil

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('/tmp/service_manager.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

class ServiceManager:
    def __init__(self):
        self.project_dir = Path(__file__).parent
        self.is_shutting_down = False
        self.services = {}
        
        # Docker client
        try:
            self.docker_client = docker.from_env()
        except Exception as e:
            logger.error(f"Failed to connect to Docker: {e}")
            sys.exit(1)
            
        # Service configurations
        self.service_configs = {
            'livekit': {
                'type': 'docker',
                'container_name': 'livekit-pipecat-demo-livekit-1',
                'health_check': self.check_livekit_health,
                'port': 7880,
                'startup_time': 5
            },
            'redis': {
                'type': 'docker', 
                'container_name': 'livekit-pipecat-demo-redis-1',
                'health_check': self.check_redis_health,
                'port': 6379,
                'startup_time': 2
            },
            'http_server': {
                'type': 'process',
                'command': [sys.executable, '-m', 'http.server', '8000'],
                'cwd': self.project_dir / 'client',
                'health_check': self.check_http_health,
                'port': 8000,
                'startup_time': 2
            },
            'agent': {
                'type': 'process',
                'command': [sys.executable, 'supervisor.py'],
                'cwd': self.project_dir / 'agent', 
                'health_check': self.check_agent_health,
                'startup_time': 5,
                'depends_on': ['livekit', 'redis']
            }
        }

    async def start_all_services(self):
        """Start all services in dependency order"""
        logger.info("🚀 Starting LiveKit + Pipecat Demo Services")
        
        # Load environment variables
        self.load_environment()
        
        # Check prerequisites
        if not self.check_prerequisites():
            return False
            
        # Start services in dependency order
        start_order = ['redis', 'livekit', 'http_server', 'agent']
        
        for service_name in start_order:
            if not await self.start_service(service_name):
                logger.error(f"❌ Failed to start {service_name}")
                return False
                
        logger.info("🎉 All services started successfully!")
        return True
    
    def load_environment(self):
        """Load environment variables from .env file"""
        env_file = self.project_dir / '.env'
        if env_file.exists():
            with open(env_file) as f:
                for line in f:
                    if line.strip() and not line.startswith('#') and '=' in line:
                        key, value = line.strip().split('=', 1)
                        os.environ[key] = value
            logger.info("✅ Environment variables loaded")
        else:
            logger.warning("⚠️ .env file not found")

    def check_prerequisites(self) -> bool:
        """Check if all prerequisites are met"""
        logger.info("🔍 Checking prerequisites...")
        
        # Check Python
        if not sys.version_info >= (3, 8):
            logger.error("❌ Python 3.8+ required")
            return False
            
        # Check Docker
        try:
            self.docker_client.ping()
        except Exception as e:
            logger.error(f"❌ Docker not available: {e}")
            return False
            
        # Check .env file
        env_file = self.project_dir / '.env'
        if not env_file.exists():
            logger.error("❌ .env file not found")
            return False
            
        # Check API keys
        if not os.getenv('OPENAI_API_KEY') or os.getenv('OPENAI_API_KEY') == 'your-openai-api-key':
            logger.error("❌ OPENAI_API_KEY not set in .env")
            return False
            
        logger.info("✅ Prerequisites check passed")
        return True

    async def start_service(self, service_name: str) -> bool:
        """Start a single service"""
        config = self.service_configs[service_name]
        
        # Check dependencies
        if 'depends_on' in config:
            for dep in config['depends_on']:
                if not await self.is_service_healthy(dep):
                    logger.error(f"❌ Dependency {dep} not healthy for {service_name}")
                    return False
        
        logger.info(f"🚀 Starting {service_name}...")
        
        if config['type'] == 'docker':
            return await self.start_docker_service(service_name)
        elif config['type'] == 'process':
            return await self.start_process_service(service_name)
            
        return False

    async def start_docker_service(self, service_name: str) -> bool:
        """Start a Docker service"""
        try:
            # Use docker-compose to ensure all settings are correct
            cmd = ['docker-compose', 'up', '-d', service_name]
            result = subprocess.run(cmd, cwd=self.project_dir, capture_output=True, text=True)
            
            if result.returncode != 0:
                logger.error(f"❌ Failed to start {service_name}: {result.stderr}")
                return False
                
            # Wait for startup
            config = self.service_configs[service_name]
            await asyncio.sleep(config['startup_time'])
            
            # Health check
            if await self.is_service_healthy(service_name):
                logger.info(f"✅ {service_name} started successfully")
                return True
            else:
                logger.error(f"❌ {service_name} failed health check")
                return False
                
        except Exception as e:
            logger.error(f"❌ Error starting {service_name}: {e}")
            return False

    async def start_process_service(self, service_name: str) -> bool:
        """Start a process service"""
        config = self.service_configs[service_name]
        
        try:
            # Start process
            process = subprocess.Popen(
                config['command'],
                cwd=config['cwd'],
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                env=os.environ.copy()
            )
            
            self.services[service_name] = {
                'type': 'process',
                'process': process,
                'config': config
            }
            
            # Wait for startup
            await asyncio.sleep(config['startup_time'])
            
            # Health check
            if await self.is_service_healthy(service_name):
                logger.info(f"✅ {service_name} started successfully")
                return True
            else:
                logger.error(f"❌ {service_name} failed health check")
                return False
                
        except Exception as e:
            logger.error(f"❌ Error starting {service_name}: {e}")
            return False

    async def is_service_healthy(self, service_name: str) -> bool:
        """Check if a service is healthy"""
        config = self.service_configs[service_name]
        
        try:
            return await config['health_check']()
        except Exception as e:
            logger.debug(f"Health check failed for {service_name}: {e}")
            return False

    async def check_livekit_health(self) -> bool:
        """Check LiveKit server health"""
        try:
            async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=5)) as session:
                async with session.get('http://localhost:7880') as resp:
                    return resp.status in [200, 404]  # 404 is OK for LiveKit
        except:
            return False

    async def check_redis_health(self) -> bool:
        """Check Redis health"""
        try:
            container = self.docker_client.containers.get('livekit-pipecat-demo-redis-1')
            return container.status == 'running'
        except:
            return False

    async def check_http_health(self) -> bool:
        """Check HTTP server health"""
        try:
            async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=5)) as session:
                async with session.get('http://localhost:8000') as resp:
                    return resp.status == 200
        except:
            return False

    async def check_agent_health(self) -> bool:
        """Check agent health"""
        try:
            # Check if supervisor process is running
            if 'agent' in self.services:
                process = self.services['agent']['process']
                if process.poll() is not None:
                    return False
                    
            # Check if agent log has recent activity
            log_file = Path('/tmp/pipecat_agent.log')
            if log_file.exists():
                age = time.time() - log_file.stat().st_mtime
                return age < 300  # Log activity within 5 minutes
            return False
        except:
            return False

    async def monitor_services(self):
        """Monitor all services and restart if needed"""
        logger.info("🔍 Starting service monitoring")
        
        while not self.is_shutting_down:
            try:
                for service_name in self.service_configs.keys():
                    if not await self.is_service_healthy(service_name):
                        logger.warning(f"⚠️ {service_name} unhealthy, restarting...")
                        await self.restart_service(service_name)
                        
                await asyncio.sleep(30)  # Check every 30 seconds
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"❌ Monitor error: {e}")
                await asyncio.sleep(5)

    async def restart_service(self, service_name: str):
        """Restart a specific service"""
        logger.info(f"🔄 Restarting {service_name}...")
        
        # Stop service first
        await self.stop_service(service_name)
        await asyncio.sleep(2)
        
        # Start service
        if await self.start_service(service_name):
            logger.info(f"✅ {service_name} restarted successfully")
        else:
            logger.error(f"❌ Failed to restart {service_name}")

    async def stop_service(self, service_name: str):
        """Stop a specific service"""
        config = self.service_configs[service_name]
        
        if config['type'] == 'docker':
            try:
                subprocess.run(['docker-compose', 'stop', service_name], 
                             cwd=self.project_dir, capture_output=True)
            except Exception as e:
                logger.error(f"Error stopping {service_name}: {e}")
                
        elif config['type'] == 'process' and service_name in self.services:
            try:
                process = self.services[service_name]['process']
                process.terminate()
                try:
                    process.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    process.kill()
                del self.services[service_name]
            except Exception as e:
                logger.error(f"Error stopping {service_name}: {e}")

    async def stop_all_services(self):
        """Stop all services"""
        logger.info("🛑 Stopping all services...")
        self.is_shutting_down = True
        
        # Stop in reverse order
        stop_order = ['agent', 'http_server', 'livekit', 'redis']
        
        for service_name in stop_order:
            await self.stop_service(service_name)
            
        # Stop docker-compose
        try:
            subprocess.run(['docker-compose', 'down'], 
                         cwd=self.project_dir, capture_output=True)
        except Exception as e:
            logger.error(f"Error stopping docker-compose: {e}")
            
        logger.info("✅ All services stopped")

    async def show_status(self):
        """Show status of all services"""
        print("\n" + "="*50)
        print("📊 SERVICE STATUS")
        print("="*50)
        
        for service_name, config in self.service_configs.items():
            try:
                is_healthy = await self.is_service_healthy(service_name)
                status = "🟢 Running" if is_healthy else "🔴 Stopped"
                
                if 'port' in config:
                    print(f"{service_name:12} {status} (port {config['port']})")
                else:
                    print(f"{service_name:12} {status}")
            except Exception as e:
                print(f"{service_name:12} 🔴 Error ({e})")
                
        print("="*50)
        print("🌐 Web Interface: http://localhost:8000")
        print("📊 Logs: tail -f /tmp/service_manager.log")
        print("="*50 + "\n")

async def main():
    """Main function"""
    manager = ServiceManager()
    
    # Signal handlers
    def signal_handler(signum, frame):
        logger.info(f"📡 Received signal {signum}, shutting down...")
        asyncio.create_task(manager.stop_all_services())
        sys.exit(0)
    
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    # Parse command line arguments
    if len(sys.argv) < 2:
        cmd = 'start'
    else:
        cmd = sys.argv[1]
    
    try:
        if cmd == 'start':
            if await manager.start_all_services():
                # Start monitoring
                await manager.monitor_services()
        elif cmd == 'stop':
            await manager.stop_all_services()
        elif cmd == 'restart':
            await manager.stop_all_services()
            await asyncio.sleep(3)
            if await manager.start_all_services():
                await manager.monitor_services()
        elif cmd == 'status':
            await manager.show_status()
        else:
            print("Usage: python service-manager.py {start|stop|restart|status}")
            
    except KeyboardInterrupt:
        logger.info("👋 Service manager interrupted")
    except Exception as e:
        logger.error(f"❌ Service manager error: {e}")
    finally:
        await manager.stop_all_services()

if __name__ == "__main__":
    # Try to use the virtual environment from agent directory
    venv_python = Path(__file__).parent / 'agent' / 'venv' / 'bin' / 'python'
    if venv_python.exists():
        # Re-run with virtual environment python
        if 'USING_VENV' not in os.environ:
            os.environ['USING_VENV'] = '1'
            os.execv(str(venv_python), [str(venv_python)] + sys.argv)
    
    # Install required packages if missing
    try:
        import aiohttp
        import docker
    except ImportError:
        logger.info("📦 Installing required packages...")
        try:
            subprocess.run([sys.executable, '-m', 'pip', 'install', 'aiohttp', 'docker'], check=True)
            import aiohttp
            import docker
        except subprocess.CalledProcessError:
            logger.error("❌ Failed to install required packages")
            sys.exit(1)
    
    asyncio.run(main())
