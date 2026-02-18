class ClinicError(Exception):
    code: str = "clinic_error"
    def __init__(self, message: str):
        super().__init__(message)

class NotFoundError(ClinicError):
    code = "not_found"


class ValidationError(ClinicError):
    code = "validation_error"


class ConflictError(ClinicError):
   code = "conflict"
