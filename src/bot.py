import config as conf
from telebot import TeleBot
from telebot.apihelper import ApiException
from src.database import database
import config

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


    def _game_handler(self, handler):
        def decorator(message, *args, **kwargs):
            game = database.games.find_one({'chat': message.chat.id})
            if game and game['game'] == 'mafia':
                delete = False
                try:
                    player = next(p for p in game['players'] if p['id'] == message.from_user.id)
                except StopIteration:
                    if config.DELETE_FROM_EVERYONE and game['stage'] not in (0, -4):
                        delete = True
                else:
                    if game['stage'] in (2, 7):
                        victim = game.get('victim')
                        if victim is not None and victim != message.from_user.id:
                            delete = True
                    elif not player.get('alive', True) or game['stage'] not in (0, -4):
                        delete = True
                if delete:
                    self.safely_delete_message(chat_id=message.chat.id, message_id=message.message_id)
                    return

            return handler(message, game, *args, **kwargs)
        return decorator

    def group_message_handler(self, *, func=None, **kwargs):
        def decorator(handler):
            if func is None:
                conjuction = group_only
            else:
                conjuction = lambda message: group_only(message) and func(message)

            new_handler = self._game_handler(handler)
            handler_dict = self._build_handler_dict(new_handler, func=conjuction, **kwargs)
            self.add_message_handler(handler_dict)
            return new_handler

        return decorator

    def safely_delete_message(self, *args, **kwargs):
        try:
            self.delete_message(*args, **kwargs)
        except ApiException:
            print("Oshibka")
            #logger.debug('Ошибка API при удалении сообщения', exc_info=True)


bot = HostBot(conf.TOKEN)

# @bot.message_handler(commands=['start'])
# def start_message(message):
#     # tb.send_message(-1001403548604, 'privet')
#     bot.send_message(message.chat.id, 'privet')
#
#
# bot.polling()
