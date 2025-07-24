# -------------------------------------------------- Imports --------------------------------------------------

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

# -------------------------------------------------- Bot Setup --------------------------------------------------

intents = discord.Intents.all()
bot = commands.Bot(command_prefix="-", intents=intents, help_command=None)

@bot.event
async def on_ready():
    print("[+] Bot is running.")

# -------------------------------------------------- Token Import --------------------------------------------------

def get_token():
    with open('token.txt', 'r') as file:
        lines = file.readlines()  
        return lines[0].strip()   

token = get_token()

def get_owner():
    with open('token.txt', 'r') as file:
        lines = file.readlines()  
        return int(lines[1].strip())   

owner = get_owner()



# -------------------------------------------------- Audio Config --------------------------------------------------

ydl_opts = {
    'format': 'bestaudio/best',
    'postprocessors': [{
        'key': 'FFmpegExtractAudio',
        'preferredcodec': 'mp3',
        'preferredquality': '192',
    }],
}

queue = {}

# -------------------------------------------------- Database Setup --------------------------------------------------


DB_PATH = "bank.db"

async def init_db():
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute('''
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                wallet INTEGER,
                bank INTEGER
            )
        ''')
        await db.commit()

# -------------------------------------------------- Get Balances --------------------------------------------------


async def get_balances(user_id):
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute('SELECT wallet, bank FROM users WHERE user_id = ?', (user_id,)) as cursor:
            result = await cursor.fetchone()
            if result is None:
                await db.execute('INSERT INTO users (user_id, wallet, bank) VALUES (?, ?, ?)', (user_id, 50000, 0))
                await db.commit()
                return 50000, 0
            return result

# -------------------------------------------------- Update Balances --------------------------------------------------

async def update_balances(user_id, wallet, bank):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute('UPDATE users SET wallet = ?, bank = ? WHERE user_id = ?', (wallet, bank, user_id))
        await db.commit()

# -------------------------------------------------- Command: Balance --------------------------------------------------

@bot.command(name="bal")
async def balance(ctx):
    wallet, bank = await get_balances(ctx.author.id)
    total_balance = wallet + bank
    await ctx.send(f"{ctx.author.mention},\nWallet: {wallet}\nBank:   {bank}\nTotal:   {total_balance} coins.")


# -------------------------------------------------- Command: Deposit --------------------------------------------------

@bot.command(name="deposit")
async def deposit(ctx, amount: int = None):
    wallet, bank = await get_balances(ctx.author.id)
    
    if amount is None:
        amount = wallet
    
    if amount <= 0:
        return await ctx.send(f"{ctx.author.mention}, you must deposit a positive amount of coins.")
    
    if amount > wallet:
        return await ctx.send(f"{ctx.author.mention}, you don't have enough coins in your wallet.")
    
    await update_balances(ctx.author.id, wallet - amount, bank + amount)
    
    await ctx.send(f"{ctx.author.mention}, successfully deposited {amount} coins.")

# -------------------------------------------------- Command: Withdraw --------------------------------------------------

@bot.command(name="withdraw")
async def withdraw(ctx, amount: int):
    wallet, bank = await get_balances(ctx.author.id)
    if amount > bank:
        return await ctx.send(f"{ctx.author.mention}, not enough coins in bank.")
    await update_balances(ctx.author.id, wallet + amount, bank - amount)
    await ctx.send(f"{ctx.author.mention}, withdrew {amount} coins.")

# -------------------------------------------------- Command: Give --------------------------------------------------

@bot.command(name="give")
async def give(ctx, recipient: discord.User, amount: int):
    wallet, bank = await get_balances(ctx.author.id)
    
    if amount > wallet:
        return await ctx.send(f"{ctx.author.mention}, you don't have enough coins in your wallet to give.")

    recipient_wallet, recipient_bank = await get_balances(recipient.id)

    await update_balances(ctx.author.id, wallet - amount, bank)
    await update_balances(recipient.id, recipient_wallet + amount, recipient_bank)
    
    await ctx.send(f"{ctx.author.mention} has given {amount} coins to {recipient.mention}.")

# -------------------------------------------------- Command: Rob --------------------------------------------------

@bot.command(name="rob")
@commands.cooldown(1, 3600, commands.BucketType.user)  
async def rob(ctx, target: discord.User):

    if target.id == ctx.author.id:
        return await ctx.send("You cannot rob yourself!")


    robber_wallet, robber_bank = await get_balances(ctx.author.id)
    target_wallet, target_bank = await get_balances(target.id)

    if target_wallet == 0:
        return await ctx.send(f"{target.mention} has no coins to rob!")

    rob_amount = random.randint(1, target_wallet)

    success_chance = random.randint(1, 100)
    if success_chance <= 50:
               await update_balances(ctx.author.id, robber_wallet + rob_amount, robber_bank)  # Add to robber's wallet
        await update_balances(target.id, target_wallet - rob_amount, target_bank)  # Subtract from target's wallet

              await ctx.send(f"{ctx.author.mention} successfully robbed {rob_amount} coins from {target.mention}!")
    else:
               fine_amount = random.randint(0, robber_wallet)  # Fine is a random number between 0 and robber's wallet
        await update_balances(ctx.author.id, robber_wallet - fine_amount, robber_bank)  # Subtract the fine from the robber's wallet

               await ctx.send(f"{ctx.author.mention} got caught while trying to rob {target.mention} and lost {fine_amount} coins as a fine!")


@rob.error
async def rob_error(ctx, error):
    if isinstance(error, commands.CommandOnCooldown):
        remaining_minutes = math.ceil(error.retry_after / 60)
        await ctx.send(f"You're on cooldown! Try again in {remaining_minutes} minute(s).")

# -------------------------------------------------- Command: Dice --------------------------------------------------

@bot.command(name="dice")
@commands.cooldown(1, 60, commands.BucketType.user)  
async def dice(ctx, bet_option: int, bet_amount: int):
    wallet, bank = await get_balances(ctx.author.id)
    if bet_amount > wallet:
        return await ctx.send(f"{ctx.author.mention}, not enough coins.")
    if not (1 <= bet_option <= 6):
        return await ctx.send("Choose a number between 1 and 6.")

    dice_faces = {
        1: "⚀ (1)",  
        2: "⚁ (2)",  
        3: "⚂ (3)",  
        4: "⚃ (4)",  
        5: "⚄ (5)",  
        6: "⚅ (6)",  
    }


    roll = random.randint(1, 6)

   
    result_face = dice_faces[roll]
    

    if roll == bet_option:
        winnings = bet_amount * 5
        await update_balances(ctx.author.id, wallet + winnings, bank)
        await ctx.send(f"{ctx.author.mention}, you rolled {result_face} and won {winnings} coins!")
    else:
        await update_balances(ctx.author.id, wallet - bet_amount, bank)
        await ctx.send(f"{ctx.author.mention}, you rolled {result_face} and lost {bet_amount} coins.")



@dice.error
async def dice_error(ctx, error):
    if isinstance(error, commands.CommandOnCooldown):
        await ctx.send(f"You're on cooldown! Try again in {math.ceil(error.retry_after)} second(s).")

# -------------------------------------------------- Command: CF --------------------------------------------------

@bot.command(name="cf")
@commands.cooldown(1, 60, commands.BucketType.user)  
async def cf(ctx, bet_option: str, bet_amount: int):
    wallet, bank = await get_balances(ctx.author.id)
    if bet_amount > wallet:
        return await ctx.send("Not enough coins.")
    if bet_option.lower() not in ["heads", "tails"]:
        return await ctx.send("Choose heads or tails.")
    outcome = random.choice(["heads", "tails"])
    if outcome == bet_option.lower():
        winnings = bet_amount
        await update_balances(ctx.author.id, wallet + winnings, bank)
        await ctx.send(f"It's 🪙{outcome}! You win {winnings} coins.")
    else:
        await update_balances(ctx.author.id, wallet - bet_amount, bank)
        await ctx.send(f"It's {outcome}. You lost {bet_amount} coins.")

@cf.error
async def cf_error(ctx, error):
    if isinstance(error, commands.CommandOnCooldown):
        await ctx.send(f"You're on cooldown! Try again in {math.ceil(error.retry_after)} second(s).")

# -------------------------------------------------- Command: Roulette --------------------------------------------------

@bot.command(name="roulette")
@commands.cooldown(1, 60, commands.BucketType.user)  
async def roulette(ctx, bet_option: str, bet_amount: int):
    wallet, bank = await get_balances(ctx.author.id)
    if bet_amount > wallet:
        return await ctx.send(f"{ctx.author.mention}, not enough coins in wallet.")


    wheel = {
        "red": [1, 3, 5, 7, 9, 12, 14, 16, 18, 19, 21, 23, 25, 27, 30, 32, 34, 36],
        "black": [2, 4, 6, 8, 10, 11, 13, 15, 17, 20, 22, 24, 26, 28, 29, 31, 33, 35],
        "green": [0]
    }


    result_number = random.randint(0, 36)  
    
    if result_number == 0:
        result_color = "green"
    elif result_number in wheel["red"]:
        result_color = "red"
    else:
        result_color = "black"
    
   
    if bet_option.isdigit():  
        bet_number = int(bet_option)
        if bet_number < 0 or bet_number > 36:
            return await ctx.send(f"{ctx.author.mention}, please choose a number between 0 and 36.")
        
        if result_number == bet_number:
            winnings = bet_amount * 35
            await update_balances(ctx.author.id, wallet + winnings, bank)
            await ctx.send(f"{ctx.author.mention}, the ball landed on {result_number} ({result_color}). You bet on {bet_number} and win {winnings} coins!")
        else:
            await update_balances(ctx.author.id, wallet - bet_amount, bank)
            await ctx.send(f"{ctx.author.mention}, the ball landed on {result_number} ({result_color}). You bet on {bet_number} and lost {bet_amount} coins.")
    
    elif bet_option == "red" or bet_option == "black":
        # User bets on the color (red or black)
        if bet_option == result_color:
            winnings = bet_amount
            await update_balances(ctx.author.id, wallet + winnings, bank)
            await ctx.send(f"{ctx.author.mention}, the ball landed on {result_number} ({result_color}). You bet on {bet_option} and win {winnings} coins!")
        else:
            await update_balances(ctx.author.id, wallet - bet_amount, bank)
            await ctx.send(f"{ctx.author.mention}, the ball landed on {result_number} ({result_color}). You bet on {bet_option} and lost {bet_amount} coins.")
    
    elif bet_option == "even" or bet_option == "odd":
     
        if (result_number % 2 == 0 and bet_option == "even") or (result_number % 2 != 0 and bet_option == "odd"):
            winnings = bet_amount
            await update_balances(ctx.author.id, wallet + winnings, bank)
            await ctx.send(f"{ctx.author.mention}, the ball landed on {result_number} ({result_color}). You bet on {bet_option} and win {winnings} coins!")
        else:
            await update_balances(ctx.author.id, wallet - bet_amount, bank)
            await ctx.send(f"{ctx.author.mention}, the ball landed on {result_number} ({result_color}). You bet on {bet_option} and lost {bet_amount} coins.")
    
    elif bet_option == "low" or bet_option == "high":
       
        if bet_option == "low" and 1 <= result_number <= 18:
            winnings = bet_amount
            await update_balances(ctx.author.id, wallet + winnings, bank)
            await ctx.send(f"{ctx.author.mention}, the ball landed on {result_number} ({result_color}). You bet on low and win {winnings} coins!")
        elif bet_option == "high" and 19 <= result_number <= 36:
            winnings = bet_amount
            await update_balances(ctx.author.id, wallet + winnings, bank)
            await ctx.send(f"{ctx.author.mention}, the ball landed on {result_number} ({result_color}). You bet on high and win {winnings} coins!")
        else:
            await update_balances(ctx.author.id, wallet - bet_amount, bank)
            await ctx.send(f"{ctx.author.mention}, the ball landed on {result_number} ({result_color}). You bet on {bet_option} and lost {bet_amount} coins.")
    
    elif bet_option == "0" or bet_option == "green":
        
        if result_number == 0:
            winnings = bet_amount * 35
            await update_balances(ctx.author.id, wallet + winnings, bank)
            await ctx.send(f"{ctx.author.mention}, the ball landed on 0 (green). You bet on green and win {winnings} coins!")
        else:
            await update_balances(ctx.author.id, wallet - bet_amount, bank)
            await ctx.send(f"{ctx.author.mention}, the ball landed on {result_number} ({result_color}). You bet on green and lost {bet_amount} coins.")
    
    else:
        await ctx.send(f"Invalid bet option: `{bet_option}`. Please use one of the following bet types: `number`, `even`, `odd`, `red`, `black`, `low`, `high` or `green`.")


@roulette.error
async def roulette_error(ctx, error):
    if isinstance(error, commands.CommandOnCooldown):
        await ctx.send(f"You're on cooldown! Try again in {math.ceil(error.retry_after)} second(s).")

# -------------------------------------------------- Command: Slots --------------------------------------------------

@bot.command(name="slots")
@commands.cooldown(1, 60, commands.BucketType.user)  
async def slots(ctx, bet_amount: int):
    wallet, bank = await get_balances(ctx.author.id)
    if bet_amount > wallet:
        return await ctx.send("Not enough coins.")
    
   
    emojis = ["🍒", "🍋", "7️⃣", "🍉", "🍊", "🍓"]
    
 
    reels = [random.choice(emojis) for _ in range(3)]
    

    if reels.count(reels[0]) == 3:  # All three symbols match
        winnings = bet_amount * 10
        await update_balances(ctx.author.id, wallet + winnings, bank)
        await ctx.send(f"{' | '.join(reels)} — You won {winnings} coins!")
    elif len(set(reels)) == 2:  # Two symbols match
        winnings = bet_amount
        await update_balances(ctx.author.id, wallet + winnings, bank)
        await ctx.send(f"{' | '.join(reels)} — You won {winnings} coins!")
    else:  # No matching symbols
        await update_balances(ctx.author.id, wallet - bet_amount, bank)
        await ctx.send(f"{' | '.join(reels)} — You lost {bet_amount} coins.")


@slots.error
async def slots_error(ctx, error):
    if isinstance(error, commands.CommandOnCooldown):
        await ctx.send(f"You're on cooldown! Try again in {math.ceil(error.retry_after)} second(s).")


# -------------------------------------------------- Command: TB --------------------------------------------------

pending_battles = {}  
battle_timers = {}    

@bot.command(name="tb")
@commands.cooldown(1, 60, commands.BucketType.user)  # 1 usage per 60 seconds (1 min)
async def tb(ctx, arg=None, amount: int = None):
    if arg is None:
        return await ctx.send("Usage: `-tb @user <amount>` or `-tb accept/reject`")
    
    user_id = ctx.author.id

    if arg.lower() == "accept":
        if user_id not in pending_battles:
            return await ctx.send("You don't have any pending toss battles.")

        challenger_id, bet_amount = pending_battles.pop(user_id)
        if user_id in battle_timers:
            battle_timers[user_id].cancel()
            del battle_timers[user_id]

        challenger_wallet, challenger_bank = await get_balances(challenger_id)
        challenged_wallet, challenged_bank = await get_balances(user_id)

        if challenger_wallet < bet_amount:
            return await ctx.send("The challenger no longer has enough coins.")
        if challenged_wallet < bet_amount:
            return await ctx.send("You don't have enough coins to accept this bet.")

        await update_balances(challenger_id, challenger_wallet - bet_amount, challenger_bank)
        await update_balances(user_id, challenged_wallet - bet_amount, challenged_bank)

       
        winner = challenger_id if secrets.choice(["heads", "tails"]) == "heads" else user_id
        total = bet_amount * 2
        winner_wallet, winner_bank = await get_balances(winner)
        await update_balances(winner, winner_wallet + total, winner_bank)

        challenger = await bot.fetch_user(challenger_id)
        challenged = ctx.author
        winner_user = await bot.fetch_user(winner)

        await ctx.send(f"🪙 Coin toss result: **{'Heads' if winner == challenger_id else 'Tails'}**!\n{winner_user.mention} wins {total} coins!")

    elif arg.lower() == "reject":
        if user_id not in pending_battles:
            return await ctx.send("You don't have any pending toss battles.")

        challenger_id, _ = pending_battles.pop(user_id)
        if user_id in battle_timers:
            battle_timers[user_id].cancel()
            del battle_timers[user_id]

        challenger = await bot.fetch_user(challenger_id)
        await ctx.send(f"{ctx.author.mention} has rejected the toss battle challenge from {challenger.mention}.")

    else:
        if not ctx.message.mentions:
            return await ctx.send("You must mention a user to challenge.")
        challenged_user = ctx.message.mentions[0]
        challenger_id = ctx.author.id

        if challenged_user.id == ctx.author.id:
            return await ctx.send("You cannot challenge yourself.")
        if amount is None or amount <= 0:
            return await ctx.send("Please specify a valid amount of coins.")

        challenger_wallet, challenger_bank = await get_balances(challenger_id)
        challenged_wallet, challenged_bank = await get_balances(challenged_user.id)

        if challenger_wallet < amount:
            return await ctx.send("You don't have enough coins for this battle.")
        if challenged_wallet < amount:
            return await ctx.send(f"{challenged_user.mention} doesn't have enough coins to accept this battle.")

    
        pending_battles[challenged_user.id] = (challenger_id, amount)
        await ctx.send(f"{ctx.author.mention} has challenged {challenged_user.mention} to a toss battle for {amount} coins!\n{challenged_user.mention}, respond with `-tb accept` or `-tb reject` within 60 seconds.")

        async def expire_battle():
            await asyncio.sleep(60)
            if challenged_user.id in pending_battles:
                del pending_battles[challenged_user.id]
                await ctx.send(f"{challenged_user.mention}, your toss battle request from {ctx.author.mention} has expired (timeout).")
                battle_timers.pop(challenged_user.id, None)

        
        task = asyncio.create_task(expire_battle())
        battle_timers[challenged_user.id] = task


@tb.error
async def tb_error(ctx, error):
    if isinstance(error, commands.CommandOnCooldown):
        await ctx.send(f"You're on cooldown! Try again in {math.ceil(error.retry_after)} second(s).")

# -------------------------------------------------- Command: Blackjack --------------------------------------------------


# -------------------------------------------------- Command: Setbal --------------------------------------------------


@bot.command(name="setbal")
async def set_balance(ctx, user: discord.User, wallet: int, bank: int):
    # Replace with your Discord user ID
    if ctx.author.id != owner:
        await ctx.send("You are not authorized to use this command.")
        return
    
    await update_balances(user.id, wallet, bank)
    await ctx.send(f"Set {user.mention}'s balance: wallet {wallet}, bank {bank}")

# -------------------------------------------------- Command: Top --------------------------------------------------

@bot.command(name="top")
async def top_balances(ctx):
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute('''
            SELECT user_id, wallet, bank, (wallet + bank) AS total_balance
            FROM users
            ORDER BY total_balance DESC
            LIMIT 10
        ''') as cursor:
            results = await cursor.fetchall()

            if not results:
                await ctx.send("No users found in the database.")
                return

            leaderboard = "***TOP 10***\n"
            for i, (user_id, wallet, bank, total_balance) in enumerate(results, 1):
                try:
                    user = await bot.fetch_user(user_id)
                    leaderboard += f"{i}. {user.name} , wallet: {wallet}, bank: {bank}, total: {total_balance}\n"
                except discord.NotFound:
                    leaderboard += f"{i}. User not found (ID: {user_id}) , wallet: {wallet}, bank: {bank}, total: {total_balance}\n"

            await ctx.send(leaderboard)

# -------------------------------------------------- Command: Help --------------------------------------------------

@bot.command(name="help")
async def help(ctx):
    
    help_message = """

**Games Commands**
- `-bal`: View balances.
- `-deposit <amount>`: Wallet to bank.
- `-withdraw <amount>`: Bank to wallet.
- `-give @recipient <amount>`: Give to user.
- `-top`: Richest 10 players.
- `-rob @victim` : Once an hour, rob a user
- `-dice <1-6> <amount>`: Dice gamble.
- `-cf <heads/tails> <amount>`: Coin flip.
- `-slots <amount>`: Slot machine.
- `-bj <amount>` : Bet on blackjack ------- *coming soon*
    They must reply with `-bj hit` or `-bj stand` within 60 seconds.
- `-tb @user <amount>`: Coin toss battle, challenger takes heads.
    They must reply with `-tb accept` or `-tb reject` within 60 seconds.
- `-roulette <bet_option> <bet_amount>`: Roulette game.

**Music Commands**
- `-connect`: Join voice.
- `-disconnect`: Leave voice.
- `-skip`: Skip current song.
- `-play <song>`: Play from YouTube.
- `-pause`, `-resume`, `-stop`: Control playback.
"""

    await ctx.send(help_message)

# -------------------------------------------------- Check Queue --------------------------------------------------

def check_queue(ctx, id):
    if queue.get(id):
        voice = ctx.guild.voice_client
        source = queue[id].pop(0)  
        voice.play(source, after=lambda x=None: check_queue(ctx, id))  
    else:
        print("Queue is empty.")

# -------------------------------------------------- Command: Connect --------------------------------------------------

@bot.command()
async def connect(ctx):
    if ctx.author.voice:
        channel = ctx.author.voice.channel
        await channel.connect()
    else:
        await ctx.send("You're not in a voice channel.")

# -------------------------------------------------- Command: Disconnect --------------------------------------------------

@bot.command()
async def disconnect(ctx):
    if ctx.voice_client:
        await ctx.voice_client.disconnect()

# -------------------------------------------------- Command: Pause --------------------------------------------------

@bot.command()
async def pause(ctx):
    voice = ctx.voice_client
    if voice and voice.is_playing():
        voice.pause()

# -------------------------------------------------- Command: Resume --------------------------------------------------

@bot.command()
async def resume(ctx):
    voice = ctx.voice_client
    if voice and voice.is_paused():
        voice.resume()

# -------------------------------------------------- Command: Stop --------------------------------------------------

@bot.command()
async def stop(ctx):
    voice = ctx.voice_client
    if voice:
        voice.stop()

# -------------------------------------------------- Command: Skip --------------------------------------------------

@bot.command()
async def skip(ctx):
    voice = ctx.voice_client
    if voice and voice.is_playing():
        voice.stop()  
        await ctx.send("Skipped the current song.")
        
        check_queue(ctx, ctx.guild.id)

# -------------------------------------------------- Command: Play --------------------------------------------------

@bot.command()
async def play(ctx, *, search: str):
    if not ctx.voice_client:
        if ctx.author.voice:
            await ctx.author.voice.channel.connect()
        else:
            return await ctx.send("Join a voice channel first.")

    voice = ctx.voice_client
    await ctx.send(f"Searching for: {search}")
    query = search.replace(" ", "+")
    html = urllib.request.urlopen(f"https://www.youtube.com/results?search_query={query}")
    video_ids = re.findall(r"watch\?v=(\S{11})", html.read().decode())
    url = "https://www.youtube.com/watch?v=" + video_ids[0]
    await ctx.send(f"Found: {url}")

    with YoutubeDL(ydl_opts) as ydl:
        ydl.download([url])

    for file in os.listdir("./"):
        if video_ids[0] in file:
            source = FFmpegPCMAudio(file)
            if not voice.is_playing():
                voice.play(source, after=lambda x=None: check_queue(ctx, ctx.guild.id))
            else:
                queue.setdefault(ctx.guild.id, []).append(source)
                await ctx.send("Added to queue.")

# -------------------------------------------------- Run the Bot --------------------------------------------------

bot.run(token)
