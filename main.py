# This code is based on the following example:
# https://discordpy.readthedocs.io/en/stable/quickstart.html#a-minimal-bot

import re
import os

import bisect
import discord
import random
import requests
from threading import Thread
from dataclasses import dataclass

from dotenv import load_dotenv

load_dotenv()

intents = discord.Intents.default()
intents.dm_messages = True
intents.message_content = True

hdrs = {
    'Authorization': 'Bearer ' + os.environ['CHASTER_TOKEN'],
    'X-Chaster-Client-Id': os.environ['CHASTER_ID'],
    'X-Chaster-Client-Secret': os.environ['CHASTER_SECRET']
}

client = discord.Client(intents=intents)


@client.event
async def on_ready():
  print('We have logged in as {0.user}'.format(client))


jabucheeId = 810676202175725599
users = {}


@dataclass
class User:
  name: str
  lock: int
  answer: str
  guesses: int = 0
  resets: int = 0
  mode: str = "wordle"
  woodle_multiplier: int = 300


#users = {jabucheeId: {'name': 'Jabuchee'}}
def register_user(user_id, username):
  # check that given username is locked
  r = requests.post('https://api.chaster.app/keyholder/locks/search',
                    headers=hdrs,
                    json={'status': 'locked'})
  found_lock = None
  for lock in r.json()['locks']:
    if lock['user']['username'] == username:
      found_lock = lock
      break
  if found_lock is not None:
    # check not already registered
    for user in users.values():
      if user.lock == found_lock['_id']:
        return 'Lock is already registered'
    users[user_id] = User(name=username,
                          lock=found_lock['_id'],
                          answer=random_word())
    if 'Woodle' in lock['title']:
        users[user_id].mode = 'woodle'
        users[user_id].woodle_multiplier = 0
    r = requests.post(
        f"https://api.chaster.app/locks/{found_lock['_id']}/freeze",
        headers=hdrs,
        json={'isFrozen': True})
    return f'You are now registered as wearer {username}'
  return f'Username {username} is not locked by Jabuchee'


def get_lock(user_id):
  r = requests.get(f"https://api.chaster.app/locks/{users[user_id].lock}",
                   headers=hdrs)
  return r.json()['status']


def get_history(user_id, last_id=None):
  history = []
  req = {'extension': 'wheel-of-fortune', 'limit': 10}
  if last_id is not None:
    req['lastId'] = last_id
  r = requests.post(
      f"https://api.chaster.app/locks/{users[user_id].lock}/history",
      headers=hdrs,
      json=req)
  results = r.json()['results']
  if r.json()['hasMore']:
    print(f'need page starting at {results[-1]["_id"]}')
    results += get_history(user_id, results[-1]['_id'])
  return results


def add_time(user_id, time):
  if time == 0:
    return
  print(f'Adding {time} minutes to {users[user_id].name}')

  requests.post(
      f"https://api.chaster.app/locks/{users[user_id].lock}/update-time",
      headers=hdrs,
      json={'duration': time})


def random_word():
  with open('wordle-answers-alphabetical.txt') as f:
    lines = f.read().splitlines()
    return random.choice(lines)


def check_guesses(user_id):
  history = get_history(user_id)
  guesses = 0
  resets = 0
  for log in history:
    if log['description'] == 'Take a guess':
      guesses += 1
    if log['description'] == 'Reset the answer':
      resets += 1
  if resets > users[user_id].resets:
    users[user_id].resets = resets
    users[user_id].guesses = guesses
    old_answer = users[user_id].answer
    new_answer = random_word()
    users[user_id].answer = new_answer
    return f'The answer has been reset to a new word. The old answer was {old_answer}'
  if guesses <= users[user_id].guesses:
    print(
        f'{users[user_id].name}: Need more guesses {guesses} vs {users[user_id].guesses}'
    )
    return 'You have no guesses available - spin wheel to earn guesses'
  return None


def check_answer(user_id, guess):
  if not check_valid_guess(guess):
    return 'Not a valid word'
  users[user_id].guesses += 1
  answer = users[user_id].answer
  if guess == answer:
    return None
  garray = list(guess)
  ansarray = list(answer)
  response = ['⬜️'] * 5
  woodle_time = 0
  for i in range(5):
    if answer[i] == guess[i]:
      response[i] = '🟩'
      garray[i] = ''
      ansarray[i] = ''
      if users[user_id].mode == 'woodle':
        woodle_time += 4
  for i in range(5):
    if garray[i] == '':
      continue
    if garray[i] in ansarray:
      index = ansarray.index(garray[i])
      response[i] = '🟨'
      ansarray[index] = ''
      if users[user_id].mode == 'woodle':
        woodle_time += 1
  if users[user_id].mode == 'woodle':
    add_time(user_id, woodle_time * users[user_id].woodle_multiplier)
    return f'Incorrect guess - score {woodle_time}'
  return ''.join(response)


def check_valid_guess(guess):
  with open('wordle-answers-alphabetical.txt') as f:
    lines = f.read().splitlines()
    idx = bisect.bisect_left(lines, guess)
    if idx < len(lines) and lines[idx] == guess:
      return True
  with open('wordle-allowed-guesses.txt') as f:
    lines = f.read().splitlines()
    idx = bisect.bisect_left(lines, guess)
    if idx < len(lines) and lines[idx] == guess:
      return True
  return False


def set_woodle(username, time):
  for user in users.values():
    if user.name == username:
      user.mode = 'woodle'
      user.woodle_multiplier = time
      return 'Updated woodle settings'
  return 'User not found'


@client.event
async def on_message(message):
  if message.author == client.user:
    return
  if not isinstance(message.channel, discord.DMChannel):
    return
  m = re.search('^Register (\w*)$', message.content)
  if m is not None:
    msg = register_user(message.author.id, m.group(1))
    await message.channel.send(msg)
    return
  if message.author.id not in users:
    await message.channel.send('Need to register first')
    print(f'Unregistered: {message.content}')
    return
  if message.author.id == jabucheeId:
    m = re.search('^Locks', message.content)
    if m is not None:
      r = requests.post('https://api.chaster.app/keyholder/locks/search',
                        headers=hdrs,
                        json={'status': 'locked'})
      for lock in r.json()['locks']:
        await message.channel.send(f"locked user: {lock['user']['username']}")
      return
    m = re.search('^Woodle (\w*) (\d*)$', message.content)
    if m is not None:
      msg = set_woodle(m.group(1), 60*int(m.group(2)))
      await message.channel.send(msg)
      return
    
    
  m = re.search('^Guess ([a-z]{5})$', message.content)
  print(f'{users[message.author.id].name}: {message.content}')
  print(
      f'{users[message.author.id].name}: answer is {users[message.author.id].answer}'
  )
  if m is not None:
    msg = check_guesses(message.author.id)
    if msg is not None:
      await message.channel.send(msg)
      return
    response = check_answer(message.author.id, m.group(1))
    if response is not None:
      await message.channel.send(response)
      return
    r = requests.post(
        f"https://api.chaster.app/locks/{users[message.author.id].lock}/freeze",
        headers=hdrs,
        json={'isFrozen': False})
    await message.channel.send('🎉🎉🎉 ')
    return
  await message.channel.send(
      'Guesses are case sensitive and should be of the form\nGuess steam')
  return


try:
  token = os.getenv("TOKEN") or ""
  if token == "":
    raise Exception("Please add your token to the Secrets pane.")
  client.run(token)
except discord.HTTPException as e:
  if e.status == 429:
    print(
        "The Discord servers denied the connection for making too many requests"
    )
    print(
        "Get help from https://stackoverflow.com/questions/66724687/in-discord-py-how-to-solve-the-error-for-toomanyrequests"
    )
  else:
    raise e
