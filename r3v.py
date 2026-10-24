#!/usr/bin/env python3
"""
R3v — AI Terminal Assistant & Multi-Provider REPL (BYOK + Custom Provider Support)
Supports: OpenAI, Anthropic, Gemini, and Custom OpenAI-Compatible Endpoints (Ollama, Groq, DeepSeek, OpenRouter, etc.)
"""

import os
import sys
import json
import re
import time
import subprocess
import shutil
import urllib.request
import urllib.error
from datetime import datetime
from pathlib import Path

CONFIG_DIR  = Path.home() / ".r3v"
HISTORY_DIR = CONFIG_DIR / "history"
CONFIG_FILE = CONFIG_DIR / "config.json"
CONFIG_DIR.mkdir(exist_ok=True)
HISTORY_DIR.mkdir(exist_ok=True)

DEFAULT_CONFIG = {
    "provider": "openai",
    "model": {
        "openai": "gpt-4o",
        "anthropic": "claude-3-5-sonnet-20241022",
        "gemini": "gemini-1.5-flash",
        "custom": "llama3"
    },
    "api_keys": {
        "openai": "",
        "anthropic": "",
        "gemini": "",
        "custom": "not-needed"
    },
    "base_url": {
        "custom": "http://localhost:11434/v1"
    },
    "max_tokens": 2048,
    "temperature": 0.7
}

R="\033[0m"; BOLD="\033[1m"; DIM="\033[2m"; ITALIC="\033[3m"
RED="\033[91m"; GREEN="\033[92m"; YELLOW="\033[93m"
BLUE="\033[94m"; MAGENTA="\033[95m"; CYAN="\033[90m"; WHITE="\033[97m"

def load_config():
    if CONFIG_FILE.exists():
        try:
            cfg = json.loads(CONFIG_FILE.read_text())
            # Merge defaults for any missing keys
            merged = {**DEFAULT_CONFIG, **cfg}
            merged["model"] = {**DEFAULT_CONFIG["model"], **cfg.get("model", {})}
            merged["api_keys"] = {**DEFAULT_CONFIG["api_keys"], **cfg.get("api_keys", {})}
            merged["base_url"] = {**DEFAULT_CONFIG["base_url"], **cfg.get("base_url", {})}
            return merged
        except Exception:
            pass
    return DEFAULT_CONFIG

def save_config(config):
    CONFIG_FILE.write_text(json.dumps(config, indent=2))

def banner(provider, model):
    print(f"""
{CYAN}╔════════════════════════════════════════════════════════════╗{R}
{CYAN}║{R} {BOLD}R3v AI Terminal Assistant{R}                             {CYAN}║{R}
{CYAN}║{R} Provider: {GREEN}{provider:<10}{R} | Model: {YELLOW}{model:<24}{R} {CYAN}║{R}
{CYAN}╚════════════════════════════════════════════════════════════╝{R}
Type {BOLD}/help{R} for commands, {BOLD}!cmd{R} for shell, or type your query.
""")

def call_openai_compatible(api_key, base_url, model, messages, max_tokens, temperature):
    url = f"{base_url.rstrip('/')}/chat/completions"
    headers = {"Content-Type": "application/json"}
    if api_key and api_key != "not-needed":
        headers["Authorization"] = f"Bearer {api_key}"
    data = {"model": model, "messages": messages, "max_tokens": max_tokens, "temperature": temperature}
    req = urllib.request.Request(url, data=json.dumps(data).encode("utf-8"), headers=headers)
    try:
        with urllib.request.urlopen(req) as resp:
            res = json.loads(resp.read().decode("utf-8"))
            return res["choices"][0]["message"]["content"]
    except urllib.error.HTTPError as e:
        err_body = e.read().decode("utf-8")
        return f"{RED}API Error ({e.code}): {err_body}{R}"
    except Exception as e:
        return f"{RED}Error: {e}{R}"

def call_anthropic(api_key, model, messages, max_tokens, temperature):
    url = "https://api.anthropic.com/v1/messages"
    system_prompt = "You are R3v, an advanced AI terminal assistant integrated into the user's shell."
    anthropic_msgs = []
    for m in messages:
        if m["role"] == "system":
            system_prompt = m["content"]
        else:
            anthropic_msgs.append({"role": m["role"], "content": m["content"]})

    headers = {
        "Content-Type": "application/json",
        "x-api-key": api_key,
        "anthropic-version": "2023-06-01"
    }
    data = {
        "model": model,
        "system": system_prompt,
        "messages": anthropic_msgs,
        "max_tokens": max_tokens,
        "temperature": temperature
    }
    req = urllib.request.Request(url, data=json.dumps(data).encode("utf-8"), headers=headers)
    try:
        with urllib.request.urlopen(req) as resp:
            res = json.loads(resp.read().decode("utf-8"))
            return res["content"][0]["text"]
    except urllib.error.HTTPError as e:
        err_body = e.read().decode("utf-8")
        return f"{RED}Anthropic API Error ({e.code}): {err_body}{R}"
    except Exception as e:
        return f"{RED}Error: {e}{R}"

def call_gemini(api_key, model, messages, max_tokens, temperature):
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={api_key}"
    contents = []
    for m in messages:
        role = "user" if m["role"] == "user" else "model"
        if m["role"] == "system":
            role = "user"
        contents.append({"role": role, "parts": [{"text": m["content"]}]})

    headers = {"Content-Type": "application/json"}
    data = {
        "contents": contents,
        "generationConfig": {"maxOutputTokens": max_tokens, "temperature": temperature}
    }
    req = urllib.request.Request(url, data=json.dumps(data).encode("utf-8"), headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req) as resp:
            res = json.loads(resp.read().decode("utf-8"))
            return res["candidates"][0]["content"]["parts"][0]["text"]
    except urllib.error.HTTPError as e:
        err_body = e.read().decode("utf-8")
        return f"{RED}Gemini API Error ({e.code}): {err_body}{R}"
    except Exception as e:
        return f"{RED}Error: {e}{R}"

def call_ai(config, messages):
    provider = config["provider"]
    model = config["model"].get(provider)
    api_key = config["api_keys"].get(provider) or os.getenv(f"{provider.upper()}_API_KEY", "")

    if provider == "openai":
        if not api_key:
            return f"{RED}⚠️ No API key found for OpenAI. Set with: /keys openai <key>{R}"
        return call_openai_compatible(api_key, "https://api.openai.com/v1", model, messages, config["max_tokens"], config["temperature"])
    elif provider == "anthropic":
        if not api_key:
            return f"{RED}⚠️ No API key found for Anthropic. Set with: /keys anthropic <key>{R}"
        return call_anthropic(api_key, model, messages, config["max_tokens"], config["temperature"])
    elif provider == "gemini":
        if not api_key:
            return f"{RED}⚠️ No API key found for Gemini. Set with: /keys gemini <key>{R}"
        return call_gemini(api_key, model, messages, config["max_tokens"], config["temperature"])
    elif provider == "custom":
        base_url = config.get("base_url", {}).get("custom", "http://localhost:11434/v1")
        return call_openai_compatible(api_key, base_url, model, messages, config["max_tokens"], config["temperature"])
    else:
        return f"{RED}Unknown provider: {provider}{R}"

def main():
    config = load_config()
    current_provider = config["provider"]
    current_model = config["model"].get(current_provider)
    
    banner(current_provider, current_model)
    history = [{"role": "system", "content": "You are R3v, a concise, expert AI assistant embedded in the user's shell."}]

    while True:
        try:
            prompt = input(f"{CYAN}r3v[{GREEN}{current_provider}{CYAN}] › {R}").strip()
        except (KeyboardInterrupt, EOFError):
            print(f"\n{YELLOW}Exiting R3v. Goodbye!{R}")
            break

        if not prompt:
            continue

        if prompt.lower() in ("/exit", "/quit", "exit", "quit"):
            print(f"{YELLOW}Exiting R3v. Goodbye!{R}")
            break

        if prompt == "/help":
            print(f"""
{BOLD}R3v Commands:{R}
  {GREEN}/provider openai|anthropic|gemini|custom{R} - Switch AI provider
  {GREEN}/model <model_name>{R}                 - Change active model
  {GREEN}/keys <provider> <key>{R}            - Save API key securely
  {GREEN}/url <base_url>{R}                    - Set custom base URL (for custom provider)
  {GREEN}/cmd <natural language>{R}           - Translate natural language to shell command & run
  {GREEN}/analyze <shell command>{R}          - Run command and have AI analyze output
  {GREEN}! <shell command>{R}                 - Quick run shell command
  {GREEN}/save <session_name>{R}              - Save current session history
  {GREEN}/load <session_name>{R}              - Load saved session history
  {GREEN}/history{R}                          - List saved sessions
  {GREEN}/clear{R}                            - Clear conversation history
  {GREEN}/config{R}                           - View current configuration
  {GREEN}/help{R}                             - Show this help menu
""")
            continue

        if prompt == "/clear":
            history = [history[0]]
            print(f"{GREEN}✓ Conversation history cleared.{R}")
            continue

        if prompt == "/config":
            print(json.dumps(config, indent=2))
            continue

        if prompt.startswith("/provider "):
            parts = prompt.split(maxsplit=1)
            if len(parts) == 2 and parts[1] in config["model"]:
                config["provider"] = parts[1]
                current_provider = config["provider"]
                current_model = config["model"].get(current_provider)
                save_config(config)
                print(f"{GREEN}✓ Switched to provider: {current_provider} ({current_model}){R}")
            else:
                print(f"{RED}Invalid provider. Choose from: {list(config['model'].keys())}{R}")
            continue

        if prompt.startswith("/model "):
            parts = prompt.split(maxsplit=1)
            if len(parts) == 2:
                config["model"][current_provider] = parts[1]
                current_model = parts[1]
                save_config(config)
                print(f"{GREEN}✓ Model updated to: {current_model}{R}")
            else:
                print(f"{RED}Usage: /model <model_name>{R}")
            continue

        if prompt.startswith("/keys "):
            parts = prompt.split()
            if len(parts) == 3:
                prov, key = parts[1], parts[2]
                if prov in config["api_keys"]:
                    config["api_keys"][prov] = key
                    save_config(config)
                    print(f"{GREEN}✓ API key saved for {prov}.{R}")
                else:
                    print(f"{RED}Unknown provider. Choose: {list(config['api_keys'].keys())}{R}")
            else:
                print(f"{RED}Usage: /keys <openai|anthropic|gemini|custom> <key>{R}")
            continue

        if prompt.startswith("/url "):
            parts = prompt.split(maxsplit=1)
            if len(parts) == 2:
                config["base_url"]["custom"] = parts[1]
                save_config(config)
                print(f"{GREEN}✓ Custom base URL updated to: {parts[1]}{R}")
            else:
                print(f"{RED}Usage: /url <base_url> (e.g. http://localhost:11434/v1){R}")
            continue

        if prompt.startswith("/save "):
            name = prompt.split(maxsplit=1)[1]
            path = HISTORY_DIR / f"{name}.json"
            path.write_text(json.dumps(history, indent=2))
            print(f"{GREEN}✓ Session saved to {path}{R}")
            continue

        if prompt.startswith("/load "):
            name = prompt.split(maxsplit=1)[1]
            path = HISTORY_DIR / f"{name}.json"
            if path.exists():
                history = json.loads(path.read_text())
                print(f"{GREEN}✓ Loaded session '{name}' ({len(history)} messages){R}")
            else:
                print(f"{RED}Session not found: {name}{R}")
            continue

        if prompt == "/history":
            files = list(HISTORY_DIR.glob("*.json"))
            if files:
                print(f"{BOLD}Saved Sessions:{R}")
                for f in files:
                    print(f"  - {f.stem}")
            else:
                print(f"{YELLOW}No saved sessions found.{R}")
            continue

        if prompt.startswith("!"):
            cmd = prompt[1:].strip()
            print(f"{DIM}$ {cmd}{R}")
            subprocess.run(cmd, shell=True)
            continue

        if prompt.startswith("/cmd "):
            natural_query = prompt[5:].strip()
            os_name = sys.platform
            prompt_text = f"Given operating system '{os_name}', provide ONLY the exact shell command to accomplish this task: '{natural_query}'."
            temp_history = [{"role": "user", "content": prompt_text}]
            print(f"{DIM}Generating command...{R}")
            cmd = call_ai(config, temp_history).strip()
            cmd = re.sub(r"^```(?:bash|sh)?\n?", "", cmd)
            cmd = re.sub(r"\n?```$", "", cmd).strip()
            print(f"{YELLOW}Suggested Command:{R} {BOLD}{cmd}{R}")
            ans = input(f"{CYAN}Run it? [y/N]: {R}").strip().lower()
            if ans == 'y':
                subprocess.run(cmd, shell=True)
            continue

        if prompt.startswith("/analyze "):
            shell_cmd = prompt[9:].strip()
            print(f"{DIM}Running: {shell_cmd}{R}")
            try:
                res = subprocess.run(shell_cmd, shell=True, capture_output=True, text=True, timeout=60)
                output = res.stdout + res.stderr
            except Exception as e:
                output = str(e)

            analysis_prompt = f"Analyze the following output from the command `{shell_cmd}`:\n\n```\n{output}\n```"
            print(f"{DIM}Analyzing with {current_provider}...{R}")
            reply = call_ai(config, [{"role": "user", "content": analysis_prompt}])
            print(f"\n{reply}\n")
            continue

        history.append({"role": "user", "content": prompt})
        print(f"{DIM}Thinking...{R}")
        reply = call_ai(config, history)
        history.append({"role": "assistant", "content": reply})
        print(f"\n{reply}\n")

if __name__ == "__main__":
    main()
