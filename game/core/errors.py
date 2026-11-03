"""Domain errors raised by the progression layer (UI catches these, never raw ValueErrors)."""


class ProgressError(Exception):
    """Base class for rule violations in the progression system."""


class DifficultyLockedError(ProgressError):
    pass


class LevelLockedError(ProgressError):
    pass


class NoLivesError(ProgressError):
    pass


class LivesFullError(ProgressError):
    pass


class InsufficientFundsError(ProgressError):
    pass


class SaveError(Exception):
    """Reading or writing the save file failed."""
