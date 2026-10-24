# R3v — AI Terminal Assistant & Multi-Provider REPL (BYOK)

R3v is a lightweight, zero-dependency Python terminal assistant featuring **Bring Your Own Key (BYOK)** support for OpenAI, Anthropic (Claude), and Google Gemini, shell execution, natural language command generation, and session persistence.

## Features

- **Multi-Provider**: Instant switching between OpenAI (GPT-4o), Anthropic (Claude 3.5 Sonnet), and Gemini.
- **BYOK (Bring Your Own Key)**: Secure local storage of API keys (`~/.r3v/config.json`) or environment variables.
- **Natural Language to Shell (`/cmd`)**: Translate plain English into executable shell commands.
- **Output Analysis (`/analyze`)**: Run terminal commands and automatically send output to AI for troubleshooting.
- **Session Persistence**: Save and reload chat history (`/save`, `/load`, `/history`).
- **Inline Shell Shortcut (`!`)**: Run quick shell commands directly.

---

## Installation & Setup

1. Clone or copy `r3v.py` to your local directory.
2. Make it executable and add to your PATH (or run directly with python3):

```bash
chmod +x r3v.py
# Optional: create a symlink
sudo ln -s $(pwd)/r3v.py /usr/local/bin/r3v
```

---

## Usage

Start the REPL:
```bash
python3 r3v.py
```

### Commands

| Command | Description |
| :--- | :--- |
| `/provider openai\|anthropic\|gemini` | Switch active AI provider |
| `/model <model_name>` | Change model |
| `/keys <provider> <key>` | Save API key |
| `/cmd <task>` | Convert natural language to shell command |
| `/analyze <command>` | Run shell command and analyze output |
| `! <command>` | Run shell command directly |
| `/save <session>` | Save conversation session |
| `/load <session>` | Load saved session |
| `/history` | List saved sessions |
| `/clear` | Clear chat history |
| `/config` | View configuration |
| `/help` | Show help menu |
| `/exit` | Exit REPL |
