import datetime
import asyncio
import traceback
import json

import discord
from discord.ext import commands
from discord.utils import get
import sqlite3
from textblob import TextBlob

with open('settings.json') as settings_file:
    settings = json.load(settings_file)

sql = sqlite3.connect('sql.db')
print('Loaded SQL Database')
cur = sql.cursor()
cur.execute('CREATE TABLE IF NOT EXISTS users(id INTEGER, positive INTEGER, neutral INTEGER, negative INTEGER)')
print('Loaded Users')
sql.commit()

username = settings["discord"]["description"]
version = settings["discord"]["version"]
start_time = datetime.datetime.utcnow()
client = commands.Bot(
    command_prefix=settings["discord"]["command_prefix"],
    description=settings["discord"]["description"])

print('{} - {}'.format(username, version))


@client.command(pass_context=True, name="ping")
async def bot_ping(ctx):
    pong_message = await ctx.message.channel.send("Pong!")
    await asyncio.sleep(0.5)
    delta = pong_message.created_at - ctx.message.created_at
    millis = delta.days * 24 * 60 * 60 * 1000
    millis += delta.seconds * 1000
    millis += delta.microseconds / 1000
    await pong_message.edit(content="Pong! `{}ms`".format(int(millis)))


@client.event
async def on_command_error(error, ctx):
    if isinstance(error, commands.errors.CommandNotFound):
        pass  # ...don't need to know if commands don't exist
    if isinstance(error, commands.errors.CheckFailure):
        await ctx.message.channel.send(
            ctx.message.channel,
            '{} You don''t have permission to use this command.' \
            .format(ctx.message.author.mention))
    elif isinstance(error, commands.errors.CommandOnCooldown):
        try:
            await ctx.message.delete()
        except discord.errors.NotFound:
            pass
        await ctx.message.channel.send(
            ctx.message.channel, '{} This command was used {:.2f}s ago ' \
            'and is on cooldown. Try again in {:.2f}s.' \
            .format(ctx.message.author.mention,
                    error.cooldown.per - error.retry_after,
                    error.retry_after))
        await asyncio.sleep(10)
        await ctx.message.delete()
    else:
        await ctx.message.channel.send(
            'An error occured while processing the `{}` command.' \
            .format(ctx.command.name))
        print('Ignoring exception in command {0.command} ' \
            'in {0.message.channel}'.format(ctx))
        tb = traceback.format_exception(type(error), error, error.__traceback__)
        print(''.join(tb))


@client.event
async def on_error(event_method, *args, **kwargs):
    if isinstance(args[0], commands.errors.CommandNotFound):
        # For some reason runs despite the above
        return
    print('Ignoring exception in {}'.format(event_method))
    mods_msg = "Exception occured in {}".format(event_method)
    tb = traceback.format_exc()
    print(''.join(tb))
    mods_msg += '\n```' + ''.join(tb) + '\n```'
    mods_msg += '\nargs: `{}`\n\nkwargs: `{}`'.format(args, kwargs)
    print(mods_msg)
    print(args)
    print(kwargs)


@client.event
async def on_ready():
    await asyncio.sleep(1)
    print("Logged in to discord.")
    try:
        await client.change_presence(
            activity=discord.Game(name=settings["discord"]["game"]),
            status=discord.Status.online,
            afk=False)
    except Exception as e:
        print('on_ready : ', e)
        pass
    await asyncio.sleep(1)


@client.event
async def on_message(message):
    try:
        if message.author == client.user:
            return
        if not message.content.startswith(settings["discord"]["command_prefix"]):
            analysis = TextBlob(message.content)
            cur.execute('SELECT count(*) as user FROM users WHERE id=?', (message.author.id,))
            user = cur.fetchone()
            if int(user[0]) != 0:
                if analysis.sentiment.polarity > 0:
                    # log positive
                    cur.execute('UPDATE users SET positive = positive + 1 WHERE id=?', (message.author.id,))
                elif analysis.sentiment.polarity < 0:
                    # log negative
                    cur.execute('UPDATE users SET negative = negative + 1 WHERE id=?', (message.author.id,))
                else:
                    # log neutral
                    cur.execute('UPDATE users SET neutral = neutral + 1 WHERE id=?', (message.author.id,))
            else:
                if analysis.sentiment.polarity > 0:
                    # log positive
                    cur.execute('INSERT INTO users VALUES(?,1,0,0)', (message.author.id,))
                elif analysis.sentiment.polarity < 0:
                    # log negative
                    cur.execute('INSERT INTO users VALUES(?,0,0,1)', (message.author.id,))
                else:
                    # log neutral
                    cur.execute('INSERT INTO users VALUES(?,0,1,0)', (message.author.id,))
            sql.commit()
        await client.process_commands(message)
    except Exception as e:
        print('on_message : ', e)
        pass


@client.command(pass_context=True, name='leaders')
async def leaders(ctx):
    try:
        # say top X list of positive vibe users
        # select top X (positive + negative * -1) / total desc
        rank = 1
        lines = []
        cur.execute('SELECT id, ((CAST(positive AS FLOAT)+CAST(negative AS FLOAT)*-1.0)/(CAST(positive AS FLOAT)+CAST(neutral AS FLOAT)+CAST(negative AS FLOAT))) as score FROM users ORDER BY 2 DESC LIMIT 10')
        users = cur.fetchall()
        for row in users:
            user = get(client.get_all_members(), id=row[0])
            lines.append('{0}. {1} - {2}%'.format(rank, user, round(float(row[1]) * 100, 2)))
            rank+=1
            if rank > 10:
                break
        await ctx.send("\n".join(lines))
    except Exception as e:
        print('leaders : ', e)
        pass


@client.command(pass_context=True, name='losers')
async def losers(ctx):
    try:
        # say top X list of negative vibe users
        # select top X (positive + negative * -1) / total asc
        rank = 1
        lines = []
        cur.execute('SELECT id, ((CAST(positive AS FLOAT)+CAST(negative AS FLOAT)*-1.0)/(CAST(positive AS FLOAT)+CAST(neutral AS FLOAT)+CAST(negative AS FLOAT))) as score FROM users ORDER BY 2 ASC LIMIT 10')
        users = cur.fetchall()
        for row in users:
            user = get(client.get_all_members(), id=row[0])
            lines.append('{0}. {1} - {2}%'.format(rank, user, round(float(row[1]) * 100, 2)))
            rank+=1
            if rank > 10:
                break
        await ctx.send("\n".join(lines))
    except Exception as e:
        print('losers : ', e)
        pass


@client.command(pass_context=True, name='score')
async def score(ctx):
    try:
        print(ctx.message.author.id)
        cur.execute('SELECT id, ((CAST(positive AS FLOAT)+CAST(negative AS FLOAT)*-1.0)/(CAST(positive AS FLOAT)+CAST(neutral AS FLOAT)+CAST(negative AS FLOAT))) as score FROM users WHERE id=?', (ctx.message.author.id,))
        user = cur.fetchone()
        if not user is None:
            score = float(user[1])
            if score > 0.67:
                await ctx.send("{0.author.mention} Your score is {1}%.  Way to be positive!".format(ctx.message, round(float(score)*100,2)))
            elif score > 0.33:
                await ctx.send("{0.author.mention} Your score is {1}%.  I know you're trying your best to be positive!".format(ctx.message, round(float(score)*100,2)))
            elif score > 0:
                await ctx.send("{0.author.mention} Your score is {1}%.  Keep trying to be more positive!".format(ctx.message, round(float(score)*100,2)))
            elif score > -0.33:
                await ctx.send("{0.author.mention} Your score is {1}%.  I know things can be rough, try looking on the bright side!".format(ctx.message, round(float(score)*100,2)))
            elif score > -0.9:
                await ctx.send("{0.author.mention} Your score is {1}%.  Let's turn that frown upside-down!".format(ctx.message, round(float(score)*100,2)))
            elif score > -0.9:
                await ctx.send("{0.author.mention} Your score is {1}%.  I'm always here for you!".format(ctx.message, round(float(score)*100,2)))
            else:
                await ctx.send("{0.author.mention} Your score is {1}%.  Your negativity is dragging me down.".format(ctx.message, round(float(score)*100,2)))
    except Exception as e:
        print('score : ', e)
        pass

async def generate_reply(ctx, model):
    try:
        sentence = model.make_sentence(tries=100, retain_original=False)
        if sentence:
            await ctx.send('{0.author.mention} {1}'.format(ctx.message, sentence))
        else:
            await ctx.send('{0.author.mention} {1}'.format(ctx.message, '`Unable to build text chain`'))
    except Exception as e:
        print('generate_reply : ', e)
        pass


client.run(settings["discord"]["client_token"])
