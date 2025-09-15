#!/usr/bin/env python3
"""
LiveKit Connection Manager

This module provides utilities to prevent "participant already exists" errors
by managing unique identities and cleaning up stale connections.
"""

import asyncio
import logging
import time
import random
import string
import os
from typing import Optional, Dict, Any

logger = logging.getLogger(__name__)

class ConnectionManager:
    """Manages LiveKit connections to prevent participant conflicts"""
    
    def __init__(self):
        self.active_connections: Dict[str, Any] = {}
        self.connection_history: list = []
        self.max_history = 100
    
    def generate_unique_identity(self, prefix: str = "PipecatAgent") -> str:
        """Generate a truly unique participant identity"""
        # Use nanosecond precision timestamp for maximum uniqueness
        timestamp = time.time_ns()
        
        # Add random component for additional uniqueness
        random_suffix = ''.join(random.choices(
            string.ascii_lowercase + string.digits, k=8
        ))
        
        # Include process ID to handle multiple instances
        process_id = os.getpid()
        
        unique_identity = f"{prefix}-{timestamp}-{process_id}-{random_suffix}"
        
        # Store in history for debugging
        self.connection_history.append({
            'identity': unique_identity,
            'created_at': time.time(),
            'status': 'created'
        })
        
        # Trim history
        if len(self.connection_history) > self.max_history:
            self.connection_history.pop(0)
        
        logger.info(f"🆔 Generated unique identity: {unique_identity}")
        return unique_identity
    
    def register_connection(self, identity: str, transport: Any) -> None:
        """Register an active connection"""
        self.active_connections[identity] = {
            'transport': transport,
            'connected_at': time.time(),
            'status': 'active'
        }
        
        # Update history
        for entry in self.connection_history:
            if entry['identity'] == identity:
                entry['status'] = 'connected'
                break
        
        logger.info(f"📝 Registered connection: {identity}")
    
    def unregister_connection(self, identity: str) -> None:
        """Unregister a connection"""
        if identity in self.active_connections:
            del self.active_connections[identity]
            
            # Update history
            for entry in self.connection_history:
                if entry['identity'] == identity:
                    entry['status'] = 'disconnected'
                    entry['disconnected_at'] = time.time()
                    break
            
            logger.info(f"🗑️ Unregistered connection: {identity}")
    
    async def cleanup_stale_connections(self, max_age_seconds: int = 300) -> None:
        """Clean up connections older than max_age_seconds"""
        current_time = time.time()
        stale_identities = []
        
        for identity, connection_info in self.active_connections.items():
            age = current_time - connection_info['connected_at']
            if age > max_age_seconds:
                stale_identities.append(identity)
        
        for identity in stale_identities:
            logger.warning(f"🧹 Cleaning up stale connection: {identity}")
            await self.force_disconnect(identity)
    
    async def force_disconnect(self, identity: str) -> None:
        """Force disconnect a connection"""
        if identity in self.active_connections:
            connection_info = self.active_connections[identity]
            transport = connection_info.get('transport')
            
            if transport and hasattr(transport, 'disconnect'):
                try:
                    await transport.disconnect()
                    logger.info(f"✅ Force disconnected: {identity}")
                except Exception as e:
                    logger.error(f"❌ Failed to force disconnect {identity}: {e}")
            
            self.unregister_connection(identity)
    
    def get_connection_status(self) -> Dict[str, Any]:
        """Get current connection status"""
        return {
            'active_connections': len(self.active_connections),
            'connection_history_count': len(self.connection_history),
            'active_identities': list(self.active_connections.keys()),
            'recent_history': self.connection_history[-10:]  # Last 10 entries
        }
    
    async def emergency_cleanup(self) -> None:
        """Emergency cleanup of all connections"""
        logger.warning("🚨 Performing emergency cleanup of all connections")
        
        identities = list(self.active_connections.keys())
        for identity in identities:
            await self.force_disconnect(identity)
        
        # Clear everything
        self.active_connections.clear()
        
        # Mark all history entries as emergency cleaned
        for entry in self.connection_history:
            if entry.get('status') == 'active' or entry.get('status') == 'connected':
                entry['status'] = 'emergency_cleanup'
                entry['cleanup_at'] = time.time()
        
        logger.info("✅ Emergency cleanup completed")

# Global connection manager instance
connection_manager = ConnectionManager()