import json
import asyncio
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from typing import List, Dict, Any, Union
import logging
import uuid # Import uuid for generating session IDs

# --- Connection Manager for MCP Sessions ---
class ConnectionManager:
    def __init__(self):
        # Dictionary to store active WebSocket connections
        # Key: session_id (string), Value: WebSocket
        self.active_connections: Dict[str, WebSocket] = {}

    async def connect(self, websocket: WebSocket) -> str:
        """Accepts a new WebSocket connection and assigns a session ID."""
        session_id = str(uuid.uuid4()) # Generate a unique session ID
        await websocket.accept()
        self.active_connections[session_id] = websocket
        logger.info(f"WebSocket connected. New session ID: {session_id}. Total active connections: {len(self.active_connections)}")
        return session_id

    def disconnect(self, session_id: str):
        """Removes a disconnected WebSocket from the active connections."""
        if session_id in self.active_connections:
            del self.active_connections[session_id]
            logger.info(f"WebSocket disconnected for session ID: {session_id}. Total active connections: {len(self.active_connections)}")

    async def send_personal_message(self, message: Union[str, Dict], session_id: str):
        """Sends a message to a specific WebSocket session."""
        websocket = self.active_connections.get(session_id)
        if websocket:
            try:
                if isinstance(message, dict):
                    await websocket.send_json(message)
                else:
                    await websocket.send_text(message)
            except WebSocketDisconnect:
                logger.warning(f"Attempted to send to disconnected WebSocket for session ID {session_id}. Removing.")
                self.disconnect(session_id)
            except Exception as e:
                logger.error(f"Error sending message to session ID {session_id}: {e}", exc_info=True)
        else:
            logger.warning(f"Attempted to send message to non-existent session ID: {session_id}")

    # You might add a broadcast method later if needed:
    # async def broadcast(self, message: str):
    #     for connection in self.active_connections.values():
    #         await connection.send_text(message)

# Initialize the ConnectionManager
manager = ConnectionManager()


from servicenow_client import ServiceNowClient

# --- Configuration & Logging ---
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

app = FastAPI(
    title="ServiceNow MCP Server",
    description="Model Context Protocol Server for ServiceNow Incident Management",
    version="0.1.0"
)

# Initialize ServiceNow Client
try:
    sn_client = ServiceNowClient()
    logger.info("ServiceNowClient initialized successfully.")
except ValueError as e:
    logger.error(f"Failed to initialize ServiceNowClient: {e}. Ensure .env variables are set.")
    # Exit or handle this more gracefully in a production environment
    exit(1)

# --- MCP Tool Definitions ---
# These describe the capabilities to the AI model.
# They align with the operations in servicenow_client.py

TOOLS_DEFINITIONS = [
    {
        "name": "get_incident_details",
        "description": "Retrieves comprehensive details of a ServiceNow incident.",
        "input_schema": {
            "type": "object",
            "properties": {
                "incident_number": {
                    "type": "string",
                    "description": "The unique number of the incident (e.g., 'INC0010001').",
                    "example": "INC0010001"
                },
                "sys_id": {
                    "type": "string",
                    "description": "The sys_id (unique record identifier) of the incident.",
                    "example": "62826bf03710200044e0bfc129e415f2"
                }
            },
            "required": [], # We will handle logic for at least one of these being present
            "oneOf": [
                {"required": ["incident_number"]},
                {"required": ["sys_id"]}
            ]
        },
        "output_schema": {
            "type": "object",
            "description": "The full JSON object representing the incident record from ServiceNow.",
            "properties": {
                # This will vary based on what ServiceNow returns, but generally includes:
                "number": {"type": "string"},
                "sys_id": {"type": "string"},
                "short_description": {"type": "string"},
                "description": {"type": "string"},
                "state": {"type": "string"},
                "priority": {"type": "string"},
                "caller_id": {"type": "object", "properties": {"link": {"type": "string"}, "value": {"type": "string"}}},
                # ... and many other fields
            },
            "additionalProperties": True # Allow other ServiceNow fields not explicitly listed
        }
    },
    {
        "name": "create_incident",
        "description": "Creates a new incident record in ServiceNow.",
        "input_schema": {
            "type": "object",
            "properties": {
                "short_description": {
                    "type": "string",
                    "description": "A concise summary of the incident.",
                    "example": "User unable to log in."
                },
                "caller_id": {
                    "type": "string",
                    "description": "The user_name or sys_id of the person reporting the incident.",
                    "example": "abel.tuter"
                },
                "description": {
                    "type": "string",
                    "description": "A detailed explanation of the incident.",
                    "example": "The user is receiving an 'invalid credentials' error repeatedly when trying to access the portal."
                },
                "impact": {
                    "type": "string",
                    "description": "The impact of the incident (e.g., '1' for High, '2' for Medium, '3' for Low).",
                    "enum": ["1", "2", "3"],
                    "example": "2"
                },
                "urgency": {
                    "type": "string",
                    "description": "The urgency of the incident (e.g., '1' for High, '2' for Medium, '3' for Low).",
                    "enum": ["1", "2", "3"],
                    "example": "2"
                }
                # Add more fields as needed for incident creation
            },
            "required": ["short_description", "caller_id"]
        },
        "output_schema": {
            "type": "object",
            "description": "The full JSON object of the newly created incident, including its number and sys_id.",
            "properties": {
                "number": {"type": "string"},
                "sys_id": {"type": "string"},
                "short_description": {"type": "string"},
                "state": {"type": "string"}
                # ... other relevant fields of the created incident
            },
            "additionalProperties": True
        }
    }
]

# --- HTTP Endpoint for Tool Discovery (MCP Specification requires /tools) ---
@app.get("/tools")
async def get_mcp_tools():
    """
    Endpoint for AI agents to discover the available tools and their schemas.
    This adheres to the MCP specification's discovery mechanism.
    """
    logger.info("Serving MCP tool definitions.")
    return JSONResponse(content=TOOLS_DEFINITIONS)

# --- WebSocket Endpoint for MCP Communication ---
# This is where the AI agent will connect and send 'execute' requests.

# --- Modify the WebSocket Endpoint to use the Manager ---
@app.websocket("/mcp")
async def websocket_endpoint(websocket: WebSocket):
    session_id = await manager.connect(websocket) # Connect and get the session_id
    
    # Send a session_id message back to the client immediately upon connection
    # This is crucial for the client to know its session ID for subsequent messages.
    await manager.send_personal_message(
        {"type": "session_id", "id": str(uuid.uuid4()), "session_id": session_id},
        session_id
    )
    logger.info(f"Sent session_id {session_id} to client.")

    try:
        while True:
            raw_message = await websocket.receive_text()
            logger.info(f"Received raw message from session {session_id}: {raw_message}")

            try:
                mcp_message = json.loads(raw_message)
                message_type = mcp_message.get("type")
                message_id = mcp_message.get("id", str(uuid.uuid4())) # Ensure message has an ID

                if not message_type:
                    logger.warning(f"Received message without 'type' from session {session_id}: {mcp_message}")
                    await manager.send_personal_message({"id": message_id, "type": "error", "error": "Message type missing."}, session_id)
                    continue

                logger.info(f"Received MCP message type: {message_type}, ID: {message_id}, Session: {session_id}")

                # --- Handle MCP Heartbeat Messages ---
                if message_type == "heartbeat":
                    # Optionally, check for payload for specific heartbeat types
                    await manager.send_personal_message(
                        {"id": message_id, "type": "heartbeat_ack", "timestamp": mcp_message.get("timestamp")},
                        session_id
                    )
                    logger.info(f"Sent heartbeat_ack for ID {message_id} to session {session_id}")
                    continue # Process next message

                elif message_type == "execute":
                    tool_name = mcp_message.get("tool_name")
                    tool_params = mcp_message.get("params", {})
                    
                    logger.info(f"Executing tool '{tool_name}' for session {session_id} with params: {tool_params}")

                    tool_result_payload = {}
                    error_message = None
                    try:
                        if tool_name == "get_incident_details":
                            if not tool_params.get("incident_number") and not tool_params.get("sys_id"):
                                raise ValueError("Either 'incident_number' or 'sys_id' must be provided for get_incident_details.")
                            
                            incident_data = sn_client.get_incident(
                                incident_number=tool_params.get("incident_number"),
                                sys_id=tool_params.get("sys_id")
                            )
                            tool_result_payload = incident_data

                        elif tool_name == "create_incident":
                            required_params = ["short_description", "caller_id"]
                            if not all(p in tool_params for p in required_params):
                                raise ValueError(f"Missing required parameters for create_incident: {', '.join(required_params)}")

                            new_incident_data = sn_client.create_incident(
                                short_description=tool_params.get("short_description"),
                                caller_id=tool_params.get("caller_id"),
                                description=tool_params.get("description"),
                                impact=tool_params.get("impact"),
                                urgency=tool_params.get("urgency")
                                # Pass other optional parameters dynamically
                            )
                            tool_result_payload = new_incident_data

                        else:
                            error_message = f"Unknown tool: '{tool_name}'"
                            logger.warning(error_message)

                    except Exception as e:
                        error_message = f"Error executing tool '{tool_name}': {str(e)}"
                        logger.error(error_message)

                    # Prepare and send response (tool_result or error)
                    if error_message:
                        response_message = {
                            "id": message_id,
                            "type": "error",
                            "error": error_message
                        }
                    else:
                        response_message = {
                            "id": message_id,
                            "type": "tool_result",
                            "tool_name": tool_name,
                            "result": tool_result_payload
                        }
                    
                    await manager.send_personal_message(response_message, session_id)
                    logger.info(f"Sent response for message ID {message_id} to session {session_id}: {response_message['type']}")

                # Add handlers for other MCP message types (e.g., 'cancel', 'feedback') if needed later
                else:
                    logger.warning(f"Received unhandled MCP message type: {message_type} from session {session_id}")
                    await manager.send_personal_message({"id": message_id, "type": "error", "error": f"Unhandled message type: {message_type}"}, session_id)

            except json.JSONDecodeError:
                logger.error(f"Received invalid JSON from session {session_id}: {raw_message}")
                await manager.send_personal_message({"type": "error", "error": "Invalid JSON received."}, session_id)
            except Exception as e:
                logger.error(f"An unexpected error occurred in WebSocket handler for session {session_id}: {e}", exc_info=True)
                await manager.send_personal_message({"type": "error", "error": f"Internal server error: {str(e)}"}, session_id)

    except WebSocketDisconnect:
        manager.disconnect(session_id) # Disconnect using the session ID
    except Exception as e:
        logger.error(f"WebSocket connection error for session {session_id}: {e}", exc_info=True)

# --- Health Check (Optional but Recommended) ---
@app.get("/health")
async def health_check():
    return {"status": "ok", "message": "ServiceNow MCP Server is running."}
