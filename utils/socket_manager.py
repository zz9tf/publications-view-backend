import asyncio
import uuid
import json
import logging
import traceback
from datetime import datetime
import starlette.websockets
from schemas import BaseEvent

logger = logging.getLogger("socket_manager")

class ConnectionClient:
    """
    Represents a connected WebSocket client with its own data, listeners, and tasks.
    """
    def __init__(self, client_id: str, websocket, initial_data: dict = None):
        self.client_id = client_id
        self.websocket = websocket
        self.data = initial_data or {
            "connected_at": datetime.now().isoformat(),
            "last_active": datetime.now().isoformat()
        }
        self.listeners = {}  # name -> {func, interval}
        self.tasks = set()   # Set of background tasks
        self.is_active = True
        
    def get_data(self, key=None, default=None):
        """
        Get stored client data.
        
        Args:
            key: Optional specific data key to retrieve
            default: Default value if key not found
            
        Returns:
            The requested data or all client data if key is None
        """
        if key is None:
            return self.data
            
        return self.data.get(key, default)
        
    def set_data(self, key, value):
        """
        Store data for this client.
        
        Args:
            key: The data key
            value: The data value
        """
        self.data[key] = value
        self.data["last_active"] = datetime.now().isoformat()
        
    def add_listener(self, name, listener_func, interval=None):
        """
        Add a background listener function for this client.
        
        Args:
            name: A unique name for this listener
            listener_func: An async function that takes (socket_manager, client) as arguments
            interval: Optional custom interval in seconds for this listener
            
        Returns:
            True if the listener was added, False otherwise
        """
        # Check if this listener already exists
        if name in self.listeners:
            logger.warning(f"Listener '{name}' already exists for client {self.client_id}")
            return False
            
        # Store the listener with its custom interval
        self.listeners[name] = {
            "func": listener_func,
            "interval": interval
        }
        
        logger.info(f"Added listener '{name}' for client {self.client_id}")
        return True
        
    def remove_listener(self, name):
        """
        Remove a background listener.
        
        Args:
            name: The name of the listener to remove
            
        Returns:
            True if the listener was removed, False otherwise
        """
        if name not in self.listeners:
            logger.warning(f"Listener '{name}' not found for client {self.client_id}")
            return False
            
        # Remove the listener
        del self.listeners[name]
        logger.info(f"Removed listener '{name}' for client {self.client_id}")
        return True
        
    def get_listeners(self):
        """
        Get all registered listeners for this client.
        
        Returns:
            Dict of listener names to listener details
        """
        return self.listeners
        
    async def send(self, event, data):
        """
        Send an event to this client.
        
        Args:
            event: The event name
            data: The event data
            
        Returns:
            True if the message was sent, False otherwise
        """
        if not self.is_active:
            logger.warning(f"Cannot send to inactive client {self.client_id}")
            return False
            
        try:
            json.dumps(data)
            message = json.dumps({
                "event": event,
                "data": data
            })
            
            await self.websocket.send_text(message)
            self.data["last_active"] = datetime.now().isoformat()
            return True
        except Exception as e:
            tb_info = traceback.format_exc()
            logger.error(f"Error sending to client {self.client_id}: {str(e)}")
            logger.error(f"Traceback: {tb_info}")
            self.is_active = False
            return False
            
    def cancel_tasks(self):
        """
        Cancel all background tasks for this client.
        """
        for task in self.tasks:
            if not task.done():
                task.cancel()
                
        self.tasks.clear()
        logger.debug(f"Cancelled all tasks for client {self.client_id}")
        
    def deactivate(self):
        """
        Mark this client as inactive and clean up resources.
        """
        self.is_active = False
        self.cancel_tasks()
        
    def __str__(self):
        return f"WebSocketClient(id={self.client_id}, active={self.is_active}, listeners={len(self.listeners)})"


class ConnectionManager:
    """
    Manages WebSocket connections and client-specific functionality.
    """
    def __init__(self):
        self.clients = {}  # client_id -> WebSocketClient
        self.default_listener_interval = 1  # Default interval in seconds
    
    async def connect(self, websocket, client_id=None, **kwargs):
        """
        Connect a client to the WebSocket manager.
        
        Args:
            websocket: The WebSocket connection
            client_id: Optional client ID (will be generated if not provided)
            **kwargs: Additional data to store with the client
            
        Returns:
            The client ID
        """
        # Generate ID if not provided
        if client_id is None:
            client_id = str(uuid.uuid4())
            
        # Prepare initial data
        initial_data = {
            "client_id": client_id,
            "client_ip": websocket.client.host if hasattr(websocket, "client") else "unknown",
            "connected_at": datetime.now().isoformat(),
            "last_active": datetime.now().isoformat(),
        }
        initial_data.update(kwargs)
        
        # Accept the WebSocket connection
        await websocket.accept()
        
        # Create and store the client
        client = ConnectionClient(client_id, websocket, initial_data)
        self.clients[client_id] = client
        
        # 🔥 发送 client_id 给前端
        await self.clients[client_id].send("client_connected", {"client_id": client_id})
        
        logger.info(f"Client {client_id} connected. Total clients: {len(self.clients)}")
        return client_id
        
    async def disconnect(self, client_id=None):
        """
        Disconnect one or all clients.
        
        Args:
            client_id: The client ID to disconnect, or None to disconnect all
        """
        if client_id is None:
            # Disconnect all clients
            for cid, client in list(self.clients.items()):
                client.deactivate()
                
            self.clients.clear()
            logger.info("All clients disconnected")
        elif client_id in self.clients:
            # Disconnect specific client
            self.clients[client_id].deactivate()
            del self.clients[client_id]
            logger.info(f"Client {client_id} disconnected. Remaining clients: {len(self.clients)}")
        else:
            logger.warning(f"Attempted to disconnect non-existent client: {client_id}")
    
    def is_connected(self, client_id):
        """
        Check if a client is connected.
        
        Args:
            client_id: The client ID to check
            
        Returns:
            True if the client is connected, False otherwise
        """
        return client_id in self.clients
    
    def get_client(self, client_id):
        """
        Get a specific client.
        
        Args:
            client_id: The client ID
            
        Returns:
            The WebSocketClient object or None if not found
        """
        return self.clients.get(client_id)
        
    def get_client_data(self, client_id, key=None, default=None):
        """
        Get stored data for a client.
        
        Args:
            client_id: The client ID
            key: Optional specific data key (returns all data if None)
            default: Default value if key not found
            
        Returns:
            The requested client data or default
        """
        client = self.get_client(client_id)
        if not client:
            return default if key else {}
            
        return client.get_data(key, default)
        
    def set_client_data(self, client_id, key, value):
        """
        Store data for a client.
        
        Args:
            client_id: The client ID
            key: The data key
            value: The data value
            
        Returns:
            True if successful, False otherwise
        """
        client = self.get_client(client_id)
        if not client:
            logger.warning(f"Cannot set data for non-existent client: {client_id}")
            return False
            
        client.set_data(key, value)
        return True
        
    def get_connected_clients(self):
        """
        Get a list of connected client IDs.
        
        Returns:
            List of client IDs
        """
        return list(self.clients.keys())
        
    def get_client_count(self):
        """
        Get the number of connected clients.
        
        Returns:
            Number of connected clients
        """
        return len(self.clients)
        
    def add_client_listener(self, client_id, name, listener_func, interval=None):
        """
        Add a background listener function for a specific client.
        
        Args:
            client_id: The client ID to add the listener for
            name: A unique name for this listener
            listener_func: An async function that takes (socket_manager, client_id) as arguments
            interval: Optional custom interval in seconds for this listener
            
        Returns:
            True if the listener was added, False otherwise
        """
        client = self.get_client(client_id)
        if not client:
            logger.warning(f"Cannot add listener for non-existent client: {client_id}")
            return False
            
        # Add the listener to the client
        success = client.add_listener(name, listener_func, interval or self.default_listener_interval)
        if not success:
            return False
            
        # Start a background task to run this listener periodically
        task = asyncio.create_task(self._run_listener(client_id, name))
        
        # Store the task with the client
        client.tasks.add(task)
        
        return True
        
    def remove_client_listener(self, client_id, name):
        """
        Remove a background listener for a specific client.
        
        Args:
            client_id: The client ID to remove the listener from
            name: The name of the listener to remove
            
        Returns:
            True if the listener was removed, False otherwise
        """
        client = self.get_client(client_id)
        if not client:
            logger.warning(f"Cannot remove listener from non-existent client: {client_id}")
            return False
            
        return client.remove_listener(name)
        
    async def _run_listener(self, client_id, listener_name):
        """
        Run a specific listener for a client periodically.
        
        Args:
            client_id: The client ID
            listener_name: The name of the listener to run
        """
        try:
            while client_id in self.clients:
                client = self.clients[client_id]
                
                # Check if the listener still exists
                if listener_name not in client.listeners:
                    break
                    
                # Get the listener details
                listener = client.listeners[listener_name]
                interval = listener["interval"]
                
                try:
                    # Execute the listener function
                    await listener["func"](self, client_id)
                    
                    # Update last active timestamp
                    client.set_data("last_active", datetime.now().isoformat())
                except Exception as e:
                    logger.error(f"Error in listener '{listener_name}' for client {client_id}: {e}")
                    
                # Wait for the specified interval
                await asyncio.sleep(interval)
        except asyncio.CancelledError:
            logger.info(f"Listener task '{listener_name}' for client {client_id} was cancelled")
        except Exception as e:
            logger.error(f"Unexpected error in listener task '{listener_name}' for client {client_id}: {e}")
        
    async def send(self, event, data, client_id=None):
        """
        Send an event to a specific client or broadcast to all clients.
        
        Args:
            event: The event name
            data: The event data
            client_id: The client ID to send to, or None to broadcast
            
        Returns:
            True if any messages were sent successfully
        """
        logger.info(f"Sending event {event} to client {client_id}")
        if client_id is not None:
            # Send to specific client
            client = self.get_client(client_id)
            if not client:
                logger.info(f"Current clients: {self.clients.keys()}")
                logger.warning(f"Cannot send to non-existent client: {client_id}")
                return False
            return await client.send(event, data)
        else:
            # Broadcast to all clients
            success = False
            try:
                for client in list(self.clients.values()):
                    if await client.send(event, data):
                        success = True
            except Exception as e:
                tb_info = traceback.format_exc()
                logger.error(f"Error during broadcast: {str(e)}")
                logger.error(f"Traceback: {tb_info}")
                    
            return success
            
    async def start_listening(self, message_handler, client_id):
        """
        Start listening for messages from a specific client.
        
        Args:
            message_handler: Async function to handle incoming messages
            client_id: The client ID to listen to
        """
        client = self.get_client(client_id)
        if not client or not client.is_active:
            logger.warning(f"Cannot listen to non-existent or inactive client: {client_id}")
            return
            
        try:
            # Listen for messages from this client
            while client_id in self.clients and client.is_active:
                try:
                    # Receive message
                    data = await client.websocket.receive_text()
                    
                    try:
                        # Parse JSON
                        parsed_data = json.loads(data)
                        parsed_data = BaseEvent(**parsed_data)
                        
                        # Update last active timestamp
                        client.set_data("last_active", datetime.now().isoformat())
                        
                        # Call message handler
                        if message_handler.__code__.co_argcount > 1:
                            await message_handler(parsed_data, client_id)
                        else:
                            await message_handler(parsed_data)
                    except json.JSONDecodeError:
                        tb_info = traceback.format_exc()
                        logger.error(f"Invalid JSON from client {client_id}: {data}")
                        logger.error(f"Traceback: {tb_info}")
                except starlette.websockets.WebSocketDisconnect as e:
                    # 正常断开连接，记录日志但不触发断开操作
                    logger.info(f"WebSocket client {client_id} disconnected normally: code={e.code}")
                    # 仅将客户端标记为非活动，但不触发完整的断开流程
                    if client_id in self.clients:
                        self.clients[client_id].is_active = False
                    break
                except Exception as e:
                    # 异常断开，需要完整清理
                    tb_info = traceback.format_exc()
                    logger.error(f"Error receiving from client {client_id}: {str(e)}")
                    logger.error(f"Traceback: {tb_info}")
                    await self.disconnect(client_id)
                    break
        except Exception as e:
            tb_info = traceback.format_exc()
            logger.error(f"Error in start_listening for client {client_id}: {str(e)}")
            logger.error(f"Traceback: {tb_info}")
            await self.disconnect(client_id)

# Create a singleton instance
socket_manager = ConnectionManager()