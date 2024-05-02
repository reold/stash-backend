import time
import random
import math

from typing import Union, List
from pydantic import BaseModel, Field
from enum import IntEnum

MAX_CARD_COUNT = 15
MAX_PLAYER_COUNT = 4

class CardType(IntEnum):
    number = 0b0
    plus2 = 0b1
    plus4 = 0b10
    reverse = 0b11

class CardColor(IntEnum):
    red = 0b0
    green = 0b1
    blue = 0b10
    yellow = 0b11

class CardInfo(BaseModel):
    type: CardType
    color: CardColor = CardColor.red
    number: int = 0

class PlayerInfo(BaseModel):
    username: str
    cards: list = []
    debt: int = Field(default=0, ge=0)

class OpponentInfo(BaseModel):
    username: str
    card_count: int

class GameConfig(BaseModel):
    card_count: int = Field(5, ge=2, le=MAX_CARD_COUNT)
    max_players: int = Field(MAX_PLAYER_COUNT, ge=2, le=MAX_PLAYER_COUNT)

class BasicGameInfo(BaseModel):
    creator: str
    config: GameConfig = GameConfig()

class GameInfo(BasicGameInfo):
    key: Union[str, None] = None
    creation: Union[str, None] = None
    players: List[PlayerInfo] = Field([], max_items=MAX_PLAYER_COUNT, min_items=1)
    ref_card: Union[int, None] = Field(None, le=255, ge=0, description="(single byte) 2b-type 2b-color 4b-number")
    current: Union[str, None] = None
    clockwise: bool = True
    filled: bool = False

class ActionType(IntEnum):
    place = 0b0
    pull = 0b1
    neutralize = 0b10


class GameAction(BaseModel):
    username: str
    type: ActionType
    # type: int = Field(le=0b11, ge=0b0, description="(double bit)0b00 - place card, 0b01 - take card, 0b10 - neutralize debt")
    card: Union[int, None] = Field(le=255, ge=0, default=None, description="(single byte) 2b-type 2b-color 4b-number")

class PlayerAlreadyInGameError(Exception):
    pass
class GameIsFullError(Exception):
    pass
class NotTurnError(Exception):
    pass
class PlayerNoCardError(Exception):
    pass
class CardMismatchError(Exception):
    pass

class Heartbeat:

    def sine(time: int, duration: int = 60*30):
        print(f"{time=} {duration=}")
        print(f"{time/duration=}")
        return Heartbeat._sine(time / duration)

    def _sine(t: int):
        t = max(min(t, 1), 0)
        return 0.5 * math.sin(math.pi * (t + 0.5)) + 0.5


class Engine:
    def __init__(self):
        self.heartbeat = 0
        self.game: GameInfo

    def beat(self):
        creation = float(self.game.creation)
        self.heartbeat = Heartbeat.sine(time.time()-creation)

    @staticmethod
    def gen_random_card(only_number: bool = False, bias: Union[int, None] = None, beat: int = 1):
        inv_beat = 1 - beat

        if only_number:
            card_type = 0b0
        else:
            card_types = [0b00, 0b01, 0b10, 0b11]
            card_type_prob = [0.75, 0.05, 0.02, 0.15]

            card_type = random.choices(card_types, card_type_prob)[0]

        if card_type == 0b10:
            return card_type << 6
        else:
            colors = [0b00, 0b01, 0b10, 0b11]
            colors_prob = [0.25, 0.25, 0.25, 0.25]
            
            if bias is not None:
                bias_parsed = Engine.parse_card(bias)
                
                colors.sort(key=lambda x: abs(bias_parsed.color - x))
                colors_prob = [0.4, 0.2 * beat, 0.2 * beat, 0.2 * beat]
                print(f"{colors_prob=}")

            color = random.choices(colors, colors_prob)[0]

            number = 0b0

            if card_type == 0b00:
                numbers = [0, 1, 2, 3, 4, 5, 6, 7, 8, 9]
                numbers_prob = [0.1]*10
                
                if bias is not None:
                    bias_parsed = Engine.parse_card(bias)

                    if bias_parsed.type == CardType.number:

                        numbers.sort(key=lambda x: abs(bias_parsed.number - x))
                        numbers_prob = [0.6, *[0.044*beat]*9]
                        print(f"{numbers_prob=}")


                number = random.choices(numbers, numbers_prob)[0]
            
            return (card_type << 6) + (color << 4) + number
    
    # TODO: abstract on parse_card method
    @staticmethod
    def is_congruent_card(real_card: int, check_card: int):
        # check if same color
        realcolor = (real_card & 0b11_0000) >> 4
        checkcolor = (check_card & 0b11_0000) >> 4

        if realcolor == checkcolor: return True

        realtype = real_card >> 6
        checktype = check_card >> 6

        # allow if +4 card
        if checktype == 0b10: return True

        # allow if check and real are +2, rev
        if checktype == realtype and checktype in [0b01, 0b11]:
            return True

        realnum = real_card & 0b1111
        checknum = check_card & 0b1111

        # allow if same number
        if realnum == checknum and realtype == 0b00:
            return True

        return False

    @staticmethod
    def parse_card(card: int):
        card_type = card >> 6

        parsed = CardInfo(type=card_type)

        if parsed.type == CardType.plus4:
            return parsed

        card_color = (card & 0b11_0000) >> 4

        parsed.color = card_color

        if parsed.type in [CardType.plus2, CardType.reverse]:
            return parsed
        
        card_number = card & 0b1111
        parsed.number = card_number

        return parsed

    def load(self, game_info: dict):
        self.game = GameInfo.parse_obj(game_info)

    def create(self, game_info: BasicGameInfo):
        self.game = GameInfo(creator=game_info.creator, config=game_info.config)

        creation_t: int = time.time()
        creator: PlayerInfo = PlayerInfo(
            username = self.game.creator,
            cards = [self.gen_random_card() for _ in range(self.game.config.card_count)])

        self.game.key = f"{round(creation_t % 10000, 1)}-{creator.username}"

        self.game.players.append(creator)

        self.game.creation = str(creation_t)
        self.game.ref_card = self.gen_random_card(only_number=True)

    def join(self, username: str):
        player = PlayerInfo(username=username)

        if any([user.username == player.username for user in self.game.players]):
            raise PlayerAlreadyInGameError()
        if self.game.filled: raise GameIsFullError("game is full")

        player.cards = [self.gen_random_card() for _ in range(self.game.config.card_count)]

        self.game.players.append(player)

        if len(self.game.players) >= self.game.config.max_players:
            self.game.filled = True
            self.game.current = self.game.creator
    
    def action(self, action: GameAction):
        player_i = next(i for i, player in enumerate(self.game.players) if player.username == action.username)

        if action.type == ActionType.neutralize:

            new_cards = [self.gen_random_card() for _ in range(self.game.players[player_i].debt)]
            
            self.game.players[player_i].cards.extend(new_cards)
            self.game.players[player_i].debt = 0

            # TODO: remove returns. create dumps for specifics
            return {"debt": self.game.players[player_i].debt,
                    "cards": self.game.players[player_i].cards}

        if self.game.current != action.username:
            raise NotTurnError()

        if action.type == ActionType.pull:
            
            self.beat()
            new_card = self.gen_random_card(bias=self.game.ref_card, beat=self.heartbeat)
            self.game.players[player_i].cards.append(new_card)

            # TODO: remove returns. create dumps for specifics
            return self.game.players[player_i].cards
        
        elif action.type == ActionType.place:

            card = action.card
            parsed_card = self.parse_card(card)

            next_player_i = self._get_next_player_i(player_i)

                
            if not self.is_congruent_card(self.game.ref_card, card):
                raise CardMismatchError()

            if parsed_card.type == CardType.plus4:

                if not 0b10_00_0000 in self.game.players[player_i].cards:
                    raise PlayerNoCardError()
            
                self.game.players[next_player_i].debt += 4
                self.game.players[player_i].cards.remove(0b10_00_0000)
            
            else:

                if not card in self.game.players[player_i].cards:
                    raise PlayerNoCardError()
                
                if parsed_card.type == CardType.plus2:
                    
                    self.game.players[next_player_i].debt += 2
                
                elif parsed_card.type == CardType.reverse:
                    self.game.clockwise = not self.game.clockwise

                    if len(self.game.players) == 2:
                        next_player_i = player_i
                    else:
                        next_player_i = self._get_next_player_i(player_i)

                self.game.players[player_i].cards.remove(card)

            self.game.ref_card = card
            self.game.current = \
                    self.game.players[next_player_i].username


    def _get_next_player_i(self, player_i: int):
        if self.game.clockwise: 
            return (player_i + 1) % self.game.config.max_players
        else:
            return player_i - 1


    # TODO: utilize dump method in api.py
    def dump(self, depth: int, username: Union[str, None] = None):
        
        state = self.game.dict(include=("filled", "ref_card"))
        state["oppstate"] = [OpponentInfo(username=opp.username, card_count=len(opp.cards or [])) for opp in self.game.players if opp.username != username]

        if depth == 0:
            return state