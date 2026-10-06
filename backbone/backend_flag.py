"""`--backend openai|ollama` on any entry point, so the same command works in PowerShell, cmd, bash and zsh.

Must run before `backbone.config` is imported: it sets BACKBONE_BACKEND and removes the flag from sys.argv.
"""
import os
import sys


def apply(argv=None) -> None:
    argv = sys.argv if argv is None else argv
    for i, a in enumerate(list(argv)):
        if a == "--backend" and i + 1 < len(argv):
            os.environ["BACKBONE_BACKEND"] = argv[i + 1]
            del argv[i:i + 2]
            return
        if a.startswith("--backend="):
            os.environ["BACKBONE_BACKEND"] = a.split("=", 1)[1]
            del argv[i]
            return
