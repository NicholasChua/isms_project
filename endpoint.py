from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse
import os
from common.auth_utils import AuthException, AuthErrorCode

# Import routes from routes directory
from routes.user_document import router as document_router
from routes.user_root import router as root_router
from routes.user_audit import router as audit_router


# Create a FastAPI instance
app = FastAPI()

# Include routes from routes directory
app.include_router(root_router)
app.include_router(document_router, prefix="/v1/documents")
app.include_router(audit_router, prefix="/v1/audit")


# Custom 404 error handler
@app.exception_handler(HTTPException)
async def custom_404_handler(request, exc):
    if exc.status_code == 404:
        # Returns a 418 status code with a custom themed message
        return JSONResponse(
            status_code=418,
            content={
                "message": "Roses are red, violets are blue, 404 is boring, so I'm a teapot for you!"
            },
        )
    # Return other exceptions with original status and detail
    return JSONResponse(status_code=exc.status_code, content={"message": exc.detail})


# Custom 403 error handler
@app.exception_handler(AuthException)
async def auth_exception_handler(request, exc: AuthException):
    error_messages = {
        AuthErrorCode.MISSING_API_KEY: "Please provide an API key using the X-API-Key header",
        AuthErrorCode.INVALID_API_KEY: "Invalid API key provided",
        AuthErrorCode.MISSING_OTHER_HEADER: "Missing required header",
    }
    return JSONResponse(
        status_code=403, content={"detail": error_messages[exc.error_code]}
    )


def main():
    # Warn user that you do not run this file directly
    print("This is the fastapi endpoint file. Do not run this file directly.")
    print("Instead, use the command below to start this endpoint:")
    print(f"fastapi dev {os.path.basename(__file__)}")


if __name__ == "__main__":
    main()
