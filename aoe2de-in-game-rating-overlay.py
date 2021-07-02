# -*- coding: utf-8 -*-
#!/usr/bin/python3

#
# python -m pysimplegui-exemaker.pysimplegui-exemaker
#

import os
import requests
import sys
import threading
import time

import PySimpleGUI as sg


LEFT = 0
RIGHT = 1

AOE2NET_URL = 'https://aoe2.net/api/'

CONFIGURATION_FILE = './AOE2NET_PROFILE_ID.txt'

FONT_TYPE = 'Liberation Mono Bold'

FONT_SIZE = 10

NO_PADDING = ((0,0),(0,0))

TEXT_BG_COLOR = '#000000'

BG_COLOR_INVISIBLE = '#010101'

COPYRIGHT_FONT = ('Arial', 8)

COPYRIGHT_TEXT = u'\u00A9' + ' Dooque'

REFRESH_TIMEOUT = 10 # Seconds

NO_DATA_STRING = '----'

MAX_NUMBER_OF_PLAYERS = 8

SAVE_WINDOW_LOCATION_INTERVAL = 1 # Seconds.

WINDOW_LOCATION_FILE = '{}\\aoe2de_in_game_rating_overlay-window_location.txt'

loading_progress = {'steps':1, 'current':0}

# This is not an error!!!
JUSTIFICATION = {
    LEFT: 'right',
    RIGHT: 'left'
}

COLOR_CODES = {
    1: '#7A7AFC', # blue
    2: '#FD3434', # red
    3: '#00ff00', # green
    4: '#ffff00', # yellow
    5: '#00fafa', # teal
    6: '#ff00ff', # purple
    7: '#bababa', # gary
    8: '#ffA500', # orange
}

COLOR_STRINGS = {
    1: 'blue',
    2: 'red',
    3: 'green',
    4: 'yellow',
    5: 'teal',
    6: 'purple',
    7: 'gary',
    8: 'orange',
}


class Rating():

    def __init__(self, rating=None):
        if rating is not None:
            self.rating = rating["rating"]
            self.num_wins = rating["num_wins"]
            self.num_losses = rating["num_losses"]
            self.streak = rating["streak"]
            self.games = self.num_wins + self.num_losses
            self.win_ratio = self.num_wins / self.games
        else:
            self.rating = 0
            self.num_wins = 0
            self.num_losses = 0
            self.streak = 0
            self.games = 0
            self.win_ratio = 0


class Player():

    def __init__(self, player, strings):
        self.profile_id = player['profile_id']
        self.steam_id = player['steam_id']
        self.name = player['name']
        self.number = player['color']
        self.color_number = player['color']
        self.color_string = COLOR_STRINGS[player['color']]
        self.color_code = COLOR_CODES[player['color']]
        self.team = player['team']
        civ = [ x['string'] for x in strings['civ'] if x['id'] == player['civ'] ]
        self.civ = civ.pop() if civ else NO_DATA_STRING

        if self.name is None:
            self.name = 'IA ' + self.civ

    def fetch_rating_information(self):
        print('[Thread-1] Fetching 1v1 rating information for player {}'.format(self.name))
        if self.profile_id is not None:
            rating_1v1 = requests.get(AOE2NET_URL + 'player/ratinghistory?game=aoe2de&leaderboard_id=3&count=1&profile_id={}'.format(self.profile_id)).json()
            if rating_1v1:
                self.rating_1v1 = Rating(rating_1v1[0])
            else:
                self.rating_1v1 = Rating()
        else:
            self.rating_1v1 = Rating()
        loading_progress['current'] += 1

        print('[Thread-1] Fetching TG rating information for player {}'.format(self.name))
        if self.profile_id is not None:
            rating_tg = requests.get(AOE2NET_URL + 'player/ratinghistory?game=aoe2de&leaderboard_id=4&count=1&profile_id={}'.format(self.profile_id)).json()
            if rating_tg:
                self.rating_tg = Rating(rating_tg[0])
            else:
                self.rating_tg = Rating()
        else:
            self.rating_tg = Rating()
        loading_progress['current'] += 1


class Match():

    def __init__(self, match, strings):
        last_match = match['last_match']

        self.match_id = last_match['match_uuid']
        self.game_type = [x['string'] for x in strings['game_type'] if x['id'] == last_match['game_type']].pop()
        self.map_type = [x['string'] for x in strings['map_type'] if x['id'] == last_match['map_type']].pop()
        self.number_of_players = last_match['num_players']

        self.players = [ Player(player, strings) for player in last_match['players'] ]

    def fetch_rating_information(self):
        for player in self.players:
            player.fetch_rating_information()

class PlayerInformationPrinter():

    def print(self, number, name, elo, tgelo, text_position):
        if text_position == LEFT:
            return '{name} ({tgelo}) [{elo}] P{number}'.format(name=name, tgelo=tgelo, elo=elo, number=number)
        elif text_position == RIGHT:
            return 'P{number} [{elo}] ({tgelo}) {name}'.format(number=number, elo=elo, tgelo=tgelo, name=name)
        else:
            raise Exception('Invalid text_position value: {}'.format(text_position))


class InGameRatingOverlay():

    def __init__(self):
        self._event_refresh_game_information = threading.Event()
        self._player_info_printer = PlayerInformationPrinter()
        self._strings = requests.get(AOE2NET_URL + 'strings?game=aoe2de&language=en').json()
        self._current_match_lock = threading.Lock()
        self._fetching_data = False
        self._current_match = None
        self._finish = False

        self._loading_information_window_text = sg.Text('Loading game information:   0%', pad=NO_PADDING, background_color=TEXT_BG_COLOR, justification='center', font=(FONT_TYPE, 14))
        self._loading_information_window_location = (None, None)
        self._loading_information_window_layout = [
            [
                self._loading_information_window_text
            ],
            [
                self._get_copyright_text()
            ]
        ]
        self._loading_information_window_menu = ['menu', ['Exit',]]
        self._loading_information_window = None

        self._main_window_last_location = self._get_last_window_location()
        self._main_window_columns = [[], []]
        self._main_window_layout = None
        self._main_window_menu = ['menu', ['Refresh now...', 'Exit']]
        self._main_window = None
        self._update_main_window = False

    def run(self):
        self._create_loading_information_window()

        print('[Thread-0] Starting "update_game_information" thread.')
        self._update_game_information_thread = threading.Thread(target=self._update_game_information)
        self._update_game_information_thread.start()

        print('[Thread-0] Entering main loop...')

        while not self._finish:
            percentage = int(loading_progress['current'] / loading_progress['steps'] * 100)
            self._loading_information_window_text.update(value='Loading game information: {}%'.format(percentage))
            self._loading_information_window.refresh()

            if self._main_window is not None:
                e1, v1 = self._main_window.read(100)
            else:
                e1, v1 = ('no-event', [])

            e2, v2 = self._loading_information_window.read(100)

            if e1 in (sg.WIN_CLOSED, 'Exit') or e2 in (sg.WIN_CLOSED, 'Exit'):
                print('[Thread-0] finish = True')
                self._finish = True
                self._event_refresh_game_information.set()

            if e1 == 'Refresh now...':
                print('[Thread-0] Evenet: "Refresh now" generated.')
                self._event_refresh_game_information.set()

            self._save_windows_location()

            if self._fetching_data:
                print('[Thread-0] Fetching new data')
                if self._main_window is not None:
                    self._main_window.close()
                    self._main_window = None
                if self._main_window_last_location != (None, None):
                    c, y = self._main_window_last_location
                    sx, sy = self._loading_information_window.size
                    self._loading_information_window.move(int(c - sx/2), y)
                self._loading_information_window.reappear()
                self._loading_information_window.refresh()
                self._fetching_data = False

            if self._update_main_window:
                print('[Thread-0] Updating main window.')
                self._current_match_lock.acquire()
                if self._main_window is not None:
                    self._main_window.close()
                    self._main_window = None
                self._create_main_window()
                self._update_main_window = False
                self._loading_information_window.disappear()
                self._loading_information_window.refresh()
                self._current_match_lock.release()

        print('[Thread-0] Main loop terminated!')

        if self._main_window is not None:
            self._main_window.close()
            self._main_window = None
        if self._loading_information_window is not None:
            self._loading_information_window.close()
            self._loading_information_window = None

        print('[Thread-0] Waiting for update_game_information thread to terminate...')
        self._update_game_information_thread.join()
        print('[Thread-0] update_game_information thread terminated!')

    def _get_copyright_text(self):
        return sg.Text(COPYRIGHT_TEXT, pad=NO_PADDING, background_color=TEXT_BG_COLOR, justification='center', font=COPYRIGHT_FONT)

    def _create_loading_information_window(self):
        print('[Thread-0] Creating loading_information_window...')
        self._loading_information_window = sg.Window(
            None,
            self._loading_information_window_layout,
            no_titlebar=True,
            keep_on_top=True,
            grab_anywhere=True,
            background_color=BG_COLOR_INVISIBLE,
            transparent_color=BG_COLOR_INVISIBLE,
            alpha_channel=1,
            element_justification='center',
            right_click_menu=self._loading_information_window_menu
        )

        # We show this window in the same location than the main window.
        self._loading_information_window.finalize()
        if self._main_window_last_location != (None, None):
            c, y = self._main_window_last_location
            sx, sy = self._loading_information_window.size
            self._loading_information_window.move(int(c - sx/2), y)
            self._loading_information_window.refresh()
        print('[Thread-0] loading_information_window created!')

    def _create_main_window(self):
        print('[Thread-0] Creating main window...')
        self._update_main_window_layout()
        self._main_window = sg.Window(
            None,
            self._main_window_layout,
            no_titlebar=True,
            keep_on_top=True,
            grab_anywhere=True,
            background_color=BG_COLOR_INVISIBLE,
            transparent_color=BG_COLOR_INVISIBLE,
            alpha_channel=1,
            element_justification='center',
            right_click_menu=self._main_window_menu
        )
        self._main_window.finalize()
        if self._main_window_last_location != (None, None):
            c, y = self._main_window_last_location
            sx, sy = self._main_window.size
            self._main_window.move(int(c - sx/2), y)
        self._main_window.refresh()
        print('[Thread-0] Main window created!')

    def _update_main_window_layout(self):
        print('[Thread-0] Updating main window layout...')
        self._main_window_layout = [
            [
                sg.Column(self._main_window_columns[LEFT], pad=NO_PADDING, background_color=BG_COLOR_INVISIBLE, vertical_alignment='top', element_justification='right'),
                sg.VSeparator(),
                sg.Column(self._main_window_columns[RIGHT], pad=NO_PADDING, background_color=BG_COLOR_INVISIBLE, vertical_alignment='top', element_justification='left'),
            ],
            [
                self._get_copyright_text()
            ]
        ]

    def _get_last_window_location(self):
        try:
            location_file_path = WINDOW_LOCATION_FILE.format(os.getenv('USERPROFILE'))
            location_file = open(location_file_path, 'r')
            try:
                location = tuple(map(int, location_file.read().split(',')))
            except:
                location = (None, None)
        except FileNotFoundError:
            location = (None, None)

        print('[Thread-0] Getting last window location:', location)

        return location

    def _save_windows_location(self):
        if self._main_window is not None:
            x, y = self._main_window.CurrentLocation()
            sx, sy = self._main_window.size
        else:
            x, y = self._loading_information_window.CurrentLocation()
            sx, sy = self._loading_information_window.size
        current_location = (int(x + sx/2), int(y))
        if current_location != self._main_window_last_location:
            print('[Thread-0] Saving new window location:', current_location)
            self._main_window_last_location = current_location
            location_file_path = WINDOW_LOCATION_FILE.format(os.getenv('USERPROFILE'))
            location_file = open(location_file_path, 'w')
            location_file.write(str(int(current_location[0])) + ',' + str(int(current_location[1])))
            location_file.close()

    def _update_game_information(self):
        while not self._finish:
            print('[Thread-1] update_game_information thread loop...')

            # Read AoE2.net profile ID from configuration file.
            configuration_file = open(CONFIGURATION_FILE, 'r')
            AOE2NET_PROFILE_ID = int(configuration_file.read())
            configuration_file.close()
            print('[Thread-1] AOE2NET_PROFILE_ID:', AOE2NET_PROFILE_ID)

            # Get Last/Current match.
            print('[Thread-1] Fetching game data...')
            try:
                match_data = requests.get(AOE2NET_URL + 'player/lastmatch?game=aoe2de&profile_id={}'.format(AOE2NET_PROFILE_ID)).json()
            except Exception as error:
                print('[Thread-1] request timeout... retrying...:', error)
                self._event_refresh_game_information.wait(REFRESH_TIMEOUT)
                self._event_refresh_game_information.clear()
                continue
            new_match = Match(match_data, self._strings)
            print('[Thread-1] Fetching game data done!')

            if (self._current_match is None):
                print('[Thread-1] New match id: {}'.format(new_match.match_id))            
            else:
                print('[Thread-1] Current match id: {} - New match id: {}'.format(self._current_match.match_id, new_match.match_id))
            if (self._current_match is None) or (self._current_match.match_id != new_match.match_id):
                self._fetching_data = True

                loading_progress['current'] = 0
                loading_progress['steps'] = new_match.number_of_players * 2

                print('[Thread-1] Fetching rating information...')
                try:
                    new_match.fetch_rating_information()
                except Exception as error:
                    print('[Thread-1] request timeout... retrying...:', error)
                    self._event_refresh_game_information.wait(REFRESH_TIMEOUT)
                    self._event_refresh_game_information.clear()
                    continue
                print('[Thread-1] Fetching rating information done!')

                self._current_match_lock.acquire()
                self._current_match = new_match

                self._main_window_columns = [[], []]

                print('[Thread-1] Generating players rating information...')
                max_text_size = 0
                for player in self._current_match.players:
                    player.text = self._player_info_printer.print(
                        player.number,
                        player.name,
                        player.rating_1v1.rating,
                        player.rating_tg.rating,
                        player.team % 2
                    )
                    max_text_size = max_text_size if max_text_size > len(player.text) else len(player.text)

                for player in self._current_match.players:
                    column = player.team % 2

                    if column == LEFT:
                        player.text = ' ' * (max_text_size - len(player.text)) + player.text
                    else: # column == RIGH:
                        player.text = player.text + ' ' * (max_text_size - len(player.text))

                    text = sg.Text(
                        player.text,
                        pad=NO_PADDING,
                        background_color=TEXT_BG_COLOR,
                        justification=JUSTIFICATION[column],
                        font=(FONT_TYPE, FONT_SIZE),
                        text_color=COLOR_CODES[player.color_number]
                    )

                    self._main_window_columns[column].append([text])
                print('[Thread-1] Generating players rating information done!')

                if not self._finish:
                    print('[Thread-1] update_main_window = True')
                    self._update_main_window = True
                self._current_match_lock.release()

            if not self._finish:
                print('[Thread-1] Waiting for {} seconds to next update or for "Refresh now" event.'.format(REFRESH_TIMEOUT))
                self._event_refresh_game_information.wait(REFRESH_TIMEOUT)
                self._event_refresh_game_information.clear()


def previouse_version_cleanup():
    USERPROFILE = os.getenv('USERPROFILE')
    old_file = '{}\\aoe2de-mp-ratings_window-location.txt'.format(USERPROFILE)
    new_file = WINDOW_LOCATION_FILE.format(USERPROFILE)
    if os.path.exists(old_file):
        os.rename(old_file, new_file)


if __name__ == '__main__':
    previouse_version_cleanup()
    overlay = InGameRatingOverlay()
    overlay.run()