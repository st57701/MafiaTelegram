from uuid import uuid4
from datetime import datetime
import config
# from .game import role_titles, stop_game
# from .stages import stages, go_to_next_stage, format_roles, get_votes
import lang
from game import role_titles, stop_game
from src.bot import bot
import re
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton
from src.database import database
from pymongo.collection import ReturnDocument
from time import time
from src.stages import stages, go_to_next_stage, format_roles, get_votes
import random


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
    # bot.send_message(message.chat.id, get_full_name())


@bot.message_handler(regexp=command_regexp('stats'))
def stats_command(message, *args, **kwargs):
    stats = database.stats.find_one({'id': message.from_user.id, 'chat': message.chat.id})

    if not stats:
        bot.send_message(message.chat.id, f'Статистика {get_name(message.from_user)} пуста.')
        return

    paragraphs = []

    if 'total' in stats:
        win = stats.get('win', 0)
        answer = (
            # f'Счёт {get_name(message.from_user)} в мафии: {get_mafia_score(stats)}\n'
            f'Побед: {win}/{stats["total"]} ({100 * win // stats["total"]}%)'
        )
        roles = []
        for role, title in role_titles.items():
            if role in stats:
                role_win = stats[role].get('win', 0)
                roles.append({
                    'title': title,
                    'total': stats[role]['total'],
                    'win': role_win,
                    'rate': 100 * role_win // stats[role]['total']
                })
        for role in sorted(roles, key=lambda s: s['rate'], reverse=True):
            answer += (
                f'\n{role["title"].capitalize()}: '
                f'побед - {role.get("win", 0)}/{role["total"]} ({role["rate"]}%)'
            )
        paragraphs.append(answer)


@bot.callback_query_handler(func=lambda call: call.data == 'take card')
def take_card(call):
    player_game = database.games.find_one({
        'game': 'mafia',
        'stage': -4,
        'players.id': call.from_user.id,
        'chat': call.message.chat.id,
    })

    if player_game:
        player_index = next(i for i, p in enumerate(player_game['players']) if p['id'] == call.from_user.id)
        player_object = player_game['players'][player_index]

        if player_object.get('role') is None:
            keyboard = InlineKeyboardMarkup()
            keyboard.add(
                InlineKeyboardButton(
                    text='🃏 Вытянуть карту',
                    callback_data='take card'
                )
            )

            player_role = player_game['cards'][player_index]

            player_game = database.games.find_one_and_update(
                {'_id': player_game['_id']},
                {'$set': {
                    f'players.{player_index}.role': player_role,
                    f'players.{player_index}.alive': True
                }},
                return_document=ReturnDocument.AFTER
            )

            bot.answer_callback_query(
                callback_query_id=call.id,
                show_alert=True,
                text=f'Твоя роль - {role_titles[player_role]}.'
            )

            players_without_roles = [i + 1 for i, p in enumerate(player_game['players']) if p.get('role') is None]

            if len(players_without_roles) > 0:
                bot.edit_message_text(
                    lang.take_card.format(
                        order=format_roles(player_game),
                        not_took=', '.join(map(str, players_without_roles))),
                    chat_id=call.message.chat.id,
                    message_id=call.message.message_id,
                    reply_markup=keyboard
                )

            else:
                database.games.update_one(
                    {'_id': player_game['_id']},
                    {'$set': {'order': []}}
                )

                bot.edit_message_text(
                    'Порядок игроков для игры следующий:\n\n' + format_roles(player_game),
                    chat_id=call.message.chat.id,
                    message_id=call.message.message_id,
                )

                go_to_next_stage(player_game, inc=2)

        else:
            bot.answer_callback_query(
                callback_query_id=call.id,
                show_alert=False,
                text='У тебя уже есть роль.'
            )

    else:
        bot.answer_callback_query(
            callback_query_id=call.id,
            show_alert=False,
            text='Ты сейчас не играешь в игру в этой конфе.'
        )


# Sozdajotsa igra
@bot.group_message_handler(regexp=command_regexp('create'))
def create(message, *args, **kwargs):
    existing_request = database.requests.find_one({'chat': message.chat.id})
    if existing_request:
        bot.send_message(message.chat.id, 'В этом чате уже есть игра!',
                         reply_to_message_id=existing_request['message_id'])
        return

    keyboard = InlineKeyboardMarkup()
    keyboard.add(
        InlineKeyboardButton(
            text='Вступить в игру или выйти из игры',
            callback_data='request interact'
        )
    )

    player_object = user_object(message.from_user)
    request_overdue_time = time() + config.REQUEST_OVERDUE_TIME

    answer = lang.new_request.format(
        owner=get_name(message.from_user),
        time=datetime.utcfromtimestamp(request_overdue_time).strftime('%H:%M'),
        order=f'Игроки:\n1. {player_object["name"]}'
    )
    sent_message = bot.send_message(message.chat.id, answer, reply_markup=keyboard)

    database.requests.insert_one({
        'id': str(uuid4())[:8],
        'owner': player_object,
        'players': [player_object],
        'time': request_overdue_time,
        'chat': message.chat.id,
        'message_id': sent_message.message_id,
        'players_count': 1
    })


# pitajemsa vojti v igru
@bot.callback_query_handler(func=lambda call: call.data == 'request interact')
def request_interact(call):
    message_id = call.message.message_id
    required_request = database.requests.find_one({'message_id': message_id})

    if required_request:
        update_dict = {}
        player_object = None
        for player in required_request['players']:
            print(player['id'])
            if player['id'] == call.from_user.id:
                player_object = player
                increment_value = -1
                request_action = '$pull'
                alert_message = 'Ты больше не в игре.'

                break

        if player_object is None:
            if len(required_request['players']) >= config.PLAYERS_COUNT_LIMIT:
                bot.answer_callback_query(
                    callback_query_id=call.id,
                    show_alert=False,
                    text='В игре состоит максимальное количество игроков.'
                )
                return

            player_object = user_object(call.from_user)
            increment_value = 1
            request_action = '$push'
            alert_message = 'Ты теперь в игре.'
            update_dict['$set'] = {'time': time() + config.REQUEST_OVERDUE_TIME}

        update_dict.update(
            {request_action: {'players': player_object},
             '$inc': {'players_count': increment_value}}
        )

        updated_document = database.requests.find_one_and_update(
            {'_id': required_request['_id']},
            update_dict,
            return_document=ReturnDocument.AFTER
        )

        keyboard = InlineKeyboardMarkup()
        keyboard.add(
            InlineKeyboardButton(
                text='Вступить в игру или выйти из игры',
                callback_data='request interact'
            )
        )

        bot.edit_message_text(
            lang.new_request.format(
                owner=updated_document['owner']['name'],
                time=datetime.utcfromtimestamp(updated_document['time']).strftime('%H:%M'),
                order='Игроков нет.' if not updated_document['players_count'] else
                'Игроки:\n' + '\n'.join([f'{i + 1}. {p["name"]}' for i, p in enumerate(updated_document['players'])])
            ),
            chat_id=call.message.chat.id,
            message_id=message_id,
            reply_markup=keyboard
        )

        bot.answer_callback_query(callback_query_id=call.id, show_alert=False, text=alert_message)
    else:
        bot.edit_message_text('Заявка больше не существует.', chat_id=call.message.chat.id, message_id=message_id)


@bot.group_message_handler(regexp=command_regexp('start'))
def start_game(message, *args, **kwargs):
    print("STAAAAART")
    req = database.requests.find_and_modify(
        {
            'owner.id': message.from_user.id,
            'chat': message.chat.id,
            'players_count': {'$gte': config.PLAYERS_COUNT_TO_START}
        },
        new=False,
        remove=True
    )
    if req is not None:
        players_count = req['players_count']

        cards = ['mafia'] * (players_count // 3 - 1) + ['don', 'sheriff']
        print(cards)
        cards += ['peace'] * (players_count - len(cards))
        random.shuffle(cards)

        keyboard = InlineKeyboardMarkup()
        keyboard.add(
            InlineKeyboardButton(
                text='🃏 Вытянуть карту',
                callback_data='take card'
            )
        )

        stage_number = min(stages.keys())

        message_id = bot.send_message(
            message.chat.id,
            lang.take_card.format(
                order='\n'.join([f'{i + 1}. {p["name"]}' for i, p in enumerate(req['players'])]),
                not_took=', '.join(map(str, range(1, len(req['players']) + 1))),
            ),
            reply_markup=keyboard
        ).message_id

        database.games.insert_one({
            'game': 'mafia',
            'chat': req['chat'],
            'id': req['id'],
            'stage': stage_number,
            'day_count': 0,
            'players': req['players'],
            'cards': cards,
            'next_stage_time': time() + stages[stage_number]['time'],
            'message_id': message_id,
            'don': [],
            'vote': {},
            'shots': [],
            'played': []
        })

    else:
        bot.send_message(message.chat.id, 'У тебя нет заявки на игру, которую возможно начать.')
     ################################################################
@bot.callback_query_handler(func=lambda call: call.data == 'mafia team')
def mafia_team(call):
    player_game = database.games.find_one({
        'game': 'mafia',
        'players': {'$elemMatch': {
            'id': call.from_user.id,
            'role': {'$in': ['don', 'mafia']},
        }},
        'chat': call.message.chat.id
    })

    if player_game:
        bot.answer_callback_query(
            callback_query_id=call.id,
            show_alert=True,
            text='Ты играешь в следующей команде:\n' +
            format_roles(player_game, True, lambda p: p['role'] in ('don', 'mafia')))

    else:
        bot.answer_callback_query(
            callback_query_id=call.id,
            show_alert=False,
            text='Ты не можешь знакомиться с командой мафии.'
        )

@bot.callback_query_handler(func=lambda call: call.data.startswith('check don'))
def check_don(call):
    player_game = database.games.find_one({
        'game': 'mafia',
        'stage': 5,
        'players': {'$elemMatch': {
            'alive': True,
            'role': 'don',
            'id': call.from_user.id
        }},
        'chat': call.message.chat.id
    })

    if player_game and call.from_user.id not in player_game['played']:
        check_player = int(re.match(r'check don (\d+)', call.data).group(1)) - 1

        bot.answer_callback_query(
            callback_query_id=call.id,
            show_alert=True,
            text=f'Да, игрок под номером {check_player + 1} - {role_titles["sheriff"]}'
                 if player_game['players'][check_player]['role'] == 'sheriff' else
                 f'Нет, игрок под номером {check_player + 1} - не {role_titles["sheriff"]}'
        )

        database.games.update_one({'_id': player_game['_id']}, {'$addToSet': {'played': call.from_user.id}})

    else:
        bot.answer_callback_query(
            callback_query_id=call.id,
            show_alert=False,
            text='Ты не можешь совершать проверку дона.'
        )

@bot.callback_query_handler(func=lambda call: call.data.startswith('check sheriff'))
def check_sheriff(call):
    player_game = database.games.find_one({
        'game': 'mafia',
        'stage': 6,
        'players': {'$elemMatch': {
            'alive': True,
            'role': 'sheriff',
            'id': call.from_user.id
        }},
        'chat': call.message.chat.id
    })

    if player_game and call.from_user.id not in player_game['played']:
        check_player = int(re.match(r'check sheriff (\d+)', call.data).group(1)) - 1

        bot.answer_callback_query(
            callback_query_id=call.id,
            show_alert=True,
            text=f'Да, игрок под номером {check_player + 1} - {role_titles["don"]}'
                 if player_game['players'][check_player]['role'] == 'don' else
                 f'Да, игрок под номером {check_player + 1} - {role_titles["mafia"]}'
                 if player_game['players'][check_player]['role'] == 'mafia' else
                 f'Нет, игрок под номером {check_player + 1} - не {role_titles["mafia"]}'
        )

        database.games.update_one({'_id': player_game['_id']}, {'$addToSet': {'played': call.from_user.id}})

    else:
        bot.answer_callback_query(
            callback_query_id=call.id,
            show_alert=False,
            text='Ты не можешь совершать проверку шерифа.'
        )

@bot.callback_query_handler(func=lambda call: call.data.startswith('append to order'))
def append_order(call):
    player_game = database.games.find_one({
        'game': 'mafia',
        'stage': -2,
        'players': {'$elemMatch': {
            'role': 'don',
            'id': call.from_user.id
        }},
        'chat': call.message.chat.id
    })

    if player_game:
        call_player = re.match(r'append to order (\d+)', call.data).group(1)

        database.games.update_one(
            {'_id': player_game['_id']},
            {'$addToSet': {'order': call_player}}
        )

        bot.answer_callback_query(
            callback_query_id=call.id,
            show_alert=False,
            text=f'Игрок под номером {call_player} добавлен в приказ.'
        )

    else:
        bot.answer_callback_query(
            callback_query_id=call.id,
            show_alert=False,
            text='Ты не можешь отдавать приказ дона.'
        )

@bot.callback_query_handler(func=lambda call: call.data.startswith('vote'))
def vote(call):
    player_game = database.games.find_one({
        'game': 'mafia',
        'stage': 1,
        'players': {'$elemMatch': {
            'alive': True,
            'id': call.from_user.id
        }},
        'chat': call.message.chat.id
    })

    if player_game and call.from_user.id not in player_game['played']:
        vote_player = int(re.match(r'vote (\d+)', call.data).group(1)) - 1
        player_index = next(i for i, p in enumerate(player_game['players']) if p['id'] == call.from_user.id)

        game = database.games.find_one_and_update(
            {'_id': player_game['_id']},
            {'$addToSet': {
                'played': call.from_user.id,
                'vote.%d' % vote_player: player_index
            }},
            return_document=ReturnDocument.AFTER
        )

        keyboard = InlineKeyboardMarkup(row_width=8)
        keyboard.add(
            *[InlineKeyboardButton(
                text=f'{i + 1}',
                callback_data=f'vote {i + 1}'
            ) for i, player in enumerate(game['players']) if player['alive']]
        )
        keyboard.add(
            InlineKeyboardButton(
                text='Не голосовать',
                callback_data='vote 0'
            )
        )
        bot.edit_message_text(
            lang.vote.format(vote=get_votes(game)),
            chat_id=game['chat'],
            message_id=game['message_id'],
            reply_markup=keyboard
        )

        bot.answer_callback_query(
            callback_query_id=call.id,
            show_alert=False,
            text=f'Голос отдан против игрока {vote_player + 1}.' if vote_player >= 0 else 'Голос отдан.'
        )

    else:
        bot.answer_callback_query(
            callback_query_id=call.id,
            show_alert=False,
            text='Ты не можешь голосовать.'
        )

@bot.callback_query_handler(func=lambda call: call.data == 'end order')
def end_order(call):
    player_game = database.games.find_one({
        'game': 'mafia',
        'stage': -2,
        'players': {'$elemMatch': {
            'role': 'don',
            'id': call.from_user.id
        }},
        'chat': call.message.chat.id
    })

    if player_game:
        bot.answer_callback_query(
            callback_query_id=call.id,
            show_alert=False,
            text='Приказ записан и будет передан команде мафии.'
        )

        go_to_next_stage(player_game)

    else:
        bot.answer_callback_query(
            callback_query_id=call.id,
            show_alert=False,
            text='Ты не можешь отдавать приказ дона.'
        )

@bot.callback_query_handler(
    func=lambda call: call.data == 'get order',
)
def get_order(call):
    player_game = database.games.find_one({
        'game': 'mafia',
        '$or': [
            {'players': {'$elemMatch': {
                'role': 'don',
                'id': call.from_user.id
            }}},
            {'players': {'$elemMatch': {
                'role': 'mafia',
                'id': call.from_user.id
            }}}
        ],
        'chat': call.message.chat.id
    })

    if player_game:
        if player_game.get('order'):
            order_text = f'Я отдал тебе следующий приказ: {", ".join(player_game["order"])}. Стреляем именно в таком порядке, в противном случае промахнёмся. ~ {role_titles["don"]}'
        else:
            order_text = f'Я не отдал приказа, импровизируем по ходу игры. Главное - стрелять в одних и тех же людей в одну ночь, в противном случае промахнёмся. ~ {role_titles["don"]}'

        bot.answer_callback_query(
            callback_query_id=call.id,
            show_alert=True,
            text=order_text
        )

    else:
        bot.answer_callback_query(
            callback_query_id=call.id,
            show_alert=False,
            text='Ты не можешь получать приказ дона.'
        )

@bot.group_message_handler(regexp=command_regexp('cancel'))
def cancel(message, *args, **kwargs):
    print("cancel")
    req = database.requests.find_one_and_delete({
        'owner.id': message.from_user.id,
        'chat': message.chat.id
    })
    if req:
        answer = 'Твоя заявка удалена.'
    else:
        answer = 'У тебя нет заявки на игру.'
    bot.send_message(message.chat.id, answer)


def create_poll(message, game, poll_type, suggestion):
    print("ddasssss")
    if not game or game['stage'] not in (0, -4):
        return

    check_roles = game['stage'] == 0

    existing_poll = database.polls.find_one({
        'chat': message.chat.id,
        'type': poll_type
    })
    if existing_poll:
        bot.send_message(
            message.chat.id,
            'В этом чате уже идёт голосование!',
            reply_to_message_id=existing_poll['message_id']
        )
        return

    poll = {
        'chat': message.chat.id,
        'type': poll_type,
        'creator': get_name(message.from_user),
        'check_roles': check_roles,
        'votes': [message.from_user.id],
    }

    keyboard = InlineKeyboardMarkup()
    if check_roles:
        peace_team = set()
        mafia_team = set()

        for player in game['players']:
            if player['alive']:
                if player['role'] in ('don', 'mafia'):
                    mafia_team.add(player['id'])
                else:
                    peace_team.add(player['id'])

        peace_votes = 0
        mafia_votes = 0
        if message.from_user.id in peace_team:
            peace_votes += 1
        else:
            mafia_votes += 1

        poll['peace_count'] = peace_votes
        poll['peace_required'] = 2 * len(peace_team) // 3
        poll['mafia_count'] = mafia_votes
        poll['mafia_required'] = 2 * len(mafia_team) // 3

    else:
        poll['count'] = 1
        poll['required'] = 2 * len(game['players']) // 3

    keyboard.add(
        InlineKeyboardButton(
            text='Проголосовать',
            callback_data='poll'
        )
    )

    answer = f'{poll["creator"]} предлагает {suggestion}.'
    poll['message_id'] = bot.send_message(message.chat.id, answer, reply_markup=keyboard).message_id
    database.polls.insert_one(poll)


@bot.group_message_handler(regexp=command_regexp('end'))
def force_game_end(message, game, *args, **kwargs):
    print('enddd')
    create_poll(message, game, 'end', 'закончить игру')


@bot.group_message_handler(regexp=command_regexp('skip'))
def skip_current_stage(message, game, *args, **kwargs):
    print("skip")
    create_poll(message, game, 'skip', 'пропустить текущую стадию')


@bot.callback_query_handler(func=lambda call: call.data == 'poll')
def poll_vote(call):
    message_id = call.message.message_id
    poll = database.polls.find_one({'message_id': message_id})

    if not poll:
        bot.edit_message_text(
            'Голосование больше не существует.',
            chat_id=call.message.chat.id,
            message_id=message_id
        )
        return

    if call.from_user.id in poll['votes']:
        bot.answer_callback_query(
            callback_query_id=call.id,
            show_alert=False,
            text='Твой голос уже был учтён.',
        )
        return

    player_game = database.games.find_one({
        'game': 'mafia',
        'players': {'$elemMatch': {
            'alive': True,
            'id': call.from_user.id
        }},
        'chat': call.message.chat.id
    })

    if not player_game:
        bot.answer_callback_query(
            callback_query_id=call.id,
            show_alert=False,
            text='Ты не можешь голосовать.',
        )
        return

    increment_value = {}

    if poll['check_roles']:
        mafia_count = poll['mafia_count']
        peace_count = poll['peace_count']

        for player in player_game['players']:
            if player['id'] == call.from_user.id:
                if player['role'] in ('don', 'mafia'):
                    increment_value['mafia_count'] = 1
                    mafia_count += 1
                else:
                    increment_value['peace_count'] = 1
                    peace_count += 1

                poll_condition = mafia_count > poll['mafia_required'] and peace_count >= poll['peace_required']
                break
    else:
        increment_value['count'] = 1
        poll_condition = poll['count'] + 1 > poll['required']

    if poll_condition:
        bot.edit_message_reply_markup(
            chat_id=call.message.chat.id,
            message_id=message_id
        )
        if poll['type'] == 'skip':
            go_to_next_stage(player_game)
        elif poll['type'] == 'end':
            stop_game(player_game, reason='Игроки проголосовали за окончание игры.')
            return

    database.polls.update_one(
        {'_id': poll['_id']},
        {
            '$addToSet': {'votes': call.from_user.id},
            '$inc': increment_value
        }
    )

    bot.answer_callback_query(
        callback_query_id=call.id,
        show_alert=False,
        text='Голос учтён.'
    )


@bot.callback_query_handler(func=lambda call: call.data == 'shot')
def callback_inline(call):
    player_game = database.games.find_one({
        'game': 'mafia',
        'stage': 4,
        'players': {'$elemMatch': {
            'alive': True,
            'role': {'$in': ['don', 'mafia']},
            'id': call.from_user.id
        }},
        'chat': call.message.chat.id
    })

    if player_game and call.from_user.id not in player_game['played']:
        victim = int(re.match(r'(\d+)\. .*', call.message.text).group(1)) - 1
        database.games.update_one(
            {'_id': player_game['_id']},
            {
                '$addToSet': {'played': call.from_user.id},
                '$push': {'shots': victim}
            }
        )

        bot.answer_callback_query(
            callback_query_id=call.id,
            show_alert=False,
            text=f'Выстрел произведён в игрока {victim + 1}'
        )

    else:
        bot.answer_callback_query(
            callback_query_id=call.id,
            show_alert=False,
            text='Ты не можешь участвовать в стрельбе'
        )


@bot.message_handler(
    func=lambda message: message.from_user.id == config.ADMIN_ID,
    regexp=command_regexp('reset')
)
def reset(message, *args, **kwargs):
    database.games.delete_many({})
    bot.send_message(message.chat.id, 'База игр сброшена!')


@bot.message_handler(
    func=lambda message: message.from_user.id == config.ADMIN_ID,
    regexp=command_regexp('database')
)
def print_database(message, *args, **kwargs):
    print(list(database.games.find()))
    bot.send_message(message.chat.id, 'Все документы базы данных игр выведены в терминал!')




bot.polling()
