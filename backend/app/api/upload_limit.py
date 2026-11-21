from fastapi.responses import JSONResponse

from app.core.errors import ApiError
from app.services.resume_parser import MAX_FILE_BYTES

UPLOAD_LIMITS = {
    "/api/v1/resumes/upload": (MAX_FILE_BYTES, "FILE_TOO_LARGE", "简历文件最多 10 MB"),
    "/api/v1/jobs/import": (2 * 1024 * 1024, "JOB_FILE_TOO_LARGE", "岗位文件最多 2 MB"),
}

class ResumeUploadLimit:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        limit = UPLOAD_LIMITS.get(scope.get("path"))
        if scope["type"] != "http" or not limit or scope["method"] != "POST":
            await self.app(scope, receive, send)
            return

        file_bytes, code, message = limit
        request_bytes = file_bytes + 64 * 1024
        headers = dict(scope.get("headers", []))
        declared = headers.get(b"content-length", b"")
        if declared and (not declared.isdigit() or len(declared) > 12 or int(declared) > request_bytes):
            response = JSONResponse({"error": {"code": code, "message": message, "details": []}},
                                    status_code=413, headers={"Cache-Control": "no-store"})
            await response(scope, receive, send)
            return

        total = 0
        async def limited_receive():
            nonlocal total
            event = await receive()
            total += len(event.get("body", b""))
            if total > request_bytes:
                raise ApiError(413, code, message)
            return event

        await self.app(scope, limited_receive, send)
