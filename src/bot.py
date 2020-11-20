import config as conf
from telebot import TeleBot
from telebot.apihelper import ApiException

# from .logger import logger
print(conf.TOKEN)

tb = TeleBot(conf.TOKEN)
# tb.send_message('-492482025', 'privet')
# TeleBot.send_message(conf.TOKEN,'-492482025', 'privet')
-1001403548604

# @tb.message_handler(commands= ['start'])
# def start_message(message):
#     #tb.send_message(-1001403548604, 'privet')
#     tb.send_message(message.chat.id, 'privet')
#
# tb.polling()

def group_only(message):
    return message.chat.type in ('group', 'supergroup')

class HostBot(TeleBot):
    def try_to_send_message(self, *args, **kwargs):

        try:
            self.send_message(*args, **kwargs)
        except ApiException:
            print("logger error, Appi error ")


bot = HostBot(conf.TOKEN)


# @bot.message_handler(commands=['start'])
# def start_message(message):
#     # tb.send_message(-1001403548604, 'privet')
#     bot.send_message(message.chat.id, 'privet')
#
#
# bot.polling()