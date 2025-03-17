# Redacted implementation
import requests
from urllib3.exceptions import InsecureRequestWarning
import os
import dotenv

# Disable TLS warnings assuming use of self-signed certificate
requests.packages.urllib3.disable_warnings(InsecureRequestWarning)

# Load environment variables from .env file
dotenv.load_dotenv()


class BaseXDRClass:
    def __init__(self):
        self.api_key = os.getenv("XDR_API_KEY")
        self.base_url = os.getenv("XDR_URL") + "/api/"
        self.headers = {
            "api-secret-key": self.api_key,
            "api-version": "v1",
        }
    
    def _make_api_request(self, endpoint: str, request_type: str) -> dict:
        """Make API request to Redacted XDR's API. Supports GET and POST requests.

        Args:
            endpoint: The endpoint to query
            request_type: The type of request to make. Options are "GET" or "POST"

        Returns:
            dict: The JSON response from the API

        Raises:
            ValueError: If the request type is not "GET" or "POST"
            ValueError: If the API key is not authorized to access the resource
            ValueError: If unable to retrieve data
        """
        # Check if request type is valid
        if request_type not in ["GET", "POST"]:
            raise ValueError("Invalid request type. Must be 'GET' or 'POST'")

        # Make the API request
        response = requests.request(
            request_type,
            f"{self.base_url}{endpoint}",
            headers=self.headers,
            verify=False,
        )

        # If the response was successful, return the JSON response
        if response.status_code == 200:
            return response.json()
        # Handle 403 Forbidden error
        elif response.status_code == 403:
            raise ConnectionRefusedError(
                "API key is not authorized to access this resource"
            )
        # Else raise an exception with the error message
        else:
            raise RuntimeError(f"Unable to retrieve data")

    def _filter_response(
        self,
        response: dict,
        resource_key: str,
        filtered: bool = True,
        default_fields: dict[str, bool] = None,
        **fields,
    ) -> dict:
        """Filters the API response based on user-provided fields. If no fields are provided, the default fields for the resource are used

        Args:
            response: The API response
            resource_key: The key in the response that contains the resource list
            filtered: A boolean value that determines if the response should be filtered. Default is True
            default_fields: The default fields to include in the response
            **fields: Optional fields to filter by. If none provided, uses default fields. Ignored if filtered is False

        Returns:
            dict: The API response. If filtered is True, the response is filtered based on the fields provided
        """
        # If not filtered, return the response as-is
        if not filtered:
            return response
        # Else if filtered, filter the response based on the fields provided
        else:
            # Get the fields to filter. If none are provided, use the default fields for the resource
            fields_to_filter = fields if fields else default_fields

            def filter_item(item, fields):
                filtered_item = {}
                for field in fields:
                    keys = field.split(".")
                    value = item
                    for key in keys:
                        if isinstance(value, dict):
                            value = value.get(key, {})
                        else:
                            value = {}
                    if value:
                        nested_dict = filtered_item
                        for key in keys[:-1]:
                            nested_dict = nested_dict.setdefault(key, {})
                        nested_dict[keys[-1]] = value
                return filtered_item

            return {
                resource_key: [
                    filter_item(item, fields_to_filter)
                    for item in response[resource_key]
                ]
            }


class GenericClass(BaseXDRClass):
    def get(self, endpoint: str, filtered: bool = True, **fields) -> dict[str, any]:
        """Retrieve a list of resources from the Redacted XDR server.

        Args:
            endpoint: The endpoint to query
            filtered: A boolean value that determines if the response should be filtered. Default is True
            **fields: Optional fields to filter by. If none provided, uses default fields. Ignored if filtered is False

        Returns:
            dict: A list of resources with filtered fields
        """
        default_fields = {
            "field1": True,
        }
        # Merge default fields with user-provided fields
        all_fields = {**default_fields, **fields}
        try:
            response = self._make_api_request(
                endpoint=endpoint, request_type="GET"
            )
            return self._filter_response(
                response, endpoint, filtered, default_fields, **all_fields
            )
        except:
            raise  # Re-raising the exception to be handled by the caller
