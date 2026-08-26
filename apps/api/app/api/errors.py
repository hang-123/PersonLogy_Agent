from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from personlogy.shared.errors import DomainValidationError, InvalidStateTransitionError

from app.application.errors import ApplicationError


async def application_error_handler(_: Request, error: Exception) -> JSONResponse:
    if not isinstance(error, ApplicationError):
        raise error
    return JSONResponse(
        status_code=error.status_code,
        content={"error": {"code": error.code, "message": error.message}},
    )


async def domain_validation_error_handler(_: Request, error: Exception) -> JSONResponse:
    if not isinstance(error, (DomainValidationError, InvalidStateTransitionError)):
        raise error
    return JSONResponse(
        status_code=422,
        content={"error": {"code": "domain_validation_error", "message": str(error)}},
    )


def register_error_handlers(application: FastAPI) -> None:
    application.add_exception_handler(ApplicationError, application_error_handler)
    application.add_exception_handler(DomainValidationError, domain_validation_error_handler)
    application.add_exception_handler(InvalidStateTransitionError, domain_validation_error_handler)
