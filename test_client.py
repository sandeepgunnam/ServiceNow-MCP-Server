# test_client.py (updated)
import asyncio
import websockets
import json
import time # For timestamp in heartbeats
import uuid # For unique message IDs

async def test_mcp_client():
    uri = "ws://localhost:8000/mcp"
    async with websockets.connect(uri) as websocket:
        print(f"Connected to {uri}")

        session_id = None
        # First message expected is session_id
        session_id_msg = json.loads(await websocket.recv())
        if session_id_msg.get("type") == "session_id":
            session_id = session_id_msg.get("session_id")
            print(f"Received session ID: {session_id}")
        else:
            print(f"Expected session_id message, got: {session_id_msg}")
            return # Exit if no session ID

        # --- Heartbeat task ---
        async def send_heartbeats():
            while True:
                await asyncio.sleep(5) # Send heartbeat every 5 seconds
                heartbeat_message = {
                    "id": str(uuid.uuid4()),
                    "type": "heartbeat",
                    "timestamp": int(time.time() * 1000) # Current timestamp in ms
                }
                print(f"Sending heartbeat: {heartbeat_message['id']}")
                await websocket.send(json.dumps(heartbeat_message))
        
        heartbeat_task = asyncio.create_task(send_heartbeats())

        # --- Test 1: Get Incident Details ---
        get_incident_message = {
            "id": str(uuid.uuid4()),
            "type": "execute",
            "tool_name": "get_incident_details",
            "params": {
                "incident_number": "INC0010007" # Replace with a real incident number from your instance
                # OR "sys_id": "your_incident_sys_id"
            }
        }
        print(f"\nSending: {json.dumps(get_incident_message, indent=2)}")
        await websocket.send(json.dumps(get_incident_message))
        response = json.loads(await websocket.recv())
        print(f"Received: {json.dumps(response, indent=2)}")
        if response.get("type") == "tool_result" and response.get("tool_name") == "get_incident_details":
            print(f"Successfully got incident: {response['result'].get('number')}")
        elif response.get("type") == "error":
            print(f"Error getting incident: {response['error']}")
        elif response.get("type") == "heartbeat_ack":
            print(f"Received heartbeat ACK: {response['id']}")
            response = json.loads(await websocket.recv()) # Get next actual response
            print(f"Received: {json.dumps(response, indent=2)}")
            if response.get("type") == "tool_result" and response.get("tool_name") == "get_incident_details":
                print(f"Successfully got incident: {response['result'].get('number')}")
            else:
                 print(f"Unexpected response after heartbeat ack: {response}")


        # --- Test 2: Create Incident ---
        create_incident_message = {
            "id": str(uuid.uuid4()),
            "type": "execute",
            "tool_name": "create_incident",
            "params": {
                "short_description": f"AI-requested: System alert {int(time.time())}.", # Unique description
                "caller_id": "abel.tuter", # Replace with a valid user_name or sys_id from your instance
                "description": "The AI agent detected an unusual system load and created this incident.",
                "impact": "3",
                "urgency": "3"
            }
        }
        print(f"\nSending: {json.dumps(create_incident_message, indent=2)}")
        await websocket.send(json.dumps(create_incident_message))
        response = json.loads(await websocket.recv())
        print(f"Received: {json.dumps(response, indent=2)}")
        if response.get("type") == "tool_result" and response.get("tool_name") == "create_incident":
            print(f"Successfully created incident: {response['result'].get('number')}")
        elif response.get("type") == "error":
            print(f"Error creating incident: {response['error']}")
        elif response.get("type") == "heartbeat_ack":
            print(f"Received heartbeat ACK: {response['id']}")
            response = json.loads(await websocket.recv()) # Get next actual response
            print(f"Received: {json.dumps(response, indent=2)}")
            if response.get("type") == "tool_result" and response.get("tool_name") == "create_incident":
                print(f"Successfully created incident: {response['result'].get('number')}")
            else:
                 print(f"Unexpected response after heartbeat ack: {response}")


        # --- Test 3: Unknown Tool (Error Case) ---
        unknown_tool_message = {
            "id": str(uuid.uuid4()),
            "type": "execute",
            "tool_name": "unknown_tool_name",
            "params": {}
        }
        print(f"\nSending: {json.dumps(unknown_tool_message, indent=2)}")
        await websocket.send(json.dumps(unknown_tool_message))
        response = json.loads(await websocket.recv())
        print(f"Received: {json.dumps(response, indent=2)}")
        if response.get("type") == "heartbeat_ack":
            print(f"Received heartbeat ACK: {response['id']}")
            response = json.loads(await websocket.recv()) # Get next actual response
            print(f"Received: {json.dumps(response, indent=2)}")


        # Allow heartbeats to continue for a bit before closing
        await asyncio.sleep(10) 
        heartbeat_task.cancel() # Stop the heartbeat task
        print("Heartbeat task cancelled.")


    print("Connection closed.")

if __name__ == "__main__":
    asyncio.run(test_mcp_client())