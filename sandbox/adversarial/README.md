# Adversarial bots

Each file attacks the ranked jail in one way. `sandbox/tests/test_adversarial.py` plays every one against a built-in bot, checks it ended the way its docstring says, and checks the host afterwards: no leftover processes or cgroups.

A bot that gets further than it should writes `ESCAPED: ...` to its log, and the test fails on that. A new escape idea gets a bot here first, then the fix (see CLAUDE.md).
