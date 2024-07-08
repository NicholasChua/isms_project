from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse
import os

# Import routes from routes directory
from routes.user_document import router as document_router
from routes.user_root import router as root_router


# Create a FastAPI instance
app = FastAPI()

# Include routes from routes directory
app.include_router(root_router)
app.include_router(document_router, prefix="/v1/documents")


# Custom 404 error handler
@app.exception_handler(HTTPException)
async def custom_404_handler(request, exc):
    if exc.status_code == 404:
        # Returns a 418 status code with a custom themed message
        return JSONResponse(
            status_code=418,
            content={"message": "Roses are red, violets are blue, 404 is boring, so I'm a teapot for you!"},
        )
    # Pass other status codes to the default handler
    return await request.app.default_exception_handler(request, exc)


def main():
    # Warn user that you do not run this file directly
    print("This is the fastapi endpoint file. Do not run this file directly.")
    print("Instead, use the command below to start this endpoint:")
    print(f"fastapi dev {os.path.relpath(__file__)}")


if __name__ == "__main__":
    main()
