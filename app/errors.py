class DomainError(Exception):
    """Base class for business rule violations."""


class PermissionDenied(DomainError):
    pass


class NotFoundError(DomainError):
    pass


class ValidationError(DomainError):
    pass


class DuplicateError(DomainError):
    pass


class LockedResult(DomainError):
    pass
