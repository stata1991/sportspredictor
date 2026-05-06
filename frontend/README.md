# FantasyFuel Frontend

React 19 + MUI 7 + TypeScript SPA for World Cup 2026 predictions.

## Build

react-snap pre-renders public routes at build time. It requires a modern Chrome because the bundled Chromium (v77) cannot parse the compiled JS.

Set `PUPPETEER_EXECUTABLE_PATH` before building:

```bash
# macOS
export PUPPETEER_EXECUTABLE_PATH="/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"

# Linux / CI
export PUPPETEER_EXECUTABLE_PATH=$(which google-chrome || which chromium)

npm run build
```

The build will fail fast with a clear error if the variable is not set.

## Environment Variables

Copy `.env.example` to `.env.local` and fill in values as needed. See that file for documentation of each variable.
