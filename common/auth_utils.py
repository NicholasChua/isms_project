from enum import Enum
from fastapi import HTTPException

class AuthErrorCode(str, Enum):
    MISSING_API_KEY = "MISSING_API_KEY"
    INVALID_API_KEY = "INVALID_API_KEY" 
    MISSING_OTHER_HEADER = "MISSING_OTHER_HEADER"

class AuthException(HTTPException):
    def __init__(self, error_code: AuthErrorCode):
        super().__init__(status_code=403)
        self.error_code = error_code
