# -------------------------------------------------- Imports --------------------------------------------------

import discord
import aiosqlite
import secrets
import os
from discord import app_commands
import functools
import time
import yt_dlp
import asyncio
import sys
import aiohttp
import random
import html
import contextlib
from urllib.parse import urlparse, parse_qs, urlencode, urlunparse

# -------------------------------------------------- Decorator: Cooldown --------------------------------------------------

def cooldown(cooldown_seconds: int):
    def decorator(func):
        @functools.wraps(func)
        async def wrapper(interaction: discord.Interaction, *args, **kwargs):
            user_id = interaction.user.id
            command_name = func.__name__
            now = time.time()
            key = (user_id, command_name)

            bot = interaction.client

            cooldown_end = bot.cooldowns.get(key, 0)
            if cooldown_end > now:
                time_left = cooldown_end - now
                await interaction.response.send_message(
                    embed=discord.Embed(
                        title=f"⏳ Please wait {int(time_left)} seconds before using this command again.",
                        color=discord.Color.gold()
                    ),
                    ephemeral=True
                )
                return

            bot.cooldowns[key] = now + cooldown_seconds
            await func(interaction, *args, **kwargs)
        return wrapper
    return decorator

# -------------------------------------------------- Decorator: Requires Coins --------------------------------------------------

def requires_coins(param_name="bet_amount"):
    def decorator(func):
        @functools.wraps(func)
        async def wrapper(interaction: discord.Interaction, *args, **kwargs):
            bet_amount = kwargs.get(param_name)
            if bet_amount is None:
                import inspect
                sig = inspect.signature(func)
                params = list(sig.parameters)
                try:
                    idx = params.index(param_name) - 1
                    bet_amount = args[idx]
                except (ValueError, IndexError):
                    bet_amount = None


            if not isinstance(bet_amount, int) or bet_amount <= 0:
                await interaction.response.send_message(
                    embed=discord.Embed(
                        title="❌ Invalid bet amount!",
                        description="Please enter a positive integer for your bet amount.",
                        color=discord.Color.gold()
                    ),
                    ephemeral=True
                )
                return

            if bet_amount is None:
                return await func(interaction, *args, **kwargs)

            bot = interaction.client
            wallet, _ = await bot.get_balances(interaction.user.id)
            if bet_amount > wallet:
                await interaction.response.send_message(
                    embed=discord.Embed(
                        title="❌ Not enough coins in wallet!",
                        description=f"You need {bet_amount:,} coins but have only {wallet:,}.",
                        color=discord.Color.gold()
                    ),
                    ephemeral=True
                )
                return

            return await func(interaction, *args, **kwargs)
        return wrapper
    return decorator


# -------------------------------------------------- Decorator: Validate Option --------------------------------------------------

def validate_option(param_name: str, valid_options: set):
    def decorator(func):
        @functools.wraps(func)
        async def wrapper(interaction: discord.Interaction, *args, **kwargs):

            if param_name in kwargs:
                option = kwargs[param_name]
            else:

                import inspect
                sig = inspect.signature(func)
                params = list(sig.parameters)
                try:
                    idx = params.index(param_name) - 1
                    option = args[idx]
                except (ValueError, IndexError):
                    return await interaction.response.send_message(
                        embed=discord.Embed(
                            description=f"❌ Missing or invalid {param_name} parameter.",
                            color=discord.Color.gold()
                        ),
                        ephemeral=True
                    )

            if isinstance(option, str):
                option_check = option.lower()
                valid_options_check = {opt.lower() for opt in valid_options}
                if option_check not in valid_options_check:
                    return await interaction.response.send_message(
                        embed=discord.Embed(
                            description=f"❌ Invalid option {option}. Valid options: {', '.join(valid_options)}.",
                            color=discord.Color.gold()
                        ),
                        ephemeral=True
                    )
            else:
                if option not in valid_options:
                    return await interaction.response.send_message(
                        embed=discord.Embed(
                            description=f"❌ Invalid option {option}. Valid options: {', '.join(str(o) for o in valid_options)}.",
                            color=discord.Color.gold()
                        ),
                        ephemeral=True
                    )

            return await func(interaction, *args, **kwargs)
        return wrapper
    return decorator


# -------------------------------------------------- Decorator: Owner Only --------------------------------------------------

def owner_only():
    def decorator(func):
        @functools.wraps(func)
        async def wrapper(interaction: discord.Interaction, *args, **kwargs):
            app_info = await interaction.client.application_info()
            owner_id = app_info.owner.id
            if interaction.user.id != owner_id:
                await interaction.response.send_message(
                    "❌ You are not authorized to use this command.",
                    ephemeral=True
                )
                return
            return await func(interaction, *args, **kwargs)
        return wrapper
    return decorator

# -------------------------------------------------- Decorator: Blacklist Check --------------------------------------------------

def blacklist_check(command_name=None):
    def decorator(func):
        @functools.wraps(func)
        async def wrapper(interaction: discord.Interaction, *args, **kwargs):
            cmd = command_name or func.__name__
            bl = interaction.client.blacklist.get(cmd, set())
            if interaction.user.id in bl:
                await interaction.response.send_message(
                    "🚫 You are blacklisted from using this command.",
                    ephemeral=True
                )
                return
            return await func(interaction, *args, **kwargs)
        return wrapper
    return decorator



# -------------------------------------------------- Bot Class --------------------------------------------------

class Dealer(discord.Client):
    def __init__(self, config_path, db_path):
        intents = discord.Intents.all()
        super().__init__(intents=intents)
        self.tree = app_commands.CommandTree(self)

        with open(config_path, "r") as f:
            lines = f.readlines()
        self.token = lines[0].strip()
        self.source_code_link = lines[1].strip()

        self.db_path = db_path

        self.cooldowns = {}
        self.db = None
        self.music_queue = {}
        self.blacklist = {}
        self.prefetch_tasks = {}
        self.current_song = {}
        self.pause_disconnect_tasks = {}
        self.PAUSE_TIMEOUT = 900

        self.FFMPEG_OPTIONS = {
            'before_options': '-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5',
            'options': '-vn',
        }
        self.YDL_OPTIONS = {
            'format': 'bestaudio[ext=webm][acodec=opus]/bestaudio/best',
            'noplaylist': False,
            'quiet': True,
            'default_search': 'ytsearch',
            'extract_flat': False,
            'ignoreerrors': True,
            'lazy_playlist': True,
            'js_runtimes': {
                'deno': {'path': 'deno'}
            },
            'remote_components': ['ejs:github'],
        }


    async def setup_hook(self):
        self.db = await aiosqlite.connect(self.db_path)
        await self.init_db()

        # Global sync
        await self.tree.sync()
        print("[+] Slash commands synced globally.")



    async def setup_hook(self):
        self.db = await aiosqlite.connect(self.db_path)
        await self.init_db()

        # Global sync
        await self.tree.sync()
        print("[+] Slash commands synced globally.")

    async def on_ready(self):
        print(f"[+] Logged in as {self.user} ({self.user.id})")

        for guild in self.guilds:
            try:
                for channel in guild.text_channels:
                    if (
                        channel.name.lower() == "general"
                        and channel.permissions_for(guild.me).send_messages
                    ):
                        await channel.send("hello im online")
                        break
            except Exception as e:
                print(f"[!] Failed in guild {guild.id}: {e}")




    async def close(self):
        if self.db:
            await self.db.close()
        await super().close()

# -------------------------------------------------- Function: Init DB --------------------------------------------------

    async def init_db(self):
        await self.db.execute('''
            CREATE TABLE IF NOT EXISTS accounts (
                user_id INTEGER PRIMARY KEY,
                wallet INTEGER NOT NULL DEFAULT 50000,
                bank INTEGER NOT NULL DEFAULT 0
            )
        ''')
        await self.db.commit()

# -------------------------------------------------- Function: Get Balances --------------------------------------------------

    async def get_balances(self, user_id):
        async with self.db.execute('SELECT wallet, bank FROM accounts WHERE user_id = ?', (user_id,)) as cursor:
            result = await cursor.fetchone()
            if result is None:
                await self.db.execute(
                    'INSERT INTO accounts (user_id, wallet, bank) VALUES (?, ?, ?)',
                    (user_id, 50000, 0)
                )
                await self.db.commit()
                return 50000, 0
            return result

# -------------------------------------------------- Function: Update Balances --------------------------------------------------

    async def update_balances(self, user_id, wallet, bank):
        await self.db.execute(
            'UPDATE accounts SET wallet = ?, bank = ? WHERE user_id = ?',
            (wallet, bank, user_id)
        )
        await self.db.commit()

# -------------------------------------------------- Function: Check Queue --------------------------------------------------

    async def check_queue(self, guild_id):
        guild = self.get_guild(guild_id)
        if not guild:
            return

        voice_client = guild.voice_client
        queue = self.music_queue.get(guild_id, [])

        if not voice_client:
            return

        if not queue:
            self.current_song.pop(guild_id, None)

            old_task = self.prefetch_tasks.pop(guild_id, None)
            if old_task and not old_task.done():
                old_task.cancel()

            if voice_client.is_connected():
                await voice_client.disconnect()
            return

        next_song = queue.pop(0)

        resolved = await self.resolve_song(next_song)
        if not resolved:
            return await self.check_queue(guild_id)

        stream_url = resolved['stream_url']
        title = resolved.get('title', 'Unknown title')
        duration = resolved.get('duration') or 0

        self.current_song[guild_id] = resolved

        try:
            source = discord.FFmpegOpusAudio(stream_url, **self.FFMPEG_OPTIONS)
        except Exception:
            return await self.check_queue(guild_id)

        def after_playback(error):
            if error:
                print(f"Playback error in guild {guild_id}: {error}")

            self.loop.call_soon_threadsafe(
                lambda: self.loop.create_task(self.check_queue(guild_id))
            )

        self.cancel_pause_disconnect(guild_id)
        voice_client.play(source, after=after_playback)

        channel_id = resolved.get('text_channel_id')
        song_url = resolved.get('webpage_url')
        title = resolved.get('title', 'Unknown title')

        if channel_id and song_url:
            text_channel = self.get_channel(channel_id)
            if text_channel:
                try:
                    await text_channel.send(f"🎶 Now playing: **{title}**\n{song_url}")
                except Exception as e:
                    print(f"[!] Failed to send now playing message: {e}")

        if self.music_queue.get(guild_id):
            prefetch_delay = max(0, duration - 10) if duration else 15
            self.schedule_prefetch(guild_id, prefetch_delay)

# --------------------------------------------------- Function: Song Fetch Helpers ---------------------------------------------


    def extract_info_sync(self, query, *, flat=False, no_playlist=False):
        opts = dict(self.YDL_OPTIONS)
        opts['extract_flat'] = 'in_playlist' if flat else False
        opts['noplaylist'] = no_playlist

        with yt_dlp.YoutubeDL(opts) as ydl:
            return ydl.extract_info(query, download=False)

    async def extract_info_async(self, query, *, flat=False, no_playlist=False):
        return await asyncio.to_thread(
            self.extract_info_sync,
            query,
            flat=flat,
            no_playlist=no_playlist
        )


    async def resolve_song(self, song: dict):
        if song.get('stream_url'):
            return song

        query = song.get('webpage_url') or song.get('query')
        if not query:
            return None

        try:
            info = await self.extract_info_async(query, flat=False, no_playlist=True)
        except Exception:
            return None

        if not info:
            return None

        stream_url = info.get('url')
        if not stream_url:
            return None

        song['stream_url'] = stream_url
        song['title'] = info.get('title', song.get('title', 'Unknown title'))
        song['webpage_url'] = info.get('webpage_url', song.get('webpage_url', query))
        song['duration'] = info.get('duration', song.get('duration'))
        return song

    async def prefetch_next_song(self, guild_id: int, delay: float = 0):
        if delay > 0:
            await asyncio.sleep(delay)

        queue = self.music_queue.get(guild_id)
        if not queue:
            return

        next_song = queue[0]
        if next_song.get('stream_url'):
            return

        await self.resolve_song(next_song)

    def schedule_prefetch(self, guild_id: int, delay: float):
        old_task = self.prefetch_tasks.get(guild_id)
        if old_task and not old_task.done():
            old_task.cancel()

        self.prefetch_tasks[guild_id] = self.loop.create_task(
            self.prefetch_next_song(guild_id, delay=max(0, delay))
        )

    def is_playlist_query(self, query: str) -> bool:
        q = query.strip()

        if not q.startswith(("http://", "https://")):
            return False

        parsed = urlparse(q)
        host = parsed.netloc.lower()
        path = parsed.path.lower()

        if "youtube.com" in host or "music.youtube.com" in host:
            return path == "/playlist"

        return False


    def normalize_single_track_url(self, query: str) -> str:
        q = query.strip()

        if not q.startswith(("http://", "https://")):
            return q

        parsed = urlparse(q)
        host = parsed.netloc.lower()

        if "youtube.com" not in host and "music.youtube.com" not in host:
            return q

        params = parse_qs(parsed.query)

        for key in ("list", "index", "start_radio", "pp"):
            params.pop(key, None)

        new_query = urlencode(params, doseq=True)
        return urlunparse(parsed._replace(query=new_query))

# -------------------------------------------------- Function: Pause Timer --------------------------------------------------


    async def disconnect_if_paused_too_long(self, guild_id: int, delay: float = None):
        if delay is None:
            delay = self.PAUSE_TIMEOUT
        try:
            await asyncio.sleep(delay)

            guild = self.get_guild(guild_id)
            if not guild:
                return

            voice_client = guild.voice_client
            if not voice_client or not voice_client.is_connected():
                return

            if voice_client.is_paused():
                self.music_queue[guild_id] = []
                self.current_song.pop(guild_id, None)

                prefetch_task = self.prefetch_tasks.pop(guild_id, None)
                if prefetch_task and not prefetch_task.done():
                    prefetch_task.cancel()

                self.pause_disconnect_tasks.pop(guild_id, None)

                try:
                    await voice_client.disconnect()
                except Exception as e:
                    print(f"[!] Failed to disconnect paused bot in guild {guild_id}: {e}")
        except asyncio.CancelledError:
            pass


    def schedule_pause_disconnect(self, guild_id: int, delay: float = None):
        if delay is None:
            delay = self.PAUSE_TIMEOUT
        old_task = self.pause_disconnect_tasks.get(guild_id)
        if old_task and not old_task.done():
            old_task.cancel()

        self.pause_disconnect_tasks[guild_id] = self.loop.create_task(
            self.disconnect_if_paused_too_long(guild_id, delay)
        )


    def cancel_pause_disconnect(self, guild_id: int):
        old_task = self.pause_disconnect_tasks.pop(guild_id, None)
        if old_task and not old_task.done():
            old_task.cancel()


# -------------------------------------------------- Init Bot --------------------------------------------------

bot = Dealer("config.txt", "db.db")

# -------------------------------------------------- Command: Balance --------------------------------------------------

@bot.tree.command(name="balance", description="Check your balance")
@blacklist_check()
async def balance(interaction: discord.Interaction):
    wallet, bank = await bot.get_balances(interaction.user.id)
    total = wallet + bank
    embed = discord.Embed(
        title=f"🪙 {interaction.user.display_name}'s Balance",
        color=discord.Color.gold()
    )
    embed.set_thumbnail(url=interaction.user.avatar.url if interaction.user.avatar else None)
    embed.add_field(name="💰 Wallet", value=f"{wallet:,}", inline=True)
    embed.add_field(name="🏦 Bank", value=f"{bank:,}", inline=True)
    embed.add_field(name="📊 Total", value=f"{total:,}", inline=True)
    await interaction.response.send_message(embed=embed)


# -------------------------------------------------- Command: Deposit --------------------------------------------------

@bot.tree.command(name="deposit", description="Deposit coins from wallet to bank")
@app_commands.describe(amount="Amount of coins to deposit (optional, defaults to all)")
@blacklist_check()
async def deposit(interaction: discord.Interaction, amount: int = None):
    wallet, bank = await bot.get_balances(interaction.user.id)

    if amount is None:
        if wallet == 0:
            await interaction.response.send_message(
                "You have no coins in your wallet to deposit.",
                ephemeral=True
            )
            return
        deposit_amount = wallet
    else:
        if not isinstance(amount, int) or amount <= 0:
            await interaction.response.send_message(
                "Please enter a positive integer amount to deposit.",
                ephemeral=True
            )
            return
        if amount > wallet:
            await interaction.response.send_message(
                f"You cannot deposit more coins than you have in your wallet ({wallet:,}).",
                ephemeral=True
            )
            return
        deposit_amount = amount

    wallet -= deposit_amount
    bank += deposit_amount
    total = wallet + bank
    await bot.update_balances(interaction.user.id, wallet, bank)

    embed = discord.Embed(
        title=f"{interaction.user.display_name} deposited {deposit_amount:,} coins into the bank",
        color=discord.Color.gold()
    )
    embed.add_field(name="💰 Wallet", value=f"{wallet:,}", inline=True)
    embed.add_field(name="🏦 Bank", value=f"{bank:,}", inline=True)
    embed.add_field(name="📊 Total", value=f"{total:,}", inline=True)

    await interaction.response.send_message(embed=embed)


# -------------------------------------------------- Command: Withdraw --------------------------------------------------

@bot.tree.command(name="withdraw", description="Withdraw coins from your bank to wallet")
@app_commands.describe(amount="Amount of coins to withdraw (optional, defaults to all)")
@blacklist_check()
async def withdraw(interaction: discord.Interaction, amount: int = None):
    wallet, bank = await bot.get_balances(interaction.user.id)

    if amount is None:
        if bank == 0:
            await interaction.response.send_message(
                "You have no coins in your bank to withdraw.",
                ephemeral=True
            )
            return
        withdraw_amount = bank
    else:
        if not isinstance(amount, int) or amount <= 0:
            await interaction.response.send_message(
                "Please enter a positive integer amount to withdraw.",
                ephemeral=True
            )
            return
        if amount > bank:
            await interaction.response.send_message(
                f"You cannot withdraw more coins than you have in your bank ({bank:,}).",
                ephemeral=True
            )
            return
        withdraw_amount = amount

    bank -= withdraw_amount
    wallet += withdraw_amount
    total = wallet + bank
    await bot.update_balances(interaction.user.id, wallet, bank)

    embed = discord.Embed(
        title=f"{interaction.user.display_name} withdrew {withdraw_amount:,} coins from the bank",
        color=discord.Color.gold()
    )
    embed.add_field(name="💰 Wallet", value=f"{wallet:,}", inline=True)
    embed.add_field(name="🏦 Bank", value=f"{bank:,}", inline=True)
    embed.add_field(name="📊 Total", value=f"{total:,}", inline=True)

    await interaction.response.send_message(embed=embed)


# -------------------------------------------------- Command: Give --------------------------------------------------

@bot.tree.command(name="give", description="Give coins to another user from your wallet")
@app_commands.describe(user="User to give coins to", amount="Amount of coins to give (optional, defaults to all)")
@blacklist_check()
async def give(interaction: discord.Interaction, user: discord.Member, amount: int = None):
    if user.id == interaction.user.id:
        await interaction.response.send_message(
            "You cannot give coins to yourself.",
            ephemeral=True
        )
        return

    sender_wallet, sender_bank = await bot.get_balances(interaction.user.id)
    receiver_wallet, receiver_bank = await bot.get_balances(user.id)

    if amount is None:
        if sender_wallet == 0:
            await interaction.response.send_message(
                "You have no coins in your wallet to give.",
                ephemeral=True
            )
            return
        give_amount = sender_wallet
    else:
        if not isinstance(amount, int) or amount <= 0:
            await interaction.response.send_message(
                "Please enter a positive integer amount to give.",
                ephemeral=True
            )
            return
        if amount > sender_wallet:
            await interaction.response.send_message(
                f"You don't have enough coins in your wallet. You have {sender_wallet:,} coins.",
                ephemeral=True
            )
            return
        give_amount = amount

    sender_wallet -= give_amount
    receiver_wallet += give_amount

    await bot.update_balances(interaction.user.id, sender_wallet, sender_bank)
    await bot.update_balances(user.id, receiver_wallet, receiver_bank)

    embed = discord.Embed(
        title=f"💸 {interaction.user.display_name} gave {give_amount:,} coins to {user.display_name}",
        color=discord.Color.gold()
    )
    embed.add_field(name=f"{interaction.user.display_name}'s Wallet", value=f"{sender_wallet:,}", inline=True)
    embed.add_field(name=f"{user.display_name}'s Wallet", value=f"{receiver_wallet:,}", inline=True)

    await interaction.response.send_message(embed=embed)




# -------------------------------------------------- Command: Fortune --------------------------------------------------

@bot.tree.command(name="fortune", description="Spin the wheel of fortune and win coins!")
@blacklist_check()
@cooldown(3600)
async def fortune(interaction: discord.Interaction):
    rewards = [0, 1000, 2000, 3000, 4000, 5000]
    reward = secrets.choice(rewards)

    wallet, bank = await bot.get_balances(interaction.user.id)
    wallet += reward
    await bot.update_balances(interaction.user.id, wallet, bank)

    if reward == 0:
        description = "You spun the wheel and got **0** coins. Better luck next time!"
        color = discord.Color.red()
    else:
        description = f"Congratulations! You spun the wheel and won **{reward:,}** coins!"
        color = discord.Color.green()

    embed = discord.Embed(
        title=f"{interaction.user.display_name}'s Wheel of Fortune",
        description=description,
        color=color
    )
    embed.add_field(name="💰 Wallet", value=f"{wallet:,} coins", inline=True)
    embed.set_footer(text="⏳ Cooldown: 1 hour")

    await interaction.response.send_message(embed=embed)



# -------------------------------------------------- Command: Rob --------------------------------------------------

@bot.tree.command(name="rob", description="Attempt to rob coins from another user")
@discord.app_commands.describe(user="User to rob from")
@blacklist_check()
@cooldown(3600)  # 1 hour cooldown
async def rob(interaction: discord.Interaction, user: discord.Member):
    if user.id == interaction.user.id:
        await interaction.response.send_message(
            "You cannot rob yourself.",
            ephemeral=True
        )
        return

    robber = interaction.user
    robber_wallet, robber_bank = await bot.get_balances(robber.id)
    target_wallet, target_bank = await bot.get_balances(user.id)

    if target_wallet < 1:
        await interaction.response.send_message(
            f"{user.display_name} has no coins in their wallet to rob.",
            ephemeral=True
        )
        return

    success = secrets.choice([True, False])

    if success:
        amount = secrets.randbelow(target_wallet) + 1
        target_wallet -= amount
        robber_wallet += amount

        await bot.update_balances(user.id, target_wallet, target_bank)
        await bot.update_balances(robber.id, robber_wallet, robber_bank)

        embed = discord.Embed(
            title=f"💰 Robbery Successful!",
            description=f"{robber.display_name} robbed {amount:,} coins from {user.display_name}.",
            color=discord.Color.green()
        )
        embed.add_field(name=f"{robber.display_name}'s Wallet", value=f"{robber_wallet:,}", inline=True)
        embed.add_field(name=f"{user.display_name}'s Wallet", value=f"{target_wallet:,}", inline=True)
    else:
        if robber_wallet > 0:
            fine = secrets.randbelow(robber_wallet) + 1
            robber_wallet -= fine
            await bot.update_balances(robber.id, robber_wallet, robber_bank)
            fine_text = f"\n{robber.display_name} was fined {fine:,} coins for a failed robbery."
        else:
            fine_text = ""

        embed = discord.Embed(
            title="❌ Robbery Failed!",
            description=f"{robber.display_name} failed to rob {user.display_name}.{fine_text}",
            color=discord.Color.red()
        )
        embed.add_field(name=f"{robber.display_name}'s Wallet", value=f"{robber_wallet:,}", inline=True)

    embed.set_footer(text="⏳ Cooldown: 1 hour")
    await interaction.response.send_message(embed=embed)


# -------------------------------------------------- Command: Top --------------------------------------------------

@bot.tree.command(name="top", description="Show top 10 players by total coins")
@blacklist_check()
async def top(interaction: discord.Interaction):
    await interaction.response.defer()  # Defer immediately!

    async with bot.db.execute('SELECT user_id, wallet, bank FROM accounts') as cursor:
        rows = await cursor.fetchall()

    if not rows:
        await interaction.followup.send("No player data found.", ephemeral=True)
        return

    players = []
    for user_id, wallet, bank in rows:
        total = wallet + bank
        players.append((user_id, wallet, bank, total))

    players.sort(key=lambda x: x[3], reverse=True)
    top_players = players[:10]

    embed = discord.Embed(title="🏆 Top 10 Players", color=discord.Color.gold())

    for idx, (user_id, wallet, bank, total) in enumerate(top_players, start=1):
        try:
            user = await bot.fetch_user(user_id)
            username = user.name
        except Exception:
            username = f"User ID {user_id}"

        embed.add_field(
            name=f"{idx}. {username}",
            value=f"Wallet: {wallet:,} | Bank: {bank:,} | Total: {total:,}",
            inline=False
        )

    await interaction.followup.send(embed=embed)



# -------------------------------------------------- Command: Coin --------------------------------------------------

@bot.tree.command(name="coin", description="Flip a coin and try your luck")
@app_commands.describe(bet_option="Heads or Tails", bet_amount="How many coins to bet")
@blacklist_check()
@cooldown(60)
@requires_coins(param_name="bet_amount")
@validate_option(param_name="bet_option", valid_options={"heads", "tails"})

async def coin(interaction: discord.Interaction, bet_option: str, bet_amount: int):
    wallet, bank = await bot.get_balances(interaction.user.id)

    result = secrets.choice(["heads", "tails"])
    if result == bet_option.lower():
        winnings = bet_amount
        wallet += winnings
        await bot.update_balances(interaction.user.id, wallet, bank)
        embed = discord.Embed(
            title=f"🏆 {interaction.user.display_name} won {winnings:,} coins in Coin Flip",
            color=discord.Color.green()
        )
    else:
        wallet -= bet_amount
        await bot.update_balances(interaction.user.id, wallet, bank)
        embed = discord.Embed(
            title=f"❌ {interaction.user.display_name} lost {bet_amount:,} coins in Coin Flip",
            color=discord.Color.red()
        )

    embed.add_field(name="🎯 Bet Amount", value=f"{bet_amount:,}", inline=True)
    embed.add_field(name="🎲 Bet Option", value=bet_option.capitalize(), inline=True)
    embed.add_field(name="🏁 Result", value=result.capitalize(), inline=True)
    embed.set_footer(text="⏳ Cooldown: 1 minute")
    await interaction.response.send_message(embed=embed)


# -------------------------------------------------- Command: Dice --------------------------------------------------

@bot.tree.command(name="dice", description="Roll a dice and try to guess the number")
@app_commands.describe(bet_option="Your number (1-6)", bet_amount="How many coins to bet")
@blacklist_check()
@cooldown(60)
@requires_coins(param_name="bet_amount")
@validate_option(param_name="bet_option", valid_options={1, 2, 3, 4, 5, 6})

async def dice(interaction: discord.Interaction, bet_option: int, bet_amount: int):
    wallet, bank = await bot.get_balances(interaction.user.id)

    result = secrets.randbelow(6) + 1
    if result == bet_option:
        winnings = bet_amount * 5
        wallet += winnings
        await bot.update_balances(interaction.user.id, wallet, bank)
        embed = discord.Embed(
            title=f"🏆 {interaction.user.display_name} won {winnings:,} coins in Dice",
            color=discord.Color.green()
        )
    else:
        wallet -= bet_amount
        await bot.update_balances(interaction.user.id, wallet, bank)
        embed = discord.Embed(
            title=f"❌ {interaction.user.display_name} lost {bet_amount:,} coins in Dice",
            color=discord.Color.red()
        )

    embed.add_field(name="🎯 Bet Amount", value=f"{bet_amount:,}", inline=True)
    embed.add_field(name="🎲 Bet Option", value=str(bet_option), inline=True)
    embed.add_field(name="🏁 Result", value=str(result), inline=True)
    await interaction.response.send_message(embed=embed)


# -------------------------------------------------- Command: Roulette --------------------------------------------------

@bot.tree.command(name="roulette", description="Play European roulette and try your luck")
@app_commands.describe(bet_option="Bet on high/low, even/odd, red/black/green, or a number 0-36", bet_amount="How many coins to bet")
@blacklist_check()
@cooldown(60)
@requires_coins(param_name="bet_amount")
@validate_option(param_name="bet_option", valid_options={str(n) for n in range(0, 37)} | {"high", "low", "even", "odd", "red", "black", "green"})
async def roulette(interaction: discord.Interaction, bet_option: str, bet_amount: int):
    if bet_option.isdigit():
        bet_option = int(bet_option)

    wallet, bank = await bot.get_balances(interaction.user.id)

    red_numbers = {1,3,5,7,9,12,14,16,18,19,21,23,25,27,30,32,34,36}
    green_numbers = {0}
    black_numbers = set(range(0, 37)) - red_numbers - green_numbers

    result = secrets.choice(list(range(0, 37)))

    if result in green_numbers:
        result_color = "green"
    elif result in red_numbers:
        result_color = "red"
    else:
        result_color = "black"

    won = False
    payout = 0

    bet_option_lower = bet_option.lower() if isinstance(bet_option, str) else None

    if (isinstance(bet_option, int) and bet_option == result) or (isinstance(bet_option, str) and bet_option_lower == str(result)):
        won = True
        payout = bet_amount * 35
    elif bet_option_lower == "high" and 19 <= result <= 36:
        won = True
        payout = bet_amount * 1
    elif bet_option_lower == "low" and 1 <= result <= 18:
        won = True
        payout = bet_amount * 1
    elif bet_option_lower == "even" and result != 0 and result % 2 == 0:
        won = True
        payout = bet_amount * 1
    elif bet_option_lower == "odd" and result % 2 == 1:
        won = True
        payout = bet_amount * 1
    elif bet_option_lower == "red" and result_color == "red":
        won = True
        payout = bet_amount * 1
    elif bet_option_lower == "black" and result_color == "black":
        won = True
        payout = bet_amount * 1
    elif bet_option_lower == "green" and result_color == "green":
        won = True
        payout = bet_amount * 35

    if won:
        wallet += payout
        embed_color = discord.Color.green()
        title = f"🏆 {interaction.user.display_name} won {payout:,} coins in Roulette!"
    else:
        wallet -= bet_amount
        embed_color = discord.Color.red()
        title = f"❌ {interaction.user.display_name} lost {bet_amount:,} coins in Roulette."

    await bot.update_balances(interaction.user.id, wallet, bank)

    embed = discord.Embed(title=title, color=embed_color)
    embed.add_field(name="🎯 Bet Amount", value=f"{bet_amount:,}", inline=True)
    embed.add_field(name="🎲 Bet Option", value=str(bet_option).capitalize(), inline=True)
    embed.add_field(name="🎲 Result", value=f"{result} ({result_color.capitalize()})", inline=True)
    embed.set_footer(text="⏳ Cooldown: 1 minute")

    await interaction.response.send_message(embed=embed)


# -------------------------------------------------- Command: Slots --------------------------------------------------


@bot.tree.command(name="slots", description="Spin the slot machine and try your luck")
@app_commands.describe(bet_amount="How many coins to bet")
@blacklist_check()
@cooldown(60)
@requires_coins(param_name="bet_amount")
async def slots(interaction: discord.Interaction, bet_amount: int):
    wallet, bank = await bot.get_balances(interaction.user.id)

    symbols = ["🍒", "🍋", "🍊", "🍇", "🔔", "⭐", "💎"]
    spin = [secrets.choice(symbols) for _ in range(3)]

    if spin[0] == spin[1] == spin[2]:
        multiplier = 10   # Jackpot
    elif spin[0] == spin[1] or spin[1] == spin[2] or spin[0] == spin[2]:
        multiplier = 2
    else:
        multiplier = 0

    if multiplier > 0:
        winnings = int(bet_amount * multiplier)
        wallet += winnings
        title = f"🏆 {interaction.user.display_name} won {winnings:,} coins in Slots!"
        color = discord.Color.green()
    else:
        wallet -= bet_amount
        winnings = 0
        title = f"❌ {interaction.user.display_name} lost {bet_amount:,} coins in Slots."
        color = discord.Color.red()

    await bot.update_balances(interaction.user.id, wallet, bank)

    embed = discord.Embed(title=title, color=color)
    embed.add_field(name="🎯 Bet Amount", value=f"{bet_amount:,}", inline=True)
    embed.add_field(name="🎰 Result", value=" | ".join(spin), inline=True)
    embed.set_footer(text="⏳ Cooldown: 1 minute")

    await interaction.response.send_message(embed=embed)



# -------------------------------------------------- Command: Quiz --------------------------------------------------

@bot.tree.command(name="quiz", description="Answer a quiz question from OpenTriviaDB and earn 1000 coins!")
@app_commands.describe(category="Quiz category ID (optional, any category if not specified)")
@blacklist_check()
@cooldown(60)
async def quiz(interaction: discord.Interaction, category: int = None):
    base_url = "https://opentdb.com/api.php?amount=1&type=multiple"
    if category:
        url = f"{base_url}&category={category}"
    else:
        url = base_url

    async with aiohttp.ClientSession() as session:
        async with session.get(url) as resp:
            data = await resp.json()

    if not data["results"]:
        await interaction.response.send_message("No quiz questions found for that category.")
        return

    quiz_data = data["results"][0]
    question = html.unescape(quiz_data["question"])
    correct_answer = html.unescape(quiz_data["correct_answer"])
    options = [html.unescape(ans) for ans in quiz_data["incorrect_answers"]] + [correct_answer]
    random.shuffle(options)

    desc = f"**{question}**\n\n"
    for i, opt in enumerate(options, 1):
        desc += f"{i}. {opt}\n"

    embed = discord.Embed(title="Quiz Time!", description=desc, color=discord.Color.gold())
    embed.set_footer(text="Reply with the number of the correct answer. You have 20 seconds. ⏳ Cooldown: 1 minute")
    await interaction.response.send_message(embed=embed)

    def check(m):
        return m.author.id == interaction.user.id and m.channel == interaction.channel and m.content.isdigit() and 1 <= int(m.content) <= len(options)

    try:
        msg = await bot.wait_for("message", timeout=20.0, check=check)
        selected_index = int(msg.content) - 1
        selected_option = options[selected_index]

        if selected_option == correct_answer:
            wallet, bank = await bot.get_balances(interaction.user.id)
            wallet += 1000
            await bot.update_balances(interaction.user.id, wallet, bank)
            await interaction.followup.send(f"🎉 Correct! You won 1000 coins. Your wallet now has {wallet:,} coins.")
        else:
            await interaction.followup.send(f"❌ Incorrect. The correct answer was: **{correct_answer}**.")

    except asyncio.TimeoutError:
        await interaction.followup.send(f"⏰ Time's up! The correct answer was: **{correct_answer}**.")



# -------------------------------------------------- Command: Toss Battle --------------------------------------------------

@bot.tree.command(name="tossbattle", description="Challenge a user to a coin toss battle")
@app_commands.describe(user="User to challenge", amount="Amount of coins to wager")
@blacklist_check()
@cooldown(60)
@requires_coins(param_name="amount")
async def tossbattle(interaction: discord.Interaction, user: discord.Member, amount: int):
    challenger = interaction.user

    if user.id == challenger.id:
        await interaction.response.send_message("You cannot challenge yourself.")
        return

    challenged_wallet, challenged_bank = await bot.get_balances(user.id)
    if challenged_wallet < amount:
        await interaction.response.send_message(
            f"{user.display_name} does not have enough coins to accept the challenge."
        )
        return

    msg = await interaction.response.send_message(
        f"{challenger.mention} (HEADS) has challenged {user.mention} (TAILS) to a coin toss battle for {amount} coins!\n"
        f"{user.mention}, type **accept** (in this channel) within 60 seconds to accept."
    )

    def check(m: discord.Message):
        print(f"Message seen: {m.author} ({m.author.id}), content: {m.content}")
        return (m.author.id == user.id and
                m.channel.id == interaction.channel.id and
                m.content.strip().lower() == "accept")

    try:
        msg = await bot.wait_for("message", check=check, timeout=60)
    except asyncio.TimeoutError:
        await interaction.channel.send(f"{user.mention} did not accept the challenge in time. Toss battle cancelled.")
        return

    challenger_wallet, challenger_bank = await bot.get_balances(challenger.id)
    if challenger_wallet < amount:
        await interaction.channel.send(f"{challenger.mention} doesn't have enough coins for the toss battle.")
        return

    # Deduct
    await bot.update_balances(challenger.id, challenger_wallet - amount, challenger_bank)
    await bot.update_balances(user.id, challenged_wallet - amount, challenged_bank)

    result = secrets.choice(["heads", "tails"])
    winner = challenger if result == "heads" else user

    winner_wallet, winner_bank = await bot.get_balances(winner.id)
    await bot.update_balances(winner.id, winner_wallet + amount*2, winner_bank)

    await interaction.channel.send(
        f"Coin toss result: **{result.upper()}**!\n"
        f"🎉 {winner.mention} wins {amount*2} coins!"
    )


# -------------------------------------------------- Command: Play --------------------------------------------------

@bot.tree.command(name="play", description="Play a song or playlist")
@app_commands.describe(query="Song name or URL")
@blacklist_check()
async def play(interaction: discord.Interaction, query: str):
    await interaction.response.defer()

    if not interaction.user.voice or not interaction.user.voice.channel:
        await interaction.followup.send(
            "You must be in a voice channel to use this command!",
            ephemeral=True
        )
        return

    guild_id = interaction.guild.id
    channel = interaction.user.voice.channel

    if guild_id not in bot.music_queue:
        bot.music_queue[guild_id] = []

    raw_query = query.strip()
    is_url = raw_query.startswith(("http://", "https://"))

    is_playlist = False
    if is_url:
        parsed = urlparse(raw_query)
        host = parsed.netloc.lower()
        path = parsed.path.lower()
        if ("youtube.com" in host or "music.youtube.com" in host) and path == "/playlist":
            is_playlist = True

    if is_playlist:
        lookup_query = raw_query
        flat = True
        no_playlist = False
        treat_as_playlist = True
    elif is_url:
        lookup_query = bot.normalize_single_track_url(raw_query)
        flat = False
        no_playlist = True
        treat_as_playlist = False
    else:
        lookup_query = f"ytsearch1:{raw_query}"
        flat = False
        no_playlist = True
        treat_as_playlist = False

    try:
        info = await bot.extract_info_async(
            lookup_query,
            flat=flat,
            no_playlist=no_playlist
        )
    except Exception as e:
        await interaction.followup.send(
            f"Could not find/download the song or playlist: {e}",
            ephemeral=True
        )
        return

    if not info:
        await interaction.followup.send(
            "Could not extract information from that query.",
            ephemeral=True
        )
        return

    added_count = 0
    added_titles = []

    if treat_as_playlist and 'entries' in info and info['entries']:
        for entry in info['entries']:
            if not entry:
                continue

            page_url = entry.get('url') or entry.get('webpage_url')
            title = entry.get('title', 'Unknown title')
            duration = entry.get('duration')

            if not page_url:
                continue

            bot.music_queue[guild_id].append({
                'title': title,
                'webpage_url': page_url,
                'query': page_url,
                'duration': duration,
                'stream_url': None,
                'text_channel_id': interaction.channel.id,
            })
            added_count += 1

            if len(added_titles) < 5:
                added_titles.append(title)

        if added_count == 0:
            await interaction.followup.send(
                "Could not extract any playable tracks from that playlist.",
                ephemeral=True
            )
            return

    else:
        if 'entries' in info and info['entries']:
            first = next((entry for entry in info['entries'] if entry), None)
            if first:
                info = first

        title = info.get('title', raw_query)
        page_url = info.get('webpage_url') or info.get('url') or lookup_query
        duration = info.get('duration')
        stream_url = info.get('url')

        bot.music_queue[guild_id].append({
            'title': title,
            'webpage_url': page_url,
            'query': page_url,
            'duration': duration,
            'stream_url': stream_url,
            'text_channel_id': interaction.channel.id,
        })

        added_count = 1
        added_titles = [title]

    voice_client = interaction.guild.voice_client
    if not voice_client:
        voice_client = await channel.connect()
    elif voice_client.channel != channel:
        await voice_client.move_to(channel)

    if not voice_client.is_playing() and not voice_client.is_paused():
        await bot.check_queue(guild_id)
    else:
        bot.schedule_prefetch(guild_id, 0)

    preview = "\n".join(f"• {t}" for t in added_titles)
    message = f"✅ Added **{added_count}** track(s) to the queue."
    if preview:
        message += f"\n{preview}"
    if added_count > len(added_titles):
        message += f"\n...and **{added_count - len(added_titles)}** more."

    await interaction.followup.send(message)

# -------------------------------------------------- Command: Pause --------------------------------------------------

@bot.tree.command(name="pause", description="Pause the current song")
@blacklist_check()
async def pause(interaction: discord.Interaction):
    voice_client = interaction.guild.voice_client
    guild_id = interaction.guild.id

    if not voice_client or not voice_client.is_playing():
        await interaction.response.send_message("There is no song playing right now.", ephemeral=True)
        return

    voice_client.pause()
    bot.schedule_pause_disconnect(guild_id, bot.PAUSE_TIMEOUT)

    await interaction.response.send_message(
        "⏸️ Paused the current song. I will disconnect and clear the queue after 15 minutes if still paused."
    )

# -------------------------------------------------- Command: Resume --------------------------------------------------

@bot.tree.command(name="resume", description="Resume a paused song")
@blacklist_check()
async def resume(interaction: discord.Interaction):
    voice_client = interaction.guild.voice_client
    guild_id = interaction.guild.id

    if not voice_client or not voice_client.is_paused():
        await interaction.response.send_message("There is no paused song to resume.", ephemeral=True)
        return

    bot.cancel_pause_disconnect(guild_id)
    voice_client.resume()

    await interaction.response.send_message("▶️ Resumed the song.")





# -------------------------------------------------- Command: Shuffle --------------------------------------------------

@bot.tree.command(name="shuffle", description="Shuffle the current queue")
@blacklist_check()
async def shuffle(interaction: discord.Interaction):
    guild_id = interaction.guild.id
    queue = bot.music_queue.get(guild_id, [])

    if not queue:
        await interaction.response.send_message("There are no songs in the queue to shuffle.", ephemeral=True)
        return

    random.shuffle(queue)

    preview = "\n".join(f"• {song.get('title', 'Unknown title')}" for song in queue[:5])
    message = "🔀 Queue shuffled."
    if preview:
        message += f"\nNext up:\n{preview}"
    if len(queue) > 5:
        message += f"\n...and **{len(queue) - 5}** more."

    await interaction.response.send_message(message)




# -------------------------------------------------- Command: Skip --------------------------------------------------

@bot.tree.command(name="skip", description="Skip the current song or multiple songs")
@app_commands.describe(amount="How many songs to skip total (default: 1)")
@blacklist_check()
async def skip(interaction: discord.Interaction, amount: int = 1):
    voice_client = interaction.guild.voice_client
    guild_id = interaction.guild.id

    if amount < 1:
        await interaction.response.send_message("Please provide a positive integer.", ephemeral=True)
        return

    if not voice_client or not voice_client.is_playing():
        await interaction.response.send_message("There is no song playing to skip.", ephemeral=True)
        return

    bot.cancel_pause_disconnect(guild_id)

    queue = bot.music_queue.get(guild_id, [])

    # /skip 1 => skip current song only
    # /skip n => skip current song + remove next n-1 songs from queue
    remove_count = max(0, amount - 1)

    actually_removed = min(remove_count, len(queue))
    if actually_removed > 0:
        del queue[:actually_removed]

    voice_client.stop()

    if amount == 1:
        await interaction.response.send_message("⏭️ Skipped to the next song.")
    else:
        skipped_total = 1 + actually_removed
        await interaction.response.send_message(
            f"⏭️ Skipped **{skipped_total}** song(s)."
        )

# -------------------------------------------------- Command: Stop --------------------------------------------------

@bot.tree.command(name="stop", description="Stop playing and clear the queue")
@blacklist_check()
async def stop(interaction: discord.Interaction):
    voice_client = interaction.guild.voice_client
    guild_id = interaction.guild.id

    if not voice_client or not voice_client.is_connected():
        await interaction.response.send_message("I am not connected to a voice channel.", ephemeral=True)
        return

    bot.music_queue[guild_id] = []
    bot.current_song.pop(guild_id, None)
    bot.cancel_pause_disconnect(guild_id)

    prefetch_task = bot.prefetch_tasks.pop(guild_id, None)
    if prefetch_task and not prefetch_task.done():
        prefetch_task.cancel()

    voice_client.stop()
    await voice_client.disconnect()

    await interaction.response.send_message("⏹️ Stopped playback, cleared the queue, and left the voice channel.")


# -------------------------------------------------- Command: Ping --------------------------------------------------

@bot.tree.command(name="ping", description="Show API and gateway latency")
@blacklist_check()
async def ping(interaction: discord.Interaction):
    gateway_latency_ms = round(bot.latency * 1000, 2)

    before = time.monotonic()
    await interaction.response.defer(thinking=True)
    after = time.monotonic()
    api_latency_ms = round((after - before) * 1000, 2)

    embed = discord.Embed(
        title="🏓 Pong!",
        color=discord.Color.blue()
    )
    embed.add_field(name="Gateway Latency", value=f"{gateway_latency_ms} ms", inline=True)
    embed.add_field(name="API Latency", value=f"{api_latency_ms} ms", inline=True)

    await interaction.followup.send(embed=embed)


# -------------------------------------------------- Command: Set Balance --------------------------------------------------

@bot.tree.command(name="setbalance", description="Set wallet and bank balance for a user (bot owner only)")
@app_commands.describe(user="User to set balances for", wallet="Wallet balance (non-negative integer)", bank="Bank balance (non-negative integer)")
@owner_only()
async def setbalance(interaction: discord.Interaction, user: discord.Member, wallet: int, bank: int):
    if wallet < 0 or bank < 0:
        await interaction.response.send_message("Wallet and bank balances must be non-negative.", ephemeral=True)
        return

    await bot.update_balances(user.id, wallet, bank)

    total = wallet + bank
    embed = discord.Embed(
        title=f"{user.display_name}'s balances have been set",
        color=discord.Color.blue()
    )
    embed.add_field(name="Wallet", value=f"{wallet:,} coins", inline=True)
    embed.add_field(name="Bank", value=f"{bank:,} coins", inline=True)
    embed.add_field(name="Total", value=f"{total:,} coins", inline=True)
    embed.set_footer(text=f"Set by {interaction.user.display_name}")

    await interaction.response.send_message(embed=embed, ephemeral=True)


# -------------------------------------------------- Command: Restart --------------------------------------------------

@bot.tree.command(name="restart", description="Restart the bot or host (owner only)")
@app_commands.describe(target="Choose 'bot' to restart bot or 'host' to reboot the host")
@owner_only()
async def restart(interaction: discord.Interaction, target: str):
    await interaction.response.send_message(f"Attempting to restart {target}...")

    if target.lower() == "bot":
        try:
            await bot.close()
        except Exception as e:
            print(f"Bot restart failed: {e}")
    elif target.lower() == "host":
        try:
            await bot.close()
            os.system("sudo reboot")
        except Exception as e:
            print(f"Host reboot failed: {e}")

# -------------------------------------------------- Command: Announce ---------------------------------------------------

@bot.tree.command(name="announce", description="Announce a message (owner only)")
@app_commands.describe(announcement="Type the message to be announced")
@owner_only()
async def announce(interaction: discord.Interaction, announcement: str):
    await interaction.response.send_message(announcement)


# -------------------------------------------------- Command: Blacklist --------------------------------------------------

@bot.tree.command(name="blacklist", description="Blacklist a user from a command (in-memory)")
@owner_only()
async def blacklist(interaction: discord.Interaction, user: discord.Member, command_name: str):
    bl = bot.blacklist.setdefault(command_name, set())
    bl.add(user.id)
    await interaction.response.send_message(f"🚫 {user.display_name} is now blacklisted from `{command_name}`.")


# -------------------------------------------------- Command: Whitelist --------------------------------------------------

@bot.tree.command(name="whitelist", description="Whitelist a user for a command")
@owner_only()
async def whitelist(interaction: discord.Interaction, user: discord.Member, command_name: str):
    if command_name in bot.blacklist and user.id in bot.blacklist[command_name]:
        bot.blacklist[command_name].remove(user.id)
        await interaction.response.send_message(f"✅ {user.display_name} has been whitelisted for `{command_name}`.")
    else:
        await interaction.response.send_message(f"{user.display_name} is already whitelisted for `{command_name}`.")


# -------------------------------------------------- Command: Help --------------------------------------------------

@bot.tree.command(name="help", description="Show all available commands")
@blacklist_check()
async def help_command(interaction: discord.Interaction):

    # Prepare title with version
    filename = os.path.basename(__file__).replace('.py', '') if '__file__' in globals() else 'Dealer'
    title = f"Dealer {filename}"

    # Use bot.source_code_link, which is loaded from your config
    source_link = getattr(bot, "source_code_link", "Link unavailable")

    description = (
        f"[Source Code]({source_link})\n\n"
        f"**🎲 Games & Economy**\n"
        f"`/balance` ― View your balances\n"
        f"`/deposit <amount>` ― Wallet → Bank\n"
        f"`/withdraw <amount>` ― Bank → Wallet\n"
        f"`/give @user <amount>` ― Send coins\n"
        f"`/rob @user` ― Rob another wallet\n"
        f"`/dice <1-6> <amount>` ― Bet on dice roll\n"
        f"`/coin <heads/tails> <amount>` ― Coin flip\n"
        f"`/roulette <option> <amount>` ― Number, color, parity\n"
        f"`/slots <amount>` ― Slot machine\n"
        f"`/fortune` ― Try your luck (hourly)\n"
        f"`/top` ― Richest users\n"
        f"`/quiz <category>` ― Answer trivia\n"
        f"`/tossbattle @user <amount>` ― Toss battle\n\n"
        f"**🎵 Music**\n"
        f"`/play <song|playlist>` ― Play a song/playlist\n"
        f"`/pause` ― Pause music\n"
        f"`/resume` ― Resume playback\n"
        f"`/shuffle` ― Shuffle queue\n"
        f"`/skip <number>` ― Skip song(s)\n"
        f"`/stop` ― Stop and clear\n\n"
        f"**🛠 Utility & Admin**\n"
        f"`/ping` ― Ping stats\n"
        f"`/restart <bot|host>` ― Restart/reboot\n"
        f"`/whitelist @user <cmd>` ― Whitelist user on cmd\n"
        f"`/blacklist @user <cmd>` ― Blacklist user on cmd\n"
        f"`/setbalance @user <wallet> <bank>` ― Set user balance\n"
        f"`/announce <message>` ― Announce a message\n"
        f"`/help` ― Show this help\n"
    )

    embed = discord.Embed(
        title=title,
        description=description,
        color=discord.Color.blue()
    )
    await interaction.response.send_message(embed=embed)





# -------------------------------------------------- Run Bot --------------------------------------------------

bot.run(bot.token)

