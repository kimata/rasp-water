# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

This is a Raspberry Pi automated watering system ("rasp-water") with the following architecture:

- **Frontend**: Angular 19 application (TypeScript/SCSS) in `src/`
- **Backend**: Flask application in `flask/src/` (Python)
- **Hardware Control**: Uses rpi-lgpio to control GPIO pins for electromagnetic valves
- **Data Storage**: SQLite database for logging and scheduling
- **External Integrations**: Weather forecasting, Slack notifications, InfluxDB metrics

## Core Components

### Frontend (Angular)

- Main components: `valve-control`, `scheduler-control`, `log`, `header`, `footer`, `toast`
- Services: `push.service`, `toast.service` for notifications
- Built with Bootstrap 5 and ng-bootstrap for UI
- Uses tempus-dominus for date/time picking and FontAwesome icons

### Backend (Flask)

- Entry point: `flask/src/app.py` - main Flask server with blueprint registration
- Core modules in `flask/src/rasp_water/`:
    - `valve.py` - Electromagnetic valve control (customize {set,get}\_state methods here)
    - `scheduler.py` - Automated watering scheduling with weather integration
    - `weather_forecast.py` - Yahoo weather API integration for rain predictions
    - `weather_sensor.py` - Rain sensor data collection
    - `webapp_*.py` - Web API endpoints for valve and schedule control
- Uses my-lib dependency for common webapp utilities, logging, and configuration

## Development Commands

### Frontend (Angular)

```bash
# Install dependencies
npm ci

# Development server (accessible on all interfaces)
npm start

# Build for production
npm run build

# Run tests
npm test

# Watch mode during development
npm run watch

# Lint TypeScript files (manual ESLint run)
npx eslint 'src/**/*.{ts,tsx}'
```

### Backend (Python)

```bash
# Using Rye (recommended)
rye sync
rye run python flask/src/app.py

# Using pip (alternative)
pip install -r requirements.lock
python flask/src/app.py

# Run with debug mode
rye run python flask/src/app.py -D

# Run in dummy mode (for testing without hardware)
rye run python flask/src/app.py -d
```

### Testing

```bash
# Run Python tests with coverage
rye run pytest

# Run single test file
rye run pytest tests/test_basic.py

# Run Playwright tests (end-to-end browser testing)
rye run pytest tests/test_playwright.py

# Tests generate HTML report at tests/evidence/index.htm
# Coverage report at tests/evidence/coverage/
# Playwright test recordings in tests/evidence/test_*/
```

### Docker Deployment

```bash
# Full build and run
npm ci && npm run build
docker compose run --build --rm --publish 5000:5000 rasp-water
```

## Configuration

- Copy `config.example.yaml` to `config.yaml` and customize
- Flask app runs on port 5000 by default
- Angular build outputs to `dist/rasp-water/browser/` with base href `/rasp-water/`
- Configuration includes GPIO pin settings, sensor calibration, weather API keys
- Supports InfluxDB, Slack, and weather service integrations

## Hardware Integration

- GPIO control via rpi-lgpio library (replaces deprecated RPi.GPIO)
- Requires `/dev/gpiomem` access and ADS1015 overlay for analog sensors
- ADS1015 ADC for flow rate measurement via IIO interface
- Valve control logic is in `flask/src/rasp_water/valve.py`
- Sensor data collection handles flow rate monitoring and error detection

## Key Files to Understand

- `flask/src/app.py` - Flask application factory with blueprint registration
- `src/app/app.component.ts` - Angular root component
- `config.yaml` - Runtime configuration for hardware, APIs, and integrations
- `compose.yaml` - Docker deployment with hardware device access
- `pyproject.toml` - Python dependency management and test configuration
