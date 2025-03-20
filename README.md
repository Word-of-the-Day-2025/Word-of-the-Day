<p align="center">
  <img src="https://raw.githubusercontent.com/gaming-gaming/WOTD-Brand-Assets/main/logos/accent/wotd-logo.svg" width="50%">
</p>

# Word of the Day
[![Version](https://raw.githubusercontent.com/gaming-gaming/WOTD-Brand-Assets/main/badges/Version-1.0.0-%231976d2.svg)](https://github.com/gaming-gaming/Word-of-the-Day/releases/)
[![License](https://raw.githubusercontent.com/gaming-gaming/WOTD-Brand-Assets/main/badges/License-Apache%202.0-gradient.svg)](LICENSE)

**Word of the Day (WOTD)** is a service for providing a unique and interesting word every day via website and communication services.
The code is completely free to use and open-source under the [Apache License 2.0](https://www.apache.org/licenses/LICENSE-2.0).

### Key Features
- A website for displaying the Word of the Day (default port: `80`)
- A Discord bot that messages subscribing users and server channels daily

### Extensions
By default, all extensions (in `./src/extensions`) are placed in the `.dormant` folder. If you would like to use any of the included extensions, simply take the folders outside of the `.dormant` folder. Extensions may include files for configuration.

### Hosting

```bash
git clone https://github.com/gaming-gaming/Word-of-the-Day.git
cd Word-of-the-Day
pip install -r requirements.txt
python main.py
```
