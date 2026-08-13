#!/usr/bin/env python3
"""Bind a declared worker backend to the command that will actually launch."""

from __future__ import annotations

import argparse
import hashlib
import os
import re
import shlex
import sys


BACKENDS = {
    "claude": "claude-code",
    "codex": "codex",
    "codebuddy": "codebuddy",
    "workbuddy": "codebuddy",
    "qoderclicn": "qoderwork-cn",
}
SHELLS = {"bash", "sh", "zsh"}
SHELL_FLAGS = {"-c", "-lc", "-cl"}
CHAIN_TOKENS = {";", "&&", "||", "|", "&"}
REDIRECT_TOKENS = {"<", ">", "<<", ">>"}


class ValidationError(ValueError):
    """Raised when a launch command cannot prove the declared backend."""


def split_words(text: str, *, shell_body: bool = False) -> list[str]:
    try:
        if shell_body:
            lexer = shlex.shlex(text, posix=True, punctuation_chars=";&|<>")
            lexer.whitespace_split = True
            return list(lexer)
        return shlex.split(text, posix=True)
    except ValueError as exc:
        raise ValidationError(f"command is not parseable: {exc}") from exc


def strip_environment(words: list[str]) -> list[str]:
    index = 0
    while index < len(words) and "=" in words[index] and not words[index].startswith(("/", "-")):
        index += 1
    if index >= len(words) or os.path.basename(words[index]).lower() != "env":
        return words[index:]

    index += 1
    while index < len(words):
        token = words[index]
        if token in {"-u", "--unset"}:
            if index + 1 >= len(words):
                raise ValidationError(f"{token} is missing its environment variable")
            index += 2
        elif token.startswith("--unset=") or ("=" in token and not token.startswith(("/", "-"))):
            index += 1
        elif token == "--":
            index += 1
            break
        elif token.startswith("-"):
            raise ValidationError(f"unsupported env launcher option: {token}")
        else:
            break
    return words[index:]


def validate_safe_command_substitutions(command: str) -> None:
    if "`" in command:
        raise ValidationError("backtick command substitution is not an accepted worker launcher")
    starts = [match.start() for match in re.finditer(r"\$\(", command)]
    for start in starts:
        end = command.find(")", start + 2)
        if end < 0:
            raise ValidationError("unterminated command substitution")
        body = command[start + 2 : end]
        words = split_words(body)
        if len(words) != 2 or os.path.basename(words[0]).lower() != "cat":
            raise ValidationError("only the renderer's single-file $(cat PROMPT_FILE) substitution is accepted")


def command_backend(
    words: list[str],
    *,
    expected: str,
    trusted_claude_wrapper: str,
    depth: int = 0,
    shell_body: bool = False,
) -> str:
    if depth > 3:
        raise ValidationError("nested shell launch depth exceeds the supported limit")
    words = strip_environment(words)
    if not words:
        raise ValidationError("command has no executable")
    if shell_body and CHAIN_TOKENS.intersection(words):
        raise ValidationError("shell command chaining is not an accepted worker launcher")
    if shell_body and REDIRECT_TOKENS.intersection(words):
        redirect_indices = [index for index, token in enumerate(words) if token in REDIRECT_TOKENS]
        if len(redirect_indices) != 1 or words[redirect_indices[0]] != "<" or redirect_indices[0] != len(words) - 2:
            raise ValidationError("only the renderer's final single-file stdin redirect is accepted")
        redirect_target = words[-1]
        if not os.path.isabs(redirect_target):
            raise ValidationError("renderer stdin redirect must use an absolute prompt file")
        words = words[: redirect_indices[0]]

    executable = words[0]
    basename = os.path.basename(executable).lower()
    actual = BACKENDS.get(basename)
    if actual is not None:
        return actual

    if basename in SHELLS:
        if len(words) >= 3 and words[1] in SHELL_FLAGS:
            return command_backend(
                split_words(words[2], shell_body=True),
                expected=expected,
                trusted_claude_wrapper=trusted_claude_wrapper,
                depth=depth + 1,
                shell_body=True,
            )
        if expected == "claude-code" and len(words) >= 2:
            wrapper = os.path.realpath(words[1])
            if wrapper == os.path.realpath(trusted_claude_wrapper) and "--" in words[2:]:
                marker = words.index("--", 2)
                return command_backend(
                    words[marker + 1 :],
                    expected=expected,
                    trusted_claude_wrapper=trusted_claude_wrapper,
                    depth=depth + 1,
                )
        raise ValidationError(f"untrusted or opaque shell wrapper cannot prove backend identity: {executable}")

    raise ValidationError(f"executable is not a configured worker backend: {executable}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--backend", required=True, choices=sorted(set(BACKENDS.values())))
    parser.add_argument("--command", required=True)
    parser.add_argument("--trusted-claude-wrapper", required=True)
    args = parser.parse_args()

    try:
        validate_safe_command_substitutions(args.command)
        actual = command_backend(
            split_words(args.command, shell_body=True),
            expected=args.backend,
            trusted_claude_wrapper=args.trusted_claude_wrapper,
            shell_body=True,
        )
        if actual != args.backend:
            raise ValidationError(
                f"declared backend {args.backend} does not match executable backend {actual}"
            )
    except ValidationError as exc:
        print(str(exc))
        return 64

    print(hashlib.sha256(args.command.encode("utf-8")).hexdigest())
    return 0


if __name__ == "__main__":
    sys.exit(main())
