import os
import json
import uuid
from datetime import datetime
from typing import List, Dict, Optional, Any
import aiofiles

class ChatHistory:
    def __init__(self, storage_dir: str = "./chat_history"):
        """
        Initialize chat history storage.
        
        Args:
            storage_dir: Directory to store chat history files
        """
        self.storage_dir = storage_dir
        os.makedirs(storage_dir, exist_ok=True)
    
    def _get_session_path(self, session_id: str) -> str:
        """Get file path for a session's chat history."""
        return os.path.join(self.storage_dir, f"{session_id}.json")
    
    async def add_message(
        self,
        session_id: str,
        role: str,
        content: str,
        document_context: Optional[Dict[str, Any]] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Add a message to the chat history.
        
        Args:
            session_id: Unique identifier for the chat session
            role: 'user' or 'assistant'
            content: The message content
            document_context: Optional document context for the message
            metadata: Additional metadata about the message
            
        Returns:
            The saved message with additional metadata
        """
        message = {
            "id": str(uuid.uuid4()),
            "timestamp": datetime.utcnow().isoformat(),
            "role": role,
            "content": content,
            "document_context": document_context or {},
            "metadata": metadata or {}
        }
        
        # Load existing messages or create new list
        messages = await self.get_messages(session_id)
        messages.append(message)
        
        # Save updated messages
        file_path = self._get_session_path(session_id)
        async with aiofiles.open(file_path, 'w') as f:
            await f.write(json.dumps({"messages": messages}, indent=2))
            
        return message
    
    async def get_messages(self, session_id: str) -> List[Dict[str, Any]]:
        """
        Get all messages for a session.
        
        Args:
            session_id: The session ID to retrieve messages for
            
        Returns:
            List of message dictionaries
        """
        file_path = self._get_session_path(session_id)
        if not os.path.exists(file_path):
            return []
            
        try:
            async with aiofiles.open(file_path, 'r') as f:
                content = await f.read()
                data = json.loads(content)
                return data.get("messages", [])
        except (json.JSONDecodeError, FileNotFoundError):
            return []
    
    async def clear_session(self, session_id: str) -> bool:
        """
        Clear all messages for a session.
        
        Args:
            session_id: The session ID to clear
            
        Returns:
            True if successful, False otherwise
        """
        file_path = self._get_session_path(session_id)
        if os.path.exists(file_path):
            os.remove(file_path)
            return True
        return False
    
    async def get_session_stats(self, session_id: str) -> Dict[str, Any]:
        """
        Get statistics for a chat session.
        
        Args:
            session_id: The session ID to get stats for
            
        Returns:
            Dictionary containing session statistics
        """
        messages = await self.get_messages(session_id)
        user_messages = [m for m in messages if m["role"] == "user"]
        assistant_messages = [m for m in messages if m["role"] == "assistant"]
        
        return {
            "total_messages": len(messages),
            "user_messages": len(user_messages),
            "assistant_messages": len(assistant_messages),
            "has_document_context": any(m.get("document_context") for m in messages),
            "last_message_at": messages[-1]["timestamp"] if messages else None
        }
