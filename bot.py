import datetime
import asyncio
import traceback
import json
import re
from enum import Enum

import discord
from discord.ext import commands
from discord.utils import get
import sqlite3
from textblob import TextBlob
from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer
from twitter_scraper import get_tweets
import requests
from POSifiedText import POSifiedText

class ScoreboardTypes(Enum):
    leaders = 1
    losers = 2

with open('settings.json') as settings_file:
    settings = json.load(settings_file)

sql = sqlite3.connect('sql.db')
print('Loaded SQL Database')
cur = sql.cursor()
cur.execute('CREATE TABLE IF NOT EXISTS users(id INTEGER, score FLOAT, messages INTEGER, ignore BIT)')
print('Loaded Users')
sql.commit()

analyzer = SentimentIntensityAnalyzer()

username = settings["discord"]["description"]
version = settings["discord"]["version"]
command_prefix = settings["discord"]["command_prefix"]
message_history = int(settings["discord"]["message_history"])
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
    # =(running score * (100 - comment count) / 100) + (message score * comment count / 100)
    try:
        message_score = 0
        if message.author == client.user or message.author.bot:
            return
        if not message.content.startswith(command_prefix):
            cur.execute('SELECT count(*), score, messages, ignore from users where id=?', (message.author.id,))
            user = cur.fetchone()
            if int(user[0]) != 0 and int(user[3]) != 0:
                return
            # analysis = TextBlob(message.content)
            sentiment_dictionary = analyzer.polarity_scores(message.content)
            message_score = float(sentiment_dictionary['compound'])
            if "hell yeah brother" in message.content.lower():
                message_score = 1
            # elif (analysis.sentiment.polarity != 0):
            #     message_score = 0.5 + analysis.sentiment.polarity * 0.5
            elif (message_score != 0):
                message_score = 0.5 + message_score * 0.5
            else:
                return
            if int(user[0]) != 0:
                running_score = float(user[1])
                messages = min(int(user[2]) + 1,  message_history)
                new_score = (running_score * ((messages - 1) / messages)) + (message_score / messages)
                cur.execute('UPDATE users SET score = ?, messages = ? WHERE id=?', (new_score, min(messages, message_history), message.author.id))
            else:
                cur.execute('INSERT INTO users VALUES(?,?,1,0)', (message.author.id, message_score))
            sql.commit()
            cur.execute('VACUUM')
        await client.process_commands(message)
    except Exception as e:
        print('on_message : ', e)
        pass


@client.command(pass_context=True, name='check')
async def check(ctx):
    try:
        if ctx.message.author == client.user or ctx.message.author.bot:
            return
        text = str(ctx.message.content).replace(command_prefix + 'check', '').strip()
        sentiment_dict = analyzer.polarity_scores(ctx.message.content)
        message_score = sentiment_dict['compound']
        message_score = 0.5 + message_score * 0.5
        # analysis = TextBlob(text)
        # message_score = 0.5 + analysis.sentiment.polarity * 0.5
        if "hell yeah brother" in ctx.message.content.lower():
            await ctx.send("Hell yeah brother")
        elif message_score > 0.67:
            await ctx.send("{0.author.mention} Your statement has a polarity of {1}%.  I love it!".format(ctx.message, round(float(message_score)*100,2)))
        elif message_score < 0.33:
            await ctx.send("{0.author.mention} Your statement has a polarity of {1}%.  You should probably keep that to yourself.".format(ctx.message, round(float(message_score)*100,2)))
        else:
            await ctx.send("{0.author.mention} Your statement has a polarity of {1}%.  Very neutral".format(ctx.message, round(float(message_score)*100,2)))
    except Exception as e:
        print('on_message : ', e)
        pass


@client.command(pass_context=True, name='markov')
async def markov(ctx):
    if ctx.message.author == client.user or ctx.message.author.bot:
        return
    argument = ctx.message.content.split(' ', 2)[1]
    url = 'https://www.reddit.com/user/{0}/comments/.json?limit=100&sort=new'.format(argument)
    headers = {'User-agent': '{} - {}'.format(username, version)}
    r = requests.get(url, headers=headers)
    raw = r.json()
    try:
        if str(raw['message']).lower() == "not found":
            await ctx.send('{0.author.mention} {1}'.format(ctx.message, 'User not found.'))
            return
    except:
        pass
    corpus = []
    for item in raw['data']['children']:
        try:
            corpus.append('. '.join(re.split(r'\s*\n\s*', str(item['data']['body']))))
        except:
            pass
    text_model = POSifiedText(corpus)
    reply = ''
    sentence = text_model.make_sentence(tries=100)
    if sentence:
        reply = '{0.author.mention} {1}'.format(ctx.message, sentence)
        await ctx.send(reply)
    else:
        await ctx.send('{0.author.mention} {1}'.format(ctx.message, 'Unable to build text chain.'))
    await asyncio.sleep(2)


@client.command(pass_context=True, name='twmarkov')
async def twmarkov(ctx):
    if ctx.message.author == client.user or ctx.message.author.bot:
        return
    argument = ctx.message.content.split(' ', 2)[1]
    print(argument)
    corpus = [t['text'] for t in get_tweets(argument, pages=2)]
    print(corpus)
    await asyncio.sleep(1)
    text_model = POSifiedText('\n'.join(corpus))
    await asyncio.sleep(1)
    sentence = text_model.make_sentence(tries=100)
    await asyncio.sleep(1)
    if sentence:
        await ctx.send('{0.author.mention} {1}'.format(ctx.message, sentence))
    else:
        await ctx.send('{0.author.mention} {1}'.format(ctx.message, 'Unable to build text chain.'))


@client.command(pass_context=True, name='leaders')
async def leaders(ctx):
    try:
        await scoreboard(ctx, ScoreboardTypes.leaders)
    except Exception as e:
        print('leaders : ', e)
        pass


@client.command(pass_context=True, name='losers')
async def losers(ctx):
    try:
        await scoreboard(ctx, ScoreboardTypes.losers)
    except Exception as e:
        print('losers : ', e)
        pass


async def scoreboard(ctx, scoreboardType):
    try:
        if ctx.message.author == client.user or ctx.message.author.bot:
            return
        rank = 1
        lines = []
        if scoreboardType == ScoreboardTypes.leaders:
            cur.execute('SELECT id, score FROM users WHERE messages >= 50 AND ignore = 0 ORDER BY 2 DESC LIMIT 10;')
        elif scoreboardType == ScoreboardTypes.losers:
            cur.execute('SELECT id, score FROM users WHERE messages >= 50 AND ignore = 0 ORDER BY 2 ASC LIMIT 10;')
        else:
            return
        users = cur.fetchall()
        embed = discord.Embed(title='Leaderboard', type='rich', colour=0x77B255)
        for row in users:
            # user = get(client.get_all_members(), id=row[0])
            user = await client.fetch_user(row[0])
            # print(user)
            if user is None:
                # print('continue')
                continue
            score = round(float(row[1]) * 100, 2)
            lines.append('**{0}. {1} - {2}**'.format(rank, user.name, score))
            # print('**{0}. {1} - {2}**'.format(rank, user.display_name, score))
            rank+=1
            # if rank > 10:
            #     break
        embed.add_field(name='Players', value="\n".join(lines))
        embed.set_footer(text='*Minimum 50 scored comments to be ranked.*')
        await ctx.send(embed=embed)
    except Exception as e:
        print('scoreboard : ', e)
        pass


@client.command(pass_context=True, name='score')
async def score(ctx):
    try:
        if ctx.message.author == client.user or ctx.message.author.bot:
            return
        cur.execute('SELECT count(*), score, ignore FROM users WHERE id=?', (ctx.message.author.id,))
        user = cur.fetchone()
        if int(user[0]) != 0:
            if int(user[2]) != 0:
                await ctx.send("You opted out, I'm not tracking your positivity.")
                return
            score = float(user[1])
            if score > 0.9:
                await ctx.send("{0.author.mention} Your score is {1}%.  Way to be positive!".format(ctx.message, round(float(score)*100,2)))
            elif score > 0.75:
                await ctx.send("{0.author.mention} Your score is {1}%.  I know you're trying your best to be positive!".format(ctx.message, round(float(score)*100,2)))
            elif score >= 0.5:
                await ctx.send("{0.author.mention} Your score is {1}%.  Keep trying to be more positive!".format(ctx.message, round(float(score)*100,2)))
            elif score > 0.4:
                await ctx.send("{0.author.mention} Your score is {1}%.  I know things can be rough, try looking on the bright side!".format(ctx.message, round(float(score)*100,2)))
            elif score > 0.25:
                await ctx.send("{0.author.mention} Your score is {1}%.  Let's turn that frown upside-down!".format(ctx.message, round(float(score)*100,2)))
            elif score > 0.1:
                await ctx.send("{0.author.mention} Your score is {1}%.  I'm always here for you!".format(ctx.message, round(float(score)*100,2)))
            else:
                await ctx.send("{0.author.mention} Your score is {1}%.  Your negativity is dragging me down.".format(ctx.message, round(float(score)*100,2)))
        return
    except Exception as e:
        print('score : ', e)
        pass


@client.command(pass_context=True, name='optin')
async def opt_in(ctx):
    try:
        if ctx.message.author == client.user or ctx.message.author.bot:
            return
        cur.execute('SELECT count(*), ignore from users where id=?', (ctx.message.author.id,))
        user = cur.fetchone()
        if int(user[0]) != 0:
            cur.execute('UPDATE users SET ignore = 0 WHERE id=?', (ctx.message.author.id,))
        else:
            cur.execute('INSERT INTO users VALUES(?,0,0,0)', (ctx.message.author.id,))
        sql.commit()
        cur.execute('VACUUM')
        await ctx.send("Hi {0.author.mention}!  Let's start being positive!".format(ctx.message))
    except Exception as e:
        print('opt_in : ', e)
        pass


@client.command(pass_context=True, name='optout')
async def opt_out(ctx):
    try:
        if ctx.message.author == client.user or ctx.message.author.bot:
            return
        cur.execute('SELECT count(*), ignore from users where id=?', (ctx.message.author.id,))
        user = cur.fetchone()
        if int(user[0]) != 0:
            cur.execute('UPDATE users SET ignore = 1 WHERE id=?', (ctx.message.author.id,))
        else:
            cur.execute('INSERT INTO users VALUES(?,0,0,1)', (ctx.message.author.id,))
        sql.commit()
        cur.execute('VACUUM')
        await ctx.send("Sorry to see you go, {0.author.mention}!".format(ctx.message))
    except Exception as e:
        print('opt_out : ', e)
        pass


@client.command(pass_context=True, name='hyb')
async def hell_yeah_brother(ctx):
    try:
        if ctx.message.author == client.user or ctx.message.author.bot:
            return
        await ctx.send("{0.author.mention} Hell yeah brother!".format(ctx.message))
    except Exception as e:
        print('hell_yeah_brother : ', e)
        pass


# @client.command(pass_context=True, name='reset')
# async def reset(ctx):
#     try:
#         return
#         if ctx.message.author == client.user or ctx.message.author.bot:
#             return
#         cur.execute('SELECT count(*), ignore from users where id=?', (ctx.message.author.id,))
#         user = cur.fetchone()
#         if int(user[0]) != 0:
#             cur.execute('UPDATE users SET score = 0, messages = 0 WHERE id=?', (ctx.message.author.id,))
#         else:
#             cur.execute('INSERT INTO users VALUES(?,0,0,0)', (ctx.message.author.id,))
#         sql.commit()
#         cur.execute('VACUUM')
#         await ctx.send("Okay {0.author.mention}, you have a clean slate!".format(ctx.message))
#     except Exception as e:
#         print('reset : ', e)
#         pass


client.run(settings["discord"]["client_token"])
