                      Dealer

--------------------Description--------------------

A music and mini-games bot for discord written in Python3

--------------------Dependencies--------------------

The following modules needs to be installed manually:
  1. FFMPEG (python pip and os)
  2. PyNaCl (python pip)
  3. discord (python pip)
  4. yt_dlp (python pip)
  5. aiosqlite (python pip)
  6. aiohttp (python pip)

The directory containing the .py file should have 2 more files:
  1. config.txt: This file contains 2 lines: first having the 
     bot token and the next containing the bot owner's discord id.
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
       Added NSFW features (hentai, neko, trap, blowjob)
       Added GitHub link in the help message