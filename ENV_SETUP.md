# Environment Configuration for ha-cli

## Where each setting comes from

| Setting | Sources (first wins) |
|---------|----------------------|
| URL | `--url`, `HA_URL` / `HOME_ASSISTANT_URL` (environment or `.env`), `"url"` in `~/.config/home-assistant-cli/config.json`, prompt |
| Token | `--token NAME` (an environment variable's **name**), `HA_TOKEN` / `HOME_ASSISTANT_TOKEN` in the **environment**, prompt |

**Tokens are never read from files.** A token in `.env` or in the config file is
ignored with a warning naming the variable, and ha-cli never saves one. Put the token
in the process environment from your secret store, for example:

```bash
bao-run --secret <path>#token=HA_TOKEN -- ha-cli automations list
```

**Prompts only happen at a terminal.** Without one (agents, cron, pipes), a missing
URL or token is an immediate error (exit 1) naming what to set, never a hang. A
prompted token is used for that run only.

## .env

`.env` (git-ignored) is for non-secret settings: `HA_URL`, `HA_SSH_HOST`,
`HA_FILE_EDITOR_URL`, and the optional screenshot login `HA_USERNAME`/`HA_PASSWORD`.
See `.env.example`.

## Getting a token

1. Log into Home Assistant
2. Click your profile (bottom left), then the "Security" tab
3. Create a "Long-Lived Access Token"
4. Store it in your secret store, not in a file in this repo
