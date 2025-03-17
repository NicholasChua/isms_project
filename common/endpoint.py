from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
from common.auth_utils import AuthException, AuthErrorCode

# Import routes from routes directory
from routes.user_document import router as document_router
from routes.user_root import router as root_router
from routes.user_audit import router as audit_router
from routes.user_risk_calc import router as risk_calc_router


# Create a FastAPI instance
app = FastAPI()

# Include routes from routes directory
app.include_router(root_router)
app.include_router(document_router, prefix="/v1/documents")
app.include_router(audit_router, prefix="/v1/audit")
app.include_router(risk_calc_router, prefix="/v1/risk")


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


# Custom 422 error handler
@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request, exc: RequestValidationError):
    # Custom error handling for risk calculation routes
    if request.url.path.startswith("/v1/risk"):
        error_details = []
        
        # Define endpoint-specific constraints
        before_after_constraints = {
            "asset_value": "Must be greater than 0",
            "exposure_factor": "Must be between 0 and 1",
            "annual_rate_of_occurrence": "Must be greater than 0",
            "percentage_reduction": "Must be less than or equal to 99",
            "cost_of_control": "Must be greater than 0",
            "simulation_method": "Must be 0 (Monte Carlo) or 1 (Markov Chain Monte Carlo)",
        }

        rqmc_sequence_constraints = {
            "asset_value": "Must be greater than 0",
            "exposure_factor_min": "Must be between 0 and 1",
            "exposure_factor_max": "Must be between 0 and 1",
            "annual_rate_of_occurrence_min": "Must be greater than 0",
            "annual_rate_of_occurrence_max": "Must be greater than 0",
            "cost_adjustment_min": "Must be between -1 and 1",
            "cost_adjustment_max": "Must be between -1 and 1",
            "control_reductions": "List of control reduction decimals (0-0.99)",
            "control_costs": "List of control costs (must be > 0)",
        }

        vendor_assessment_constraints = {
            "asset_value": "Must be greater than 0",
            "exposure_factor_min": "Must be between 0 and 1",
            "exposure_factor_max": "Must be between 0 and 1",
            "annual_rate_of_occurrence_min": "Must be greater than 0",
            "annual_rate_of_occurrence_max": "Must be greater than 0",
            "control_costs": "List of control costs (must be > 0)",
            "control_reduction_mins": "List of minimum control reduction decimals (0-0.99)",
            "control_reduction_maxs": "List of maximum control reduction decimals (0-0.99)",
        }

        # Select constraints based on endpoint
        if request.url.path.endswith("/before-after"):
            constraints = before_after_constraints
        elif request.url.path.endswith("/rqmc-sequence-analysis"):
            constraints = rqmc_sequence_constraints
        elif request.url.path.endswith("/rqmc-vendor-assessment"):
            constraints = vendor_assessment_constraints
        else:
            constraints = {}

        for error in exc.errors():
            loc = error["loc"]
            field = loc[-1]
            field_type = loc[0] if len(loc) > 1 else "value"

            error_details.append(
                {
                    "field": field,
                    "type": field_type,
                    "message": f"Invalid {field}: {error['msg']}",
                    "value": error.get("ctx", {}).get("value"),
                    "constraints": constraints.get(field),
                }
            )

        return JSONResponse(
            status_code=422,
            content={
                "detail": "Validation error",
                "errors": error_details,
            },
        )

    # Default handler for other routes
    return JSONResponse(status_code=422, content={"detail": exc.errors()})
