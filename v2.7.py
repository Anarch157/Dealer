import discord
from discord.ext import commands
from discord import FFmpegPCMAudio
import random
import sqlite3
import urllib.request
import re
import os
import math
from yt_dlp import YoutubeDL
import asyncio
import aiosqlite
import secrets
import time
import aiohttp
import html

class Dealer(commands.Bot):
    def __init__(self, config_path, db_path):
        intents = discord.Intents.all()
        super().__init__(command_prefix="-", intents=intents, help_command=None)
        with open(config_path, "r") as f:
            lines = f.readlines()
        self.token = lines[0].strip()
        self.owner_id = int(lines[1].strip())

        self.db_path = db_path
        self.queue = {}
        self.ydl_opts = {
            'format': 'bestaudio/best',
            'postprocessors': [{
                'key': 'FFmpegExtractAudio',
                'preferredcodec': 'mp3',
                'preferredquality': '192',
            }],
        }
        self.pending_battles = {}
        self.battle_timers = {}

    async def cleanup_mp3_files(self):
        for file in os.listdir("."):
            if file.endswith(".mp3"):
                try:
                    os.remove(file)
                    print(f"Removed mp3 file: {file}")
                except Exception as e:
                    print(f"Failed to remove {file}: {e}")


    async def setup_hook(self):
        await self.cleanup_mp3_files()
        self.main_loop = asyncio.get_running_loop()
        await self.init_db()
        await self.add_cog(GamesCog(self))
        await self.add_cog(UtilsCog(self))
        await self.add_cog(MusicCog(self))

    async def on_ready(self):
        print("[+] Bot is running.")

    async def init_db(self):
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute('''
                CREATE TABLE IF NOT EXISTS accounts (
                    user_id INTEGER PRIMARY KEY,
                    wallet INTEGER,
                    bank INTEGER
                )
            ''')
            await db.commit()

    async def get_balances(self, user_id):
        async with aiosqlite.connect(self.db_path) as db:
            async with db.execute('SELECT wallet, bank FROM accounts WHERE user_id = ?', (user_id,)) as cursor:
                result = await cursor.fetchone()
                if result is None:
                    await db.execute('INSERT INTO accounts (user_id, wallet, bank) VALUES (?, ?, ?)', (user_id, 50000, 0))
                    await db.commit()
                    return 50000, 0
                return result

    async def update_balances(self, user_id, wallet, bank):
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute('UPDATE accounts SET wallet = ?, bank = ? WHERE user_id = ?', (wallet, bank, user_id))
            await db.commit()

    async def check_queue(self, ctx, guild_id, last_source):
        try:
            if last_source and hasattr(last_source, "filepath") and os.path.exists(last_source.filepath):
                os.remove(last_source.filepath)
        except Exception:
            pass
        if self.queue.get(guild_id):
            voice = ctx.guild.voice_client
            next_source = self.queue[guild_id].pop(0)
            voice.play(next_source, after=lambda x=None: asyncio.run_coroutine_threadsafe(
                self.check_queue(ctx, guild_id, next_source), self.main_loop))
        else:
            voice = ctx.guild.voice_client
            if voice and voice.is_connected():
                await voice.disconnect()

# ---------------------------------------------------- GAMES COG --------------------------------------------------------

class GamesCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.command(name="bal")
    async def bal(self, ctx):
        wallet, bank = await self.bot.get_balances(ctx.author.id)
        total = wallet + bank
        await ctx.send(f"{ctx.author.mention},\nWallet: {wallet}\nBank: {bank}\nTotal: {total} coins.")

    @commands.command(name="deposit")
    async def deposit(self, ctx, amount: int = None):
        wallet, bank = await self.bot.get_balances(ctx.author.id)
        if amount is None:
            amount = wallet
        if amount <= 0:
            return await ctx.send(f"{ctx.author.mention}, you must deposit a positive amount.")
        if amount > wallet:
            return await ctx.send(f"{ctx.author.mention}, you don't have enough coins in your wallet.")
        await self.bot.update_balances(ctx.author.id, wallet - amount, bank + amount)
        await ctx.send(f"{ctx.author.mention}, deposited {amount} coins.")

    @commands.command(name="withdraw")
    async def withdraw(self, ctx, amount: int):
        wallet, bank = await self.bot.get_balances(ctx.author.id)
        if amount > bank:
            return await ctx.send(f"{ctx.author.mention}, not enough coins in bank.")
        await self.bot.update_balances(ctx.author.id, wallet + amount, bank - amount)
        await ctx.send(f"{ctx.author.mention}, withdrew {amount} coins.")

    @commands.command(name="give")
    async def give(self, ctx, recipient: discord.User, amount: int):
        wallet, bank = await self.bot.get_balances(ctx.author.id)
        if amount > wallet:
            return await ctx.send(f"{ctx.author.mention}, not enough coins to give.")
        recipient_wallet, recipient_bank = await self.bot.get_balances(recipient.id)
        await self.bot.update_balances(ctx.author.id, wallet - amount, bank)
        await self.bot.update_balances(recipient.id, recipient_wallet + amount, recipient_bank)
        await ctx.send(f"{ctx.author.mention} gave {amount} coins to {recipient.mention}.")

    @commands.command(name="rob")
    @commands.cooldown(1, 3600, commands.BucketType.user)
    async def rob(self, ctx, target: discord.User):
        if target.id == ctx.author.id:
            return await ctx.send("You cannot rob yourself.")
        robber_wallet, robber_bank = await self.bot.get_balances(ctx.author.id)
        target_wallet, target_bank = await self.bot.get_balances(target.id)
        if target_wallet == 0:
            return await ctx.send(f"{target.mention} has no coins to rob!")
        rob_amount = random.randint(1, target_wallet)
        success = random.randint(1, 100)
        if success <= 50:
            await self.bot.update_balances(ctx.author.id, robber_wallet + rob_amount, robber_bank)
            await self.bot.update_balances(target.id, target_wallet - rob_amount, target_bank)
            await ctx.send(f"{ctx.author.mention} robbed {rob_amount} coins from {target.mention}!")
        else:
            fine = random.randint(0, robber_wallet)
            await self.bot.update_balances(ctx.author.id, robber_wallet - fine, robber_bank)
            await ctx.send(f"{ctx.author.mention} got caught trying to rob {target.mention} and lost {fine} coins!")

    @rob.error
    async def rob_error(self, ctx, error):
        if isinstance(error, commands.CommandOnCooldown):
            await ctx.send(f"You're on cooldown! Try again in {math.ceil(error.retry_after / 60)} minute(s).")

    @commands.command(name="dice")
    @commands.cooldown(1, 60, commands.BucketType.user)
    async def dice(self, ctx, bet_option: int, bet_amount: int):
        wallet, bank = await self.bot.get_balances(ctx.author.id)
        if bet_amount > wallet:
            return await ctx.send(f"{ctx.author.mention}, not enough coins.")
        if not (1 <= bet_option <= 6):
            return await ctx.send("Choose a number between 1 and 6.")
        roll = random.randint(1, 6)
        if roll == bet_option:
            winnings = bet_amount * 5
            await self.bot.update_balances(ctx.author.id, wallet + winnings, bank)
            await ctx.send(f"{ctx.author.mention}, rolled {roll} and won {winnings} coins!")
        else:
            await self.bot.update_balances(ctx.author.id, wallet - bet_amount, bank)
            await ctx.send(f"{ctx.author.mention}, rolled {roll} and lost {bet_amount} coins.")

    @dice.error
    async def dice_error(self, ctx, error):
        if isinstance(error, commands.CommandOnCooldown):
            await ctx.send(f"You're on cooldown! Try again in {math.ceil(error.retry_after)} second(s).")

    @commands.command(name="cf")
    @commands.cooldown(1, 60, commands.BucketType.user)
    async def cf(self, ctx, bet_option: str, bet_amount: int):
        wallet, bank = await self.bot.get_balances(ctx.author.id)
        if bet_amount > wallet:
            return await ctx.send("Not enough coins.")
        if bet_option.lower() not in ["heads", "tails"]:
            return await ctx.send("Choose heads or tails.")
        outcome = random.choice(["heads", "tails"])
        if outcome == bet_option.lower():
            winnings = bet_amount
            await self.bot.update_balances(ctx.author.id, wallet + winnings, bank)
            await ctx.send(f"It's 🪙{outcome}! You win {winnings} coins.")
        else:
            await self.bot.update_balances(ctx.author.id, wallet - bet_amount, bank)
            await ctx.send(f"It's {outcome}. You lost {bet_amount} coins.")

    @cf.error
    async def cf_error(self, ctx, error):
        if isinstance(error, commands.CommandOnCooldown):
            await ctx.send(f"You're on cooldown! Try again in {math.ceil(error.retry_after)} second(s).")



    @commands.command(name="roulette")
    @commands.cooldown(1, 60, commands.BucketType.user)
    async def roulette(self, ctx, bet_option: str, bet_amount: int):
        wallet, bank = await self.bot.get_balances(ctx.author.id)
        if bet_amount > wallet:
            return await ctx.send(f"{ctx.author.mention}, not enough coins in wallet.")

        wheel = {
            "red": [1, 3, 5, 7, 9, 12, 14, 16, 18, 19, 21, 23, 25, 27, 30, 32, 34, 36],
            "black": [2, 4, 6, 8, 10, 11, 13, 15, 17, 20, 22, 24, 26, 28, 29, 31, 33, 35],
            "green": [0]
        }

        result_number = random.randint(0, 36)
        result_color = (
            "green" if result_number == 0 else
            "red" if result_number in wheel["red"] else "black"
        )

        if bet_option.isdigit():
            bet_number = int(bet_option)
            if bet_number < 0 or bet_number > 36:
                return await ctx.send(f"{ctx.author.mention}, choose a number between 0 and 36.")
            if result_number == bet_number:
                winnings = bet_amount * 35
                await self.bot.update_balances(ctx.author.id, wallet + winnings, bank)
                await ctx.send(f"{ctx.author.mention}, ball landed on {result_number}. You win {winnings} coins!")
            else:
                await self.bot.update_balances(ctx.author.id, wallet - bet_amount, bank)
                await ctx.send(f"{ctx.author.mention}, ball landed on {result_number}. You lost {bet_amount} coins.")
        elif bet_option in ["red", "black"]:
            if bet_option == result_color:
                winnings = bet_amount
                await self.bot.update_balances(ctx.author.id, wallet + winnings, bank)
                await ctx.send(f"{ctx.author.mention}, ball landed on {result_number} ({result_color}). You win {winnings} coins!")
            else:
                await self.bot.update_balances(ctx.author.id, wallet - bet_amount, bank)
                await ctx.send(f"{ctx.author.mention}, ball landed on {result_number} ({result_color}). You lost {bet_amount} coins.")
        elif bet_option in ["even", "odd"]:
            if (result_number % 2 == 0 and bet_option == "even") or (result_number % 2 != 0 and bet_option == "odd"):
                winnings = bet_amount
                await self.bot.update_balances(ctx.author.id, wallet + winnings, bank)
                await ctx.send(f"{ctx.author.mention}, ball landed on {result_number} ({result_color}). You win {winnings} coins!")
            else:
                await self.bot.update_balances(ctx.author.id, wallet - bet_amount, bank)
                await ctx.send(f"{ctx.author.mention}, ball landed on {result_number} ({result_color}). You lost {bet_amount} coins.")
        elif bet_option in ["low", "high"]:
            if bet_option == "low" and 1 <= result_number <= 18:
                winnings = bet_amount
                await self.bot.update_balances(ctx.author.id, wallet + winnings, bank)
                await ctx.send(f"{ctx.author.mention}, ball landed on {result_number} ({result_color}). You win {winnings} coins!")
            elif bet_option == "high" and 19 <= result_number <= 36:
                winnings = bet_amount
                await self.bot.update_balances(ctx.author.id, wallet + winnings, bank)
                await ctx.send(f"{ctx.author.mention}, ball landed on {result_number} ({result_color}). You win {winnings} coins!")
            else:
                await self.bot.update_balances(ctx.author.id, wallet - bet_amount, bank)
                await ctx.send(f"{ctx.author.mention}, ball landed on {result_number} ({result_color}). You lost {bet_amount} coins.")
        elif bet_option in ["0", "green"]:
            if result_number == 0:
                winnings = bet_amount * 35
                await self.bot.update_balances(ctx.author.id, wallet + winnings, bank)
                await ctx.send(f"{ctx.author.mention}, ball landed on 0 (green). You win {winnings} coins!")
            else:
                await self.bot.update_balances(ctx.author.id, wallet - bet_amount, bank)
                await ctx.send(f"{ctx.author.mention}, ball landed on {result_number} ({result_color}). You lost {bet_amount} coins.")
        else:
            await ctx.send(f"Invalid bet option: `{bet_option}`. Choose a number 0–36, or red, black, even, odd, low, high, green.")

    @roulette.error
    async def roulette_error(self, ctx, error):
        if isinstance(error, commands.CommandOnCooldown):
            await ctx.send(f"You're on cooldown! Try again in {math.ceil(error.retry_after)} second(s).")



    @commands.command(name="slots")
    @commands.cooldown(1, 60, commands.BucketType.user)
    async def slots(self, ctx, bet_amount: int):
        wallet, bank = await self.bot.get_balances(ctx.author.id)
        if bet_amount > wallet:
            return await ctx.send("Not enough coins.")

        emojis = ["🍒", "🍋", "7️⃣", "🍉", "🍊", "🍓"]
        reels = [random.choice(emojis) for _ in range(3)]
        if reels.count(reels[0]) == 3:
            winnings = bet_amount * 10
            await self.bot.update_balances(ctx.author.id, wallet + winnings, bank)
            await ctx.send(f"{' | '.join(reels)} — You won {winnings} coins!")
        elif len(set(reels)) == 2:
            winnings = bet_amount
            await self.bot.update_balances(ctx.author.id, wallet + winnings, bank)
            await ctx.send(f"{' | '.join(reels)} — You won {winnings} coins!")
        else:
            await self.bot.update_balances(ctx.author.id, wallet - bet_amount, bank)
            await ctx.send(f"{' | '.join(reels)} — You lost {bet_amount} coins.")

    @slots.error
    async def slots_error(self, ctx, error):
        if isinstance(error, commands.CommandOnCooldown):
            await ctx.send(f"You're on cooldown! Try again in {math.ceil(error.retry_after)} second(s).")



    @commands.command(name="tb")
    @commands.cooldown(1, 60, commands.BucketType.user)
    async def tb(self, ctx, arg=None, amount: int = None):
        if arg is None:
            return await ctx.send("Usage: `.tb @user <amount>` or `.tb accept/reject`")
        user_id = ctx.author.id
        if arg.lower() == "accept":
            if user_id not in self.bot.pending_battles:
                return await ctx.send("You don't have any pending toss battles.")
            challenger_id, bet_amount = self.bot.pending_battles.pop(user_id)
            if user_id in self.bot.battle_timers:
                self.bot.battle_timers[user_id].cancel()
                del self.bot.battle_timers[user_id]
            challenger_wallet, challenger_bank = await self.bot.get_balances(challenger_id)
            challenged_wallet, challenged_bank = await self.bot.get_balances(user_id)
            if challenger_wallet < bet_amount:
                return await ctx.send("The challenger no longer has enough coins.")
            if challenged_wallet < bet_amount:
                return await ctx.send("You don't have enough coins to accept this bet.")
            await self.bot.update_balances(challenger_id, challenger_wallet - bet_amount, challenger_bank)
            await self.bot.update_balances(user_id, challenged_wallet - bet_amount, challenged_bank)
            winner = challenger_id if secrets.choice(["heads", "tails"]) == "heads" else user_id
            total = bet_amount * 2
            winner_wallet, winner_bank = await self.bot.get_balances(winner)
            await self.bot.update_balances(winner, winner_wallet + total, winner_bank)
            challenger = await self.bot.fetch_user(challenger_id)
            challenged = ctx.author
            winner_user = await self.bot.fetch_user(winner)
            await ctx.send(
                f"🪙 Coin toss result: **{'Heads' if winner == challenger_id else 'Tails'}**!\n"
                f"{winner_user.mention} wins {total} coins!"
            )
        elif arg.lower() == "reject":
            if user_id not in self.bot.pending_battles:
                return await ctx.send("You don't have any pending toss battles.")
            challenger_id, _ = self.bot.pending_battles.pop(user_id)
            if user_id in self.bot.battle_timers:
                self.bot.battle_timers[user_id].cancel()
                del self.bot.battle_timers[user_id]
            challenger = await self.bot.fetch_user(challenger_id)
            await ctx.send(f"{ctx.author.mention} rejected the toss battle from {challenger.mention}.")
        else:
            if not ctx.message.mentions:
                return await ctx.send("You must mention a user to challenge.")
            challenged_user = ctx.message.mentions[0]
            challenger_id = ctx.author.id
            if challenged_user.id == ctx.author.id:
                return await ctx.send("You cannot challenge yourself.")
            if amount is None or amount <= 0:
                return await ctx.send("Please specify a valid amount.")
            challenger_wallet, _ = await self.bot.get_balances(challenger_id)
            challenged_wallet, _ = await self.bot.get_balances(challenged_user.id)
            if challenger_wallet < amount:
                return await ctx.send("You don't have enough coins.")
            if challenged_wallet < amount:
                return await ctx.send(f"{challenged_user.mention} doesn't have enough coins.")
            self.bot.pending_battles[challenged_user.id] = (challenger_id, amount)
            await ctx.send(
                f"{ctx.author.mention} challenged {challenged_user.mention} to a toss battle for {amount} coins!\n"
                "Respond with `.tb accept` or `.tb reject` within 60 seconds."
            )
            async def expire_battle():
                await asyncio.sleep(60)
                if challenged_user.id in self.bot.pending_battles:
                    del self.bot.pending_battles[challenged_user.id]
                    await ctx.send(f"{challenged_user.mention}, your toss battle with {ctx.author.mention} has expired.")
                self.bot.battle_timers.pop(challenged_user.id, None)
            task = asyncio.create_task(expire_battle())
            self.bot.battle_timers[challenged_user.id] = task

    @tb.error
    async def tb_error(self, ctx, error):
        if isinstance(error, commands.CommandOnCooldown):
            await ctx.send(f"You're on cooldown! Try again in {math.ceil(error.retry_after)} second(s).")



    @commands.command(name="quiz")
    @commands.cooldown(1, 60, commands.BucketType.user)
    async def quiz(self, ctx, category_id: int = None):
        url = "https://opentdb.com/api.php?amount=1&type=multiple"
        if category_id:
            url += f"&category={category_id}"
        async with aiohttp.ClientSession() as session:
            async with session.get(url) as resp:
                if resp.status != 200:
                    return await ctx.send("❌ Failed to fetch a question. Try again later.")
                data = await resp.json()
                if data["response_code"] != 0:
                    return await ctx.send("❌ Invalid category ID or no questions found.")
                question_data = data["results"][0]
                question = html.unescape(question_data["question"])
                correct_answer = html.unescape(question_data["correct_answer"])
                options = [correct_answer] + [html.unescape(ans) for ans in question_data["incorrect_answers"]]
                random.shuffle(options)
                letters = ['A', 'B', 'C', 'D']
                answer_map = dict(zip(letters, options))
                correct_letter = [k for k, v in answer_map.items() if v == correct_answer][0]
                formatted = "\n".join(f"{letter}: {option}" for letter, option in answer_map.items())
                await ctx.send(
                    f"🧠 **Quiz Time!**\n{question}\n\n{formatted}\n\n_Reply with the letter (A-D). You have 20 seconds!_"
                )
                def check(m):
                    return m.author == ctx.author and m.channel == ctx.channel and m.content.upper() in letters
                try:
                    msg = await self.bot.wait_for("message", timeout=20.0, check=check)
                except asyncio.TimeoutError:
                    return await ctx.send(f"⏰ Time's up! Correct answer: **{correct_letter}: {correct_answer}**.")
                if msg.content.upper() == correct_letter:
                    wallet, bank = await self.bot.get_balances(ctx.author.id)
                    await self.bot.update_balances(ctx.author.id, wallet + 1000, bank)
                    await ctx.send("✅ Correct! You earned 1000 coins!")
                else:
                    await ctx.send(f"❌ Incorrect. Correct answer: **{correct_letter}: {correct_answer}**.")

    @quiz.error
    async def quiz_error(self, ctx, error):
        if isinstance(error, commands.CommandOnCooldown):
            await ctx.send(f"🕑 You're on cooldown! Try again in {math.ceil(error.retry_after)} second(s).")
        elif isinstance(error, commands.BadArgument):
            await ctx.send("❗ Please enter a valid category ID (a number).")
        else:
            raise error

    @commands.command(name="fortune")
    @commands.cooldown(1, 3600, commands.BucketType.user)
    async def fortune(self, ctx):
        winnings = random.choice([0, 1000, 2000, 3000, 4000, 5000])
        wallet, bank = await self.bot.get_balances(ctx.author.id)
        if winnings == 0:
            await ctx.send(f"{ctx.author.mention} You got a **fortune**... but it’s **nothing**! Better luck next time!")
        else:
            await self.bot.update_balances(ctx.author.id, wallet + winnings, bank)
            await ctx.send(f"{ctx.author.mention} You got a **fortune** of 🪙{winnings} coins! Lucky you!")

    @fortune.error
    async def fortune_error(self, ctx, error):
        if isinstance(error, commands.CommandOnCooldown):
            await ctx.send(f"{ctx.author.mention}, you're on cooldown! Try again in {math.ceil(error.retry_after / 60)} minute(s).")

    @commands.command(name="top")
    async def top(self, ctx):
        async with aiosqlite.connect(self.bot.db_path) as db:
            async with db.execute('''
                SELECT user_id, wallet, bank, (wallet + bank) AS total_balance
                FROM accounts
                ORDER BY total_balance DESC
                LIMIT 10
            ''') as cursor:
                results = await cursor.fetchall()
                if not results:
                    return await ctx.send("No users found in the database.")
                leaderboard = "***TOP 10***\n"
                for i, (user_id, wallet, bank, total) in enumerate(results, 1):
                    try:
                        user = await self.bot.fetch_user(user_id)
                        leaderboard += f"{i}. {user.name} , wallet: {wallet}, bank: {bank}, total: {total}\n"
                    except discord.NotFound:
                        leaderboard += f"{i}. User not found (ID: {user_id}) , wallet: {wallet}, bank: {bank}, total: {total}\n"
                await ctx.send(leaderboard)


# ----------------------------------------------------------------- UTILS COG -------------------------------------------------------------

class UtilsCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.command(name="setbal")
    async def setbal(self, ctx, user: discord.User, wallet: int, bank: int):
        if ctx.author.id != self.bot.owner_id:
            return await ctx.send(f" You are not authorized to use this command.")
        await self.bot.update_balances(user.id, wallet, bank)
        await ctx.send(f"Set {user.mention}'s balance: wallet {wallet}, bank {bank}")

    @commands.command(name="ping")
    async def ping(self, ctx):
        start = time.monotonic()
        msg = await ctx.send("Pinging...")
        end = time.monotonic()
        gateway_latency = round(self.bot.latency * 1000)
        api_latency = round((end - start) * 1000)
        await msg.edit(content=f"🏓 Pong!\nGateway latency: `{gateway_latency}ms`\nAPI latency: `{api_latency}ms`")

    @commands.command(name="help")
    async def show_help(self, ctx):
        file_name = os.path.splitext(os.path.basename(__file__))[0]
        help_message = f"""

**Dealer {file_name}**

**🎮 Games**
- `-bal`: View your wallet and bank balances.
- `-deposit <amount>`: Move coins from wallet to bank.
- `-withdraw <amount>`: Move coins from bank to wallet.
- `-give @user <amount>`: Transfer coins to another user.
- `-rob @user`: Attempt to rob another user's wallet.
- `-dice <1-6> <amount>`: Bet on a dice roll (win 5x).
- `-cf <heads/tails> <amount>`: Coin flip.
- `-roulette <option> <amount>`: Bet on number, color, or type.
- `-slots <amount>`: Slot machine game.
- `-tb @user <amount>`: Toss battle challenge.
- `-quiz <category_id>`: Answer trivia for coins.
- `-fortune`: Random fortune once per hour.
- `-top`: Show top 10 richest users.

**🛠 Utility**
- `-ping`: Check bot response time.
- `-h`: Show this help menu.
- `-setbal @user <wallet> <bank>`: Set another user's balance.

**🎵 Music**
- `-connect`: Join your voice channel.
- `-disconnect`: Leave the voice channel.
- `-play <song>`: Play from YouTube (costs 1000 coins).
- `-pause`: Pause playback.
- `-resume`: Resume playback.
- `-stop`: Stop and clear playback.
- `-skip`: Skip the current song.

"""
        await ctx.send(help_message)

# ----------------------------------------------------------------------- MUSIC COG ------------------------------------------------------------------

class MusicCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.command(name="connect")
    async def voice_connect(self, ctx):
        if ctx.author.voice:
            await ctx.author.voice.channel.connect()
        else:
            await ctx.send("You're not in a voice channel.")

    @commands.command(name="disconnect")
    async def disconnect(self, ctx):
        if ctx.voice_client:
            await ctx.voice_client.disconnect()

    @commands.command(name="pause")
    async def pause(self, ctx):
        voice = ctx.voice_client
        if voice and voice.is_playing():
            voice.pause()

    @commands.command(name="resume")
    async def resume(self, ctx):
        voice = ctx.voice_client
        if voice and voice.is_paused():
            voice.resume()

    @commands.command(name="stop")
    async def stop(self, ctx):
        voice = ctx.voice_client
        if voice:
            voice.stop()

    @commands.command(name="skip")
    async def skip(self, ctx):
        voice = ctx.voice_client
        if voice and voice.is_playing():
            current = voice.source
            voice.stop()
            await ctx.send("Skipped the current song.")
            await self.bot.check_queue(ctx, ctx.guild.id, current)

    @commands.command(name="play")
    async def play(self, ctx, *, search: str):
        wallet, bank = await self.bot.get_balances(ctx.author.id)
        if wallet < 1000:
            return await ctx.send("You need at least 1000 coins to play a song.")
        await ctx.send("I receive 1000 coins, you receive your song.")
        await self.bot.update_balances(ctx.author.id, wallet - 1000, bank)
        if not ctx.author.voice:
            return await ctx.send("Join a voice channel first.")
        if not ctx.voice_client:
            await ctx.author.voice.channel.connect()
        await ctx.send(f"Searching for: {search}")
        query = search.replace(" ", "+")
        html_response = urllib.request.urlopen(f"https://www.youtube.com/results?search_query={query}")
        video_ids = re.findall(r"watch\?v=(\S{11})", html_response.read().decode())
        if not video_ids:
            return await ctx.send("No results found on YouTube.")
        url = "https://www.youtube.com/watch?v=" + video_ids[0]
        await ctx.send(f"Found: {url}")
        with YoutubeDL(self.bot.ydl_opts) as ydl:
            ydl.download([url])
        for file in os.listdir("./"):
            if video_ids[0] in file and file.endswith(".mp3"):
                source = FFmpegPCMAudio(file)
                source.filepath = file
                voice = ctx.voice_client
                if not voice.is_playing():
                    voice.play(source, after=lambda x=None: asyncio.run_coroutine_threadsafe(
                        self.bot.check_queue(ctx, ctx.guild.id, source), self.bot.main_loop))
                else:
                    self.bot.queue.setdefault(ctx.guild.id, []).append(source)
                    await ctx.send("Added to queue.")
                break

# ---- Main Entrypoint ----
if __name__ == "__main__":
    config_path = "config.txt"
    db_path = "db.db"
    bot = Dealer(config_path=config_path, db_path=db_path)
    bot.run(bot.token)

