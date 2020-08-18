import timeit
import random
import warnings

import numpy as np

import pytest

from nle import nethack


# MORE + compass directions + long compass directions.
ACTIONS = [
    13,
    107,
    108,
    106,
    104,
    117,
    110,
    98,
    121,
    75,
    76,
    74,
    72,
    85,
    78,
    66,
    89,
]


class TestNetHack:
    @pytest.fixture
    def game(self):  # Make sure we close even on test failure.
        g = nethack.Nethack(observation_keys=("chars", "blstats"))
        try:
            yield g
        finally:
            g.close()

    def test_close_and_restart(self):
        game = nethack.Nethack()
        game.reset()
        game.close()

        game = nethack.Nethack()
        game.reset()
        game.close()

    def test_run_n_episodes(self, tmpdir, game, episodes=3):
        olddir = tmpdir.chdir()

        chars, blstats = game.reset()

        assert chars.shape == (21, 79)
        assert blstats.shape == (25,)

        game.step(ord("y"))
        game.step(ord("y"))
        game.step(ord("\n"))

        steps = 0
        start_time = timeit.default_timer()
        start_steps = steps

        mean_sps = 0
        sps_n = 0

        for episode in range(episodes):
            while True:
                ch = random.choice(ACTIONS)
                _, done = game.step(ch)
                if done:
                    break

                steps += 1

                if steps % 1000 == 0:
                    end_time = timeit.default_timer()
                    sps = (steps - start_steps) / (end_time - start_time)
                    sps_n += 1
                    mean_sps += (sps - mean_sps) / sps_n
                    print("%f SPS" % sps)
                    start_time = end_time
                    start_steps = steps
            print("Finished episode %i after %i steps." % (episode + 1, steps))
            game.reset()

        print("Finished after %i steps. Mean sps: %f" % (steps, mean_sps))

        nethackdir = tmpdir.chdir()

        assert nethackdir.fnmatch("nle*")
        assert tmpdir.ensure("nle.ttyrec")
        assert mean_sps > 10000

        if mean_sps < 15000:
            warnings.warn("Mean sps was only %f" % mean_sps)
        olddir.chdir()
        # No call to game.close() as fixture will do that for us.

    def test_error_on_second(self, game):
        game.reset()
        game1 = nethack.Nethack()
        with pytest.raises(RuntimeError, match="Cannot have more than one"):
            game1.reset()


class TestNetHackFurther:
    def test_run(self):
        # TODO: Implement ttyrecording filename in libnethack wrapper.
        # archivefile = tempfile.mktemp(suffix="nethack_test", prefix=".zip")

        game = nethack.Nethack(
            observation_keys=("glyphs", "chars", "colors", "blstats", "program_state")
        )
        _, _, _, _, program_state = game.reset()
        actions = [
            nethack.MiscAction.MORE,
            nethack.MiscAction.MORE,
            nethack.MiscAction.MORE,
            nethack.MiscAction.MORE,
            nethack.MiscAction.MORE,
            nethack.MiscAction.MORE,
        ]

        for action in actions:
            while not program_state[3]:  # in_moveloop.
                obs, done = game.step(nethack.MiscAction.MORE)
                _, _, _, _, program_state = obs

            obs, done = game.step(action)
            if done:
                # Only the good die young.
                obs = game.reset()

            glyphs, chars, colors, blstats, _ = obs

            x, y = blstats[:2]

            assert np.count_nonzero(chars == ord("@")) == 1

            # That's where you're @.
            assert chars[y, x] == ord("@")

            # You're bright (4th bit, 8) white (7), too.
            assert colors[y, x] == 8 ^ 7

            mon = nethack.permonst(nethack.glyph_to_mon(glyphs[y][x]))
            assert mon.mname == "monk"
            assert mon.mlevel == 10

            class_sym = nethack.class_sym.from_mlet(mon.mlet)
            assert class_sym.sym == "@"
            assert class_sym.explain == "human or elf"

        game.close()


class TestNethackSomeObs:
    @pytest.fixture
    def game(self):  # Make sure we close even on test failure.
        g = nethack.Nethack(observation_keys=("program_state", "message", "internal"))
        try:
            yield g
        finally:
            g.close()

    def test_message(self, game):
        messages = []

        program_state, message, _ = game.reset()
        messages.append(message)
        while not program_state[3]:  # in_moveloop.
            (program_state, message, _), done = game.step(nethack.MiscAction.MORE)
            messages.append(message)

        greeting = (
            b"Hello Agent, welcome to NetHack!  You are a neutral male human Monk."
        )
        saw_greeting = True
        for message in messages:
            # `greeting` is often the last message, but not always -- e.g.,
            # it could also be "Be careful!  New moon tonight.".
            assert len(message) == 256
            if (
                memoryview(message)[: len(greeting)] == greeting
                and memoryview(message)[len(greeting)] == 0
            ):
                saw_greeting = True
        assert saw_greeting

    def test_internal(self, game):
        program_state, _, internal = game.reset()
        while not program_state[3]:  # in_moveloop.
            (program_state, _, internal), done = game.step(nethack.MiscAction.MORE)

        assert internal[0] == 1  # deepest_lev_reached.

        (_, _, internal), done = game.step(nethack.Command.INVENTORY)
        assert internal[3] == 1  # xwaitforspace


class TestNethackFunctionsAndConstants:
    def test_permonst_and_class_sym(self):
        glyph = 155  # Lichen.

        mon = nethack.permonst(nethack.glyph_to_mon(glyph))

        assert mon.mname == "lichen"

        cs = nethack.class_sym.from_mlet(mon.mlet)

        assert cs.sym == "F"
        assert cs.explain == "fungus or mold"

        assert nethack.NHW_MESSAGE == 1
        assert hasattr(nethack, "MAXWIN")

    def test_permonst(self):
        mon = nethack.permonst(0)
        assert mon.mname == "giant ant"
        del mon

        mon = nethack.permonst(1)
        assert mon.mname == "killer bee"

    def test_some_constants(self):
        assert nethack.GLYPH_MON_OFF == 0
        assert nethack.NUMMONS > 300

    def test_illegal_numbers(self):
        with pytest.raises(IndexError):
            nethack.permonst(10000)

        with pytest.raises(IndexError):
            nethack.permonst(-1)

        with pytest.raises(IndexError):
            nethack.class_sym.from_mlet("\xFF")
