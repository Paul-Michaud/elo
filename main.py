"""
Main
"""
from __future__ import print_function
import pickle
import os.path
import math
import operator
import time
import matplotlib.pyplot as plt
import numpy as np

from googleapiclient.discovery import build
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request

from elo.classes import Tournament
from elo.classes import Player
from log import logger



SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]
ELO_SPREADSHEET_ID = "1oz3eDPJ0tSyk98HbyjpvUHrxZPwRfzSBdK4DIGVyS4o"
RANK_SHEET_NAME = "Rank"
DATA_SHEET_NAME = "Data_test"
_MAXSIZE = 100
_MINBUFFEREDELO = 1900
_MAXBUFFEREDELO = 3200
_KMAX = 8.4
_BUFFEREDELOSLOPE = -.28 / 1300
_EXPODENTIALRATE = 800
_WIN = 0.8
_LOSS = 0.0
_DEFELO = 1500.0

ALL_PLAYERS = {}


def compute_elo(teams, tournament, mode):
    """
    Compute elo for one tournament
    """
    nb_team = len(teams)

    # If you want the tournament mode to have impact on the elo fluctuation
    # or the number of team attending
    if mode == "solo":
        k_slope = 3 * nb_team / 175
        k = 8.4 - k_slope
    elif mode == "duo":
        k_slope = 3 * nb_team / 175
        k = 8.4 - k_slope
    elif mode == "squad":
        k_slope = 3 * nb_team / 175
        k = 8.4 - k_slope

    for i in teams:
        # teams with higher elo receive lower K values for stability
        multi = 1
        if i.elo > _MINBUFFEREDELO and i.elo < _MAXBUFFEREDELO:
            multi = _WIN + (_BUFFEREDELOSLOPE) * (i.elo - _MINBUFFEREDELO)
        k = multi * k

        for j in teams:
            if i.name != j.name and i.rank != j.rank:
                if i.rank < j.rank:
                    score = _WIN
                else:
                    score = _LOSS

                change = j.elo - i.elo
                # Expected is the expected score based off each teams elo
                expected_score = 1 / (1.0 + math.pow(10.0, (change) / _EXPODENTIALRATE))
                i.elo += k * (score - expected_score)

        if i.elo < 0:
            i.elo = 0

        ALL_PLAYERS[i.name].set_elo(i.elo, tournament, i.rank)


def pretty_dict(not_pretty_dict):
    """
    Print a dict as I want
    """
    prettified_dict = ""
    for key, value in not_pretty_dict.items():
        if len(value) > 2:
            prettified_dict += "{}({}):{}({})\n".format(str(key), str(value[1]), str(value[0]), str(value[2]))
    return prettified_dict

def send_to_gsheet(service):
    """
    Send data to gsheet
    """
    sorted_elo_player = sorted(ALL_PLAYERS.values(), key=operator.attrgetter('elo'))
    sorted_elo_player.reverse()
    all_players_gsheet_format = []
    rank = 1
    longest_line = 0
    for player in sorted_elo_player:
        rank_string = str(rank)
        if len(player.tournaments) == 1:
            evolution = 0
        else:
            evolution = compute_evolution(player)
        if evolution > 0:
            rank_string += "(+"+str(evolution)+")"
        elif evolution < 0:
            rank_string += ("("+str(evolution)+")")
        else:
            rank_string += ("(=)")
        rank += 1
        player_line = []
        player_line.append(rank_string)
        player_line.append(player.name)
        player_line.append(str(player.elo).replace(".", ","))
        player_line.append(len(player.tournaments))
        player_line.append(pretty_dict(player.elo_history).replace(".", ","))

        if len(player_line) > longest_line:
            longest_line = len(player_line)
        all_players_gsheet_format.append(player_line)

    rank_range = RANK_SHEET_NAME+"!A1:"+str(column_to_letter(longest_line))+str(len(all_players_gsheet_format))

    body = {
        'values': all_players_gsheet_format
    }

    clear_sheet(service, ELO_SPREADSHEET_ID, RANK_SHEET_NAME)
    result = service.spreadsheets().values().update(spreadsheetId=ELO_SPREADSHEET_ID,
                                                    range=rank_range,
                                                    valueInputOption="RAW",
                                                    body=body).execute()
    logger.info("%s cells updated.", result.get('updatedCells'))

def compute_evolution(player):
    """
    Return the evolution (Number of rank won or loss) of a player
    between his last and before last tournament
    """
    history = player.elo_history
    last_event = None
    before_last_event = None
    for event in history:
        before_last_event = last_event
        last_event = event
    #Index 2 is the overall rank in the full ranking
    evolution = history[before_last_event][2] - history[last_event][2]
    return evolution

def clear_sheet(service, spreadsheet_id, sheet_name):
    """
    Clean a gsheet
    """
    clear_values_request_body = {}
    request = service.spreadsheets().values().clear(spreadsheetId=spreadsheet_id, range=sheet_name, body=clear_values_request_body)
    request.execute()

def column_to_letter(column):
    """
    Return a gsheet column number as letter notation
    """
    temp = ''
    letter = ''
    while column > 0:
        temp = int((column - 1) % 26)
        letter = chr(temp + 65) + letter
        column = (column - temp - 1) / 26

    return letter

def google_login():
    """
    Login to google api
    """
    creds = None
    # The file token.pickle stores the user's access and refresh tokens, and is
    # created automatically when the authorization flow completes for the first
    # time.
    if os.path.exists('token.pickle'):
        with open('token.pickle', 'rb') as token:
            creds = pickle.load(token)
    # If there are no (valid) credentials available, let the user log in.
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(
                'credentials.json', SCOPES)
            creds = flow.run_local_server()
        # Save the credentials for the next run
        with open('token.pickle', 'wb') as token:
            pickle.dump(creds, token)

    return creds

def analyze():
    """
    Display the curve of the elo rank
    """
    inter = []
    res = {}
    size_inter = 10
    max_x = int(2300/size_inter)
    min_x = int(800/size_inter)
    # init list inter
    for i in range(min_x, max_x):
        inter.append(i*size_inter)
    inter = inter[::-1]

    sorted_elo_team = sorted(ALL_PLAYERS.values(), key=operator.attrgetter('elo'))
    sorted_elo_team.reverse()
    for player in sorted_elo_team:
        for elo_value in inter:
            if player.elo > elo_value:
                if elo_value in res:
                    res[elo_value] = res[elo_value]+1
                else:
                    res[elo_value] = 1
                break

    # boucher les trous
    for elo_value in inter:
        if elo_value not in res:
            res[elo_value] = 0

    sorted_res = sorted(res.items(), key=operator.itemgetter(0))
    x = []
    y = []
    for l in sorted_res:
        x.append(l[0])
        y.append(l[1])

    y_pos = np.arange(len(x))

    plt.bar(y_pos, y, align='center', alpha=0.5)
    plt.xticks(y_pos, x, rotation='vertical')

    plt.show()

def compute_elo_rank(tournament_name):
    """
    Compute the overall elo ranking after tournament_name
    """
    sorted_elo_player = sorted(ALL_PLAYERS.values(), key=operator.attrgetter('elo'))
    sorted_elo_player.reverse()
    previous_player_elo = None
    rank = 1
    for player in sorted_elo_player:
        if tournament_name in player.elo_history:
            if previous_player_elo is None:
                player.elo_history[tournament_name].append(rank)
            elif previous_player_elo == player.elo:
                player.elo_history[tournament_name].append(rank)
            else:
                rank += 1
                player.elo_history[tournament_name].append(rank)
        else:
            rank += 1
        previous_player_elo = player.elo

def fetch_data(service):
    """
    Grab the data from gsheet
    """
    column = 1
    tournaments = []
    while 1:
        data_range = DATA_SHEET_NAME+"!"+column_to_letter(column)+":"+column_to_letter(column+1)

        result = service.spreadsheets().values().get(
            spreadsheetId=ELO_SPREADSHEET_ID,
            range=data_range).execute()

        column += 2

        rows = result.get('values') if result.get('values')is not None else 0
        if rows == 0:
            break

        logger.info("Fetched tournament : %s", rows[0][0])

        tournament = {}
        tournament["tournament_name"] = rows[0][0]
        tournament["mode"] = rows[0][1]
        tournament["ranking"] = []
        for team in rows[1:]:
            tournament["ranking"].append({"rank": team[0], "players_name": team[1].split(",")})

        tournaments.append(tournament)

    return tournaments

def main():
    """
    Main
    """
    start = time.time()
    creds = google_login()
    service = build('sheets', 'v4', credentials=creds, cache_discovery=False)

    logger.info("Starting to fetch data")

    tournaments = fetch_data(service)

    logger.info("Finished fetching data")

    #Init player list
    for tournament in tournaments:
        tn_name = tournament["tournament_name"]
        for team in tournament["ranking"]:
            for player in team["players_name"]:
                if player in ALL_PLAYERS:
                    ALL_PLAYERS[player].add_tournament(tn_name, team["rank"])
                else:
                    ALL_PLAYERS[player] = Player(player, _DEFELO)
                    ALL_PLAYERS[player].add_tournament(tn_name, team["rank"])

    logger.info("Starting elo computation")

    # compute elo for each tournament
    for tournament in tournaments:
        tn = Tournament()
        tn.players = []
        tn_name = tournament["tournament_name"]
        tn_mode = tournament["mode"]
        for team in tournament["ranking"]:
            for player in team["players_name"]:
                player_rank = int(team["rank"])
                player_elo = ALL_PLAYERS[player].elo
                tn.add_player(player, player_rank, player_elo)
        compute_elo(tn.players, tn_name, tn_mode)
        compute_elo_rank(tn_name)

    logger.info("Starting to send data to gsheet")

    send_to_gsheet(service)

    end = time.time()

    logger.info("End")
    logger.info("%s s", str(round(end - start, 2)))

if __name__ == '__main__':
    main()
