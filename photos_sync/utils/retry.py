"""
utils/retry.py — Exponential backoff retry decorator for network I/O.

Usage:
    @retry(attempts=3, base_delay=1.0, exceptions=(OSError, Exception))
    def upload(self, local, remote): ...
"""
from __future__ import annotations

import functools
import time
from typing import Any, Callable, TypeVar

F = TypeVar("F", bound=Callable[..., Any])


def retry(
    attempts: int = 3,
    base_delay: float = 1.0,
    backoff: float = 2.0,
    exceptions: tuple[type[Exception], ...] = (Exception,),
) -> Callable[[F], F]:
    """Decorator that retries *func* up to *attempts* times on failure.

    Waits base_delay * (backoff ** attempt) seconds between retries.
    Re-raises the last exception if all attempts fail.

    Args:
        attempts:    Maximum number of tries (including the first).
        base_delay:  Initial wait in seconds before the first retry.
        backoff:     Multiplier applied to the delay on each retry.
        exceptions:  Exception types that trigger a retry.
    """
    def decorator(func: F) -> F:
        @functools.wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            last_exc = None  # type: Optional[Exception]
            delay = base_delay
            for attempt in range(1, attempts + 1):
                try:
                    return func(*args, **kwargs)
                except exceptions as exc:
                    last_exc = exc
                    if attempt < attempts:
                        print(
                            f"  ⚠️  {func.__qualname__} failed "
                            f"(attempt {attempt}/{attempts}): {exc}. "
                            f"Retrying in {delay:.0f}s…"
                        )
                        time.sleep(delay)
                        delay *= backoff
                    else:
                        print(
                            f"  ❌ {func.__qualname__} failed after "
                            f"{attempts} attempts: {exc}"
                        )
            raise last_exc  # type: ignore[misc]
        return wrapper  # type: ignore[return-value]
    return decorator
