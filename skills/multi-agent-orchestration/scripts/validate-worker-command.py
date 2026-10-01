#!/usr/bin/env python3
"""Bind a declared worker backend to the command that will actually launch."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shlex
import shutil
import sys


BACKENDS = {
    "claude": "claude-code",
    "codex": "codex",
    "codebuddy": "codebuddy",
    "workbuddy": "codebuddy",
    "qoderclicn": "qoder-cn",
    "zcode": "zcode",
    "mcode": "minimax-code",
}
PYTHON_EXECUTABLES = {"python", "python3"}
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
    trusted_zcode_driver: str = "",
    depth: int = 0,
    shell_body: bool = False,
    resolved_argv: list[str] | None = None,
    stdin_redirect: list[str] | None = None,
) -> str:
    if depth > 3:
        raise ValidationError("nested shell launch depth exceeds the supported limit")
    # Spawn adds separate native env wrappers for Session Context and Node cap.
    for _ in range(8):
        stripped = strip_environment(words)
        if stripped == words:
            break
        words = stripped
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
        if stdin_redirect is not None:
            stdin_redirect.append(redirect_target)
        words = words[: redirect_indices[0]]

    if shell_body and words[0] == "exec":
        words = strip_environment(words[1:])
        if not words or words[0].startswith("-"):
            raise ValidationError("unsupported shell exec launcher")
    if resolved_argv is not None:
        resolved_argv[:] = words
    executable = words[0]
    basename = os.path.basename(executable).lower()
    # qoderclicn is shared by several products. Never reinterpret a retired
    # QoderWork bundle or a QwenWork bundled runtime as the standalone CN CLI.
    resolved = os.path.realpath(shutil.which(executable) or executable).lower()
    if "qoderwork" in resolved:
        raise ValidationError("QoderWork is retired; install/select the standalone Qoder CN CLI")
    if basename == "qoderclicn":
        if "/qwenworkcn.app/contents/resources/bin/qoderclicn" in resolved:
            if words.count("--config-dir") != 1 or any(word.startswith("--config-dir=") for word in words):
                raise ValidationError("QwenWork bundled CLI requires one explicit dedicated --config-dir")
            index = words.index("--config-dir")
            if index + 1 >= len(words) or not os.path.isabs(words[index + 1]) or not os.path.isdir(words[index + 1]):
                raise ValidationError("QwenWork config-dir must be an existing absolute directory")
            config_root = os.path.realpath(words[index + 1])
            shared_roots = {os.path.realpath(os.path.expanduser(root)) for root in ("~/.qoder", "~/.qodercn", "~/.qwenwork")}
            if config_root in shared_roots:
                raise ValidationError("QwenWork config-dir must not reuse a shared native product config root")
            return "qwenwork-cn"
        return "qoder-cn"
    if basename == "zcode" and expected == "zcode-cli":
        return "zcode-cli"
    actual = BACKENDS.get(basename)
    if actual is not None:
        return actual

    # zcode driver channel: `python3 <trusted-zcode-driver> --cwd ...` wraps the
    # long-lived `zcode app-server` child. Only the exact skill-shipped driver
    # script may play this role — arbitrary python is still rejected below.
    if expected == "zcode" and basename in PYTHON_EXECUTABLES and len(words) >= 2:
        if trusted_zcode_driver and os.path.realpath(words[1]) == os.path.realpath(trusted_zcode_driver):
            return "zcode"

    if basename in SHELLS:
        if len(words) >= 3 and words[1] in SHELL_FLAGS:
            return command_backend(
                split_words(words[2], shell_body=True),
                expected=expected,
                trusted_claude_wrapper=trusted_claude_wrapper,
                trusted_zcode_driver=trusted_zcode_driver,
                depth=depth + 1,
                shell_body=True,
                resolved_argv=resolved_argv,
                stdin_redirect=stdin_redirect,
            )
        if expected == "claude-code" and len(words) >= 2:
            wrapper = os.path.realpath(words[1])
            if wrapper == os.path.realpath(trusted_claude_wrapper) and "--" in words[2:]:
                marker = words.index("--", 2)
                return command_backend(
                    words[marker + 1 :],
                    expected=expected,
                    trusted_claude_wrapper=trusted_claude_wrapper,
                    trusted_zcode_driver=trusted_zcode_driver,
                    depth=depth + 1,
                    resolved_argv=resolved_argv,
                stdin_redirect=stdin_redirect,
                )
        raise ValidationError(f"untrusted or opaque shell wrapper cannot prove backend identity: {executable}")

    raise ValidationError(f"executable is not a configured worker backend: {executable}")



def minimax_startup_mode(argv: list[str], subcommand_index: list[int] | None = None) -> str:
    """Classify the native top-level CLI, preserving option values and prompts."""
    i = 1
    value_options = {"-m", "--model", "--lane", "--tui-mode"}
    controls = {"init", "acp", "login", "logout", "update", "provider", "plugin"}
    while i < len(argv):
        word = argv[i]
        if word == "--":
            return "interactive"
        if word in value_options:
            if i + 1 >= len(argv):
                raise ValidationError(f"MiniMax option {word} requires a value")
            i += 2
            continue
        if any(word.startswith(option + "=") for option in value_options if option.startswith("--")):
            i += 1
            continue
        if word == "--session":
            i += 1
            if i < len(argv) and not argv[i].startswith("-"):
                i += 1
            continue
        if (word.startswith("-m") and len(word) > 2) or word.startswith("--session=") or word in {"-c", "--continue"}:
            i += 1
            continue
        if word == "exec":
            if subcommand_index is not None:
                subcommand_index.append(i)
            return "batch"
        if word in controls or word.startswith("-"):
            raise ValidationError("MiniMax worker requires native interactive or exec entrypoint")
        return "interactive"  # Native positional task prompt, not a subcommand.
    return "interactive"



def validate_minimax_bootstrap(argv: list[str], redirects: list[str], exec_index: int) -> None:
    options = {"--input", "--input-format", "--cwd", "--file", "--model", "--effort",
        "--prompt-mode", "--session", "--config", "--permission", "--timeout", "--max-steps",
        "--output-format", "--diagnostics-dir", "--output-schema", "-o", "--output-last-message"}
    i = exec_index + 1
    inputs, prompts = [], []
    input_format = "text"
    while i < len(argv):
        word = argv[i]
        if word == "--":
            prompts.extend(argv[i + 1:]); break
        key, sep, value = word.partition("=")
        if key in options:
            if not sep:
                if i + 1 >= len(argv):
                    raise ValidationError(f"MiniMax exec option {key} requires a value")
                value = argv[i + 1]; i += 1
            if key == "--input":
                inputs.append(value)
            if key == "--input-format":
                if value not in {"text", "json"}:
                    raise ValidationError("unknown MiniMax bootstrap input format")
                input_format = value
        elif word.startswith("-o") and len(word) > 2:
            pass
        elif word == "--continue":
            pass
        elif word.startswith("-") or word == "review":
            raise ValidationError("unknown MiniMax bootstrap entrypoint/options")
        else:
            prompts.append(word)
        i += 1
    if inputs:
        if inputs != ["-"] or prompts or len(redirects) != 1:
            raise ValidationError("MiniMax stdin bootstrap requires one explicit file and no second prompt")
        prompt_file = redirects[0]
        if not os.path.isfile(prompt_file):
            raise ValidationError("MiniMax bootstrap prompt file must exist")
        prompt = read_minimax_bootstrap_file(prompt_file)
    elif len(prompts) != 1 or not prompts[0].strip() or redirects:
        raise ValidationError("MiniMax exec requires one nonempty bootstrap prompt or redirected --input -")
    else:
        prompt = prompts[0]
    if not inputs and "$" in prompt and "$(" not in prompt:
        raise ValidationError("MiniMax bootstrap prompt cannot depend on unproven shell expansion")
    if not inputs and "$(" in prompt:
        match = re.fullmatch(r"\$\((.*)\)", prompts[0])
        words = split_words(match.group(1)) if match else []
        if len(words) != 2 or os.path.basename(words[0]) != "cat" or not os.path.isabs(words[1]) or not os.path.isfile(words[1]) or not os.path.getsize(words[1]):
            raise ValidationError("MiniMax cat bootstrap requires an existing nonempty absolute prompt file")
        prompt = read_minimax_bootstrap_file(words[1])
    if input_format == "json":
        try:
            value = json.loads(prompt)
        except ValueError as exc:
            raise ValidationError("MiniMax JSON bootstrap requires valid JSON") from exc
        prompt = value if isinstance(value, str) else value.get("prompt") if isinstance(value, dict) else None
    if not isinstance(prompt, str) or not prompt.strip():
        raise ValidationError("MiniMax bootstrap requires a nonempty task prompt")



def read_minimax_bootstrap_file(path: str) -> str:
    try:
        with open(path, encoding="utf-8") as source:
            return source.read()
    except (OSError, UnicodeError) as exc:
        raise ValidationError("MiniMax bootstrap file must be readable UTF-8 text") from exc


def resolve_minimax_startup(command: str, *, require_input: bool = False) -> str:
    validate_safe_command_substitutions(command)
    argv: list[str] = []
    redirects: list[str] = []
    actual = command_backend(split_words(command, shell_body=True), expected="minimax-code",
        trusted_claude_wrapper="", shell_body=True, resolved_argv=argv, stdin_redirect=redirects)
    if actual != "minimax-code":
        raise ValidationError("MiniMax startup command does not launch mcode")
    index: list[int] = []
    mode = minimax_startup_mode(argv, index)
    if mode == "batch" and require_input:
        validate_minimax_bootstrap(argv, redirects, index[0])
    return mode


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--backend", required=True, choices=sorted(set(BACKENDS.values()) | {"zcode-cli", "qwenwork-cn"}))
    parser.add_argument("--command", required=True)
    parser.add_argument("--trusted-claude-wrapper", required=True)
    parser.add_argument("--trusted-zcode-driver", default="")
    args = parser.parse_args()

    try:
        validate_safe_command_substitutions(args.command)
        argv: list[str] = []
        actual = command_backend(
            split_words(args.command, shell_body=True),
            expected=args.backend,
            trusted_claude_wrapper=args.trusted_claude_wrapper,
            trusted_zcode_driver=args.trusted_zcode_driver,
            shell_body=True,
            resolved_argv=argv,
        )
        if actual != args.backend:
            raise ValidationError(
                f"declared backend {args.backend} does not match executable backend {actual}"
            )
        if args.backend == "minimax-code":
            minimax_startup_mode(argv)
    except ValidationError as exc:
        print(str(exc))
        return 64

    print(hashlib.sha256(args.command.encode("utf-8")).hexdigest())
    return 0


if __name__ == "__main__":
    sys.exit(main())
