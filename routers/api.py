from fastapi import APIRouter, Query, Path, Depends, HTTPException
from fastapi.responses import HTMLResponse

import deta
import uno

from typing import Union
from time import time

MAX_JOIN_TIME = 5 * 60
MAX_PLAY_TIME =   1 * 60 * 60

router = APIRouter(prefix="/api", tags=["api"])
gamesdb = deta.Base("games")

async def is_valid_game(game: str = Path(alias="game_id")):
    game_state = gamesdb.get(game)
    if not game_state:
        raise HTTPException(404, "game not found")
    else: return (game, game_state)

@router.post("/create")
async def create(game_info: uno.BasicGameInfo):
    print(game_info)

    engine = uno.Engine()
    engine.create(game_info)

    return gamesdb.put(engine.game.dict(), expire_in=MAX_JOIN_TIME)

@router.get("/join/{game_id}")
async def join(username: str, game: str=Depends(is_valid_game)):
    (game_id, game_state) = game
    
    engine = uno.Engine()
    engine.load(game_state)

    try:
        engine.join(username)

        new_state = engine.game.dict()

        print(new_state)

        gamesdb.put(new_state,
                       expire_in=MAX_PLAY_TIME if engine.game.filled == True else None)

        return HTMLResponse()
    
    except uno.PlayerAlreadyInGameError:
        return HTMLResponse()
    
    except uno.GameIsFullError as error:
        return HTMLResponse(404, error)

    except Exception as error:
        return HTMLResponse(404, error)

def curated_state(game_state, username: str):
    fields_required = ["clockwise", "creation", "creator", "current", "filled", "key", "ref_card", "config"] 
    
    resp = {field: game_state[field] for field in fields_required}

    player_state = next(filter(lambda player: player["username"] == username, game_state["players"]))

    opponents_state = list(filter(lambda player: player["username"] != username, game_state["players"]))
    opponents_state = [{"username": opp["username"], "nocards": len(opp["cards"] or [])} for opp in opponents_state]

    resp["oppstate"] = opponents_state
    resp["cards"] = player_state["cards"]
    resp["debt"] = player_state["debt"]

    return resp

@router.get("/{game_id}/state")
async def state(game:str=Depends(is_valid_game), depth: int = Query(default=0, ge=0, le=3), username: Union[str, None] = Query(default=None)):
    (game_id, game_state) = game
    
    resp = {"filled": game_state["filled"], "ref_card": game_state["ref_card"], "oppstate": [{"username": opp["username"], "nocards": len(opp["cards"] or [])} for opp in game_state["players"] if opp["username"] != username]}

    if depth == 0: return resp
    elif depth == 1:
        resp.update({"current": game_state["current"]})
    elif depth >= 2:
        if not username:
            return HTMLResponse("username required for state", 401)
                
        if depth == 2:
            
            opponents_state = list(filter(lambda player: player["username"] != username,game_state["players"]))
            opponents_state = [{"username": opp["username"], "nocards": len(opp["cards"] or [])} for opp in opponents_state]

            player_state = next(filter(lambda player: player["username"] == username, game_state["players"]))

            return {"ref_card": game_state["ref_card"], "current": game_state["current"], "debt": player_state["debt"], "oppstate": opponents_state}
        
        elif depth == 3: return curated_state(game_state, username)

    return resp


@router.post("/{game_id}/action")
async def action(action: uno.GameAction, game:str=Depends(is_valid_game)):

    (game_id, game_state) = game

    engine = uno.Engine()
    engine.load(game_state)

    try:
        resp = engine.action(action)

        new_state = engine.game.dict()
        del new_state["key"]

        # print(new_state)
        print(engine.heartbeat)
        print(1 - engine.heartbeat)

        gamesdb.put(new_state, game_id)


        return resp

    except uno.NotTurnError:
        raise HTTPException(404, "not player's turn")
    except uno.PlayerNoCardError:
        raise HTTPException(404, "player doesn't own card")
    except uno.CardMismatchError:
        raise HTTPException(404, "card mismatch")
