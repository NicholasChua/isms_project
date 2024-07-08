from fastapi import APIRouter
from fastapi.responses import RedirectResponse

# Create an APIRouter instance
router = APIRouter()

# Define the API routes
@router.get("/")
async def root():
    return {"message": "Hello World"}


@router.get("/v1")
async def get_api_info() -> RedirectResponse:
    """Send the user to the API documentation page. RTFM!

    Returns:
    - 301 Moved Permanently | Link to the API documentation page.
    """
    return RedirectResponse(url="/docs", status_code=301)

