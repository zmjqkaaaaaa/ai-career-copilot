from fastapi import HTTPException

class ApiError(HTTPException):
    def __init__(self, status: int, code: str, message: str, headers: dict[str, str] | None = None):
        super().__init__(status, message, headers)
        self.code = code

def not_authenticated() -> ApiError:
    return ApiError(401, "NOT_AUTHENTICATED", "请登录后继续", {"WWW-Authenticate": "Bearer"})
