"""The numpy network is the shipped one, and its gradients are right."""

import numpy as np
import pytest
from arena_rl import ppo
from arena_rl.boss import BUILDS, N_FEATURES, STANCES, Net


@pytest.fixture
def params() -> ppo.Params:
    return ppo.init(8, np.random.default_rng(0))


def test_numpy_forward_matches_the_pure_python_net_the_bot_ships(params):
    rng = np.random.default_rng(1)
    params = {k: v + rng.normal(0, 0.3, v.shape) for k, v in params.items()}
    x = rng.random((5, N_FEATURES))
    f = ppo.forward(params, x)
    net = Net(ppo.to_layers(params))
    for i in range(len(x)):
        build, stance, value = net(x[i].tolist())
        assert build == pytest.approx(f.build[i].tolist(), abs=1e-12)
        assert stance == pytest.approx(f.stance[i].tolist(), abs=1e-12)
        assert value == pytest.approx(f.value[i], abs=1e-12)


def test_gradients_match_finite_differences(params):
    rng = np.random.default_rng(2)
    params = {k: v + rng.normal(0, 0.3, v.shape) for k, v in params.items()}
    n = 16
    x = rng.random((n, N_FEATURES))
    build, stance = rng.integers(0, len(BUILDS), n), rng.integers(0, len(STANCES), n)
    # Old log-probs near the current ones, so some samples are clipped and some are not.
    logp = ppo.log_prob(ppo.forward(params, x), build, stance) + rng.normal(0, 0.3, n)
    batch = ppo.Batch(x, build, stance, logp, rng.normal(size=n), rng.normal(size=n))
    coefs = ppo.Coefs(clip=0.2, value=0.5, entropy=0.05)
    _, grads, _ = ppo.loss_and_grads(params, batch, coefs)
    eps = 1e-6
    for key, value in params.items():
        for idx in [tuple(rng.integers(0, s) for s in value.shape) for _ in range(4)]:
            saved = value[idx]
            value[idx] = saved + eps
            up = ppo.loss_and_grads(params, batch, coefs)[0]
            value[idx] = saved - eps
            down = ppo.loss_and_grads(params, batch, coefs)[0]
            value[idx] = saved
            assert grads[key][idx] == pytest.approx((up - down) / (2 * eps), abs=1e-6), key


def test_gae_with_a_perfect_value_function_has_no_advantage():
    gamma = 0.9
    values = np.array([gamma**2, gamma, 1.0])  # the discounted final reward of 1
    assert ppo.gae(values, 1.0, gamma, 0.95) == pytest.approx([0, 0, 0])
