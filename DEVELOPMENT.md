# TouchTerrain Development Guide

This document provides information for developers working on the TouchTerrain project.

## Table of Contents

- [Development Setup](#development-setup)
- [Testing](#testing)
- [Code Quality](#code-quality)
- [Makefile Usage](#makefile-usage)
- [Project Structure](#project-structure)
- [Contributing](#contributing)

## Development Setup

### Prerequisites

- **Python 3.12 or higher** (required)
- [uv](https://github.com/astral-sh/uv) (recommended) or pip
- Git

**Important:** This project requires Python 3.12+. If your system's default Python is older, you'll need to use the instructions below to ensure Python 3.12 is used.

### Installation with uv (Recommended)

**Step 1: Install uv**
```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

**Step 2: Clone and Setup**
```bash
# Clone the repository
git clone https://github.com/ChHarding/TouchTerrain_for_CAGEO.git
cd TouchTerrain_for_CAGEO

# Create Python 3.12 virtual environment (automatic with make)
make venv

# OR manually create venv with specific Python version:
uv venv --python 3.12 .venv

# Install development dependencies
make install-dev

# Install pre-commit hooks
make pre-commit-install
```

**Note for uv users:** The Makefile automatically creates a Python 3.12 virtual environment if needed. If you get an error about Python version, ensure Python 3.12 is installed:

```bash
# Check available Python versions
python3.12 --version

# If not installed, install Python 3.12 first:
# On Ubuntu/Debian:
sudo apt install python3.12

# On macOS with Homebrew:
brew install python@3.12
```

### Installation with pip

```bash
# Create virtual environment with Python 3.12
python3.12 -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate

# Verify Python version
python --version  # Should show Python 3.12.x

# Install development dependencies
pip install -e ".[dev]"

# Install pre-commit hooks
pre-commit install
```

### Installing GDAL (Optional)

GDAL is only required for processing local DEM files. If you only use Earth Engine for DEM data, you can skip this section.

**Important:** GDAL requires system-level libraries and the Python bindings must match the system GDAL version.

#### Ubuntu/Debian

```bash
# Install system GDAL libraries
sudo apt-get update
sudo apt-get install -y gdal-bin libgdal-dev

# Get GDAL version
GDAL_VERSION=$(gdal-config --version)
echo "System GDAL version: $GDAL_VERSION"

# Activate your virtual environment
source .venv/bin/activate

# Install build dependencies first
pip install setuptools wheel "numpy<2"

# Install GDAL Python bindings matching system version
pip install --no-build-isolation GDAL==$GDAL_VERSION

# Verify installation
python -c "from osgeo import gdal; print(f'GDAL version: {gdal.__version__}')"
```

#### macOS

```bash
# Install GDAL via Homebrew
brew install gdal

# Get GDAL version
GDAL_VERSION=$(gdal-config --version)

# Activate your virtual environment
source .venv/bin/activate

# Install GDAL Python bindings
pip install --no-build-isolation GDAL==$GDAL_VERSION
```

#### Windows

GDAL is tricky on Windows. Get pre-compiled wheels from:
- https://github.com/cgohlke/geospatial-wheels/releases

Download the appropriate `.whl` file for your Python version and install:
```bash
pip install GDAL-3.x.x-cpXXX-cpXXX-win_amd64.whl
```

**Note:** If you encounter GDAL installation issues, the project will still work with Earth Engine DEMs.

## Testing

### Running Tests

The project uses pytest for testing. Tests are located in the `test/` directory.

**Fast tests (recommended for development):**
```bash
# Run fast tests only (excludes slow/Earth Engine tests) - ~2 seconds
make test

# Run tests with verbose output
make test-verbose

# Run tests with coverage report
make test-coverage
```

**Slow/Integration tests:**
```bash
# Run ALL tests including slow Earth Engine tests - ~37+ seconds
make test-all

# Run only Earth Engine tests (requires authentication)
make test-ee

# Run specific test file
.venv/bin/pytest test/test_coordinate_conversion.py -v
```

**⚡ Performance Note:**
- Fast tests: ~2-3 seconds (37 tests)
- All tests: ~37+ seconds (57 tests) - requires Earth Engine auth
- Earth Engine tests are marked and excluded by default for speed

### Test Coverage

Current test coverage statistics:

- **Total Tests**: 59 (37 passed, 22 skipped)
- **Overall Coverage**: ~11% → improving with new unit tests
- **Unit Tests**: 30+ passing tests for core utilities

Coverage areas:
- ✅ Vector operations (touchterrain/common/vectors.py): 33%
- ✅ GPX handling (touchterrain/common/TouchTerrainGPX.py): 42%
- ✅ Utility functions (touchterrain/common/utils.py): 14%
- ⚠️ Earth Engine integration (touchterrain/common/TouchTerrainEarthEngine.py): 6%
- ⚠️ Grid tessellation (touchterrain/common/grid_tesselate.py): 10%

### Test Structure

```
test/
├── test_coordinate_conversion.py  # Coordinate system conversion tests
├── test_vectors.py                # Vector and point operations tests
├── test_utils.py                  # Utility function tests
├── test_TouchTerrainGPX.py       # GPX handling tests (7 passing)
└── test_TouchTerrain_standalone.py # Integration tests (20 tests, require EE auth)
```

### Skipped Tests

20 tests in `test_TouchTerrain_standalone.py` are skipped by default because they require:
- Google Earth Engine authentication
- Network connectivity
- Significant processing time

To run these tests, you must:
1. Authenticate with Google Earth Engine
2. Remove `@unittest.skip()` decorators from specific tests
3. Run with `make test-verbose`

## Code Quality

### Pre-commit Hooks

The project uses pre-commit hooks to ensure code quality:

- **isort**: Organizes imports
- **black**: Code formatting
- **ruff**: Fast Python linter
- **trailing whitespace**: Removes trailing whitespace
- **end of file fixer**: Ensures files end with newline

```bash
# Run pre-commit hooks manually
make pre-commit-run

# Or
pre-commit run --all-files
```

### Linting and Formatting

```bash
# Format code
make format

# Run linter
make lint

# Run all checks (format + lint + test)
make check
```

### Code Style Configuration

The project uses modern Python tooling configured in `pyproject.toml`:

- **Black**: Line length 88, standard settings
- **isort**: Black-compatible profile
- **Ruff**: Line length 88, with per-file ignores for specific patterns

## Makefile Usage

The project includes a comprehensive Makefile that works with both `uv` and standard Python tools.

### Quick Reference

```bash
# Setup and Installation
make install          # Install package
make install-dev      # Install with dev dependencies
make pre-commit-install  # Install git hooks

# Development
make format           # Format code
make lint             # Run linters
make check            # Format + lint + test
make all              # Complete setup

# Testing
make test             # Run tests quickly
make test-verbose     # Verbose test output
make test-coverage    # Generate coverage report
make test-unit        # Run only unit tests

# Build and Package
make build            # Build distribution
make clean            # Remove build artifacts
make clean-all        # Remove everything including venv

# Utilities
make help             # Show all available targets
make env-info         # Display environment info
```

### Makefile Features

- **Auto-detection**: Automatically uses `uv` if available, falls back to pip/python
- **Color output**: Clear, colored console output
- **Comprehensive targets**: 25+ make targets for common tasks
- **Cross-platform**: Works on Linux, macOS, and Windows (with make installed)

## Project Structure

```
TouchTerrain_for_CAGEO/
├── touchterrain/
│   ├── common/
│   │   ├── Coordinate_system_conv.py  # Coordinate conversions
│   │   ├── TouchTerrainEarthEngine.py # Earth Engine integration
│   │   ├── TouchTerrainGPX.py        # GPX file handling
│   │   ├── grid_tesselate.py         # 3D mesh generation
│   │   ├── utils.py                  # Utility functions
│   │   └── vectors.py                # Vector math
│   └── server/
│       ├── TouchTerrain_app.py       # Flask web server
│       └── config.py                 # Server configuration
├── test/
│   ├── test_coordinate_conversion.py
│   ├── test_vectors.py
│   ├── test_utils.py
│   ├── test_TouchTerrainGPX.py
│   └── test_TouchTerrain_standalone.py
├── .pre-commit-config.yaml          # Pre-commit configuration
├── pyproject.toml                   # Project metadata & tool config
├── setup.py                         # Setup script
├── Makefile                         # Development automation
└── README.md                        # Project README
```

## Contributing

### Workflow

1. **Create a branch**
   ```bash
   git checkout -b feature/your-feature-name
   ```

2. **Make changes**
   - Write code
   - Add/update tests
   - Update documentation

3. **Run quality checks**
   ```bash
   make check
   ```

4. **Commit changes**
   ```bash
   git add .
   git commit -m "Description of changes"
   ```
   - Pre-commit hooks will run automatically
   - Fix any issues they find

5. **Push and create PR**
   ```bash
   git push origin feature/your-feature-name
   ```

### Writing Tests

When adding new functionality:

1. Add unit tests in appropriate test file
2. Aim for >80% coverage of new code
3. Use mocking for external dependencies (Earth Engine, network, etc.)
4. Follow existing test patterns

Example test:
```python
def test_new_feature():
    """Test description."""
    # Arrange
    input_data = setup_test_data()

    # Act
    result = function_to_test(input_data)

    # Assert
    assert result == expected_value
```

### Pull Request Guidelines

- Ensure all tests pass: `make test`
- Ensure code is formatted: `make format`
- Ensure no lint errors: `make lint`
- Update documentation if needed
- Add entry to CHANGELOG (if exists)
- Keep PRs focused on single feature/fix

## Continuous Integration

### GitHub Actions

The project uses GitHub Actions for CI (`.github/workflows/ci.yml`):

- **On**: Push and Pull Request to main/master
- **Python versions**: 3.12
- **Steps**:
  1. Checkout code
  2. Setup Python with uv
  3. Install dependencies
  4. Run linters
  5. Run tests
  6. Generate coverage report

### Local CI Simulation

```bash
# Run the same checks as CI
make check

# Or step by step
make install-dev
make lint
make test-coverage
```

## Environment Variables

### Google Earth Engine

For Earth Engine tests:
```bash
export EE_PROJECT="your-project-id"
# Then authenticate
earthengine authenticate
```

### Development Settings

```bash
# Enable debug mode
export TOUCHTERRAIN_DEBUG=1

# Set custom temp folder
export TOUCHTERRAIN_TEMP=/path/to/temp
```

## Troubleshooting

### Common Issues

**Import errors**
```bash
# Reinstall in editable mode
make install-dev
```

**Pre-commit hooks failing**
```bash
# Update hooks
pre-commit autoupdate

# Run manually to see errors
make pre-commit-run
```

**Tests failing with "Earth Engine not authenticated"**
```bash
# These are integration tests that are skipped by default
# To run them, authenticate first:
earthengine authenticate
```

**uv not found**
```bash
# Install uv
curl -LsSf https://astral.sh/uv/install.sh | sh

# Or use regular Python tools (Makefile will auto-detect)
pip install -e ".[dev]"
```

## Additional Resources

- [TouchTerrain Documentation](https://touchterrain.geol.iastate.edu/)
- [Google Earth Engine Python API](https://developers.google.com/earth-engine/guides/python_install)
- [pytest Documentation](https://docs.pytest.org/)
- [pre-commit Documentation](https://pre-commit.com/)
- [uv Documentation](https://github.com/astral-sh/uv)

## License

MIT License - see LICENSE file for details
