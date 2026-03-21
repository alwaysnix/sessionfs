# Contributing to SessionFS

Thanks for your interest in contributing to SessionFS.

## Development Setup

### Prerequisites

- Python 3.10+
- Git
- Docker and Docker Compose (for running the API server locally)

### Clone and Install

```bash
git clone https://github.com/sessionfs/sessionfs
cd sessionfs
pip install -e ".[dev]"
```

This installs SessionFS in editable mode with all development dependencies (pytest, ruff, mypy).

### Verify Setup

```bash
sfs --help
make test
make lint
```

## Running Tests

```bash
# All tests
make test

# Specific test file
pytest tests/unit/test_cc_converter.py -v

# With coverage
pytest tests/ --cov=sessionfs --cov-report=term-missing
```

### Test Structure

```
tests/
├── unit/              # Fast, no external deps
├── integration/       # Tests that use the filesystem or subprocess
└── server/            # API server tests
    ├── unit/
    └── integration/   # Require database (uses SQLite in tests)
```

Unit tests should be fast and isolated. Integration tests can use the filesystem and real processes. Server integration tests use an in-memory SQLite database.

## Running the API Server

```bash
# Start PostgreSQL and the API server
make server

# Stop
make server-down
```

## Code Style

We use [Ruff](https://docs.astral.sh/ruff/) for linting and formatting, and [mypy](https://mypy-lang.org/) for type checking.

```bash
make lint
```

Key conventions:
- Line length: 100 characters
- Target Python version: 3.10
- Type hints on all public function signatures
- No wildcard imports

## Making Changes

1. **Create a branch** from `main`:
   ```bash
   git checkout -b my-feature
   ```

2. **Make your changes.** Keep commits focused and atomic.

3. **Run tests and linting:**
   ```bash
   make test
   make lint
   ```

4. **Push and open a PR** against `main`.

### PR Guidelines

- Keep PRs focused on a single change
- Include tests for new functionality
- Update documentation if you're changing CLI commands or behavior
- PR title should be concise and descriptive
- Include a brief description of what and why

## Project Structure

```
src/sessionfs/
├── cli/          # CLI commands (Typer)
├── daemon/       # Background daemon (watchdog)
├── server/       # FastAPI API server
├── spec/         # Session format spec and converters
├── store/        # Local session storage (SQLite + filesystem)
└── watchers/     # Tool-specific session watchers
```

## Writing a New Watcher

Watchers capture sessions from specific AI tools. Each watcher implements the `Watcher` protocol defined in `src/sessionfs/watchers/base.py`:

```python
class Watcher(Protocol):
    def full_scan(self) -> None: ...
    def start_watching(self) -> None: ...
    def stop_watching(self) -> None: ...
    def process_events(self) -> None: ...
    def get_status(self) -> WatcherStatus: ...
```

See `src/sessionfs/watchers/claude_code.py` for a complete implementation. A detailed watcher development guide will be published in Phase 3.

## Reporting Issues

File issues at [github.com/sessionfs/sessionfs/issues](https://github.com/sessionfs/sessionfs/issues).

Include:
- What you expected vs. what happened
- Steps to reproduce
- Python version and OS
- Relevant log output (`sfs daemon logs`)

## License

By contributing, you agree that your contributions will be licensed under the Apache 2.0 License.
