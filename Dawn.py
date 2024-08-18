import discord
from discord.ext import commands, tasks
from discord import Member
from discord.ext.commands import has_permissions, MissingPermissions
from discord.utils import get
from discord.ui import Button, View, Select
import requests 
import asyncio
import aiofiles
import json
import traceback
import textwrap
import io
import contextlib
import os
import re
import platform
import random
from datetime import datetime, timedelta, timezone
from functools import wraps

intents = discord.Intents.default() 
intents.message_content = True 
intents.guilds = True
intents.members = True
intents.reactions = True

deleted_messages={}
embed_data = {}
muted_members = {}
edited_messages = {}

# Load warns from file if it exists
if os.path.exists("warns.json"):
    with open("warns.json", "r") as file:
        warns = json.load(file)
else:
    warns = {}

# Save warns to file
def save_warns():
    with open("warns.json", "w") as file:
        json.dump(warns, file, indent=4)

# Shiny hunt tracking
shiny_hunt_message = None
shiny_hunt_start_time = None
shiny_hunt_user_id = None
timer_embed = None

# List of allowed user IDs who can use the eval command
ALLOWED_USERS = [757066832753721375, 756460479739592705, 1121805578285625395, 894634240191389696]

THANK_YOU_CHANNEL_ID = 1174066899269718098

# JDoodle API credentials (optional, only required for non-Python code execution)
JD_API_CLIENT_ID = 'YOUR_JDOODLE_CLIENT_ID'
JD_API_CLIENT_SECRET = 'YOUR_JDOODLE_CLIENT_SECRET'

client = commands.Bot(command_prefix = commands.when_mentioned_or('!'),intents=intents)

client.remove_command('help')

giveaways = []

# Replace with role IDs that should have extra entries
EXTRA_ENTRIES_ROLES = {
    1181230168640065546: 2,  # Donator
    1174066837521174609: 2,  # lvl 40
    1174066835545669662: 3,  # lvl 50
    1174066829350674523: 4,  # lvl 80
    1174066825613545555: 5,  # lvl 100
    1180853783257948170: 4,  # booster
}

BLACKLIST_FILE = 'blacklist.json'
ENTRIES_FILE = 'entries.json'
PERMANENT_BANNER_URL = 'https://media.discordapp.net/attachments/1174066968672878603/1254337681505124452/Giveaway_20240623_125903_0001.gif?ex=6679207f&is=6677ceff&hm=5476ee71da953c185f46d9c9cba8c8c9b6bc48afb62e9cc5871e54d8d4760ee7&=&width=892&height=507'

def load_blacklist():
    if not os.path.exists(BLACKLIST_FILE):
        return set()
    with open(BLACKLIST_FILE, 'r') as file:
        return set(json.load(file))

def save_blacklist(blacklist):
    with open(BLACKLIST_FILE, 'w') as file:
        json.dump(list(blacklist), file)

def load_entries():
    if not os.path.exists(ENTRIES_FILE):
        return {}
    with open(ENTRIES_FILE, 'r') as file:
        return json.load(file)

def save_entries(entries):
    with open(ENTRIES_FILE, 'w') as file:
        json.dump(entries, file)

blacklist = load_blacklist()
entries_data = load_entries()

class Giveaway:
    def __init__(self, ctx, prize, duration, custom_message=None):
        self.ctx = ctx
        self.prize = prize
        self.end_time = datetime.utcnow() + timedelta(seconds=duration)
        self.entries = entries_data.get(str(ctx.message.id), {})
        self.message = None
        self.banner_url = PERMANENT_BANNER_URL
        self.custom_message = custom_message

    async def start(self):
        embed = discord.Embed(
            title="Giveaway!", 
            description=f"Prize: **{self.prize}**\n{self.custom_message if self.custom_message else ''}\n \n The following roles have extra entries: \n> - Level 100 - 5x entries \n> - Level 80 - 4x entries \n> - Level 50 - 3x entries \n> - Level 40 - 2x entries \n> - Boosters - 4x entries \n> - Donator - 2x entries \nReact with <a:giveaway:1254330534927007746> to enter!\nEnds at: {self.end_time} UTC", 
            color=0xee8c8c
        )
        embed.set_footer(text=f"Giveaway hosted by {self.ctx.author}")
        if self.banner_url:
            embed.set_image(url=self.banner_url)
        self.message = await self.ctx.send(embed=embed)
        await self.message.add_reaction("<a:giveaway:1254330534927007746>")
        entries_data[str(self.message.id)] = self.entries
        save_entries(entries_data)

    async def end(self):
        if not self.entries:
            await self.ctx.send("No entries, no winner!")
            return

        total_entries = []
        for user_id, extra in self.entries.items():
            total_entries.extend([user_id] * (1 + extra))

        winner_id = random.choice(total_entries)
        winner = await self.ctx.guild.fetch_member(winner_id)
        await self.ctx.send(f"Congratulations {winner.mention}! You won the **{self.prize}**!")
        entries_data.pop(str(self.ctx.message.id), None)
        save_entries(entries_data)

@client.command(name='giveaway', help='Start a giveaway. Usage: !giveaway <duration> <prize> [banner_url] [custom_message]')
@commands.has_permissions(administrator=True)
async def giveaway(ctx, duration: str, prize: str, *, custom_message: str = None):
    time_seconds = parse_time(duration)
    if time_seconds <= 0:
        await ctx.send('Please provide a valid duration.')
        return

    giveaway = Giveaway(ctx, prize, time_seconds, custom_message)
    giveaways.append(giveaway)
    await ctx.message.delete()
    await giveaway.start()
    await asyncio.sleep(time_seconds)
    await giveaway.end()
    giveaways.remove(giveaway)

@client.command(name='blacklist', help='Add or remove a user from the blacklist. Usage: !blacklist <add|remove> <user>')
@commands.has_permissions(administrator=True)
async def manage_blacklist(ctx, action: str, user: discord.Member):
    if action.lower() == 'add':
        blacklist.add(user.id)
        save_blacklist(blacklist)
        await ctx.send(f"Added {user.mention} to the blacklist.")
    elif action.lower() == 'remove':
        blacklist.discard(user.id)
        save_blacklist(blacklist)
        await ctx.send(f"Removed {user.mention} from the blacklist.")
    else:
        await ctx.send("Invalid action. Use 'add' or 'remove'.")

@client.event
async def on_reaction_add(reaction, user):
    if user.bot:
        return

    if user.id in blacklist:
        await reaction.message.remove_reaction(reaction.emoji, user)
        return

    for giveaway in giveaways:
        if giveaway.message.id == reaction.message.id and str(reaction.emoji) == "<a:giveaway:1254330534927007746>":
            extra_entries = 0
            for role_id, extra in EXTRA_ENTRIES_ROLES.items():
                if discord.utils.get(user.roles, id=role_id):
                    extra_entries += extra
            giveaway.entries[user.id] = extra_entries
            entries_data[str(giveaway.ctx.message.id)] = giveaway.entries
            save_entries(entries_data)

@client.event
async def on_reaction_remove(reaction, user):
    if user.bot:
        return

    for giveaway in giveaways:
        if giveaway.message.id == reaction.message.id and str(reaction.emoji) == "<a:giveaway:1254330534927007746>":
            giveaway.entries.pop(user.id, None)
            entries_data[str(giveaway.ctx.message.id)] = giveaway.entries
            save_entries(entries_data)


DESIGNATED_CHANNEL_ID = 1253966605629653063  # Replace with your channel ID

def in_channel(channel_id):
    def predicate(ctx):
        return ctx.channel.id == channel_id

    def wrapper(func):
        @wraps(func)
        async def inner(ctx, *args, **kwargs):
            if predicate(ctx):
                return await func(ctx, *args, **kwargs)
            else:
                await ctx.send(f'This command can only be used in the https://discord.com/channels/1174062246071128145/1253966605629653063 channel.')
        return inner
    return wrapper

@client.event
async def on_ready():
    print("The bot is now ready for use!")
    print("-----------------------------")
    check_shiny_hunt.start()


@client.event
async def on_member_update(before, after):
    if len(before.premium_since) == 0 and len(after.premium_since) > 0:
        channel = client.get_channel(THANK_YOU_CHANNEL_ID)
        if channel:
            embed = discord.Embed(
                title="Thank You!",
                description=f"Thank you {after.mention} for boosting the server! Your support is greatly appreciated!",
                color=0x00ff00
            )
            embed.set_thumbnail(url=after.avatar.url if after.avatar else "")
            embed.set_footer(text=f"Boosted by {after.name}", icon_url=after.avatar.url if after.avatar else "")
            embed.set_image(url='https://media.discordapp.net/attachments/1174066968672878603/1254334566571835443/pink_cute_boost_banner_discord.jpg?ex=66791d99&is=6677cc19&hm=2e29ef04156413ff9afe65402a324a1c966cce07054a71a2ccda9142ac4b3d6e&=&format=webp&width=920&height=537')
            await channel.send(embed=embed)


@client.command()
async def eval(ctx, lang: str, *, code: str):
    # Check if the user is allowed to use the eval command
    if (ctx.author.id) not in ALLOWED_USERS:
        await ctx.send("You do not have permission to use this command.")
        return
    
# Python execution block
    if lang.lower() == 'python':
        code = f"async def _eval(ctx):\n{textwrap.indent(code, '    ')}"
        local_vars = {'ctx': ctx}

        try:
            exec(code, globals(), local_vars)
            func = local_vars['_eval']

            with contextlib.redirect_stdout(io.StringIO()) as f:
                await func(ctx)
            result = f.getvalue()

            await ctx.send(f'{result}')
        except Exception as e:
            await ctx.send(f'Error: {e}')
    else:
        # Other languages using JDoodle API
        response = run_jdoodle_code(lang, code)
        if response:
            await ctx.send(f'{response}')
        else:
            await ctx.send(f'Error: Unable to execute code.')

def run_jdoodle_code(language, code):
    url = "https://api.jdoodle.com/v1/execute"
    payload = {
        'clientId': JD_API_CLIENT_ID,
        'clientSecret': JD_API_CLIENT_SECRET,
        'script': code,
        'language': language,
        'versionIndex': '0'
    }
    response = requests.post(url, json=payload)
    if response.status_code == 200:
        result = response.json()
        return result.get('output')
    else:
        return None 



# Helper function to create the initial embed
def create_main_embed(client):
    embed = discord.Embed(
        title="**HELP MENU**",
        description=(
            "<a:melodydance:1253674912548261960> __**BOT INFO**__\n"
            f"> Prefix: `!`\n \n"
            "<a:melodydance:1253674912548261960> __**BOT'S COMMANDS**__\n"
            "> Config Commands\n"
            "> Moderation Commands\n"
            "> Information Commands\n"
            "> Utility Commands\n"
            "> Image Commands\n \n"
            "<a:melodydance:1253674912548261960> __**BOT'S STATUS**__\n"
            #f"> current ping: {round(client.latency * 1000)}ms'\n"
            f"> discord.py Version: {discord.__version__}\n"
            f"> Running on Python {platform.python_version()} on {platform.system()} {platform.machine()}\n"
        ),
        color=discord.Color.blue()
    )
    embed.set_image(url="https://media.discordapp.net/attachments/1182245769164628011/1201489473888858293/aesethdawn.gif")
    # embed.set_thumbnail(url=client.user.avatar.url)
    return embed

# Define help menu pages
pages = {
    '0': create_main_embed(client),
    '1': discord.Embed(title="**Help Menu**", color=discord.Color.blue())
        .add_field(name="**INFO COMMANDS**", value="`help`, `ping`, `embed`", inline = False)
        .add_field(name="help", value=f"Shows this menu. \n Usage: !help", inline = False)
        .add_field(name="ping", value=f"Shows the latency of the bot. \n Usage: !ping", inline = False)
        .add_field(name="startembed", value=f"Starts an embed. \n Usage: !startembed", inline = False)
        .set_image(url="https://media.discordapp.net/attachments/1182245769164628011/1201489473888858293/aesethdawn.gif")
        .set_footer(text='Page 1'),
    '3': discord.Embed(title="**Help Menu**", color=discord.Color.blue())
        .add_field(name="**MOD COMMANDS**", value="`ban`, `purge`, `timeout`, `untimeout`, `kick`, `tempmute`, `nuke`, `addemoji`, `addrole`, `removerole`, `lock`, `unlock`, `hide`, `unhide`, `testgreet`, `testleave`", inline = False)
        .add_field(name="ban", value=f"Bans a member from the server. \n Usage: !ban @member <reason>", inline = False)
        .add_field(name="purge", value=f"Deletes messages. \n Usage: !purge <number of messages>", inline = False)
        .add_field(name="mute", value=f"Timeout a member for a specified duration. \n Usage: Usage: !timute @member 1d2h3m4s'", inline = False)
        .add_field(name="unmute", value=f"Removes timeout a member for a specified duration. \n Usage: Usage: !unmute @member 1d2h3m4s'", inline = False)
        .add_field(name="kick", value=f"Kicks a member from the server. \n Usage: !kick @member <reason>", inline = False)
        .add_field(name="temprole", value=f"Gives the member a temporary role. \n Usage: !temprole @member <duration in d/h/m/s> <role>", inline = False)
        .add_field(name="addrole", value=f"Gives the member a role. \n Usage: !addrole @member <role>", inline = False)
        .add_field(name="removerole", value=f"Removes a role from the member. \n Usage: !removerole @member <role>", inline = False)
        .add_field(name="lock", value=f"Locks the channel. \n Usage: !lock", inline = False)
        .add_field(name="unlock", value=f"Unlocks the channel. \n Usage: !unlock", inline = False)
        .add_field(name="hide", value=f"Hides the channel. \n Usage: !hide", inline = False)
        .add_field(name="unhide", value=f"Unhides the channel. \n Usage: !unhide", inline = False)
        .add_field(name="testgreet", value=f"Usage: !testgreet", inline = False)
        .add_field(name="testleave", value=f"Usage: !testleave", inline = False)
        .set_footer(text='Page 2')
        .set_image(url="https://media.discordapp.net/attachments/1182245769164628011/1201489473888858293/aesethdawn.gif"),
    '4': discord.Embed(title="**Help Menu**", color=discord.Color.blue())
        .add_field(name="**UTILITY COMMANDS**", value="`addtag`, `edittag`, `removetag`, `afk`, `editsnipe`, `snipe`, `timer`, `math`, `avatar`", inline = False)
        .add_field(name="editsnipe", value=f"Shows the recently edited messages. \n Usage: !editsnipe", inline = False)
        .add_field(name="snipe", value=f"Shows the recently deleted message. \n Usage: !snipe", inline = False)
        .add_field(name="math", value=f"Does the math for you. \n Usage: !math <expression>", inline = False)
        .set_image(url="https://media.discordapp.net/attachments/1182245769164628011/1201489473888858293/aesethdawn.gif")
        .set_footer(text='Page 3'),
    '5': discord.Embed(title="**Help Menu**", color=discord.Color.blue())
        .add_field(name="**IMAGE COMMANDS**", value="`waifu`, `neko`, `kill`", inline=False)
        .add_field(name="waifu", value=f"Sends a waifu image. \n Usage: !waifu", inline = False)
        .add_field(name="neko", value=f"Sends a neko image. \n Usage: !neko", inline = False)
        .add_field(name="kill", value=f"Sends a gif of kill. \n Usage: !kill @member", inline = False)
        .set_image(url="https://media.discordapp.net/attachments/1182245769164628011/1201489473888858293/aesethdawn.gif")
        .set_footer(text='Page 4'),
}

class HelpView(discord.ui.View):
    def __init__(self, pages):
        super().__init__(timeout=None)
        self.pages = pages
        select = discord.ui.Select(
            placeholder="Dawn Menu",
            options=[
                discord.SelectOption(label="Main Menu", description="Shows the main menu", emoji="<a:1_:1209474710308524072>", value='0'),
                discord.SelectOption(label="Information Commands", description="Shows all the config commands", emoji="<a:2_:1209474800309772298>", value='1'),
                discord.SelectOption(label="Moderation Commands", description="Shows all the fun commands", emoji="<a:3_:1209474830345310209>", value='3'),
                discord.SelectOption(label="Utility Commands", description="Shows all the game commands", emoji="<a:4_:1209474879569530900>", value='4'),
                discord.SelectOption(label="Image Commands", description="Shows all the information commands", emoji="<a:5_:1209474906413342731>", value='5'),
            ]
        )
        select.callback = self.select_callback
        self.add_item(select)

    async def select_callback(self, interaction: discord.Interaction):
        value = interaction.data['values'][0]
        embed = self.pages.get(value, create_main_embed(client))
        await interaction.response.edit_message(embed=embed, view=self)

# Help command
@client.command(name='help', aliases=['h'])
async def help_command(ctx):
    embed = create_main_embed(client)
    view = HelpView(pages)
    await ctx.send(embed=embed, view=view)

# Helper function to run the code
async def run_code(code):
    str_obj = io.StringIO()  # create an in-memory file-like string object
    try:
        with contextlib.redirect_stdout(str_obj):
            exec(code)
    except Exception as e:
        return str_obj.getvalue() + '\n' + traceback.format_exc()
    return str_obj.getvalue()

# vote
@client.command(name='vote', aliases=['v'], help='Gives the vote link to upvote the server.')
async def vote(ctx):
    await ctx.send('https://discords.com/servers/pokecafez')

# ping
@client.command(name='ping', help='checks the latency of the bot. Usage: !ping')
async def ping(ctx):
#    await ctx.send(f'Pong! Latency: {round(client.latency * 1000)}ms')
    embed = discord.Embed(
        title='Pong!',
        description=f'Latency: {round(client.latency * 1000)}ms',
        color=0x000000
    )
    embed.set_author(
        name=ctx.author.display_name,  # Author name
        icon_url=ctx.author.avatar.url  # Author's avatar as the icon
    )
    await ctx.send(embed=embed)

# calculator
@client.command(name='math', aliases=['calc'], help='Performs arithmetic calculations. Usage: !math <expression>')
async def math(ctx, *, expression: str):
    try:
        # Evaluate the expression using Python's eval function
        result = eval(expression)

        # Send the result as a message
        await ctx.send(f"Result: {result}")

    except ZeroDivisionError:
        await ctx.send("Error: Division by zero.")
    except ValueError:
        await ctx.send("Error: Invalid input.")
    except Exception as e:
        await ctx.send(f"An unexpected error occurred: {e}")

@math.error
async def calculate_error(ctx, error):
    if isinstance(error, commands.MissingRequiredArgument):
        await ctx.send("Please provide an arithmetic expression to calculate.")
    else:
        await ctx.send(f"An error occurred: {error}")


# hello
@client.command()
async def hello(ctx):
    await ctx.send("Hi! Hope you're doing good")

# greet
@client.event
async def on_member_join(member):
    channel = client.get_channel(1174066890914668615)
    guild = member.guild
    if channel:
        embed = discord.Embed(
            title=f"Welcome to {guild.name}!",
            description=f" __Welcome to the server {member.mention}!__ \n \n __We're glad to have you here.__💖 \n \n <a:Arrow3:1201024848755970149> __Pls check https://discord.com/channels/1174062246071128145/1174066893515137145__ \n \n <a:Arrow3:1201024848755970149> __Take your roles in https://discord.com/channels/1174062246071128145/1174066894723092521__ \n \n <a:Arrow3:1201024848755970149> __Want some colours? https://discord.com/channels/1174062246071128145/1182257383750258688__ \n \n <a:Arrow3:1201024848755970149> __Most important rule: Have fun!!__",
            color=discord.Color.blue()
        )
        embed.set_image(url='https://media.discordapp.net/attachments/1174066968672878603/1216752120858939432/We_hope_to_see_you_again.gif?ex=667785f7&is=66763477&hm=73a9f69c25a2a023060d25860d3ca07f680b5b389eaab6e18d65bcff531e591d&=&width=1177&height=662')
        embed.set_thumbnail(url=member.avatar.url)
        embed.set_footer(text="Enjoy your stay!")
        await channel.send(embed=embed)

    embed = discord.Embed(title=f"Welcome to {guild.name}!", description=f"Thank you for joining {guild.name}.", color=discord.Color.green())
    embed.set_thumbnail(url=guild.icon.url)
    embed.set_footer(text="Enjoy your stay!")
    await member.send(embed=embed)

#test greet
@client.command()
@commands.has_role(1174066821419257917)
async def testgreet(ctx):

    channel = client.get_channel(1174066890914668615)
    guild = ctx.author.guild
    if channel:
        embed = discord.Embed(
            title=f"Welcome to {guild.name}!",
            description=f" __Welcome to the server {ctx.author.mention}!__ \n \n __We're glad to have you here.__💖 \n \n <a:Arrow3:1201024848755970149> __Pls check https://discord.com/channels/1174062246071128145/1174066893515137145__ \n \n <a:Arrow3:1201024848755970149> __Take your roles in https://discord.com/channels/1174062246071128145/1174066894723092521__ \n \n <a:Arrow3:1201024848755970149> __Want some colours? https://discord.com/channels/1174062246071128145/1182257383750258688__ \n \n <a:Arrow3:1201024848755970149> __Most important rule: Have fun!!__",
            color=discord.Color.blue()
        )
        embed.set_image(url='https://media.discordapp.net/attachments/1174066968672878603/1216752120858939432/We_hope_to_see_you_again.gif?ex=667785f7&is=66763477&hm=73a9f69c25a2a023060d25860d3ca07f680b5b389eaab6e18d65bcff531e591d&=&width=1177&height=662')
        embed.set_thumbnail(url=ctx.author.avatar.url)
        embed.set_footer(text="Enjoy your stay!")
        await channel.send(embed=embed)

# leave
@client.event
async def on_member_remove(member):
    channel = client.get_channel(1198339044984242317)
    if channel:
        embed = discord.Embed(
            title="A Trainer has Fled.",
            description=f"It's a pity that {member.mention} left the server...",
            color=discord.Color.blue()
        )
        embed.set_thumbnail(url=member.avatar.url)
        embed.set_image(url = 'https://media.discordapp.net/attachments/1174066968672878603/1216752169408270408/Untitled_design.gif?ex=66778603&is=66763483&hm=4c2a44aaa46bf930361b1799b035982a7b2d428865733d96d0e6b85e395d8031&=&width=1177&height=662')
        embed.set_footer(text="See you soon!")
        await channel.send(embed=embed)

# testleave
@client.command()
@commands.has_role(1174066821419257917)
async def testleave(ctx):
    channel = client.get_channel(1198339044984242317)
    if channel:
        embed = discord.Embed(
            title="A Trainer has Fled.",
            description=f"It's a pity that {ctx.author.mention} left the server...",
            color=discord.Color.blue()
        )
        embed.set_thumbnail(url=ctx.author.avatar.url)
        embed.set_image(url = 'https://media.discordapp.net/attachments/1174066968672878603/1216752169408270408/Untitled_design.gif?ex=66778603&is=66763483&hm=4c2a44aaa46bf930361b1799b035982a7b2d428865733d96d0e6b85e395d8031&=&width=1177&height=662')
        embed.set_footer(text="See you soon!")
        await channel.send(embed=embed)

# kick
@client.command(name='kick', help='Kick a member from the server. Usage: !kick @member reason')
@commands.has_permissions(kick_members=True)
async def kick(ctx, member: discord.Member, *, reason=None):
    try:
        server_name = ctx.guild.name
        if member == ctx.guild.owner:
            await ctx.send("You can't kick the owner of the server. Are you mentally stable?")
            return
        
        if member == ctx.message.author:
            await ctx.send("You cannot kick yourself.")
            return

        if member.top_role >= ctx.author.top_role:
            await ctx.send("You cannot kick a member with a role higher or equal to yours.")
            return

        await member.send(f'You have been kicked from {server_name} for the reason: ||{reason}||')
        await member.kick(reason=reason)
        await ctx.send(f'Kicked {member.mention}')
        

    except discord.Forbidden:
        await ctx.send("I do not have permission to kick members.")
    except discord.HTTPException as e:
        await ctx.send(f"An error occurred while trying to kick the member: {e}")
    except Exception as e:
        await ctx.send(f"An unexpected error occurred: {e}")

# kick error handling
@kick.error
async def kick_error(ctx, error):
    if isinstance(error, commands.MissingPermissions):
        await ctx.send("You do not have permission to kick members.")
    elif isinstance(error, commands.MissingRequiredArgument):
        await ctx.send("Please mention a member to kick.")
    elif isinstance(error, commands.BadArgument):
        await ctx.send("Please mention a valid member to kick.")
    elif isinstance(error, commands.MissingRequiredArgument):
        await ctx.send("Please mention a member to kick.")
    elif isinstance(error, commands.CheckFailure):
        await ctx.send("You don't have permission to use this command.")
    elif isinstance(error, commands.CommandOnCooldown):
        await ctx.send(f"This command is on cooldown. Try again in {error.retry_after:.2f} seconds.")
    elif isinstance(error, commands.NoPrivateMessage):
        await ctx.send("This command cannot be used in private messages.")
    elif isinstance(error, commands.BotMissingPermissions):
        await ctx.send("I don't have permission to kick members.")
    else:
        await ctx.send(f"An error occurred: {error}")
    
# ban
@client.command(name='ban', help='Ban a member from the server. Usage: !ban @member reason')
@commands.has_permissions(ban_members=True)
async def ban(ctx, member: discord.Member, *, reason=None):
    try:
        server_name = ctx.guild.name
        if member == ctx.guild.owner:
            await ctx.send("You can't ban the owner of the server. Are you mentally stable?")
            return
        
        if member == ctx.message.author:
            await ctx.send("You cannot ban yourself.")
            return

        if member.top_role >= ctx.author.top_role:
            await ctx.send("You cannot ban a member with a role higher or equal to yours.")
            return
        
        await member.ban(reason=reason)
        await ctx.send(f'Banned {member.mention}')
        await member.send(f'You have been banned from the server {server_name} for the reason: ||{reason}||')
    
    except discord.Forbidden:
        await ctx.send("I do not have permission to ban members.")
    except discord.HTTPException as e:
        await ctx.send(f"An error occurred while trying to ban the member: {e}")
    except Exception as e:
        await ctx.send(f"An unexpected error occurred: {e}")

# ban error handling
@ban.error
async def ban_error(ctx, error):
    if isinstance(error, commands.MissingPermissions):
        await ctx.send("You do not have permission to ban members.")
    elif isinstance(error, commands.MissingRequiredArgument):
        await ctx.send("Please mention a member to ban.")
    elif isinstance(error, commands.BadArgument):
        await ctx.send("Please mention a valid member to ban.")
    elif isinstance(error, commands.MissingRequiredArgument):
        await ctx.send("Please mention a member to ban.")
    elif isinstance(error, commands.CheckFailure):
        await ctx.send("You don't have permission to use this command.")
    elif isinstance(error, commands.CommandOnCooldown):
        await ctx.send(f"This command is on cooldown. Try again in {error.retry_after:.2f} seconds.")
    elif isinstance(error, commands.NoPrivateMessage):
        await ctx.send("This command cannot be used in private messages.")
    elif isinstance(error, commands.BotMissingPermissions):
        await ctx.send("I don't have permission to ban members.")
    else:
        await ctx.send(f"An error occurred: {error}")

# unban 
@client.command(name='unban', help='Unban a member from the server. Usage: !unban <user id>')
async def unban(ctx, user: discord.User):
    guild = ctx.guild
    if ctx.author.guild_permissions.ban_members:
        await ctx.send(f'{user} has successfully been unbanned.')
        await guild.unban(user=user)

# Error handler for unban command
@unban.error
async def unban_error(ctx, error):
    if isinstance(error, commands.MissingPermissions):
        await ctx.send("You do not have permission to unban members.")
    elif isinstance(error, commands.MissingRequiredArgument):
        await ctx.send("Please specify the user id of the member to unban.")
    else:
        await ctx.send(f"An error occurred: {error}")

# warn
@client.command(name="warn", help='Warns the mentioned member. Usage: !warn @member <reason>')
@commands.has_role(1174066821419257917)
async def warn(ctx, member: discord.Member, *, reason=None):
    if reason is None:
        await ctx.send("Please provide a reason for the warning.")
        return

    user_id = str(member.id)
    if user_id not in warns:
        warns[user_id] = []

    warns[user_id].append({"reason": reason, "moderator": str(ctx.author)})

    save_warns()

    embed = discord.Embed(title="User Warned", color=discord.Color.red())
    embed.add_field(name="User", value=member.mention, inline=True)
    embed.add_field(name="Moderator", value=ctx.author.mention, inline=True)
    embed.add_field(name="Reason", value=reason, inline=False)

    await ctx.send(embed=embed)
    await ctx.message.delete()
    guild = ctx.guild
    embed = discord.Embed(title='Warning', description=f'You have been warned in {guild.name} for the reason: ||{reason}||')
    embed.set_thumbnail(url=guild.icon.url)
    await member.send(embed=embed)

# warnlist
@client.command(name="warnlist")
@commands.has_role(1174066821419257917)
async def warnlist(ctx, member: discord.Member):
    user_id = str(member.id)
    if user_id not in warns or len(warns[user_id]) == 0:
        embed = discord.Embed(title="No Warnings", description=f"{member.mention} has no warnings.", color=discord.Color.green())
        await ctx.send(embed=embed)
        return

    embed = discord.Embed(title=f"Warnings for {member.display_name}", color=discord.Color.orange())
    for i, warn in enumerate(warns[user_id], 1):
        embed.add_field(name=f"Warning {i}", value=f"**Reason:** {warn['reason']}\n**Moderator:** {warn['moderator']}", inline=False)

    await ctx.send(embed=embed)

# remove warns
@client.command(name="removewarn")
@commands.has_role(1174066821419257917)
async def removewarn(ctx, member: discord.Member, index: int):
    user_id = str(member.id)
    if user_id not in warns or len(warns[user_id]) == 0:
        embed = discord.Embed(title="No Warnings", description=f"{member.mention} has no warnings.", color=discord.Color.green())
        await ctx.send(embed=embed)
        return

    if index < 1 or index > len(warns[user_id]):
        await ctx.send("Invalid warning index.")
        return

    removed_warning = warns[user_id].pop(index - 1)

    if len(warns[user_id]) == 0:
        del warns[user_id]

    save_warns()

    embed = discord.Embed(title="Warning Removed", color=discord.Color.green())
    embed.add_field(name="User", value=member.mention, inline=True)
    embed.add_field(name="Moderator", value=ctx.author.mention, inline=True)
    embed.add_field(name="Removed Warning", value=f"**Reason:** {removed_warning['reason']}\n**Moderator:** {removed_warning['moderator']}", inline=False)

    await ctx.send(embed=embed)
    await ctx.message.delete()

# clear warns
@client.command(name="clearwarns", help='clears all warnings of a member. Usage: !clearwarns @member')
@commands.has_role(1174066821419257917)
async def clearwarns(ctx, member: discord.Member):
    user_id = str(member.id)
    if user_id in warns:
        del warns[user_id]
        save_warns()

        embed = discord.Embed(title="All Warnings Cleared", description=f"All warnings cleared for {member.mention}.", color=discord.Color.green())
        await ctx.send(embed=embed)
    else:
        embed = discord.Embed(title="No Warnings", description=f"{member.mention} has no warnings.", color=discord.Color.green())
        await ctx.send(embed=embed)

# error handling for all warn commands
@clearwarns.error
@removewarn.error
@warnlist.error
@warn.error
async def warns_error(ctx, error):
    if isinstance(error, commands.MissingPermissions):
        await ctx.send("You do not have permission to run this command.")
    elif isinstance(error, commands.MissingRequiredArgument):
        await ctx.send("Please use the proper format.")
    if isinstance(error, commands.BadArgument):
        await ctx.send("Invalid argument. Please check your input and try again.")
    else:
        await ctx.send(f"An error occurred: {error}")

# steal checker
# Background task to reset shiny hunt tracking
@tasks.loop(seconds=1)
async def check_shiny_hunt():
    global shiny_hunt_message, shiny_hunt_start_time, shiny_hunt_user_id, timer_embed

    if shiny_hunt_start_time:
        elapsed_time = (datetime.now() - shiny_hunt_start_time).seconds
        if elapsed_time > 20:
            if timer_embed:
                embed = discord.Embed(title="Shiny Hunt", description="Timer ended. No shiny hunt steal detected.", color=discord.Color.red())
                await timer_embed.edit(embed=embed)
                timer_embed = None
            shiny_hunt_message = None
            shiny_hunt_start_time = None
            shiny_hunt_user_id = None
        else:
            remaining_time = 20 - elapsed_time
            if timer_embed:
                embed = discord.Embed(title="Shiny Hunt", description=f"Timer: {remaining_time} seconds remaining.", color=discord.Color.blue())
                await timer_embed.edit(embed=embed)

# main auto-warn code
'''@client.event
async def on_message(message):
    global shiny_hunt_message, shiny_hunt_start_time, shiny_hunt_user_id, timer_embed

    # Prevent bot from responding to its own messages
    if message.author == client.user:
        return

    if "Shiny Hunt Pings:" in message.content and message.author.id == 874910942490677270:
        shiny_hunt_message = message
        shiny_hunt_start_time = datetime.now()
        shiny_hunt_user_id = message.author.id

        embed = discord.Embed(title="Shiny Hunt", description="Timer started for 20 seconds. Waiting for 'Congratulations' message...", color=discord.Color.blue())
        timer_embed = await message.channel.send(embed=embed)

    if shiny_hunt_start_time and (datetime.now() - shiny_hunt_start_time).seconds <= 20:
        if "Congratulations" in message.content:
            if "chain" in message.content:
                if message.channel.id == 1203415260434792518:  
                    if timer_embed:
                        embed = discord.Embed(title="Shiny Hunt", description="Caught by shiny hunter.", color=discord.Color.green())
                        await timer_embed.edit(embed=embed)
                        shiny_hunt_message = None
                        shiny_hunt_start_time = None
                        shiny_hunt_user_id = None
                        timer_embed = None
            else:
                mentioned_user = message.mentions[0] if message.mentions else None
                if message.channel.id == 1203415260434792518:  
                    if mentioned_user:
                        user_id = str(mentioned_user.id)
                        if user_id not in warns:
                            warns[user_id] = []

                        warns[user_id].append({"reason": "Shiny hunt steal", "moderator": str(client.user)})

                        save_warns()
                        
                        embed = discord.Embed(title="Shiny Hunt Steal Detected", color=discord.Color.red())
                        embed.add_field(name="User", value=mentioned_user.mention, inline=True)
                        embed.add_field(name="Reason", value="Shiny hunt steal", inline=False)

                        await message.channel.send(embed=embed)
                        guild=mentioned_user.guild
                        embed = discord.Embed(title='Warning', description=f'You have been warned in {guild.name} for the reason: ||Shiny hunt steal||', color=0xff0000)
                        embed.set_thumbnail(url=guild.icon.url)
                        await mentioned_user.send(embed=embed)

                        if timer_embed:
                            embed = discord.Embed(title="Shiny Hunt", description="Shiny hunt steal detected.", color=discord.Color.red())
                            await timer_embed.edit(embed=embed)
                            shiny_hunt_message = None
                            shiny_hunt_start_time = None
                            shiny_hunt_user_id = None
                            timer_embed = None
    await client.process_commands(message)'''


# say
@client.command(name='say', help='Repeats what you say. Usage: !say #channel <message>')
@commands.has_permissions(administrator=True)
async def say(ctx, channel: discord.TextChannel, *, message: str):
    try:
        # Bot sends the message to the specified channel
        await channel.send(message)
        # await ctx.send(f'Message sent to {channel.mention}.')
        await ctx.message.delete()
    except discord.Forbidden:
        await ctx.send("I do not have permission to send messages to the specified channel.")
    except discord.HTTPException as e:
        await ctx.send(f"An error occurred while trying to send the message: {e}")
    except Exception as e:
        await ctx.send(f"An unexpected error occurred: {e}")

# error handling for say
@say.error
async def say_error(ctx, error):
    if isinstance(error, commands.MissingPermissions):
        await ctx.send("You do not have permission to use the !say command.")
    elif isinstance(error, commands.MissingRequiredArgument):
        await ctx.send("Please specify a message to say.")
    elif isinstance(error, commands.BadArgument):
        await ctx.send("Invalid channel. Please mention a valid channel.")
    else:
        await ctx.send(f"An error occurred: {error}")

# add roles
@client.command(name='addrole', help='Add a role to a member. Usage: !addrole @member role')
@commands.has_permissions(manage_roles=True)
async def addrole(ctx, member: discord.Member, role: discord.Role):
    try:
        if ctx.author.top_role <= role:
            await ctx.send("You cannot assign a role higher than or equal to your highest role.")
            return
        
        if role in member.roles:
            await ctx.send(f'{member.mention} already has the role, {role}.')

        else:
            await member.add_roles(role)
            await ctx.send(f'Successfully added {role.mention} to {member.mention}.')

    except discord.Forbidden:
        await ctx.send("I do not have permission to manage roles.")
    except discord.HTTPException as e:
        await ctx.send(f"An error occurred while trying to add the role: {e}")
    except Exception as e:
        await ctx.send(f"An unexpected error occurred: {e}")

# error handling for add roles
@addrole.error
async def addrole_error(ctx, error):
    if isinstance(error, commands.MissingPermissions):
        await ctx.send("You do not have permission to manage roles.")
    elif isinstance(error, commands.MissingRequiredArgument):
        await ctx.send("Please mention a member and a role. Usage: !addrole @member role")
    elif isinstance(error, commands.BadArgument):
        await ctx.send("Invalid member or role. Please mention a valid member and role.")
    else:
        await ctx.send(f"An error occurred: {error}")


# remove roles
@client.command(name='removerole', help='Remove a role from a member. Usage: !removerole @member role')
@commands.has_permissions(manage_roles=True)
async def removerole(ctx, member: discord.Member, role: discord.Role):
    try:
        if ctx.author.top_role <= role:
            await ctx.send("You cannot remove a role higher than or equal to your highest role.")
            return

        if role not in member.roles:
            await ctx.send(f"{member.mention} doesn't have the role, {role}.")

        else:
            await member.remove_roles(role)
            await ctx.send(f'Successfully removed {role.mention} from {member.mention}.')

    except discord.Forbidden:
        await ctx.send("I do not have permission to manage roles.")
    except discord.HTTPException as e:
        await ctx.send(f"An error occurred while trying to remove the role: {e}")
    except Exception as e:
        await ctx.send(f"An unexpected error occurred: {e}")

# error handling for remove roles
@removerole.error
async def removerole_error(ctx, error):
    if isinstance(error, commands.MissingPermissions):
        await ctx.send("You do not have permission to manage roles.")
    elif isinstance(error, commands.MissingRequiredArgument):
        await ctx.send("Please mention a member and a role. Usage: !removerole @member role")
    elif isinstance(error, commands.BadArgument):
        await ctx.send("Invalid member or role. Please mention a valid member and role.")
    else:
        await ctx.send(f"An error occurred: {error}")

# temp roles
@client.command(name='temprole', help='Give a member a temporary role. Usage: !temprole @member [duration] [role_name]')
@commands.has_permissions(manage_roles=True)
async def temprole(ctx, member: discord.Member, duration_str: str, *, role_name: str):
    role = discord.utils.get(ctx.guild.roles, name=role_name)
    
    if not role:
        await ctx.send(f"Role `{role_name}` not found.")
        return

    duration_seconds = parse_time(duration_str.lower())
    if duration_seconds is None:
        await ctx.send("Invalid duration format. Use numbers followed by 'd', 'h', 'm', 's'.")
        return
    
    await member.add_roles(role)
    await ctx.send(f"{member.mention} has been given the role `{role_name}` for {duration_str}.")

    # Schedule task to remove the role after duration
    await asyncio.sleep(duration_seconds)
    await member.remove_roles(role)
    await ctx.send(f"Temporary role `{role_name}` has been removed from {member.mention}.")

@temprole.error
async def temprole_error(ctx, error):
    if isinstance(error, commands.MissingPermissions):
        await ctx.send("You do not have the required permissions to run this command.")
    elif isinstance(error, commands.BadArgument):
        await ctx.send("Invalid argument. Please mention a valid member, duration, and role name.")
    elif isinstance(error, commands.MissingRequiredArgument):
        await ctx.send("Missing argument. Please mention a member, duration, and role name.")
    else:
        await ctx.send(f"An error occurred: {error}")

# snipe
@client.event
async def on_message_delete(message):
    # Store the last deleted message for each channel
    deleted_messages[message.channel.id] = message

# Define the 'snipe' command
@client.command(name='snipe', help='Retrieve the most recently deleted message in this channel.')
async def snipe(ctx):
    try:
        # Get the last deleted message in the current channel
        msg = deleted_messages.get(ctx.channel.id)
        
        if msg:
            embed = discord.Embed(description=msg.content, color=discord.Color.red())
            embed.set_author(name=msg.author.display_name, icon_url=msg.author.avatar.url)
            embed.set_footer(text=f"Deleted in #{msg.channel.name}")

            await ctx.send(embed=embed)
        else:
            await ctx.send("There's no recently deleted message in this channel.")

    except Exception as e:
        await ctx.send(f"An unexpected error occurred: {e}")

# purge
@client.command(name='purge', help='Delete a specified number of messages from the channel. Usage: !purge [number]')
@commands.has_permissions(manage_messages=True)
async def purge(ctx, number: int):
    try:
        # Limit the number of messages to purge to a maximum of 100
        if number < 1 or number > 100:
            await ctx.send("Please specify a number between 1 and 100.")
            return

        # Purge the specified number of messages
        deleted = await ctx.channel.purge(limit=number + 1)
        await ctx.send(f'Successfully deleted {len(deleted) - 1} messages.', delete_after=5)

    except discord.Forbidden:
        await ctx.send("I do not have permission to manage messages.")
    except discord.HTTPException as e:
        await ctx.send(f"An error occurred while trying to delete messages: {e}")
    except Exception as e:
        await ctx.send(f"An unexpected error occurred: {e}")

# error handling for purge
@purge.error
async def purge_error(ctx, error):
    if isinstance(error, commands.MissingPermissions):
        await ctx.send("You do not have permission to manage messages.")
    elif isinstance(error, commands.MissingRequiredArgument):
        await ctx.send("Please specify the number of messages to delete. Usage: !purge [number]")
    elif isinstance(error, commands.BadArgument):
        await ctx.send("Invalid number. Please specify an integer.")
    else:
        await ctx.send(f"An error occurred: {error}")

# waifu
@client.command(name='waifu', help='sends a random waifu image.  Usage: !waifu')
#@commands.has_role('18+')
@in_channel(DESIGNATED_CHANNEL_ID)
async def waifu(ctx):
    # Fetch a waifu image from the API
    response = requests.get('https://api.waifu.pics/sfw/waifu')
    data = response.json()
    image_url = data['url']
    
    # Create an embed
    embed = discord.Embed(
        title="Here is your waifu!",
        color=discord.Color.blue()  # You can choose any color you like
    )
    embed.set_image(url=image_url)
    embed.set_author(
        name=ctx.author.display_name,  # Author name
        icon_url=ctx.author.avatar.url  # Author's avatar as the icon
    )
    
    # Send the embed in the current context
    await ctx.send(embed=embed)

# waifu error handling
@waifu.error
async def waifu_error(ctx, error):
    if isinstance(error, commands.MissingRole):
        await ctx.send("you don't have the '18+' role to access this.")

# neko
@client.command(name='neko', help='sends a neko image. Usage: !neko')
#@commands.has_role('18+')
@in_channel(DESIGNATED_CHANNEL_ID)
async def neko(ctx):
    # Fetch a neko image from the API
    response = requests.get('https://api.waifu.pics/sfw/neko')
    data = response.json()
    image_url = data['url']
    
    # Create an embed
    embed = discord.Embed(
        title="Here is your neko!",
        color=discord.Color.purple()  # You can choose any color you like
    )
    embed.set_image(url=image_url)
    embed.set_author(
        name=ctx.author.display_name,  # Author name
        icon_url=ctx.author.avatar.url  # Author's avatar as the icon
    )
    
    # Send the embed in the current context
    await ctx.send(embed=embed)

# neko error handling
@neko.error
async def neko_error(ctx, error):
    if isinstance(error, commands.MissingRole):
        await ctx.send("you don't have the '18+' role to access this.")

@client.command(name='kill', help='sends a kill gif. Usage: !kill @member')
async def kill(ctx, member: discord.Member = None):
    # Fetch a bully image from the API
    response = requests.get('https://api.waifu.pics/sfw/kill')
    data = response.json()
    image_url = data['url']

    # Determine the title
    if member:
        title = f"{ctx.author.display_name} kills {member.display_name}"
    else:
        title = f"{ctx.author.display_name} is killing someone!"

    # Create an embed
    embed = discord.Embed(
        title=title,
        color=discord.Color.red()  # You can choose any color you like
    )
    embed.set_image(url=image_url)
    
    
    # Send the embed in the current context
    await ctx.send(embed=embed)

# Command to lock the channel
@client.command(name='lock', help='Lock the channel to prevent @everyone from sending messages.')
@commands.has_permissions(manage_channels=True)
async def lock(ctx):
    try:
        # Get the @everyone role
        role = ctx.guild.default_role
        # Deny the send_messages permission
        await ctx.channel.set_permissions(role, send_messages=False)
        await ctx.send(f'{ctx.channel.mention} has been locked.')

    except discord.Forbidden:
        await ctx.send("I do not have permission to manage channel permissions.")
    except discord.HTTPException as e:
        await ctx.send(f"An error occurred while trying to lock the channel: {e}")
    except Exception as e:
        await ctx.send(f"An unexpected error occurred: {e}")

# Command to unlock the channel
@client.command(name='unlock', help='Unlock the channel to allow @everyone to send messages.')
@commands.has_permissions(manage_channels=True)
async def unlock(ctx):
    try:
        # Get the @everyone role
        role = ctx.guild.default_role
        # Allow the send_messages permission
        await ctx.channel.set_permissions(role, send_messages=True)
        await ctx.send(f'{ctx.channel.mention} has been unlocked.')

    except discord.Forbidden:
        await ctx.send("I do not have permission to manage channel permissions.")
    except discord.HTTPException as e:
        await ctx.send(f"An error occurred while trying to unlock the channel: {e}")
    except Exception as e:
        await ctx.send(f"An unexpected error occurred: {e}")

# Command to hide the channel
@client.command(name='hide', help='Hide the channel from @everyone.')
@commands.has_permissions(manage_channels=True)
async def hide(ctx):
    try:
        # Get the @everyone role
        role = ctx.guild.default_role
        # Deny the view_channel permission
        await ctx.channel.set_permissions(role, view_channel=False)
        await ctx.send(f'{ctx.channel.mention} has been hidden.')

    except discord.Forbidden:
        await ctx.send("I do not have permission to manage channel permissions.")
    except discord.HTTPException as e:
        await ctx.send(f"An error occurred while trying to hide the channel: {e}")
    except Exception as e:
        await ctx.send(f"An unexpected error occurred: {e}")

# Command to unhide the channel
@client.command(name='unhide', help='Unhide the channel to allow @everyone to view it.')
@commands.has_permissions(manage_channels=True)
async def unhide(ctx):
    try:
        # Get the @everyone role
        role = ctx.guild.default_role
        # Allow the view_channel permission
        await ctx.channel.set_permissions(role, view_channel=True)
        await ctx.send(f'{ctx.channel.mention} has been unhidden.')

    except discord.Forbidden:
        await ctx.send("I do not have permission to manage channel permissions.")
    except discord.HTTPException as e:
        await ctx.send(f"An error occurred while trying to unhide the channel: {e}")
    except Exception as e:
        await ctx.send(f"An unexpected error occurred: {e}")



# Command to start building an embed
@client.command(name='startembed', help='Start building an embed.')
async def startembed(ctx):
    embed_data[ctx.author.id] = {
        'title': '', 
        'description': '', 
        'color': None, 
        'fields': [], 
        'footer': '', 
        'thumbnail': '', 
        'image': ''
    }
    await ctx.send("Embed building started. Use `!settitle`, `!setdesc`, `!setcolor`, `!addfield`, `!setfooter`, `!setthumbnail`, and `!setbanner` to customize your embed. Use `!showembed` to preview and `!sendembed` to send.")

# Command to set the title of the embed
@client.command(name='settitle', help='Set the title of the embed. Usage: !settitle Your Title')
async def settitle(ctx, *, title):
    if ctx.author.id not in embed_data:
        await ctx.send("You haven't started building an embed yet. Use `!startembed` to start.")
        return
    embed_data[ctx.author.id]['title'] = title
    await ctx.send(f"Title set to: {title}")

# Command to set the description of the embed
@client.command(name='setdesc', help='Set the description of the embed. Usage: !setdescription Your description')
async def setdesc(ctx, *, description):
    if ctx.author.id not in embed_data:
        await ctx.send("You haven't started building an embed yet. Use `!startembed` to start.")
        return
    embed_data[ctx.author.id]['description'] = description
    await ctx.send(f"Description set to: {description}")

# Command to set the color of the embed
@client.command(name='setcolor', help='Set the color of the embed. Usage: !setcolor 0xRRGGBB')
async def setcolor(ctx, color: discord.Color):
    if ctx.author.id not in embed_data:
        await ctx.send("You haven't started building an embed yet. Use `!startembed` to start.")
        return
    embed_data[ctx.author.id]['color'] = color
    await ctx.send(f"Color set.")

# Command to add a field to the embed
@client.command(name='addfield', help='Add a field to the embed. Usage: !addfield Title Description')
async def addfield(ctx, title, *, description):
    if ctx.author.id not in embed_data:
        await ctx.send("You haven't started building an embed yet. Use `!startembed` to start.")
        return
    embed_data[ctx.author.id]['fields'].append({'name': title, 'value': description})
    await ctx.send(f"Field added: {title} - {description}")

# Command to set the footer of the embed
@client.command(name='setfooter', help='Set the footer of the embed. Usage: !setfooter Your footer')
async def setfooter(ctx, *, footer):
    if ctx.author.id not in embed_data:
        await ctx.send("You haven't started building an embed yet. Use `!startembed` to start.")
        return
    embed_data[ctx.author.id]['footer'] = footer
    await ctx.send(f"Footer set to: {footer}")

# Command to set the thumbnail of the embed
@client.command(name='setthumbnail', help='Set the thumbnail of the embed. Usage: !setthumbnail URL')
async def setthumbnail(ctx, url: str):
    if ctx.author.id not in embed_data:
        await ctx.send("You haven't started building an embed yet. Use `!startembed` to start.")
        return
    embed_data[ctx.author.id]['thumbnail'] = url
    await ctx.send(f"Thumbnail set to: {url}")

# Command to set the banner (image) of the embed
@client.command(name='setbanner', help='Set the banner (image) of the embed. Usage: !setbanner URL')
async def setbanner(ctx, url: str):
    if ctx.author.id not in embed_data:
        await ctx.send("You haven't started building an embed yet. Use `!startembed` to start.")
        return
    embed_data[ctx.author.id]['image'] = url
    await ctx.send(f"Banner set to: {url}")

# Command to preview the embed
@client.command(name='showembed', help='Show the current state of your embed.')
async def showembed(ctx):
    if ctx.author.id not in embed_data:
        await ctx.send("You haven't started building an embed yet. Use `!startembed` to start.")
        return
    
    data = embed_data[ctx.author.id]
    embed = discord.Embed(
        title=data['title'], 
        description=data['description'], 
        color=data['color']
    )

    for field in data['fields']:
        embed.add_field(name=field['name'], value=field['value'], inline=False)

    if data['footer']:
        embed.set_footer(text=data['footer'])
    if data['thumbnail']:
        embed.set_thumbnail(url=data['thumbnail'])
    if data['image']:
        embed.set_image(url=data['image'])

    await ctx.send(embed=embed)

# Command to send the embed to a specific channel
@client.command(name='sendembed', help='Send the embed to a specific channel. Usage: !sendembed #channel')
async def sendembed(ctx, channel: discord.TextChannel):
    if ctx.author.id not in embed_data:
        await ctx.send("You haven't started building an embed yet. Use `!startembed` to start.")
        return
    
    data = embed_data[ctx.author.id]
    embed = discord.Embed(
        title=data['title'], 
        description=data['description'], 
        color=data['color']
    )

    for field in data['fields']:
        embed.add_field(name=field['name'], value=field['value'], inline=False)

    if data['footer']:
        embed.set_footer(text=data['footer'])
    if data['thumbnail']:
        embed.set_thumbnail(url=data['thumbnail'])
    if data['image']:
        embed.set_image(url=data['image'])

    await channel.send(embed=embed)
    await ctx.send(f"Embed sent to {channel.mention}")
    del embed_data[ctx.author.id]  # Clear the stored data after sending

# Command to cancel the embed building process
@client.command(name='cancel', help='Cancel the embed building process.')
async def cancel(ctx):
    if ctx.author.id in embed_data:
        del embed_data[ctx.author.id]
        await ctx.send("Embed building process has been canceled.")
    else:
        await ctx.send("You haven't started building an embed yet. Use `!startembed` to start.")

@startembed.error
@settitle.error
@setdesc.error
@setcolor.error
@addfield.error
@setfooter.error
@setthumbnail.error
@setbanner.error
@showembed.error
@sendembed.error
@cancel.error
async def embed_error(ctx, error):
    if isinstance(error, commands.BadArgument):
        await ctx.send("Invalid argument. Please check your input and try again.")
    elif isinstance(error, commands.MissingRequiredArgument):
        await ctx.send("Missing argument. Please provide all required arguments.")
    else:
        await ctx.send(f"An error occurred: {error}")


@client.command(name='mute', help='Timeout a member for a specified duration. Usage: !mute @member 1d2h3m4s')
@has_permissions(manage_roles=True)
async def mute(ctx, member: discord.Member, duration: str):
    try:
        time_seconds = parse_time(duration)
        if time_seconds <= 0:
            await ctx.send('Please provide a valid duration.')
            return

        await member.edit(timed_out_until=discord.utils.utcnow() + timedelta(seconds=time_seconds))
        await ctx.send(f'{member.mention} has been timed out for {duration}.')

        await asyncio.sleep(time_seconds)
        await member.edit(timed_out_until=None)
        await ctx.send(f'{member.mention} has been removed from timeout.')

    except discord.Forbidden:
        await ctx.send('I do not have permission to timeout this member.')
    except discord.HTTPException:
        await ctx.send('An error occurred while trying to timeout this member.')

@client.command(name='unmute', help='Remove timeout from a member. Usage: !unmute @member')
@has_permissions(manage_roles=True)
async def unmute(ctx, member: discord.Member):
    try:
        await member.edit(timed_out_until=None)
        await ctx.send(f'{member.mention} has been removed from timeout.')
    except discord.Forbidden:
        await ctx.send('I do not have permission to untimeout this member.')
    except discord.HTTPException:
        await ctx.send('An error occurred while trying to untimeout this member.')

@mute.error
async def mute_error(ctx, error):
    if isinstance(error, commands.MissingPermissions):
        await ctx.send('You do not have permission to use this command.')
    elif isinstance(error, commands.BadArgument):
        await ctx.send('Could not find that member.')
    elif isinstance(error, commands.MissingRequiredArgument):
        await ctx.send('Please specify a member and a duration.')

@unmute.error
async def unmute_error(ctx, error):
    if isinstance(error, commands.MissingPermissions):
        await ctx.send('You do not have permission to use this command.')
    elif isinstance(error, commands.BadArgument):
        await ctx.send('Could not find that member.')
    elif isinstance(error, commands.MissingRequiredArgument):
        await ctx.send('Please specify a member.')

# Command to parse human-readable time strings into seconds
def parse_time(time_str):
    time_str = time_str.lower()
    unit_multipliers = {
        'd': 86400,  # days to seconds
        'h': 3600,   # hours to seconds
        'm': 60,     # minutes to seconds
        's': 1       # seconds to seconds
    }
    total_seconds = 0
    number = ''
    for char in time_str:
        if char.isdigit():
            number += char
        elif char in unit_multipliers:
            total_seconds += int(number) * unit_multipliers[char]
            number = ''
    return total_seconds

@client.event
async def on_message_edit(before, after):
    if before.author.bot:  # Ignore edits made by bots
        return

    channel_id = before.channel.id

    if channel_id not in edited_messages:
        edited_messages[channel_id] = []

    edited_messages[channel_id].append((before, after))

@client.command(name='editsnipe', help='Retrieve the most recent edited message in the channel.')
async def editsnipe(ctx):
    channel_id = ctx.channel.id
    if channel_id not in edited_messages or not edited_messages[channel_id]:
        await ctx.send("No recently edited messages found in this channel.")
        return

    messages = edited_messages[channel_id]
    total_pages = len(messages)
    current_page = total_pages - 1  # Start with the most recent message

    class Paginator(View):
        def __init__(self, initial_page=0):
            super().__init__(timeout=None)  # Ensure the view doesn't timeout
            self.current_page = initial_page
            self.total_pages = total_pages
            self.update_buttons()

        def update_buttons(self):
            self.previous.disabled = self.current_page == 0
            self.next.disabled = self.current_page == self.total_pages - 1

        async def update_embed(self, interaction: discord.Interaction):
            before, after = messages[self.current_page]
            embed = discord.Embed(title="Message Edit Snipe", color=discord.Color.blurple())
            embed.add_field(name="Before Edit", value=before.content or "No content", inline=False)
            embed.add_field(name="After Edit", value=after.content or "No content", inline=False)
            embed.set_author(name=before.author.display_name, icon_url=before.author.avatar.url)
            embed.set_footer(text=f"Page {self.current_page + 1}/{self.total_pages} | Edited in #{before.channel.name}")
            self.update_buttons()
            await interaction.response.edit_message(embed=embed, view=self)

        @discord.ui.button(label="Previous", style=discord.ButtonStyle.primary)
        async def previous(self, interaction: discord.Interaction, button: Button):
            if self.current_page > 0:
                self.current_page -= 1
                await self.update_embed(interaction)

        @discord.ui.button(label="Next", style=discord.ButtonStyle.primary)
        async def next(self, interaction: discord.Interaction, button: Button):
            if self.current_page < self.total_pages - 1:
                self.current_page += 1
                await self.update_embed(interaction)

    paginator = Paginator(initial_page=current_page)

    before, after = messages[current_page]
    embed = discord.Embed(title="Message Edit Snipe", color=discord.Color.blurple())
    embed.add_field(name="Before Edit", value=before.content or "No content", inline=False)
    embed.add_field(name="After Edit", value=after.content or "No content", inline=False)
    embed.set_author(name=before.author.display_name, icon_url=before.author.avatar.url)
    embed.set_footer(text=f"Page {current_page + 1}/{total_pages} | Edited in #{before.channel.name}")

    await ctx.send(embed=embed, view=paginator)

@editsnipe.error
async def editsnipe_error(ctx, error):
    if isinstance(error, commands.CommandError):
        await ctx.send("An error occurred while executing the command.")

client.run('MTI1Mjg2NTkxMDQzMjA3NTg1Nw.GlV10q.SkPVfFr7mqOUl5B3pye9uOH1aTQu2exx8DjIDI')