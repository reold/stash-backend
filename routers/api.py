from fastapi import APIRouter, Query, Depends, HTTPException
from fastapi.responses import HTMLResponse
from fastapi_socketio import SocketManager

import uno

from typing import Union

from database import Database
from constants import *

router = APIRouter(prefix="/api", tags=["api"])
database = Database()
socket_manager = SocketManager(app=router)


async def use_game(game_id: str):
    with database as db:
        game_state = db.get(game_id)
    if not game_state:
        raise HTTPException(404, "game not found")
    return (game_id, game_state)


@router.sio.on("connect")
async def sio_connect():
    print("client has connected")


@router.post("/create")
async def create(game_info: uno.BasicGameInfo):
    engine = uno.Engine()
    engine.create(game_info)
    engine_state = engine.game.model_dump()

    with database as db:
        db[engine_state["key"]] = engine_state  # now uses .put()

    return engine_state


@router.get("/join/{game_id}")
async def join(username: str, game: str = Depends(use_game)):
    (game_id, game_state) = game

    engine = uno.Engine()
    engine.load(game_state)

    try:
        engine.join(username)
        game_state = engine.game.model_dump()

        with database as db:
            db[game_state["key"]] = game_state

        return HTMLResponse()
    except uno.PlayerAlreadyInGameError:
        return HTMLResponse()
    except uno.GameIsFullError as error:
        return HTMLResponse(status_code=404, content=str(error))
    except Exception as error:
        return HTMLResponse(status_code=404, content=str(error))


def curated_state(game_state, username: str):
    fields_required = [
        "clockwise",
        "creation",
        "creator",
        "current",
        "filled",
        "key",
        "ref_card",
        "config",
    ]
    resp = {field: game_state[field] for field in fields_required}

    player_state = next(
        filter(lambda p: p["username"] == username, game_state["players"])
    )
    opponents_state = list(
        filter(lambda p: p["username"] != username, game_state["players"])
    )
    opponents_state = [
        {"username": opp["username"], "nocards": len(opp["cards"] or [])}
        for opp in opponents_state
    ]

    resp["oppstate"] = opponents_state
    resp["cards"] = player_state["cards"]
    resp["debt"] = player_state["debt"]

    return resp


@router.get("/{game_id}/state")
async def state(
    game: str = Depends(use_game),
    depth: int = Query(default=0, ge=0, le=3),
    username: Union[str, None] = Query(default=None),
):
    (game_id, game_state) = game

    # depth 0
    if depth == 0:
        return {
            "filled": game_state["filled"],
            "ref_card": game_state["ref_card"],
            "oppstate": [
                {
                    "username": opp["username"],
                    "nocards": len(opp["cards"] or []),
                }
                for opp in game_state["players"]
                if opp["username"] != username
            ],
        }

    # depth 1
    elif depth == 1:
        return {
            "filled": game_state["filled"],
            "ref_card": game_state["ref_card"],
            "current": game_state["current"],
            "oppstate": [
                {
                    "username": opp["username"],
                    "nocards": len(opp["cards"] or []),
                }
                for opp in game_state["players"]
                if opp["username"] != username
            ],
        }

    # depth >= 2
    elif depth >= 2:
        if not username:
            return HTMLResponse("username required for state", 401)

        player_state = next(
            p for p in game_state["players"] if p["username"] == username
        )
        opponents_state = [
            {"username": opp["username"], "nocards": len(opp["cards"] or [])}
            for opp in game_state["players"]
            if opp["username"] != username
        ]

        if depth == 2:
            return {
                "ref_card": game_state["ref_card"],
                "current": game_state["current"],
                "debt": player_state["debt"],
                "cards": player_state["cards"],  # ← cards added
                "oppstate": opponents_state,
            }

        elif depth == 3:
            return curated_state(game_state, username)

    return {"error": "invalid depth"}


@router.post("/{game_id}/action")
async def action(
    action: uno.GameAction,
    game: str = Depends(use_game),
):
    (game_id, game_state) = game

    engine = uno.Engine()
    engine.load(game_state)

    try:
        resp = engine.action(action)
        new_state = engine.game.dict()
        del new_state["key"]

        with database as db:
            db[game_id] = new_state  # now uses .put()

        return resp

    except uno.NotTurnError:
        raise HTTPException(404, "not player's turn")
    except uno.PlayerNoCardError:
        raise HTTPException(404, "player doesn't own card")
    except uno.CardMismatchError:
        raise HTTPException(404, "card mismatch")
