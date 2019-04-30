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