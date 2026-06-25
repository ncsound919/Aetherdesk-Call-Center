
def create_api_error(code: str, message: str, details: str | None = None):
    return {
        "error": {
            "code": code,
            "message": message,
            "details": details
        }
    }
