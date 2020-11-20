from bot import bot

role_titles = {
    'don': 'дон мафии',
    'mafia': 'мафия',
    'sheriff': 'шериф',
    'peace': 'мирный житель'
}


def stop_game(game, reason):
    bot.try_to_send_message(game['chat'], reason)
