from __future__ import print_function
import pickle
import os.path
import math
import operator
import logging
import time

from logging.handlers import RotatingFileHandler
from googleapiclient.discovery import build
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from datetime import datetime

SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]
ELO_SPREADSHEET_ID = "1oz3eDPJ0tSyk98HbyjpvUHrxZPwRfzSBdK4DIGVyS4o"
RANK_SHEET_NAME = "Rank"
DATA_SHEET_NAME = "Data"
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
 
logger = logging.getLogger()
logger.setLevel(logging.INFO)

formatter = logging.Formatter('%(asctime)s :: %(levelname)s :: %(message)s')

file_handler = RotatingFileHandler('activity.log', 'a', 1000000, 1)
file_handler.setLevel(logging.DEBUG)
file_handler.setFormatter(formatter)
logger.addHandler(file_handler)
 
stream_handler = logging.StreamHandler()
stream_handler.setFormatter(formatter)
stream_handler.setLevel(logging.DEBUG)
logger.addHandler(stream_handler)
 
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

class PlayerInTournament:
    """
    Class used to sotre team for one tournament
    """
    def __init__(self, name, rank, elo):
        self.name = name
        self.rank = rank
        self.elo = elo

class Tournament:
    """
    Class used to store one tournament
    """
    players = []
    def add_player(self, name, rank, elo):
        """
        Add a team to this tournament
        """
        player = PlayerInTournament(name, rank, elo)
        self.players.append(player)

class Player:
    """
    Class used to store all the information about a player
    """
    def __init__(self, name, elo):
        self.name = name
        self.tournaments = {}
        self.elo_history = {}
        self.set_elo(elo, 'default', '')

    def __eq__(self, other):
        return self.name == other.name

    def add_tournament(self, tournament, rank):
        self.tournaments[tournament] = rank

    def set_elo(self, new_elo, tournament_name, tournament_rank):
        """
        tournament_name is the tournament we just computed
        """
        self.elo_history[tournament_name] = [round(new_elo, 2), tournament_rank]
        self.elo = round(new_elo, 2)

    def __str__(self):
        s = """
        Name : {}

        Elo : {}

        Tournaments : {}  

        Elo history : {}
        """.format(self.name, self.elo, self.tournaments, self.elo_history)
        return s

    # def __str__(self):
    #     s = """
    #     Name : {}
    #     Elo : {}
    #     """.format(self.name, self.elo)
    #     return s

def pretty_dict(d):
    """
    Print a dict as I want
    """
    pd = ""
    for key, value in d.items():
        if len(value) > 2:
            pd += "{}({}):{}({})\n".format(str(key), str(value[1]), str(value[0]), str(value[2]))
    return pd

def send_to_gsheet(service):
    sorted_elo_player = sorted(ALL_PLAYERS.values(), key=operator.attrgetter('elo'))
    sorted_elo_player.reverse()
    ALL_PLAYERS_GSHEET_FORMAT = []
    rank = 1
    longest_line =  0
    for player in sorted_elo_player:
        rank_string = str(rank)
        if len(player.tournaments) == 1:
            evolution = 0
        else:
            evolution = compute_evolution(player)
        if evolution > 0:
            rank_string+="(+"+str(evolution)+")"
        elif evolution < 0:
            rank_string+=("("+str(evolution)+")")
        else:
             rank_string+=("(=)")
        rank+=1
        pl = []
        pl.append(rank_string)
        pl.append(player.name)
        pl.append(str(player.elo).replace(".", ","))
        pl.append(len(player.tournaments))
        pl.append(pretty_dict(player.elo_history).replace(".", ","))

        if len(pl) > longest_line:
            longest_line = len(pl)
        ALL_PLAYERS_GSHEET_FORMAT.append(pl)

    RANK_RANGE = RANK_SHEET_NAME+"!A1:"+str(column_to_letter(longest_line))+str(len(ALL_PLAYERS_GSHEET_FORMAT))

    body = {
        'values': ALL_PLAYERS_GSHEET_FORMAT
    }

    clear_sheet(service, ELO_SPREADSHEET_ID, RANK_SHEET_NAME)
    result = service.spreadsheets().values().update(spreadsheetId=ELO_SPREADSHEET_ID, 
                                                    range=RANK_RANGE,
                                                    valueInputOption="RAW",
                                                    body=body).execute()
    logger.info("{0} cells updated.".format(result.get('updatedCells')))

def compute_evolution(player):
    """
    Return the evolution (Number of rank won or loss) of a player between his last and before last tournament
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
    clear_values_request_body = {}
    request = service.spreadsheets().values().clear(spreadsheetId=spreadsheet_id, range=sheet_name, body=clear_values_request_body)
    request.execute()

def column_to_letter(column):
    temp = ''
    letter = ''
    while column > 0:
        temp = int((column - 1) % 26)
        letter = chr(temp + 65) + letter
        column = (column - temp - 1) / 26
  
    return letter

def google_login():
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
    inter = []
    res = {}
    size_inter = 10
    max_x = int(2300/size_inter)
    min_x = int(800/size_inter)
    # init list inter
    for i in range(min_x, max_x):
        inter.append(i*size_inter)
    inter=inter[::-1]
    
    sorted_elo_team = sorted(ALL_PLAYERS.values(), key=operator.attrgetter('elo'))
    sorted_elo_team.reverse()
    for p in sorted_elo_team:
        for k in inter:
            if(p.elo > k):
                if k in res:
                    res[k]=res[k]+1
                else:
                    res[k] = 1
                break
            
    # boucher les trous
    for k in inter: 
        if k not in res:
            res[k] = 0

    #sorted_res= sorted(res.keys(), key=operator.itemgetter(0))

    sorted_res = sorted(res.items(), key=operator.itemgetter(0))
    x=[]
    y=[]
    for l in sorted_res:
        x.append(l[0])
        y.append(l[1])
    
    
    # print(y)
    # print(x)
    y_pos = np.arange(len(x))
    
    plt.bar(y_pos, y, align='center', alpha=0.5)
    plt.xticks(y_pos, x, rotation='vertical')
    
    plt.show()

def compute_elo_rank(tournament_name):
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
                rank+=1
                player.elo_history[tournament_name].append(rank)
        else:
            rank+=1
        previous_player_elo = player.elo

def fetch_data(service):
    column = 1
    tournaments = []
    while 1:
        DATA_RANGE = DATA_SHEET_NAME+"!"+column_to_letter(column)+":"+column_to_letter(column+1)
        
        result = service.spreadsheets().values().get(
            spreadsheetId=ELO_SPREADSHEET_ID, 
            range=DATA_RANGE).execute()
        
        column+=2
        
        rows = result.get('values') if result.get('values')is not None else 0
        if rows == 0:
            break

        logger.info("Fetched tournament : " + rows[0][0])

        tournament = {}
        tournament["tournament_name"] = rows[0][0]
        tournament["mode"] = rows[0][1]
        tournament["ranking"] = []
        for team in rows[1:]:
            tournament["ranking"].append({"rank": team[0], "players_name": team[1].split(",")})

        tournaments.append(tournament)
    
    return tournaments

def main():
    start = time.time()
    creds = google_login()
    service = build('sheets', 'v4', credentials=creds, cache_discovery=False )

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
    logger.info(str(round(end - start, 2)) + " s")   

if __name__ == '__main__':
    main()
