class KernelError(RuntimeError):
    """Base exception for kernel failures."""


class GateFailure(KernelError):
    """Raised when a fail-closed gate blocks execution."""
