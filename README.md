# InstaScroll

A local Python project for scrolling Instagram chats upward (to reach older messages) using Playwright.

## Disclaimer

This tool is provided for educational and personal use only.
By using it, you acknowledge that automation may violate platform rules and can lead to account restrictions or bans.
The author is not responsible for any consequences of use, including blocks, limitations, data loss, or account suspension.
Use at your own risk and only in compliance with Instagram Terms and applicable laws.

## What's inside

- `inst_skroll.py` — the main Instagram Direct automation script.
- `ui_launcher.py` — a simple Tkinter launcher (Start/Stop buttons, log view, and input helpers).
- `requirements.txt` — project dependencies (`playwright`).

## Requirements

- Python 3.10+
- Chromium installed for Playwright

## Quick start

1. Install dependencies:

   ```bash
   pip install -r requirements.txt
   python -m playwright install chromium
   ```

2. Run the GUI launcher:

   ```bash
   python ui_launcher.py
   ```

   or run the script directly:

   ```bash
   python inst_skroll.py
   ```

3. In the opened browser:
   - sign in to Instagram,
   - open the target conversation,
   - return to the console/launcher and continue execution.

## Project structure

```text
InstaScroll/
├─ inst_skroll.py
├─ ui_launcher.py
├─ requirements.txt
└─ README.md
```
