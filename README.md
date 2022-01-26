# Music Analyzer
Music Analyzer is like Spotify Wrapped®, but year-round.

## Analyzer
The analyzer is the entire backbone of the system. It's what talks to Last.fm's API to get a user's recently played tracks. It's also asynchronous, because otherwise it takes forever (40+ minutes synchronous, 10-15 minutes asynchronous).

The analyzer requires a few environment variables, which you should set in the `.env` file (rename the `.env.sample` file to `.env` and fill in the values).

- `USERNAME`: The username you want the analyzer to analyzer
- `TIMEFRAME`: A timeframe value (must match the keys from the `Timeframe` enum)
  - `TODAY`
  - `THIS_WEEK`
  - `THIS_MONTH`
  - `THIS_YEAR`
  - `YESTERDAY`
  - `LAST_WEEK`
  - `LAST_MONTH`
  - `LAST_YEAR`
- `LAST_FM_API_KEY`: Your Last.fm API key ([generate it here](https://www.last.fm/api/account/create), then copy the API key)
- `SPOTIFY_CLIENT_ID` and `SPOTIFY_CLIENT_SECRET`: Your Spotify client ID and secret
  - To create these, you'll have to create an app in the [Spotify developer dashboard](https://developer.spotify.com/dashboard/applications)
  - Follow the on-screen instructions to create a new app, name it whatever, specify whatever URLs, and copy the client ID and secret
  - It doesn't matter whether the app is in development mode or not, as only you will be using the API
- `ANALYZER_OUTPUT` (optional): If you want detailed output from the analyzer, set this variable to anything. Omit it to not output details.
- `HISTORY_OUTPUT` (optional): If you want a `tracks.csv` file generated for each user with the user's recent tracks history, set this variable to anything. Omit it to not output a file.

Before running the analyzer, make sure to run `pip3 install -r requirements.txt` to install all dependencies.

The analyzer will generate three files per Last.fm user, and one for all users. The universal file is a track cache (expires after a month), used to cache track data from Last.fm, MusicBrainz, and Spotify. The per-user files are a user cache (stores recent tracks for a week, then clears the cache), a CSV file will the user's tracks (if the `HISTORY_OUTPUT` environment variable is set), and a JSON file with the message contents (if a message is being sent, such as through the Discord bot).

## Discord Bot
The Discord bot is a work-in-progress frontend client for the analyzer. It uses Node.js and [Discord.js](https://discordjs.guide/). The built-in `child_process` library is used to call the analyzer. It's been tested on a Mac, but I've been unable to get it to work on a Raspberry Pi.

The Discord bot also requires a few of its own environment variables, which you set in the `.env` file (rename the `.env.sample` file to `.env` and fill in the values).

- `DISCORD_TOKEN`: Generate this with the following [this guide on Discord.js's website](https://discordjs.guide/preparations/setting-up-a-bot-application.html)
- `CLIENT_ID`: Your bot's client ID
  - Go to the Discord Developer Portal, select your bot, go to "General Information", then copy the value for "Application ID"
- `GUILD_ID`: Used to deploy slash commands to a particular server/guild, instead of all servers
  - Uncomment lines 9 and 132 in `discord-bot/deploy-commands.js` and comment line 133 to switch to single-server command deployment
  - Reverse to switch to global server deployment

Before running `npm run start`, do two things.
1. `npm i` or `npm install`
    - Installs all the dependencies
2. Create an empty `users.json` file
    - Content should be the following: `{}`

## License
This program is licensed under the [GPLv3 license](https://choosealicense.com/licenses/gpl-3.0/).