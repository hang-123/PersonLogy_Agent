class DomainValidationError(ValueError):
    """Raised when an entity would violate a domain invariant."""


class InvalidStateTransitionError(DomainValidationError):
    """Raised when a state machine transition is not allowed."""
