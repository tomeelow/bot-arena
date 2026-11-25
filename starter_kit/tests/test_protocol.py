"""The wire format: lossless both ways, and strict about everything a bot sends back."""

import json

import pytest
from arena.limits import Limits
from arena.protocol import (
    ProtocolError,
    decode_event,
    decode_map_info,
    decode_observation,
    decode_rules,
    parse_orders,
    parse_ready,
)
from arena_engine import Dir, Move, Rules, event_to_plain, map_info, observe, to_plain
from engine_support import RandomBot, play

LIMITS = Limits.load()


def wire(value):
    return json.loads(json.dumps(value))


def test_observations_map_info_and_events_survive_the_wire():
    game = play((RandomBot(1), RandomBot(2)), seed=9, turns=150)
    assert any(side for events in game.events for side in events)
    for state in game.states[::10]:
        for seat in (0, 1):
            obs = observe(state, seat)
            assert decode_observation(wire(to_plain(obs))) == obs
            info = map_info(state, seat)
            assert decode_map_info(wire(to_plain(info))) == info
    for events in game.events:
        for side in events:
            for event in side:
                assert decode_event(wire(event_to_plain(event))) == event
    assert decode_rules(wire(to_plain(Rules()))) == Rules()


def reply(**fields):
    base = {"t": "orders", "n": 3, "orders": [], "log": ""}
    return json.dumps(base | fields).encode()


def test_a_well_formed_reply_is_accepted():
    orders, log = parse_orders(
        reply(orders=[{"type": "move", "unit": 1, "dir": "N"}], log="hi"), 3, LIMITS
    )
    assert orders == [Move(1, Dir.N)]
    assert log == "hi"


@pytest.mark.parametrize(
    "line",
    [
        b"not json",
        b"[]",
        b'{"t": "orders", "n": NaN, "orders": [], "log": ""}',
        b"[" * 100_000 + b"]" * 100_000,
        reply(n=4),
        reply(n=True),
        reply(t="ready"),
        reply(orders={"type": "move"}),
        reply(orders=[{"type": "move", "unit": 1, "dir": "UP"}]),
        reply(orders=[{"type": "unload", "unit": 1, "extra": 1}]),
        reply(orders=[{"type": "unload", "unit": 1}] * (LIMITS.max_orders + 1)),
        reply(log=5),
        reply(extra="field"),
        reply(log="x" * LIMITS.reply_max_bytes),
    ],
)
def test_malformed_replies_are_rejected(line):
    with pytest.raises(ProtocolError):
        parse_orders(line, 3, LIMITS)


def test_ready_needs_exactly_the_ready_shape():
    assert parse_ready(b'{"t": "ready", "log": ""}', LIMITS) == ""
    with pytest.raises(ProtocolError):
        parse_ready(b'{"t": "ready"}', LIMITS)


def test_long_logs_are_truncated_not_rejected():
    _, log = parse_orders(reply(log="é" * LIMITS.log_max_bytes_per_turn), 3, LIMITS)
    assert len(log.encode()) <= LIMITS.log_max_bytes_per_turn
    assert log.endswith("[truncated]")
