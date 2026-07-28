"""Simple console progress bar (no external dependency)."""


def progress_bar(iterable, description: str = "", total: int | None = None):
    """Yields items from *iterable* while printing a text progress bar."""
    items = list(iterable)
    n = total or len(items)
    for i, item in enumerate(items, 1):
        if n > 0:
            pct = int(i / n * 100)
            bar = "█" * (pct // 5) + "░" * (20 - pct // 5)
            print(f"\r{description} [{bar}] {i}/{n} ({pct}%)", end="", flush=True)
        yield item
    if n > 0:
        print()
