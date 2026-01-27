# Environment Configuration for ha-cli

The ha-cli tool now supports automatic loading of environment variables from a `.env` file using python-dotenv.

## Quick Start

1. Copy the example file:
   ```bash
   cp .env.example .env
   ```

2. Edit `.env` with your Home Assistant credentials:
   ```bash
   # Your Home Assistant URL
   HOME_ASSISTANT_URL=http://homeassistant.local:8123
   
   # Your Long-Lived Access Token
   HOME_ASSISTANT_TOKEN=your-token-here
   ```

3. The tool will automatically load these values - no need to export them!

## Configuration Priority

The tool looks for credentials in this order:
1. **Command line arguments** (`--url` and `--token`)
2. **Environment variables** (including those from `.env` file)
3. **Config file** (`~/.config/home-assistant-cli/config.json`)
4. **Interactive prompt** (if all else fails)

## Supported Environment Variables

- `HOME_ASSISTANT_URL` or `HA_URL` - Your Home Assistant URL
- `HOME_ASSISTANT_TOKEN` or `HA_TOKEN` - Your access token

## Security Notes

- The `.env` file is already in `.gitignore` - never commit it!
- Keep your `.env` file secure with appropriate permissions:
  ```bash
  chmod 600 .env
  ```

## Alternative: Using export

If you prefer not to use `.env` files, you can still export variables:
```bash
export HOME_ASSISTANT_URL="http://homeassistant.local:8123"
export HOME_ASSISTANT_TOKEN="your-token-here"
```

## Getting Your Token

1. Log into Home Assistant
2. Click your profile (bottom left)
3. Go to "Security" tab
4. Create a "Long-Lived Access Token"
5. Copy the token to your `.env` file