class OnlineError(Exception):
    """Base class for every online failure. The game must keep working when these are raised."""


class NetworkError(OnlineError):
    """No connection / timeout."""


class AuthError(OnlineError):
    """Not signed in, wrong credentials, or the session could not be refreshed."""


class ServerError(OnlineError):
    """The backend refused or failed the request. `code` is a stable machine-readable reason."""

    def __init__(self, code: str, message: str = ""):
        super().__init__(message or code)
        self.code = code
