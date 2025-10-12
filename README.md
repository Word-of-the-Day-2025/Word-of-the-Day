<p align="center">
  <img src="https://raw.githubusercontent.com/gaming-gaming/WOTD-Brand-Assets/main/logos/accent/wotd-logo.svg" width="50%">
</p>

# Word of the Day
[![Managed by Sesquipedalians](https://raw.githubusercontent.com/Word-of-the-Day-2025/WOTD-Brand-Assets/main/badges/Managed_by-Sesquipedalians-%231976d2.svg)](https://wotd.site)
[![Version](https://raw.githubusercontent.com/Word-of-the-Day-2025/WOTD-Brand-Assets/main/badges/Version-1.3.0-%2376D219.svg)](https://github.com/gaming-gaming/Word-of-the-Day/releases/)
[![Free API for Developers](https://raw.githubusercontent.com/Word-of-the-Day-2025/WOTD-Brand-Assets/main/badges/Free_API_for_Developers-%23d21976.svg)](https://wotd.site/api)
[![License](https://raw.githubusercontent.com/Word-of-the-Day-2025/WOTD-Brand-Assets/main/badges/License-Apache%202.0-gradient.svg)](LICENSE)

[![Integration for Discord](https://raw.githubusercontent.com/Word-of-the-Day-2025/WOTD-Brand-Assets/main/badges/Integration_for-Discord-%235865f2.svg)](https://discord.com/oauth2/authorize?client_id=1322109562119000149&permissions=0&integration_type=0&scope=bot)
[![Made With Python](https://raw.githubusercontent.com/Word-of-the-Day-2025/WOTD-Brand-Assets/main/badges/Made_With-Python-%233572a5.svg)](https://www.python.org/)
[![Made With HTML5](https://raw.githubusercontent.com/Word-of-the-Day-2025/WOTD-Brand-Assets/main/badges/Made_With-HTML5-%23e34c26.svg)](https://html.spec.whatwg.org/)
[![Made With CSS](https://raw.githubusercontent.com/Word-of-the-Day-2025/WOTD-Brand-Assets/main/badges/Made_With-CSS-%23663399.svg)](https://www.w3.org/Style/CSS/)
[![Made With JavaScript](https://raw.githubusercontent.com/Word-of-the-Day-2025/WOTD-Brand-Assets/main/badges/Made_With-JavaScript-%23f1e05a.svg)](https://tc39.es/)
[![Powered by SQLite](https://raw.githubusercontent.com/Word-of-the-Day-2025/WOTD-Brand-Assets/main/badges/Powered_by-SQLite-%23003b57.svg)](https://sqlite.org/)

### Overview
**Word of the Day (WOTD)** is a service for providing a unique and interesting word every day via website and communication services.
The code is completely free to use and open-source under the [Apache License 2.0](https://www.apache.org/licenses/LICENSE-2.0).

### Key Features
- A website for displaying the Word of the Day (default port: `443`)
- A free API for requesting Word of the Day data (default port: `8443`)
- A Discord bot that messages subscribing users and server channels daily

> [!WARNING]  
> The words database in this repository that the script uses only comes with the first 16 words, from 1 January 2025, to 16 January 2025. You must provide your own words or download the public database at https://wotd.site/databases.

# Extensions
Word of the Day comes with extensions you may use in `./src/extensions`. The extensions included by default are for providing channels to access Word of the Day. You may make your own extensions by creating a folder with a `__init__.py` file inside.
## Website + API
The **Site** extension is in the folder `./src/extensions/site`. This extension is for both the main website ([`wotd.site`](https://wotd.site)) and the API ([`api.wotd.site`](https://api.wotd.site)).
Inside the extension's folder is a `config.json` file for configuring the site, and a `.env` file for setting the hashed admin password.
There is also a `messages/` folder for messages sent via the contact page, which contains json files of user mail.

The API has a variety of endpoints for developers to use:
- **/query?date={date}**: Gets the WOTD for a specific date (format: YYYY-MM-DD). If no date is provided, it defaults to the current date.
- **/query_previous?date={date}&limit={limit}**: Gets a list of previous WOTDs. The date parameter is optional and defaults to the current date. The limit parameter specifies how many previous WOTDs to return (default is 3, maximum is 8).
- **/find_wotd?word={word}**: Searches for a specific word in the WOTD database. The word parameter is required.

> [!NOTE]  
> Displayed URLs (Like the ones shown on the API documentation page) and social links are hard-coded into the site. If you are self-hosting, be sure to replace these with your own data.

## Discord Bot
The **Discord Bot** extension is in the folder `./src/extensions/discord-bot`. Inside is a `config.json` file for your bot's configuration, and a `.env` file for your bot's token. `subscribers.db` is a database of subscribed server channels and DMs.

The Discord bot includes a variety of commands for both WOTD users and administrators. User commands use slashes, while admin commands use the "! " suffix.

Users may use basic query and config commands:
![Demonstration 0](https://raw.githubusercontent.com/Word-of-the-Day-2025/WOTD-Brand-Assets/refs/heads/main/misc/Demo0.gif)
![Demonstration 1](https://raw.githubusercontent.com/Word-of-the-Day-2025/WOTD-Brand-Assets/refs/heads/main/misc/Demo1.gif)

Admins have access to advanced commands unavailable to regular users:
- **append {word} {ipa} {pos} {definition} {date}**: Appends a new word to the `words.db` database. The {date} argument is optional and defaults to the day after the last date set in the table.
- **monitor**: Returns information on the hosting computer's specs and performance.
- **query_next**: Queries tomorrow's Word of the Day.
- **set_wotd {word} {ipa} {pos} {definition}**: Sets the current Word of the Day.
- **test_send**: A function to test the message sent to Word of the Day subscribers.

# Self-Hosting
> [!CAUTION]
> By default, both the website and API will be hosted by starting the script. To change this, you may edit the site configuration settings at `./src/extensions/site/config.json`.
#### Linux:
```bash
git clone https://github.com/gaming-gaming/Word-of-the-Day.git
cd Word-of-the-Day
pip3 install -r requirements.txt
sudo bash start.sh
```
#### Windows (CMD as admin):
```cmd
git clone https://github.com/gaming-gaming/Word-of-the-Day.git
cd Word-of-the-Day
pip install -r requirements.txt
start.bat
```

<h4 align="center">
  Thank you for using <img src="https://raw.githubusercontent.com/Word-of-the-Day-2025/WOTD-Brand-Assets/main/logos/accent/wotd-logo.svg" height=12em style="vertical-align: middle;">!
</h4>
