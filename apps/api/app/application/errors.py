class ApplicationError(Exception):
    """Base class for errors safe to expose through the API."""

    status_code = 400
    code = "application_error"

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


class ResourceNotFoundError(ApplicationError):
    status_code = 404
    code = "not_found"


class ConflictError(ApplicationError):
    status_code = 409
    code = "conflict"


class InvalidCandidateError(ApplicationError):
    status_code = 422
    code = "invalid_candidate"
