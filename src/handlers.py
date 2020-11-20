import config
#from .game import role_titles, stop_game
#from .stages import stages, go_to_next_stage, format_roles, get_votes
from src.bot import bot
import re
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton

def get_name(user):
    return '@' + user.username if user.username else user.first_name


def get_full_name(user):
    result = user.first_name
    if user.last_name:
        result += ' ' + user.last_name
    return result

def user_object(user):
    return {'id': user.id, 'name': get_name(user), 'full_name': get_full_name(user)}

def command_regexp(command):
    return f'^/{command}(@{bot.get_me().username})?$'


@bot.message_handler(regexp=command_regexp('help'))
@bot.message_handler(func=lambda message: message.chat.type == 'private', commands=['start'])
def start_command(message, *args, **kwargs):
    answer = (
        f'Привет, я {bot.get_me().first_name}!\n'
        'Я умею создавать игры в мафию в группах и супергруппах.\n'
        'Инструкция и исходный код: \n'
        'По всем вопросам пишите на https://t.me/Shocker333'
    )
    bot.send_message(message.chat.id, answer)
    #bot.send_message(message.chat.id, get_full_name())
bot.polling()

