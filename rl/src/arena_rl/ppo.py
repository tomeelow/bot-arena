"""The boss's network in numpy, and one PPO update with hand-written gradients.

The network is boss.Net's: x -> tanh -> tanh -> (build logits, stance logits, value). It is
small enough (about 6k parameters) that numpy beats a deep-learning framework here, and it
keeps the training dependencies to numpy alone. tests/test_ppo.py checks the gradients
against finite differences and the outputs against the pure-Python boss.Net.
"""

from dataclasses import dataclass

import numpy as np

from .boss import BUILDS, N_FEATURES, STANCES, Layer

type Params = dict[str, np.ndarray]
SHAPES = {"build": len(BUILDS), "stance": len(STANCES), "value": 1}


def init(hidden: int, rng: np.random.Generator) -> Params:
    """Scaled-normal trunk; near-zero policy heads, so the first policy is close to uniform."""
    p: Params = {}
    sizes = [("h1", N_FEATURES, hidden), ("h2", hidden, hidden)]
    sizes += [(name, hidden, n) for name, n in SHAPES.items()]
    for name, n_in, n_out in sizes:
        scale = 0.01 if name in ("build", "stance") else 1 / np.sqrt(n_in)
        p[f"{name}.w"] = rng.normal(0, scale, (n_in, n_out))
        p[f"{name}.b"] = np.zeros(n_out)
    return p


def to_layers(p: Params) -> dict[str, Layer]:
    """The plain lists boss.Net takes, and the export writes into the bot."""
    names = ["h1", "h2", *SHAPES]
    return {n: (p[f"{n}.w"].tolist(), p[f"{n}.b"].tolist()) for n in names}


@dataclass
class Forward:
    x: np.ndarray
    h1: np.ndarray
    h2: np.ndarray
    build: np.ndarray
    stance: np.ndarray
    value: np.ndarray


def forward(p: Params, x: np.ndarray) -> Forward:
    h1 = np.tanh(x @ p["h1.w"] + p["h1.b"])
    h2 = np.tanh(h1 @ p["h2.w"] + p["h2.b"])
    return Forward(
        x,
        h1,
        h2,
        h2 @ p["build.w"] + p["build.b"],
        h2 @ p["stance.w"] + p["stance.b"],
        (h2 @ p["value.w"] + p["value.b"])[:, 0],
    )


def log_softmax(logits: np.ndarray) -> np.ndarray:
    z = logits - logits.max(axis=1, keepdims=True)
    return z - np.log(np.exp(z).sum(axis=1, keepdims=True))


def log_prob(f: Forward, build: np.ndarray, stance: np.ndarray) -> np.ndarray:
    rows = np.arange(len(build))
    return log_softmax(f.build)[rows, build] + log_softmax(f.stance)[rows, stance]


@dataclass(frozen=True)
class Batch:
    x: np.ndarray
    build: np.ndarray
    stance: np.ndarray
    old_logp: np.ndarray
    advantage: np.ndarray
    returns: np.ndarray


@dataclass(frozen=True)
class Coefs:
    clip: float
    value: float
    entropy: float


def loss_and_grads(p: Params, b: Batch, c: Coefs) -> tuple[float, Params, dict[str, float]]:
    """The clipped PPO objective (negated, to minimise), and its gradient."""
    f = forward(p, b.x)
    n = len(b.x)
    rows = np.arange(n)
    ratio = np.exp(log_prob(f, b.build, b.stance) - b.old_logp)
    clipped = np.clip(ratio, 1 - c.clip, 1 + c.clip)
    policy_loss = -np.minimum(ratio * b.advantage, clipped * b.advantage).mean()
    # The gradient flows only where the unclipped term is the smaller one.
    active = ratio * b.advantage <= clipped * b.advantage
    d_logp = np.where(active, -b.advantage * ratio, 0.0) / n

    grads_out: dict[str, np.ndarray] = {}
    entropy_total = 0.0
    for head, actions in (("build", b.build), ("stance", b.stance)):
        logp_all = log_softmax(getattr(f, head))
        probs = np.exp(logp_all)
        entropy = -(probs * logp_all).sum(axis=1)
        entropy_total += entropy.mean()
        onehot = np.zeros_like(probs)
        onehot[rows, actions] = 1
        d = d_logp[:, None] * (onehot - probs)
        # -c * mean(entropy): dH/dz_i = -p_i (log p_i + H)
        d += c.entropy * probs * (logp_all + entropy[:, None]) / n
        grads_out[head] = d
    value_loss = ((f.value - b.returns) ** 2).mean()
    grads_out["value"] = (2 * c.value * (f.value - b.returns) / n)[:, None]
    loss = policy_loss + c.value * value_loss - c.entropy * entropy_total

    g: Params = {}
    dh2 = np.zeros_like(f.h2)
    for head, d in grads_out.items():
        g[f"{head}.w"] = f.h2.T @ d
        g[f"{head}.b"] = d.sum(axis=0)
        dh2 += d @ p[f"{head}.w"].T
    dz2 = dh2 * (1 - f.h2**2)
    g["h2.w"], g["h2.b"] = f.h1.T @ dz2, dz2.sum(axis=0)
    dz1 = (dz2 @ p["h2.w"].T) * (1 - f.h1**2)
    g["h1.w"], g["h1.b"] = f.x.T @ dz1, dz1.sum(axis=0)
    stats = {
        "policy_loss": float(policy_loss),
        "value_loss": float(value_loss),
        "entropy": float(entropy_total),
        "clip_fraction": float((~active).mean()),
    }
    return float(loss), g, stats


class Adam:
    def __init__(self, p: Params, lr: float, max_norm: float) -> None:
        self.lr, self.max_norm, self.t = lr, max_norm, 0
        self.m = {k: np.zeros_like(v) for k, v in p.items()}
        self.v = {k: np.zeros_like(v) for k, v in p.items()}

    def step(self, p: Params, g: Params) -> None:
        norm = np.sqrt(sum(float((v**2).sum()) for v in g.values()))
        scale = min(1.0, self.max_norm / (norm + 1e-8))
        self.t += 1
        for k in p:
            gk = g[k] * scale
            self.m[k] = 0.9 * self.m[k] + 0.1 * gk
            self.v[k] = 0.999 * self.v[k] + 0.001 * gk**2
            m_hat = self.m[k] / (1 - 0.9**self.t)
            v_hat = self.v[k] / (1 - 0.999**self.t)
            p[k] -= self.lr * m_hat / (np.sqrt(v_hat) + 1e-8)


def gae(values: np.ndarray, reward: float, gamma: float, lam: float) -> np.ndarray:
    """Advantages for one game whose only reward is the result at the end."""
    n = len(values)
    adv = np.zeros(n)
    last = 0.0
    for t in reversed(range(n)):
        next_value = values[t + 1] if t + 1 < n else 0.0
        r = reward if t == n - 1 else 0.0
        delta = r + gamma * next_value - values[t]
        last = delta + gamma * lam * last
        adv[t] = last
    return adv
