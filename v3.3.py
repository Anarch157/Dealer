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
from discord.ui import View, Button
from discord import ButtonStyle, Interaction

class Dealer(commands.Bot):
    def __init__(self, config_path, db_path):
        intents = discord.Intents.all()
        super().__init__(command_prefix="-", intents=intents, help_command=None)
        with open(config_path, "r") as f:
            lines = f.readlines()
        self.token = lines[0].strip()
        self.owner_id = int(lines[1].strip())
        self.source_code_link = lines[2].strip()

        self.db_path = db_path
        self.queue = {}
        self.ydl_opts = {
            'format': 'bestaudio[ext=webm][acodec=opus]/bestaudio/best',
        }
        self.pending_battles = {}
        self.battle_timers = {}
        self.blacklist = {}

    async def is_blacklisted(self, user_id, command_name):
        return user_id in self.blacklist and command_name in self.blacklist[user_id]

    async def invoke(self, ctx):
        if ctx.command is not None and await self.is_blacklisted(ctx.author.id, ctx.command.name):
            await ctx.send(f"{ctx.author.mention}, you're blacklisted from using `-{ctx.command.name}`.")
            return
        await super().invoke(ctx)


    async def cleanup_audio_files(self):
        for file in os.listdir("."):
            if file.endswith(".webm"):
                try:
                    os.remove(file)
                    print(f"Removed audio file: {file}")
                except Exception as e:
                    print(f"Failed to remove {file}: {e}")


    async def setup_hook(self):
        await self.cleanup_audio_files()
        self.main_loop = asyncio.get_running_loop()
        await self.init_db()
        await self.add_cog(GamesCog(self))
        await self.add_cog(UtilsCog(self))
        await self.add_cog(MusicCog(self))
        await self.add_cog(NSFWCog(self))

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

        embed = discord.Embed(
            title=f"🪙 {ctx.author.display_name}'s Balance",
            color=discord.Color.gold()
        )
        embed.set_thumbnail(url=ctx.author.avatar.url if ctx.author.avatar else discord.Embed.Empty)
        embed.add_field(name="💰 Wallet", value=f"{wallet:,}", inline=True)
        embed.add_field(name="🏦 Bank", value=f"{bank:,}", inline=True)
        embed.add_field(name="📊 Total", value=f"{total:,}", inline=True)

        await ctx.send(embed=embed)


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

        embed = discord.Embed(
            title="🏦 Deposit Successful",
            color=discord.Color.gold()
        )
        embed.add_field(name="Amount", value=f"🪙 {amount:,} coins", inline=True)
        embed.add_field(name="New Wallet", value=f"💰 {wallet - amount:,}", inline=True)
        embed.add_field(name="New Bank", value=f"🏦 {bank + amount:,}", inline=True)
        await ctx.send(embed=embed)

    @commands.command(name="withdraw")
    async def withdraw(self, ctx, amount: int):
        wallet, bank = await self.bot.get_balances(ctx.author.id)
        if amount > bank:
            return await ctx.send(f"{ctx.author.mention}, not enough coins in bank.")

        await self.bot.update_balances(ctx.author.id, wallet + amount, bank - amount)

        embed = discord.Embed(
            title="💰 Withdrawal Successful",
            color=discord.Color.gold()
        )
        embed.add_field(name="Amount", value=f"🪙 {amount:,} coins", inline=True)
        embed.add_field(name="New Wallet", value=f"💰 {wallet + amount:,}", inline=True)
        embed.add_field(name="New Bank", value=f"🏦 {bank - amount:,}", inline=True)
        await ctx.send(embed=embed)

    @commands.command(name="give")
    async def give(self, ctx, recipient: discord.User, amount: int):
        wallet, bank = await self.bot.get_balances(ctx.author.id)
        if amount > wallet:
            return await ctx.send(f"{ctx.author.mention}, not enough coins to give.")

        recipient_wallet, recipient_bank = await self.bot.get_balances(recipient.id)

        await self.bot.update_balances(ctx.author.id, wallet - amount, bank)
        await self.bot.update_balances(recipient.id, recipient_wallet + amount, recipient_bank)

        embed = discord.Embed(
            title="💸 Coins Transferred",
            color=discord.Color.gold()
        )
        embed.add_field(name="From", value=ctx.author.mention, inline=True)
        embed.add_field(name="To", value=recipient.mention, inline=True)
        embed.add_field(name="Amount", value=f"🪙 {amount:,} coins", inline=False)
        await ctx.send(embed=embed)


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
            # Success
            await self.bot.update_balances(ctx.author.id, robber_wallet + rob_amount, robber_bank)
            await self.bot.update_balances(target.id, target_wallet - rob_amount, target_bank)

            embed = discord.Embed(
                title="💰 Robbery Successful!",
                description=f"{ctx.author.mention} **stole** 🪙 `{rob_amount:,}` coins from {target.mention}!",
                color=discord.Color.green()
            )
        else:
            # Failed
            fine = random.randint(0, robber_wallet)
            await self.bot.update_balances(ctx.author.id, robber_wallet - fine, robber_bank)

            embed = discord.Embed(
                title="🚨 Robbery Failed!",
                description=(
                    f"{ctx.author.mention} got **caught** trying to rob {target.mention}!\n"
                    f"They paid a fine of 🪙 `{fine:,}` coins."
                ),
                color=discord.Color.red()
            )

        embed.set_footer(text="💡 Cooldown: 1 hour.")
        await ctx.send(embed=embed)

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
        win = roll == bet_option
        winnings = bet_amount * 5 if win else -bet_amount

        embed = discord.Embed(
            title="🎲 Dice Roll",
            color=discord.Color.green() if win else discord.Color.red()
        )
        embed.add_field(name="Your Bet", value=f"🎯 `{bet_option}`", inline=True)
        embed.add_field(name="Dice Rolled", value=f"🎲 `{roll}`", inline=True)

        if win:
            await self.bot.update_balances(ctx.author.id, wallet + winnings, bank)
            embed.add_field(name="🎉 Outcome", value=f"You **won** 🪙 `{winnings:,}` coins!", inline=False)
        else:
            await self.bot.update_balances(ctx.author.id, wallet + winnings, bank)
            embed.add_field(name="💸 Outcome", value=f"You **lost** 🪙 `{bet_amount:,}` coins.", inline=False)

        embed.set_footer(text="💡 Cooldown: 60 seconds.")
        await ctx.send(embed=embed)


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
        win = outcome == bet_option.lower()

        embed_color = discord.Color.green() if win else discord.Color.red()
        embed = discord.Embed(
            title="🪙 Coin Flip",
            color=embed_color
        )
        embed.add_field(name="Your Call", value=f"🔮 `{bet_option.capitalize()}`", inline=True)
        embed.add_field(name="Result", value=f"🪙 `{outcome.capitalize()}`", inline=True)

        if win:
            winnings = bet_amount
            await self.bot.update_balances(ctx.author.id, wallet + winnings, bank)
            embed.add_field(name="🎉 Outcome", value=f"You **won** 🪙 `{winnings:,}` coins!", inline=False)
        else:
            await self.bot.update_balances(ctx.author.id, wallet - bet_amount, bank)
            embed.add_field(name="💸 Outcome", value=f"You **lost** 🪙 `{bet_amount:,}` coins.", inline=False)

        embed.set_footer(text="💡 Cooldown: 60 seconds.")
        await ctx.send(embed=embed)


    @cf.error
    async def cf_error(self, ctx, error):
        if isinstance(error, commands.CommandOnCooldown):
            await ctx.send(f"You're on cooldown! Try again in {math.ceil(error.retry_after)} second(s).")


    @commands.command(name="roulette")
    @commands.cooldown(1, 60, commands.BucketType.user)
    async def roulette(self, ctx, bet_option: str, bet_amount: int):
        wallet, bank = await self.bot.get_balances(ctx.author.id)
        if bet_amount > wallet:
            embed = discord.Embed(
                title="💸 Not Enough Coins",
                description=f"{ctx.author.mention}, you don’t have enough in your wallet to place that bet.",
                color=discord.Color.red()
            )
            return await ctx.send(embed=embed)

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

        def make_embed(title, win, coins, highlight=None):
            color = discord.Color.green() if win else discord.Color.red()
            outcome = f"🎯 Ball landed on `{result_number}` ({result_color})."
            amount = f"{'You win' if win else 'You lost'} **🪙 {coins:,} coins**."
            embed = discord.Embed(
                title=title,
                description=f"{ctx.author.mention}, {outcome}\n{amount}",
                color=color
            )
            if highlight:
                embed.add_field(name="🎰 Bet", value=highlight, inline=False)
            embed.set_footer(text="Cooldown: 60s")
            return embed

        cmd = bet_option.lower()

        if cmd.isdigit():
            bet_number = int(cmd)
            if not 0 <= bet_number <= 36:
                embed = discord.Embed(
                    description=f"{ctx.author.mention}, choose a number between 0 and 36.",
                    color=discord.Color.red()
                )
                return await ctx.send(embed=embed)
            win = result_number == bet_number
            winnings = bet_amount * 35 if win else -bet_amount
            await self.bot.update_balances(ctx.author.id, wallet + winnings, bank)
            await ctx.send(embed=make_embed("🎲 Roulette — Number Bet", win, abs(winnings), f"Number: `{bet_number}`"))

        elif cmd in ["red", "black"]:
            win = cmd == result_color
            winnings = bet_amount if win else -bet_amount
            await self.bot.update_balances(ctx.author.id, wallet + winnings, bank)
            await ctx.send(embed=make_embed("🎲 Roulette — Color Bet", win, abs(winnings), f"Color: `{cmd}`"))

        elif cmd in ["even", "odd"]:
            if result_number == 0:
                win = False
            else:
                win = (result_number % 2 == 0 and cmd == "even") or (result_number % 2 != 0 and cmd == "odd")
            winnings = bet_amount if win else -bet_amount
            await self.bot.update_balances(ctx.author.id, wallet + winnings, bank)
            await ctx.send(embed=make_embed("🎲 Roulette — Parity Bet", win, abs(winnings), f"Parity: `{cmd}`"))

        elif cmd in ["low", "high"]:
            win = (cmd == "low" and 1 <= result_number <= 18) or (cmd == "high" and 19 <= result_number <= 36)
            winnings = bet_amount if win else -bet_amount
            await self.bot.update_balances(ctx.author.id, wallet + winnings, bank)
            await ctx.send(embed=make_embed("🎲 Roulette — Range Bet", win, abs(winnings), f"Range: `{cmd}`"))

        elif cmd in ["0", "green"]:
            win = result_number == 0
            winnings = bet_amount * 35 if win else -bet_amount
            await self.bot.update_balances(ctx.author.id, wallet + winnings, bank)
            await ctx.send(embed=make_embed("🎲 Roulette — Green Bet", win, abs(winnings), "Green (0)"))

        else:
            embed = discord.Embed(
                title="❌ Invalid Bet Option",
                description=(
                    f"`{bet_option}` is not a valid choice.\n\n"
                    "Try one of the following:\n"
                    "`0–36`, `red`, `black`, `even`, `odd`, `low`, `high`, `green`"
                ),
                color=discord.Color.gold()
            )
            await ctx.send(embed=embed)

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
            result = (
                "🌈 **JACKPOT!** 🌈\n"
                f"You won 🪙 `{winnings:,}` coins!"
            )
            color = discord.Color.blue()
        elif len(set(reels)) == 2:
            winnings = bet_amount
            await self.bot.update_balances(ctx.author.id, wallet + winnings, bank)
            result = f"✨ You got two! You won 🪙 `{winnings:,}` coins!"
            color = discord.Color.green()
        else:
            await self.bot.update_balances(ctx.author.id, wallet - bet_amount, bank)
            result = f"💸 You lost 🪙 `{bet_amount:,}` coins."
            color = discord.Color.red()

        embed = discord.Embed(
            title="🎰 Slot Machine",
            color=color
        )
        embed.add_field(name="🎞️ Reels", value=" | ".join(reels), inline=False)
        embed.add_field(name="🎲 Result", value=result, inline=False)
        embed.set_footer(text="💡 Cooldown: 60 seconds.")

        await ctx.send(embed=embed)


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

            winner_user = await self.bot.fetch_user(winner)

            embed = discord.Embed(
                title="🪙 Coin Toss Result",
                description=f"The coin lands on **{'Heads' if winner == challenger_id else 'Tails'}**!",
                color=discord.Color.gold()
            )
            embed.set_thumbnail(url=winner_user.avatar.url)
            embed.add_field(name="🎖️ Winner", value=winner_user.mention, inline=True)
            embed.add_field(name="💰 Prize", value=f"🪙 `{total:,}` coins", inline=True)
            embed.set_footer(text="💡 Cooldown: 60 seconds.")
            await ctx.send(embed=embed)

        elif arg.lower() == "reject":
            if user_id not in self.bot.pending_battles:
                return await ctx.send("You don't have any pending toss battles.")

            challenger_id, _ = self.bot.pending_battles.pop(user_id)
            if user_id in self.bot.battle_timers:
                self.bot.battle_timers[user_id].cancel()
                del self.bot.battle_timers[user_id]

            challenger = await self.bot.fetch_user(challenger_id)
            embed = discord.Embed(
                title="❌ Toss Battle Rejected",
                description=f"{ctx.author.mention} rejected the toss battle from {challenger.mention}.",
                color=discord.Color.red()
            )
            await ctx.send(embed=embed)

        else:
            if not ctx.message.mentions:
                return await ctx.send("You must mention a user to challenge.")
            challenged_user = ctx.message.mentions[0]

            if challenged_user.id == ctx.author.id:
                return await ctx.send("You cannot challenge yourself.")
            if amount is None or amount <= 0:
                return await ctx.send("Please specify a valid amount.")

            challenger_wallet, _ = await self.bot.get_balances(ctx.author.id)
            challenged_wallet, _ = await self.bot.get_balances(challenged_user.id)

            if challenger_wallet < amount:
                return await ctx.send("You don't have enough coins.")
            if challenged_wallet < amount:
                return await ctx.send(f"{challenged_user.mention} doesn't have enough coins.")

            self.bot.pending_battles[challenged_user.id] = (ctx.author.id, amount)

            embed = discord.Embed(
                title="⚔️ Toss Battle Challenge",
                description=(
                    f"{ctx.author.mention} has challenged {challenged_user.mention} "
                    f"to a toss battle for 🪙 `{amount:,}` coins!\n\n"
                    "Respond with `.tb accept` or `.tb reject` within 60 seconds."
                ),
                color=discord.Color.gold()
            )
            await ctx.send(embed=embed)

            async def expire_battle():
                await asyncio.sleep(60)
                if challenged_user.id in self.bot.pending_battles:
                    del self.bot.pending_battles[challenged_user.id]
                    await ctx.send(
                        f"{challenged_user.mention}, your toss battle with {ctx.author.mention} has expired."
                    )
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
                formatted = "\n".join(f"`{letter}`: {option}" for letter, option in answer_map.items())

                embed = discord.Embed(
                    title="🧠 Quiz Time!",
                    description=f"{question}\n\n{formatted}",
                    color=discord.Color.gold()
                )
                embed.set_footer(text="💡 Reply with the letter (A–D). Cooldown: 60 seconds.")
                await ctx.send(embed=embed)

                def check(m):
                    return m.author == ctx.author and m.channel == ctx.channel and m.content.upper() in letters

                try:
                    msg = await self.bot.wait_for("message", timeout=20.0, check=check)
                except asyncio.TimeoutError:
                    return await ctx.send(f"⏰ Time's up! Correct answer: **{correct_letter}: {correct_answer}**.")

                if msg.content.upper() == correct_letter:
                    wallet, bank = await self.bot.get_balances(ctx.author.id)
                    await self.bot.update_balances(ctx.author.id, wallet + 1000, bank)

                    result_embed = discord.Embed(
                        title="✅ Correct!",
                        description=f"You earned 🪙 `1,000` coins.",
                        color=discord.Color.green()
                    )
                else:
                    result_embed = discord.Embed(
                        title="❌ Incorrect",
                        description=f"The correct answer was **{correct_letter}: {correct_answer}**.",
                        color=discord.Color.red()
                    )

                await ctx.send(embed=result_embed)



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

        color = discord.Color.green() if winnings > 0 else discord.Color.red()

        embed = discord.Embed(
            title="🧧 Your Fortune",
            color=color
        )

        if winnings == 0:
            embed.description = f"{ctx.author.mention}, you got... **nothing!** 😞\nBetter luck next time."
        else:
            await self.bot.update_balances(ctx.author.id, wallet + winnings, bank)
            embed.description = (
                f"{ctx.author.mention}, you received a **fortune** of 🪙 `{winnings:,}` coins!\n"
                "Lucky you!"
            )

        embed.set_footer(text="💡 Cooldown: 1 hour.")
        await ctx.send(embed=embed)




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

                embed = discord.Embed(
                    title="🏆 Top 10 Richest Players",
                    description="Note: This list is often inverted IRL.\n\u200b",
                    color=discord.Color.gold()
                )

                for i, (user_id, wallet, bank, total) in enumerate(results, 1):
                    try:
                        user = await self.bot.fetch_user(user_id)
                        name = user.name
                    except discord.NotFound:
                        name = f"User ID: {user_id}"

                    embed.add_field(
                        name=f"{i}. {name}",
                        value=(
                            f"💰 Wallet: {wallet:,}\n"
                            f"🏦 Bank: {bank:,}\n"
                            f"📊 Total: {total:,}\n"
                            f"\u200b"  # Invisible character to add a line break
                        ),
                        inline=False
                    )

                embed.set_footer(text="💡 Use -bal to check your own balance.")

                await ctx.send(embed=embed)



    @commands.command(name="setbal")
    @commands.is_owner()
    async def setbal(self, ctx, user: discord.User, wallet: int, bank: int = 0):
        await self.bot.update_balances(user.id, wallet, bank)

        embed = discord.Embed(
            title="🛠️ Balance Updated",
            color=discord.Color.gold()
        )
        embed.add_field(name="👤 User", value=user.mention, inline=True)
        embed.add_field(name="💰 Wallet", value=f"🪙 {wallet:,}", inline=True)
        embed.add_field(name="🏦 Bank", value=f"🪙 {bank:,}", inline=True)
        embed.set_footer(text="Bot owner action.")
        await ctx.send(embed=embed)


# ----------------------------------------------------------------------- MUSIC COG ------------------------------------------------------------------

class MusicCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    def get_music_controls(self, ctx):
        view = View(timeout=None)

        async def make_ctx(interaction: Interaction):
            ctx = await self.bot.get_context(interaction.message)
            ctx.author = interaction.user
            return ctx


        pause = Button(label="⏸ Pause", style=ButtonStyle.gray)
        async def pause_callback(interaction: Interaction):
            await interaction.response.defer()
            await self.pause(await make_ctx(interaction))
        pause.callback = pause_callback
        view.add_item(pause)


        resume = Button(label="▶ Resume", style=ButtonStyle.green)
        async def resume_callback(interaction: Interaction):
            await interaction.response.defer()
            await self.resume(await make_ctx(interaction))
        resume.callback = resume_callback
        view.add_item(resume)


        skip = Button(label="⏭ Skip", style=ButtonStyle.blurple)
        async def skip_callback(interaction: Interaction):
            await interaction.response.defer()
            await self.skip(await make_ctx(interaction))
        skip.callback = skip_callback
        view.add_item(skip)


        stop = Button(label="⏹ Stop", style=ButtonStyle.red)
        async def stop_callback(interaction: Interaction):
            await interaction.response.defer()
            await self.stop(await make_ctx(interaction))
        stop.callback = stop_callback
        view.add_item(stop)

        return view



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
            if video_ids[0] in file and file.endswith(".webm"):
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

        controls = self.get_music_controls(ctx)
        await ctx.send("🎶 Use the buttons below to control playback:", view=controls)

# ----------------------------------------------------- NSFW COG -----------------------------------------------------

class NSFWCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    async def fetch_waifu_nsfw(self, category: str):
        url = f"https://api.waifu.pics/nsfw/{category}"
        async with aiohttp.ClientSession() as session:
            async with session.get(url) as response:
                if response.status != 200:
                    return None
                data = await response.json()
                return data.get("url")

    async def send_nsfw_embed(self, ctx, category: str):
        if not ctx.channel.is_nsfw():
            return await ctx.send("❌ This command can only be used in NSFW-marked channels.")

        image_url = await self.fetch_waifu_nsfw(category)
        if not image_url:
            return await ctx.send("❌ Failed to fetch image. Try again later.")

        embed = discord.Embed(
            title=f"🔞 {category.capitalize()}",
            color=discord.Color.purple()
        )
        embed.set_image(url=image_url)
        await ctx.send(embed=embed)

    @commands.command(name="nsfw")
    async def nsfw(self, ctx, category: str = None):
        valid_categories = ["waifu", "neko", "trap", "blowjob"]

        if category is None:
            return await ctx.send("❗ Usage: `-nsfw <waifu|neko|trap|blowjob>`")

        category = category.lower()
        if category not in valid_categories:
            return await ctx.send("❗ Invalid category. Choose from: `waifu`, `neko`, `trap`, `blowjob`")

        wallet, bank = await self.bot.get_balances(ctx.author.id)
        cost = 5000
        if wallet < cost:
            return await ctx.send(f"{ctx.author.mention}, you need at least {cost} coins in your wallet to use this command.")

        await self.bot.update_balances(ctx.author.id, wallet - cost, bank)
        await ctx.send(f"I receive {cost} coins, you receive {category}")
        await self.send_nsfw_embed(ctx, category)


# ----------------------------------------------------------------- UTILS COG -------------------------------------------------------------

class UtilsCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.command(name="ping")
    async def ping(self, ctx):
        start = time.monotonic()

        gateway_latency = round(self.bot.latency * 1000)
        end = time.monotonic()
        api_latency = round((end - start) * 1000)

        embed = discord.Embed(
            title="🏓 Pong!",
            color=discord.Color.gold()
        )
        embed.add_field(name="📡 Gateway Latency", value=f"`{gateway_latency}ms`", inline=True)
        embed.add_field(name="⚙️ API Latency", value=f"`{api_latency}ms`", inline=True)
        embed.set_footer(text="Response speed check")

        await ctx.send(embed=embed)


    @commands.command(name="bl")
    @commands.is_owner()
    async def blacklist(self, ctx, user: discord.User, command_name: str):
        cmd_name = command_name.lower()
        if cmd_name not in self.bot.all_commands:
            return await ctx.send(f"❌ Command `-{cmd_name}` does not exist.")

        self.bot.blacklist.setdefault(user.id, set()).add(cmd_name)

        embed = discord.Embed(
            title="🔒 Command Blacklisted",
            color=discord.Color.red()
        )
        embed.add_field(name="👤 User", value=user.mention, inline=True)
        embed.add_field(name="⛔ Command", value=f"`-{cmd_name}`", inline=True)
        embed.set_footer(text="They are now restricted from using this command.")
        await ctx.send(embed=embed)


    @commands.command(name="wl")
    @commands.is_owner()
    async def whitelist(self, ctx, user: discord.User, command_name: str):
        cmd_name = command_name.lower()

        if user.id in self.bot.blacklist and cmd_name in self.bot.blacklist[user.id]:
            self.bot.blacklist[user.id].remove(cmd_name)
            if not self.bot.blacklist[user.id]:
                del self.bot.blacklist[user.id]

            embed = discord.Embed(
                title="✅ Command Whitelisted",
                color=discord.Color.green()
            )
            embed.add_field(name="👤 User", value=user.mention, inline=True)
            embed.add_field(name="🔓 Command", value=f"`-{cmd_name}`", inline=True)
            embed.set_footer(text="They are now allowed to use this command.")
        else:
            embed = discord.Embed(
                title="ℹ️ No Action Taken",
                color=discord.Color.gold()
            )
            embed.description = f"{user.mention} was not blacklisted from `-{cmd_name}`."

        await ctx.send(embed=embed)


    @commands.command(name="restart")
    @commands.is_owner()
    async def restart(self, ctx, target: str = None):
        if target is None:
            return await ctx.send("Usage: `-restart bot` or `-restart rpi`")

        if target.lower() == "bot":
            await ctx.send("♻️ Restarting bot...")
            await self.bot.close()  # systemd will restart it

        elif target.lower() == "rpi":
            await ctx.send("🔄 Restarting Raspberry Pi...")
            os.system("sudo reboot")

        else:
            await ctx.send("Invalid option. Use `bot` or `rpi`.")


    @commands.command(name="help")
    async def show_help(self, ctx):
        file_name = os.path.splitext(os.path.basename(__file__))[0]

        embed = discord.Embed(
            title=f"          Dealer `{file_name}`",
            description=f"[Source Code]({self.bot.source_code_link})\n\u200b",
            color=discord.Color.blue()
        )

        embed.add_field(
            name="🎮 Games & Economy",
            value=(
                "`-bal` — View your balances\n"
                "`-deposit <amount>` — Wallet → Bank\n"
                "`-withdraw <amount>` — Bank → Wallet\n"
                "`-give @user <amount>` — Send coins\n"
                "`-rob @user` — Rob another wallet\n"
                "`-dice <1–6> <amount>` — Bet on dice roll\n"
                "`-cf <heads/tails> <amount>` — Coin flip\n"
                "`-roulette <option> <amount>` — Bet on number, color, parity\n"
                "`-slots <amount>` — Slot machine\n"
                "`-tb @user <amount>` — Toss battle\n"
                "`-quiz <category_id>` — Answer trivia\n"
                "`-fortune` — Try your luck (hourly)\n"
                "`-top` — Richest users\n"
                "`-setbal @user <wallet> <bank>` — Set user balance\n\u200b"
            ),
            inline=False
        )

        embed.add_field(
            name="🎵 Music",
            value=(
                "`-play <song>` — Play a track\n"
                "`-pause` — Pause music\n"
                "`-resume` — Resume playback\n"
                "`-skip` — Skip song\n"
                "`-stop` — Stop and clear\n\u200b"
            ),
            inline=False
        )

        embed.add_field(
            name="🔞 NSFW",
            value=(
                "`-nsfw <waifu|neko|trap|blowjob>` — Random hentai\n\u200b"
            ),
            inline=False
        )

        embed.add_field(
            name="🛠️ Utility & Admin",
            value=(
                "`-ping` — Bot latency\n"
                "`-help` — Show this help menu\n"
                "`-restart <bot|rpi>` — Restarts bot or rpi\n"
                "`-bl @user <command>` — Blacklist a user\n"
                "`-wl @user <command>` — Whitelist a user\n\u200b"
            ),
            inline=False
        )

        embed.set_footer(text="Kindly contact the bot owner for further clarifications.")

        await ctx.send(embed=embed)



# -------------------------------------------------- Main Entrypoint ----------------------------------------------------

if __name__ == "__main__":
    config_path = "config.txt"
    db_path = "db.db"
    bot = Dealer(config_path=config_path, db_path=db_path)
    bot.run(bot.token)

