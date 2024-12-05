import secrets
from fastapi import APIRouter, Depends, HTTPException, status, Request, Query
from fastapi.security import APIKeyHeader
from functools import wraps

# Simulated API key storage - replace with database after testing
VALID_API_KEYS = {"fbb50f341cecef24a3b994a64cf2d609734a457998a4689a40a502a5673414e9"}

# Define the API key header
api_key_header = APIKeyHeader(name="X-API-Key")

def verify_api_key(api_key: str = Depends(api_key_header)) -> str:
    """Verify the API key is valid.

    Args:
        api_key: The API key from the request header

    Returns:
        str: The validated API key

    Raises:
        HTTPException: If API key is invalid
    """
    if api_key not in VALID_API_KEYS:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="API key invalid",
        )
    return api_key

def get_filtered_fields(request: Request, filtered: bool, default_fields: dict) -> dict:
    """Extract query parameters and convert them to fields dict."""
    query_params = dict(request.query_params)
    query_params.pop("filtered", None)
    fields = {
        field.replace('.', '__'): True for field, value in query_params.items() if value.lower() == "true"
    }
    # Merge default fields with query parameters
    all_fields = {**default_fields, **fields}
    return all_fields

def handle_errors(func):
    """Decorator to handle errors for the routes."""
    @wraps(func)
    async def wrapper(*args, **kwargs):
        try:
            return await func(*args, **kwargs)
        except ValueError as e:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
        except ConnectionRefusedError as e:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(e))
        except RuntimeError as e:
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))
        except Exception as e:
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))
    return wrapper

# Create APIRouter with default dependencies for all routes
router = APIRouter(dependencies=[Depends(verify_api_key)])

@router.get("/key/generate")
async def generate_api_key() -> dict:
    """Generate a new API key. This route requires a valid API key.

    Parameters:
        None

    Returns:
        200 OK | A dictionary containing the new API key.

    Raises:
        None
    """
    api_key = secrets.token_hex(32)
    return {"X-API-Key": api_key}

@router.get("/key/test")
@handle_errors
async def test_api_key() -> bool:
    """Test the API key. This route requires a valid API key.

    Parameters:
        None

    Returns:
        200 OK | A message indicating that the API key is valid.

    Raises:
        403 Forbidden | HTTPException with status code 403 if the API key is invalid.
    """
    return True
