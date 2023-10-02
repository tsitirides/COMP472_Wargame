from __future__ import annotations
import argparse
import copy
from datetime import datetime
from enum import Enum
from dataclasses import dataclass, field, asdict
from time import sleep
from typing import Tuple, TypeVar, Type, Iterable, ClassVar
import random
import requests
import dataclasses

# maximum and minimum values for our heuristic scores (usually represents an end of game condition)
MAX_HEURISTIC_SCORE = 2000000000
MIN_HEURISTIC_SCORE = -2000000000

class UnitType(Enum):
    """Every unit type."""
    AI = 0
    Tech = 1
    Virus = 2
    Program = 3
    Firewall = 4

class Player(Enum):
    """The 2 players."""
    Attacker = 0
    Defender = 1

    def next(self) -> Player:
        """The next (other) player."""
        if self is Player.Attacker:
            return Player.Defender
        else:
            return Player.Attacker

class GameType(Enum):
    AttackerVsDefender = 0
    AttackerVsComp = 1
    CompVsDefender = 2
    CompVsComp = 3

##############################################################################################################

@dataclass(slots=True)
class Unit:
    player: Player = Player.Attacker
    type: UnitType = UnitType.Program
    health : int = 9
    # class variable: damage table for units (based on the unit type constants in order)
    damage_table : ClassVar[list[list[int]]] = [
        [3,3,3,3,1], # AI
        [1,1,6,1,1], # Tech
        [9,6,1,6,1], # Virus
        [3,3,3,3,1], # Program
        [1,1,1,1,1], # Firewall
    ]
    # class variable: repair table for units (based on the unit type constants in order)
    repair_table : ClassVar[list[list[int]]] = [
        [0,1,1,0,0], # AI
        [3,0,0,3,3], # Tech
        [0,0,0,0,0], # Virus
        [0,0,0,0,0], # Program
        [0,0,0,0,0], # Firewall
    ]

    def is_alive(self) -> bool:
        """Are we alive ?"""
        return self.health > 0

    def mod_health(self, health_delta : int):
        """Modify this unit's health by delta amount."""
        self.health += health_delta
        if self.health < 0:
            self.health = 0
        elif self.health > 9:
            self.health = 9

    def to_string(self) -> str:
        """Text representation of this unit."""
        p = self.player.name.lower()[0]
        t = self.type.name.upper()[0]
        return f"{p}{t}{self.health}"
    
    def __str__(self) -> str:
        """Text representation of this unit."""
        return self.to_string()
    
    def damage_amount(self, target: Unit) -> int:
        """How much can this unit damage another unit."""
        amount = self.damage_table[self.type.value][target.type.value]
        if target.health - amount < 0:
            return target.health
        return amount

    def repair_amount(self, target: Unit) -> int:
        """How much can this unit repair another unit."""
        amount = self.repair_table[self.type.value][target.type.value]
        if target.health + amount > 9:
            return 9 - target.health
        return amount

##############################################################################################################

@dataclass(slots=True)
class Coord:
    """Representation of a game cell coordinate (row, col)."""
    row : int = 0
    col : int = 0

    def col_string(self) -> str:
        """Text representation of this Coord's column."""
        coord_char = '?'
        if self.col < 16:
                coord_char = "0123456789abcdef"[self.col]
        return str(coord_char)

    def row_string(self) -> str:
        """Text representation of this Coord's row."""
        coord_char = '?'
        if self.row < 26:
                coord_char = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"[self.row]
        return str(coord_char)

    def to_string(self) -> str:
        """Text representation of this Coord."""
        return self.row_string()+self.col_string()
    
    def __str__(self) -> str:
        """Text representation of this Coord."""
        return self.to_string()
    
    def clone(self) -> Coord:
        """Clone a Coord."""
        return copy.copy(self)

    def iter_range(self, dist: int) -> Iterable[Coord]:
        """Iterates over Coords inside a rectangle centered on our Coord."""
        for row in range(self.row-dist,self.row+1+dist):
            for col in range(self.col-dist,self.col+1+dist):
                yield Coord(row,col)

    def iter_adjacent(self) -> Iterable[Coord]:
        """Iterates over adjacent Coords."""
        yield Coord(self.row-1,self.col)
        yield Coord(self.row,self.col-1)
        yield Coord(self.row+1,self.col)
        yield Coord(self.row,self.col+1)

    @classmethod
    def from_string(cls, s : str) -> Coord | None:
        """Create a Coord from a string. ex: D2."""
        s = s.strip()
        for sep in " ,.:;-_":
                s = s.replace(sep, "")
        if (len(s) == 2):
            coord = Coord()
            coord.row = "ABCDEFGHIJKLMNOPQRSTUVWXYZ".find(s[0:1].upper())
            coord.col = "0123456789abcdef".find(s[1:2].lower())
            return coord
        else:
            return None

##############################################################################################################

@dataclass(slots=True)
class CoordPair:
    """Representation of a game move or a rectangular area via 2 Coords."""
    src : Coord = field(default_factory=Coord)
    dst : Coord = field(default_factory=Coord)

    def to_string(self) -> str:
        """Text representation of a CoordPair."""
        return self.src.to_string()+" "+self.dst.to_string()
    
    def __str__(self) -> str:
        """Text representation of a CoordPair."""
        return self.to_string()

    def clone(self) -> CoordPair:
        """Clones a CoordPair."""
        return copy.copy(self)

    def iter_rectangle(self) -> Iterable[Coord]:
        """Iterates over cells of a rectangular area."""
        for row in range(self.src.row,self.dst.row+1):
            for col in range(self.src.col,self.dst.col+1):
                yield Coord(row,col)

    @classmethod
    def from_quad(cls, row0: int, col0: int, row1: int, col1: int) -> CoordPair:
        """Create a CoordPair from 4 integers."""
        return CoordPair(Coord(row0,col0),Coord(row1,col1))
    
    @classmethod
    def from_dim(cls, dim: int) -> CoordPair:
        """Create a CoordPair based on a dim-sized rectangle."""
        return CoordPair(Coord(0,0),Coord(dim-1,dim-1))
    
    @classmethod
    def from_string(cls, s : str) -> CoordPair | None:
        """Create a CoordPair from a string. ex: A3 B2"""
        s = s.strip()
        for sep in " ,.:;-_":
                s = s.replace(sep, "")
        if (len(s) == 4):
            coords = CoordPair()
            coords.src.row = "ABCDEFGHIJKLMNOPQRSTUVWXYZ".find(s[0:1].upper())
            coords.src.col = "0123456789abcdef".find(s[1:2].lower())
            coords.dst.row = "ABCDEFGHIJKLMNOPQRSTUVWXYZ".find(s[2:3].upper())
            coords.dst.col = "0123456789abcdef".find(s[3:4].lower())
            return coords
        else:
            return None

##############################################################################################################
# Saving game trace

@dataclass(slots=True)
class Options:
    """Representation of the game options."""
    dim: int = 5
    max_depth : int | None = 4
    min_depth : int | None = 2
    max_time : float | None = 5.0
    game_type : GameType = GameType.AttackerVsDefender
    #alpha beta default set to False for now
    alpha_beta : bool = False
    max_turns : int | None = 100
    randomize_moves : bool = True
    broker : str | None = None


##############################################################################################################

@dataclass(slots=True)
class Stats:
    """Representation of the global game statistics."""
    evaluations_per_depth : dict[int,int] = field(default_factory=dict)
    total_seconds: float = 0.0

##############################################################################################################

@dataclass(slots=True)
class Game:
    """Representation of the game state."""
    board: list[list[Unit | None]] = field(default_factory=list)
    next_player: Player = Player.Attacker
    turns_played : int = 0
    options: Options = field(default_factory=Options)
    stats: Stats = field(default_factory=Stats)
    _attacker_has_ai : bool = True
    _defender_has_ai : bool = True

    def set_game_type_mode(self, game_type: GameType):
        """Sets the game type mode.

        Args:
            game_type (GameType): The desired game type mode.
        """
        self.options.game_type = game_type
        
        # Reset to default
        self._attacker_has_ai = False
        self._defender_has_ai = False
        
        if game_type == GameType.AttackerVsDefender:
            pass  # Both are human players, so nothing to set
        elif game_type == GameType.AttackerVsComp:
            self._attacker_has_ai = True
        elif game_type == GameType.CompVsDefender:
            self._defender_has_ai = True
        elif game_type == GameType.CompVsComp:
            self._attacker_has_ai = True
            self._defender_has_ai = True
        else:
            raise ValueError("Unknown game type mode.")
    
    def start_game(self):
        """Starts the game. If game type is not human-human, it returns an error message."""
        if self.options.game_type != GameType.AttackerVsDefender:
            return "Error: Only human-human game type is allowed to start."
        
        # The logic to start the game for human-human players goes here


    def __post_init__(self):
        """Automatically called after class init to set up the default board state."""
        dim = self.options.dim
        self.board = [[None for _ in range(dim)] for _ in range(dim)]
        md = dim-1
        self.set(Coord(0,0),Unit(player=Player.Defender,type=UnitType.AI))
        self.set(Coord(1,0),Unit(player=Player.Defender,type=UnitType.Tech))
        self.set(Coord(0,1),Unit(player=Player.Defender,type=UnitType.Tech))
        self.set(Coord(2,0),Unit(player=Player.Defender,type=UnitType.Firewall))
        self.set(Coord(0,2),Unit(player=Player.Defender,type=UnitType.Firewall))
        self.set(Coord(1,1),Unit(player=Player.Defender,type=UnitType.Program))
        self.set(Coord(md,md),Unit(player=Player.Attacker,type=UnitType.AI))
        self.set(Coord(md-1,md),Unit(player=Player.Attacker,type=UnitType.Virus))
        self.set(Coord(md,md-1),Unit(player=Player.Attacker,type=UnitType.Virus))
        self.set(Coord(md-2,md),Unit(player=Player.Attacker,type=UnitType.Program))
        self.set(Coord(md,md-2),Unit(player=Player.Attacker,type=UnitType.Program))
        self.set(Coord(md-1,md-1),Unit(player=Player.Attacker,type=UnitType.Firewall))

    def clone(self) -> Game:
        """Make a new copy of a game for minimax recursion.

        Shallow copy of everything except the board (options and stats are shared).
        """
        new = copy.copy(self)
        new.board = copy.deepcopy(self.board)
        return new

    def is_empty(self, coord : Coord) -> bool:
        """Check if contents of a board cell of the game at Coord is empty (must be valid coord)."""
        return self.board[coord.row][coord.col] is None

    def get(self, coord : Coord) -> Unit | None:
        """Get contents of a board cell of the game at Coord."""
        if self.is_valid_coord(coord):
            return self.board[coord.row][coord.col]
        else:
            return None

    def set(self, coord : Coord, unit : Unit | None):
        """Set contents of a board cell of the game at Coord."""
        if self.is_valid_coord(coord):
            self.board[coord.row][coord.col] = unit

    def remove_dead(self, coord: Coord):
        """Remove unit at Coord if dead."""
        unit = self.get(coord)
        if unit is not None and not unit.is_alive():
            self.set(coord,None)
            if unit.type == UnitType.AI:
                if unit.player == Player.Attacker:
                    self._attacker_has_ai = False
                else:
                    self._defender_has_ai = False

    def mod_health(self, coord : Coord, health_delta : int):
        """Modify health of unit at Coord (positive or negative delta)."""
        target = self.get(coord)
        if target is not None:
            target.mod_health(health_delta)
            self.remove_dead(coord)

            #Mod health happens after: first we gotta create an if to check if the coord we are trying to heal is a friendly
            #if attack, we gotta check if the coord we are trying to attack is indeed an enemy (or, engage in self-destruct)

    def is_valid_move(self, coords : CoordPair) -> bool:
        """Validate a move expressed as a CoordPair."""
        if not self.is_valid_coord(coords.src) or not self.is_valid_coord(coords.dst):
            return False

        # Self Destruct
        if coords.src == coords.dst:
            return True

        unit = self.get(coords.src)

        # if the source unit DNE or is not your player => invalid
        if unit is None or unit.player != self.next_player:
            return False

        # difference of col to check if valid adjacent move
        r_diff = abs(coords.src.row - coords.dst.row)
        c_diff = abs(coords.src.col - coords.dst.col)

        # Movement can only be adjacent
        if r_diff > 1 or c_diff > 1:
            return False
        # Diagonal move
        if r_diff >= 1 and c_diff >= 1:
            return False

        ##############################################################################################################
        # Check for units engaged in combat
        ##############################################################################################################
        for adjacent_coord in coords.src.iter_adjacent():
            adjacent_unit = self.get(adjacent_coord)
            if adjacent_unit and adjacent_unit.player != unit.player:
                # Engaged in combat => checks if space it is trying to move at is empty,
                # if not => attack / repair therefore move is valid
                if unit.type in [UnitType.AI, UnitType.Firewall, UnitType.Program] and self.is_empty(coords.dst):
                    return False

        ##############################################################################################################
        # This block checks for unit player type (attacker or defender)
        # It will determine the directional movements it is capable of doing
        ##############################################################################################################
        if unit.player == Player.Attacker:
            if unit.type in [UnitType.AI, UnitType.Firewall, UnitType.Program]:
                # AI, Firewall, Program can only move up or left
                if coords.dst.row > coords.src.row or coords.dst.col > coords.src.col:
                    return False
        # Defender
        else:
            if unit.type in [UnitType.AI, UnitType.Firewall, UnitType.Program]:
                # AI, Firewall, and Program can only move down or right.
                if coords.dst.row < coords.src.row or coords.dst.col < coords.src.col:
                    return False

        # all moves valid
        return True

    def perform_move(self, coords : CoordPair) -> Tuple[bool,str]:
        """Validate and perform a move expressed as a CoordPair."""
        if self.is_valid_move(coords):
            source_unit = self.get(coords.src)
            # Self Destruct
            if coords.dst == coords.src:
                self.self_destruct(coords, source_unit)
                return True, "Self Destructed"
            # attack or repair
            if not self.is_empty(coords.dst):
                target_unit = self.get(coords.dst)
                if target_unit.player == self.next_player:  # Friendly unit => repair
                    repair_amount = source_unit.repair_amount(target_unit)
                    if repair_amount == 0 or not target_unit.health < 9:
                        return False, "Invalid Move"
                    self.mod_health(coords.dst, repair_amount)
                    return True, f"Repaired unit. New health: {target_unit.health}"
                else:  # Attack
                    damage_amount = source_unit.damage_amount(target_unit)
                    self.mod_health(coords.dst, -damage_amount)
                    # bi-directional combat
                    damage_amount = target_unit.damage_amount(source_unit)
                    self.mod_health(coords.src, -damage_amount)
                    return True, f"Attacked unit. New health: {target_unit.health}"
            else:
                self.set(coords.dst,self.get(coords.src))
                self.set(coords.src,None)
                return True, ""
        return False, "invalid move"

    def self_destruct(self, coords: CoordPair, source_unit: Unit):
        """Method to self-destruct, damages all surrounding units within range of 1"""
        self.mod_health(coords.src, -source_unit.health)
        for adjacent_coord in coords.src.iter_range(1):
            adjacent_unit = self.get(adjacent_coord)
            if adjacent_unit:
                self.mod_health(adjacent_coord, -2)


    def next_turn(self):
        """Transitions game to the next turn."""
        self.next_player = self.next_player.next()
        self.turns_played += 1

    def to_string(self) -> str:
        """Pretty text representation of the game."""
        dim = self.options.dim
        output = ""
        output += f"Next player: {self.next_player.name}\n"
        output += f"Turns played: {self.turns_played}\n"
        coord = Coord()
        output += "\n   "
        for col in range(dim):
            coord.col = col
            label = coord.col_string()
            output += f"{label:^3} "
        output += "\n"
        for row in range(dim):
            coord.row = row
            label = coord.row_string()
            output += f"{label}: "
            for col in range(dim):
                coord.col = col
                unit = self.get(coord)
                if unit is None:
                    output += " .  "
                else:
                    output += f"{str(unit):^3} "
            output += "\n"
        return output
    
    def board_config_to_string(self) -> str:
        dim = self.options.dim
        coord = Coord()
        output = ""
        output += "\n   "
        for col in range(dim):
            coord.col = col
            label = coord.col_string()
            output += f"{label:^3} "
        output += "\n"
        for row in range(dim):
            coord.row = row
            label = coord.row_string()
            output += f"{label}: "
            for col in range(dim):
                coord.col = col
                unit = self.get(coord)
                if unit is None:
                    output += " .  "
                else:
                    output += f"{str(unit):^3} "
            output += "\n"
        return output

    def __str__(self) -> str:
        """Default string representation of a game."""
        return self.to_string()
    
    def is_valid_coord(self, coord: Coord) -> bool:
        """Check if a Coord is valid within out board dimensions."""
        dim = self.options.dim
        if coord.row < 0 or coord.row >= dim or coord.col < 0 or coord.col >= dim:
            return False
        return True

    def read_move(self) -> CoordPair:
        """Read a move from keyboard and return as a CoordPair."""
        while True:
            s = input(F'Player {self.next_player.name}, enter your move: ')
            coords = CoordPair.from_string(s)
            if coords is not None and self.is_valid_coord(coords.src) and self.is_valid_coord(coords.dst):
                return coords
            else:
                print('Invalid coordinates! Try again.')
    
    def human_turn(self) -> str:
        """Human player plays a move (or get via broker)."""
        if self.options.broker is not None:
            print("Getting next move with auto-retry from game broker...")
            while True:
                mv = self.get_move_from_broker()
                if mv is not None:
                    (success,result) = self.perform_move(mv)
                    print(f"Broker {self.next_player.name}: ",end='')
                    print(result)
                    if success:
                        self.next_turn()
                        break
                sleep(0.1)
        else:
            while True:
                mv = self.read_move()
                (success,result) = self.perform_move(mv)
                if success:
                    print(f"Player {self.next_player.name}: ",end='')
                    print(result)
                    self.next_turn()
                    break
                else:
                    print("The move is not valid! Try again.")

    def computer_turn(self) -> CoordPair | None:
        """Computer plays a move."""
        mv = self.suggest_move()
        if mv is not None:
            (success,result) = self.perform_move(mv)
            if success:
                print(f"Computer {self.next_player.name}: ",end='')
                print(result)
                self.next_turn()
        return mv

    def player_units(self, player: Player) -> Iterable[Tuple[Coord,Unit]]:
        """Iterates over all units belonging to a player."""
        for coord in CoordPair.from_dim(self.options.dim).iter_rectangle():
            unit = self.get(coord)
            if unit is not None and unit.player == player:
                yield (coord,unit)

    def is_finished(self) -> bool:
        """Check if the game is over."""
        return self.has_winner() is not None

    def has_winner(self) -> Player | None:
        """Check if the game is over and returns winner"""
        if self.options.max_turns is not None and self.turns_played >= self.options.max_turns:
            return Player.Defender
        elif self._attacker_has_ai:
            if self._defender_has_ai:
                return None
            else:
                return Player.Attacker    
        elif self._defender_has_ai:
            return Player.Defender

    def move_candidates(self) -> Iterable[CoordPair]:
        """Generate valid move candidates for the next player."""
        move = CoordPair()
        for (src,_) in self.player_units(self.next_player):
            move.src = src
            for dst in src.iter_adjacent():
                move.dst = dst
                if self.is_valid_move(move):
                    yield move.clone()
            move.dst = src
            yield move.clone()

    def random_move(self) -> Tuple[int, CoordPair | None, float]:
        """Returns a random move."""
        move_candidates = list(self.move_candidates())
        random.shuffle(move_candidates)
        if len(move_candidates) > 0:
            return (0, move_candidates[0], 1)
        else:
            return (0, None, 0)

    def suggest_move(self) -> CoordPair | None:
        """Suggest the next move using minimax alpha beta. TODO: REPLACE RANDOM_MOVE WITH PROPER GAME LOGIC!!!"""
        start_time = datetime.now()
        (score, move, avg_depth) = self.random_move()
        elapsed_seconds = (datetime.now() - start_time).total_seconds()
        self.stats.total_seconds += elapsed_seconds
        print(f"Heuristic score: {score}")
        print(f"Average recursive depth: {avg_depth:0.1f}")
        print(f"Evals per depth: ",end='')
        for k in sorted(self.stats.evaluations_per_depth.keys()):
            print(f"{k}:{self.stats.evaluations_per_depth[k]} ",end='')
        print()
        total_evals = sum(self.stats.evaluations_per_depth.values())
        if self.stats.total_seconds > 0:
            print(f"Eval perf.: {total_evals/self.stats.total_seconds/1000:0.1f}k/s")
        print(f"Elapsed time: {elapsed_seconds:0.1f}s")
        return move

    def post_move_to_broker(self, move: CoordPair):
        """Send a move to the game broker."""
        if self.options.broker is None:
            return
        data = {
            "from": {"row": move.src.row, "col": move.src.col},
            "to": {"row": move.dst.row, "col": move.dst.col},
            "turn": self.turns_played
        }
        try:
            r = requests.post(self.options.broker, json=data)
            if r.status_code == 200 and r.json()['success'] and r.json()['data'] == data:
                # print(f"Sent move to broker: {move}")
                pass
            else:
                print(f"Broker error: status code: {r.status_code}, response: {r.json()}")
        except Exception as error:
            print(f"Broker error: {error}")

    def get_move_from_broker(self) -> CoordPair | None:
        """Get a move from the game broker."""
        if self.options.broker is None:
            return None
        headers = {'Accept': 'application/json'}
        try:
            r = requests.get(self.options.broker, headers=headers)
            if r.status_code == 200 and r.json()['success']:
                data = r.json()['data']
                if data is not None:
                    if data['turn'] == self.turns_played+1:
                        move = CoordPair(
                            Coord(data['from']['row'],data['from']['col']),
                            Coord(data['to']['row'],data['to']['col'])
                        )
                        print(f"Got move from broker: {move}")
                        return move
                    else:
                        # print("Got broker data for wrong turn.")
                        # print(f"Wanted {self.turns_played+1}, got {data['turn']}")
                        pass
                else:
                    # print("Got no data from broker")
                    pass
            else:
                print(f"Broker error: status code: {r.status_code}, response: {r.json()}")
        except Exception as error:
            print(f"Broker error: {error}")
        return None

##############################################################################################################

def show_menu():
    print("Choose a game type:")
    print("0. Attacker vs Defender")
    print("1. Attacker vs Computer")
    print("2. Computer vs Defender")
    print("3. Computer vs Computer")

    # choice = input("Enter your choice (0/1/2/3): ")

    while True:
        choice = input("Enter your choice (0/1/2/3): ")
        if choice in ["0", "1", "2", "3"]:
            if choice != "0":
                print("This game mode is not yet implemented. Please choose the manual game mode.")
                continue
            break
        else:
            print("Invalid choice. Please choose between 0,1, 2, or 3.")

    #The if statement menu options are for once we have implemented the AI part; ignore for D1
    # if choice == "0":
    #     return "manual"
    # elif choice == "1":
    #    print("not yet implemented")
    #    return show_menu()
    # elif choice == "2":
    #     print("not yet implemented")
    #     return show_menu()
    # elif choice == "3":
    #     print("not yet implemented")
    #     return show_menu()
    # else:
    #     print("Invalid choice. Please select again.")
    #     return show_menu()
    
    # Get max_turns value
    while True:
        try:
            max_turns = int(input("Enter maximum number of turns: "))
            break
        except ValueError:
            print("Please enter a valid integer for maximum number of turns.")

    # Get max_time value
    while True:
        try:
            max_time = float(input("Enter timeout in seconds: "))
            break
        except ValueError:
            print("Please enter a valid float value for timeout.")

    return GameType.AttackerVsDefender, max_turns, max_time


def generate_filename(options: Options) -> str:
    b = "true" if options.alpha_beta else "false"
    t = str(options.max_time)
    m = str(options.max_turns)
    return f"gameTrace-{b}-{t}-{m}.txt"

# Swapped below implementation into main
# def save_options_to_txt(options: Options, game: Game, filename="gameTrace-{b}-{t}-{m}.txt"):
#     with open(filename, 'w') as file:
#          # Output game options
#         file.write("Game Options:\n")
#         for field in dataclasses.fields(options):
#             attribute_name = field.name
#             attribute_value = getattr(options, attribute_name)
#             file.write(f"{attribute_name}: {attribute_value}\n")
#             #play modes are not included yet since only H vs H exists; TODO implement this once we have the AI version working
#         # Output board configuration
#         file.write("\nInitial Board Configuration:\n")
#         for row in game.board:
#             row_str = ', '.join([str(unit) if unit is not None else 'None' for unit in row])
#             file.write(row_str + "\n")

def main():
    game_type, max_turns, max_time = show_menu()
    # parse command line arguments
    parser = argparse.ArgumentParser(
        prog='ai_wargame',
        formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    parser.add_argument('--max_depth', type=int, help='maximum search depth')
    # parser.add_argument('--max_time', type=float, help='maximum search time')
    # parser.add_argument('--game_type', type=str, default="manual", help='game type: auto|attacker|defender|manual')
    parser.add_argument('--broker', type=str, help='play via a game broker')
    args = parser.parse_args()
    # args = parser.parse_args(args=[
    #     '--game_type', game_type,
    #     '--max_time', str(max_time),
    #     '--max_turns', str(max_turns)
    # ])

    # parse the game type (commented it out because new menu implementation that is NOT via the command line)
    # if args.game_type == "attacker":
    #     game_type = GameType.AttackerVsComp
    # elif args.game_type == "defender":
    #     game_type = GameType.CompVsDefender
    # elif args.game_type == "manual":
    #     game_type = GameType.AttackerVsDefender
    # else:
    #     game_type = GameType.CompVsComp

    # set up game options
    options = Options(max_turns=max_turns, max_time=max_time, game_type=game_type)

    # override class defaults via command line options (commented out in case we need this sort of menu implementation instead later)
    # if args.max_depth is not None:
    #     options.max_depth = args.max_depth
    # if args.max_time is not None:
    #     options.max_time = args.max_time
    # if args.broker is not None:
    #     options.broker = args.broker

    # create a new game
    game = Game(options=options)
    game.set_game_type_mode(game_type)
    #TODO set max time and max turns (though max time will not affect anything for D1)
    # Determine the filename based on game options
    filename = generate_filename(game.options)
    #  # Save to text file
    # save_options_to_txt(game.options, game)
    
    with open(filename, 'w') as file:
         # Output game options
        file.write("Game Options:\n")
        for field in dataclasses.fields(options):
            attribute_name = field.name
            attribute_value = getattr(options, attribute_name)
            file.write(f"{attribute_name}: {attribute_value}\n")
            #play modes are not included yet since only H vs H exists; TODO implement this once we have the AI version working
        # Output board configuration
        file.write("\nInitial Board Configuration:\n")
        for row in game.board:
            row_str = ', '.join([str(unit) if unit is not None else 'None' for unit in row])
            file.write(row_str + "\n")

    # the main game loop
        while True:
            print()
            print(game)
            winner = game.has_winner()
        
            if winner is not None:
                print(f"{winner.name} wins!")
                #Print winner to the output file too
                file.write(f"{winner.name} wins in " + str(game.turns_played) + " turns!\n")
                if game.turns_played == 1:
                    file.write(' turns \n')
                else:
                    file.write(' turns\n')
                break
            if game.options.game_type == GameType.AttackerVsDefender:
                result = game.human_turn()
                # file.write(f"{game.to_string()}")
                file.write(f"{game.turns_played}")
                if game.next_player == Player.Attacker:
                    player = 'Defender'
                else:
                    player = 'Attacker'
                file.write('player: ' + player + '\n')
                # TODO: Fix bug to display move made!!!!
                # file.write(result)
                file.write(game.board_config_to_string() + '\n')

            elif game.options.game_type == GameType.AttackerVsComp and game.next_player == Player.Attacker:
                game.human_turn()
           
            elif game.options.game_type == GameType.CompVsDefender and game.next_player == Player.Defender:
                game.human_turn()
            else:
                player = game.next_player
                move = game.computer_turn()
                if move is not None:
                    game.post_move_to_broker(move)
                else:
                    print("Computer doesn't know what to do!!!")
                    exit(1)


##############################################################################################################

if __name__ == '__main__':
    main()
