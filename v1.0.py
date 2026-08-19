import discord
from discord.ext import commands
import urllib.request
import re
import os
from yt_dlp import YoutubeDL

token = "OTgyNjQ1MDEzMDQ3NTQ5OTUy.GBAIpm.SZ8axrA4cwPSBxlOMqf2bM6G2HRQA62tC3Hlhk"

ydl_opts = {
    'format': 'bestaudio/best',
    'postprocessors': [{
        'key': 'FFmpegExtractAudio',
        'preferredcodec': 'mp3',
        'preferredquality': '192',
    }],
}

client = commands.Bot(command_prefix='-',intents=discord.Intents.all())


@client.event
async def on_ready():
    print('[+] Bot started running')


@client.command()
async def connect(ctx):
    await ctx.author.voice.channel.connect()


@client.command()
async def disconnect(ctx):
    await ctx.voice_client.disconnect()


@client.command()
async def pause(ctx):
    voice = discord.utils.get(client.voice_clients, guild=ctx.guild)
    voice.pause()


@client.command()
async def resume(ctx):
    voice = discord.utils.get(client.voice_clients, guild=ctx.guild)
    voice.resume()


@client.command()
async def play(ctx, *args):
    voice = discord.utils.get(client.voice_clients, guild=ctx.guild)
    video_name = ' '.join(args)
    await ctx.send(f"**Searching : **{video_name}")
    new_video_name = video_name.replace(' ', '+')
    html = urllib.request.urlopen("https://www.youtube.com/results?search_query=" + new_video_name)
    video_ids = re.findall(r"watch\?v=(\S{11})", html.read().decode())
    url = "https://www.youtube.com/watch?v=" + video_ids[0]
    await ctx.send(f"**Found : **{url}")
    with YoutubeDL(ydl_opts) as ydl:
        ydl.download([url])
    for file in os.listdir("./"):
        if file.__contains__(video_ids[0]):
            voice.play(discord.FFmpegPCMAudio(file))


client.run(token)
