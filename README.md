# Collect All Pets Launcher

Windows launcher and server switcher for running multiple Roblox accounts in Collect All Pets.

## What's Included

- `dist/CollectAllPetsLauncher.exe` - portable Windows build.
- `website_launcher.py` - source code for the desktop launcher.
- `Launch Website Launcher.vbs` - optional helper to start the Python launcher without a console window when running from source.
- `setup_guide/` - shareable setup guide images.

Local account data is not included. The app stores saved accounts, cookies, passwords, server links, window placements, and timer settings in the current Windows user's settings file.

## Use The Exe

Download and run:

```text
dist/CollectAllPetsLauncher.exe
```

Windows may show a SmartScreen warning because the app is unsigned.

## Basic Setup

1. Open the app.
2. Go to Settings.
3. Add one account block for each Roblox account.
4. Use Capture Cookie for each enabled account and sign into Roblox in the browser window.
5. Paste your private server links as Server 1 and Server 2.
6. Launch accounts, arrange Roblox windows, then save each account's window placement.
7. Use the Testing tab to run Test Keystrokes, Test Alive Check, Reposition Windows, and Diagnostics.
8. Enable Keep Alive and Auto Switch Daily once setup tests pass.

## Build From Source

Install Python 3.12 or newer, then from this folder:

```powershell
python -m pip install pillow psutil pyinstaller
python -m PyInstaller --noconfirm --clean --onefile --windowed --name CollectAllPetsLauncher website_launcher.py
```

The build output will be created at:

```text
dist/CollectAllPetsLauncher.exe
```

## Notes

- Keep each Roblox window visible during keep-alive checks.
- Use Testing > Reposition Windows if a Roblox window is moved or resized by accident.
- On lower-end PCs, use the Disconnect Sensor sliders in the Testing tab to tune alive checks.
