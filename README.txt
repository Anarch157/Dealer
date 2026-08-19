===================== Dealer =====================

--------------------Description--------------------

A music and mini-games bot for discord written in Python3

--------------------Dependencies--------------------

1. The requirements.txt contains modules needed by the python environment.
2. FFMPEG and Deno need to be installed on the host OS and added to PATH
   For debian : sudo apt install -y ffmpeg
                curl -fsSL https://deno.land/install.sh | sh
3. The directory containing the .py file should have 3 more files:
   1. config.txt: This file includes bot token, source code url and debug channel id.
   2. db.db: This acts as the database file for the bot, the bot
      automatically creates this with default values, if not present.
   3. cookies.txt: This includes youtube cookies in netscape format.
