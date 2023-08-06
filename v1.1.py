#---------------------------------------------------Importing Libraries-------------------------------------------------

import discord
from discord import FFmpegPCMAudio
from discord.ext import commands
import urllib.request
import re
import os
from yt_dlp import YoutubeDL

#---------------------------------------------------Setting Parameters--------------------------------------------------

token = "OTgyNjQ1MDEzMDQ3NTQ5OTUy.GBAIpm.SZ8axrA4cwPSBxlOMqf2bM6G2HRQA62tC3Hlhk"

ydl_opts = {
    'format': 'bestaudio/best',
    'postprocessors': [{
        'key': 'FFmpegExtractAudio',
        'preferredcodec': 'mp3',
        'preferredquality': '192',
    }],
}

client = commands.Bot(command_prefix='-', intents=discord.Intents.all())

queue = {}

#---------------------------------------------------Readiness Check-----------------------------------------------------

@client.event
async def on_ready():
    print('[+] Bot started running')

#---------------------------------------------------Queue Checker-------------------------------------------------------

def check_queue(ctx, id):
    if queue[id] != []:
        voice = ctx.guild.voice_client
        source = queue[id].pop(0)
        player = voice.play(source)

#---------------------------------------------------Connect-------------------------------------------------------------

@client.command(pass_context = True)
async def connect(ctx):
    if ctx.author.voice:
        channel = ctx.message.author.voice.channel
        await channel.connect()
    else:
        await ctx.send("You're not in any voice channel")

#---------------------------------------------------Disconnect----------------------------------------------------------

@client.command(pass_context = True)
async def disconnect(ctx):
    if ctx.voice_client:
        await ctx.guild.voice_client.disconnect()
    else:
        ctx.send("Bot not in any channel")

#---------------------------------------------------Pause---------------------------------------------------------------

@client.command()
async def pause(ctx):
    voice = discord.utils.get(client.voice_clients, guild=ctx.guild)
    if voice.is_playing():
        voice.pause()
    else:
        await ctx.send("Bot not playing anything")
    voice.pause()

#---------------------------------------------------Resume--------------------------------------------------------------

@client.command()
async def resume(ctx):
    voice = discord.utils.get(client.voice_clients, guild=ctx.guild)
    if voice.is_paused():
        voice.resume()
    else:
        await ctx.send("Nothing is paused")

#---------------------------------------------------Stop----------------------------------------------------------------

@client.command()
async def stop(ctx):
    voice = discord.utils.get(client.voice_clients, guild=ctx.guild)
    voice.stop()

#----------------------------------------------------Player-------------------------------------------------------------

@client.command()
async def play(ctx, *args):
    voice = ctx.guild.voice_client

#----------------------------------------------------Link Finder--------------------------------------------------------

    video_name = ' '.join(args)
    await ctx.send(f"**Searching : **{video_name}")
    new_video_name = video_name.replace(' ', '+')
    html = urllib.request.urlopen("https://www.youtube.com/results?search_query=" + new_video_name)
    video_ids = re.findall(r"watch\?v=(\S{11})", html.read().decode())
    url = "https://www.youtube.com/watch?v=" + video_ids[0]
    await ctx.send(f"**Found : **{url}")

#----------------------------------------------------Downloader---------------------------------------------------------

    with YoutubeDL(ydl_opts) as ydl:
        ydl.download([url])
    for file in os.listdir("./"):
        if file.__contains__(video_ids[0]):
            source = FFmpegPCMAudio(file)
            if voice.is_playing()==False:
                player = voice.play(source,after=lambda x=None: check_queue(ctx, ctx.message.guild.id))

# ----------------------------------------------------Queue Adder-------------------------------------------------------

            else:
                guild_id = ctx.message.guild.id
                if guild_id in queue:
                    queue[guild_id].append(source)
                else:
                    queue[guild_id] = [source]
                await ctx.send("Song has been added to the queue")

#----------------------------------------------------Run----------------------------------------------------------------

client.run(token)
