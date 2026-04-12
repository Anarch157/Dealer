                      Dealer

--------------------Description--------------------

A music and mini-games bot for discord written in Python3

--------------------Dependencies--------------------

The following modules needs to be installed manually:
  1. FFMPEG (os)
  2. PyNaCl (python pip)
  3. discord (python pip)
  4. yt_dlp (python pip)
  5. aiosqlite (python pip)
  6. aiohttp (python pip)
  7. davey (python pip)
  8. deno (os)

Replace the following 4 files from the venv with the ones provided:
  1. voice_client.py
  2. voice_state.py
  3. gateway.py
  4. client.py (if default file gives errors)

The directory containing the .py file should have 2 more files:
  1. config.txt: This file contains 2 lines: 
                 1. Discord bot token
                 2. Source code url
  2. db.db: This acts as the database file for the bot, the bot
     automatically creates this with default values, if not present.

--------------------Change Log--------------------

v1.0 - 04 June 2022:
       Bot has been deployed

v1.1 - 07 August 2023:
       Added "Stop" functionality
       Added "Queue" feature
       General improvements pertaining to code neatness

v2.0 - 27 April 2025:
       Added cf, dice, roulette

v2.1 - 28 April 2025:
       Added slots

v2.2 - 29 April 2025:
       Added rob, tb

v2.3 - 10 June 2025:
       fixed rob resetting bank bug

v2.4 - 14 June 2025:
       fixed roulette winning amount
       added top feature

v2.5 - 21 June 2025:
       Added ping
       Added version in help
       Added quiz
       Added wheel of fortune

v2.6 - 24 June 2025:
       Added quiz categories
       
v2.7 - 21 July 2025:
       Converted to class based bot using cogs
       Auto delete file after playing
       Auto leave voice channel after playing

v2.8 - 24 July 2025:
       Auto delete files on startup
       Use opus instead of mp3

v2.9 - 29 July 2025:
       Removed connect and disconnect
       Added Whitelist and Blacklist

v3.0 - 29 July 2025:
       Added NSFW features (waifu, neko, trap, blowjob)
       Added GitHub link in the help message

v3.1 - 01 August 2025:
       Fixed bot leaving on skip command
       Moved setbal comamnd to games cog
       Used @is_owner instead of manual id check
       Used embedded msgs for utils and games cogs

v3.2 - 03 August 2025:
       Added GUI for music control

v3.3 - 04 August 2025:
       Added restart command for bot and rpi

v3.4 - 18 August 2025:
       Converted the bot to discord.Client
       live music streaming instead of download and play
       No need for owner id in config
       Guild sync for faster testing (id in config)
       Removed GUI for music control

v3.5 - 18 September 2025:
       Fixed bug related to tossbattle bank balance

v3.6 - 03 March 2026:
       Removed test guild code
       Added DAVE compatibility
       Renamed rpi to host

v3.7 - 04 March 2026:
       Added announcement command

v4.0 - 30 March 2026:
       Added youtube playlist support
       Autodiconnect if paused more than 15 minutes
       Removed NSFW
       No coins required to play songs
       Thumbnails show only when songs start

v4.1 - 01 Aril 2026
       Added multiple skip
       Added message on start
       Added shuffle queue

v4.2 - 12 April 2026
       Removed all cooldowns except rob and fortune
