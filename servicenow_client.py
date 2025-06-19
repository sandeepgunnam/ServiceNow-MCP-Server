# servicenow_client.py
import requests
import os
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

class ServiceNowClient:
    def __init__(self):
        self.instance_url = os.getenv("SERVICENOW_INSTANCE_URL")
        self.username = os.getenv("SERVICENOW_USERNAME")
        self.password = os.getenv("SERVICENOW_PASSWORD")
        self.base_api_url = f"{self.instance_url}/api/now/table"
        self.headers = {"Content-Type": "application/json", "Accept": "application/json"}

        if not all([self.instance_url, self.username, self.password]):
            raise ValueError("ServiceNow credentials (URL, username, password) are not set in .env")

    def _make_request(self, method, endpoint, data=None, params=None):
        """Helper to make authenticated requests to ServiceNow API."""
        url = f"{self.base_api_url}/{endpoint}"
        try:
            response = requests.request(
                method,
                url,
                auth=(self.username, self.password),
                headers=self.headers,
                json=data,
                params=params
            )
            response.raise_for_status()  # Raises HTTPError for bad responses (4xx or 5xx)
            return response.json()
        except requests.exceptions.HTTPError as e:
            print(f"HTTP Error: {e.response.status_code} - {e.response.text}")
            raise
        except requests.exceptions.ConnectionError as e:
            print(f"Connection Error: {e}")
            raise
        except requests.exceptions.Timeout as e:
            print(f"Timeout Error: {e}")
            raise
        except requests.exceptions.RequestException as e:
            print(f"Request Error: {e}")
            raise

    def get_incident(self, incident_number: str = None, sys_id: str = None) -> dict:
        """
        Retrieves incident details by number or sys_id.
        Requires 'number' or 'sys_id' as a parameter.
        """
        if not incident_number and not sys_id:
            raise ValueError("Either incident_number or sys_id must be provided to get an incident.")

        params = {}
        if incident_number:
            params['number'] = incident_number
        if sys_id:
            params['sys_id'] = sys_id

        response = self._make_request("GET", "incident", params=params)
        
        # ServiceNow Table API for GET requests returns 'result' as a list
        if response and 'result' in response and len(response['result']) > 0:
            return response['result'][0] # Return the first matching incident
        return {} # No incident found

    def create_incident(self, short_description: str, caller_id: str, description: str = None, **kwargs) -> dict:
        """
        Creates a new incident.
        Requires 'short_description' and 'caller_id' (sys_id or user_name).
        Additional fields can be passed via kwargs.
        """
        incident_data = {
            "short_description": short_description,
            "caller_id": caller_id, # This can be a user's sys_id or their user_name
        }
        if description:
            incident_data["description"] = description
        
        # Add any other fields passed as keyword arguments
        incident_data.update(kwargs)

        response = self._make_request("POST", "incident", data=incident_data)
        return response.get('result', {}) # ServiceNow returns the created record in 'result'

# Example Usage (for testing the client)
if __name__ == "__main__":
    client = ServiceNowClient()
    
    # --- Test Reading an Incident ---
    print("--- Reading Incident ---")
    try:
        # Replace with an actual incident number from your instance
        test_incident_number = "INC0010007" 
        incident_data = client.get_incident(incident_number=test_incident_number)
        if incident_data:
            print(f"Found Incident {test_incident_number}:")
            print(f"  Sys ID: {incident_data.get('sys_id')}")
            print(f"  Short Description: {incident_data.get('short_description')}")
            print(f"  State: {incident_data.get('state')}")
        else:
            print(f"Incident {test_incident_number} not found.")
    except Exception as e:
        print(f"Error reading incident: {e}")

    # --- Test Creating an Incident ---
    print("\n--- Creating Incident ---")
    try:
        # Replace with a valid caller_id (sys_id or user_name) from your instance
        # You might need to query for a user's sys_id first if using sys_id
        # Example: user 'abel.tuter' has sys_id '62826bf03710200044e0bfc129e415f2'
        caller_id_example = "abel.tuter" 
        
        new_incident = client.create_incident(
            short_description="AI created incident: Database connectivity issue",
            caller_id=caller_id_example,
            description="The AI agent detected a persistent database connection failure affecting critical services.",
            impact="1", # 1-High, 2-Medium, 3-Low
            urgency="1"  # 1-High, 2-Medium, 3-Low
        )
        print(f"Created new Incident:")
        print(f"  Number: {new_incident.get('number')}")
        print(f"  Sys ID: {new_incident.get('sys_id')}")
        print(f"  Short Description: {new_incident.get('short_description')}")
    except Exception as e:
        print(f"Error creating incident: {e}")
