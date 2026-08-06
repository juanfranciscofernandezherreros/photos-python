# Contributing

Thank you for improving Photos Sync.

## Language policy

Use English for documentation, new code comments, user-facing messages, issues, commits, and pull requests. Existing Spanish route paths, payload fields, database attributes, and role values are compatibility contracts and must not be renamed without a versioned migration.

CI enforces the documentation portion of this policy with `python scripts/check_english.py`.

## Development workflow

1. Create a focused branch from the current default branch.
2. Install the development dependencies with `python -m pip install -e ".[dev,ssh,images]"`.
3. Add or update tests for behavioral changes.
4. Run the local quality gates shown below.
5. Open a pull request using the repository template and describe operational or migration impact.

```bash
python -m ruff check .
python -m mypy photos_sync
python scripts/check_english.py
python -m pytest tests -q --cov=photos_sync --cov-branch --cov-fail-under=80
cd serenity && ./mvnw verify
```

Keep commits small and imperative, for example `feat: resume partial WebDAV downloads`. Never commit generated secrets, private photo data, database dumps, or unredacted request logs.
