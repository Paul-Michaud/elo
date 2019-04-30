from .playerintournament import PlayerInTournament

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