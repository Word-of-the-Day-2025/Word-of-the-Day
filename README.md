<p align="center">
  <img src="https://raw.githubusercontent.com/gaming-gaming/WOTD-Brand-Assets/3e7d8060803a34e4d96a0230859ea18437100e17/logos/accent/wotd-logo.svg" width="50%">
</p>

# Word of the Day
[![Version](https://img.shields.io/badge/Version-1.0.0-%231976d2)](https://github.com/gaming-gaming/Word-of-the-Day/releases/)
[![License](https://raw.githubusercontent.com/gaming-gaming/WOTD-Brand-Assets/3e7d8060803a34e4d96a0230859ea18437100e17/badges/License-Apache%202.0-gradient.svg)](LICENSE)

**Word of the Day (WOTD)** is a service for providing a unique and interesting word every day via website and communication services.
The code is completely free to use and open-source under the [Apache License 2.0](https://www.apache.org/licenses/LICENSE-2.0).

### Key Features
- A website for displaying the Word of the Day (default port: `80`)
- A LAN shell terminal webpage for remotely controlling the host computer (default port: `8000`)
- A Discord bot that messages subscribing users and server channels daily

### Extensions
By default, all extensions (in `./src/extensions`) are placed in the `.dormant` folder. If you would like to use any of the included extensions, simply take the folders outside of the `.dormant` folder. Extensions may include files for configuration.

### Hosting

#### Option 1: Running from Source
```bash
git clone https://github.com/gaming-gaming/Word-of-the-Day.git
cd Word-of-the-Day
pip install -r requirements.txt
python main.py
```
#### Option 2: Portable Version
1. **Download** the latest `WOTD-Portable.zip` from [Releases](https://github.com/gaming-gaming/Word-of-the-Day/releases)
2. **Extract** the folder anywhere on your computer
3. **Run** the appropriate start script:
    - Windows: `start_amd64.bat`, `start_x86.bat`, or `start_arm64.bat`
    - Linux: `start_x86_x64.sh`, `start_i386.sh`, `start_arm64.sh`, or `start_armv7.sh`
