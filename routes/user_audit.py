# Redacted implementation
import os
import dotenv
from fastapi import APIRouter, Depends, HTTPException, Header, status, Request, Query
from functools import wraps
from common.xdr_audit import (
    GenericClass,
)


# Load the VALID_DOCSITE_API_TOKEN from the .env file
dotenv.load_dotenv()
VALID_DOCSITE_API_TOKEN = os.getenv("VALID_DOCSITE_API_TOKEN")


async def verify_api_key(
    request: Request, x_api_key: str = Header(None, alias="X-API-Key")
):
    """Verify the API key provided in the request header.

    Args:
        request: The FastAPI request object
        x_api_key: The API key provided in the X-API-Key header

    Returns:
        The API key if valid

    Raises:
        401 | HTTPException: If the API key is invalid or missing
    """
    if x_api_key is None or x_api_key != VALID_DOCSITE_API_TOKEN:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="API key invalid"
        )
    return x_api_key


def get_filtered_fields(request: Request, filtered: bool, default_fields: dict) -> dict:
    """Extract query parameters and convert them to fields dict."""
    if not filtered:
        return {}

    query_params = dict(request.query_params)
    query_params.pop("filtered", None)

    try:
        fields = {
            field.replace(".", "__"): True
            for field, value in query_params.items()
            if value and isinstance(value, str) and value.lower() == "true"
        }

        all_fields = {**default_fields, **fields}
        return all_fields
    except Exception as e:
        raise


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
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e)
            )
        except Exception as e:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e)
            )

    return wrapper


# Create APIRouter with default dependencies for all routes
router = APIRouter(dependencies=[Depends(verify_api_key)])


@router.get(
    "/xdr",
    responses={
        403: {"description": "API key invalid"},
        500: {"description": "Server error"},
    },
)
@handle_errors
async def get_xdr_valid_routes() -> list[str]:
    """Get information about auditing capabilities for generic XDR. This route requires a valid API key.

    Parameters:
        None

    Returns:
        200 OK | A list of strings containing information about generic XDR auditing capabilities.

    Raises:
        403 Forbidden | HTTPException with status code 403 if the API key is invalid.
    """
    xdr_security_routes = [
        route.path for route in router.routes if route.path.startswith("/xdr")
    ]
    return xdr_security_routes


@router.get(
    "/xdr/generic-route",
    responses={
        400: {"description": "Invalid field requested"},
        403: {"description": "API key invalid"},
        500: {"description": "Server error"},
    },
)
@handle_errors
async def get_generic_xdr_route(
    request: Request,
    filtered: bool = Query(default=True, description="Filter the response fields"),
) -> dict:
    """Get a list of generic XDR routes. This route requires a valid API key.

    Parameters:
        filtered: Filter response fields. Default True.
        Any field name as query parameter with value 'true' to include that field.

    Returns:
        200 OK | A dictionary containing the generic XDR route information.

    Raises:
        403 Forbidden | HTTPException with status code 403 if the API key is invalid.
    """
    default_fields = {
        "field1": True,
    }
    fields = get_filtered_fields(request, filtered, default_fields)
    return GenericClass().get(filtered=filtered, **fields)
