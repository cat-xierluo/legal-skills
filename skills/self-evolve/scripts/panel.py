#!/usr/bin/env python3
"""Serve the localhost-only Self Evolve review panel."""

from __future__ import annotations

import argparse
import ipaddress
import json
import re
import secrets
import socket
import sys
import threading
import webbrowser
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any
from urllib.parse import parse_qs, unquote, urlparse, urlsplit

import render_panel
from proposal_store import HUMAN_DECISIONS, ProposalStore, ProposalStoreCorruptionError
from self_evolve_paths import (
    PROPOSALS_ROOT,
    assert_external_write_path,
    assert_runtime_ready,
)
from workmode_ledger import ALLOWED_DECISIONS as WORKMODE_DECISIONS, WorkmodeLedger


MAX_BODY_BYTES = 32 * 1024
SCRIPT_NONCE_PATTERN = re.compile(r"[A-Za-z0-9_-]{16,128}")
AUTH_TOKEN_PATTERN = re.compile(r"[A-Za-z0-9_-]{16,256}")


def parse_loopback_authority(value: str) -> tuple[str, int] | None:
    """Parse an explicit numeric loopback ``host:port`` authority."""
    if not value or value != value.strip():
        return None
    try:
        parsed = urlsplit(f"//{value}")
        port = parsed.port
    except ValueError:
        return None
    if (
        not parsed.hostname
        or port is None
        or parsed.username is not None
        or parsed.password is not None
        or parsed.path
        or parsed.query
        or parsed.fragment
        or "%" in parsed.hostname
    ):
        return None
    try:
        address = ipaddress.ip_address(parsed.hostname)
    except ValueError:
        return None
    if not address.is_loopback:
        return None
    return address.compressed, port


def same_origin_loopback(value: str, expected: tuple[str, int]) -> bool:
    """Return whether an Origin is the exact HTTP origin of this loopback server."""
    if not value or value != value.strip():
        return False
    try:
        parsed = urlsplit(value)
    except ValueError:
        return False
    if (
        parsed.scheme.lower() != "http"
        or not parsed.netloc
        or parsed.path
        or parsed.query
        or parsed.fragment
        or parsed.username is not None
        or parsed.password is not None
    ):
        return False
    return parse_loopback_authority(parsed.netloc) == expected


def format_authority(host: str, port: int) -> str:
    address = ipaddress.ip_address(host)
    return f"[{address.compressed}]:{port}" if address.version == 6 else f"{address.compressed}:{port}"


def response_json(
    handler: BaseHTTPRequestHandler,
    status: int,
    payload: dict[str, Any] | list[Any],
) -> None:
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    handler.send_response(status)
    handler.send_header("Content-Type", "application/json; charset=utf-8")
    handler.send_header("Content-Length", str(len(body)))
    handler.send_header("Cache-Control", "no-store")
    handler.send_header("X-Content-Type-Options", "nosniff")
    handler.send_header("Referrer-Policy", "no-referrer")
    handler.end_headers()
    handler.wfile.write(body)


def response_html(handler: BaseHTTPRequestHandler, html: str, *, script_nonce: str) -> None:
    if not SCRIPT_NONCE_PATTERN.fullmatch(script_nonce):
        raise ValueError("invalid CSP script nonce")
    body = html.encode("utf-8")
    handler.send_response(HTTPStatus.OK)
    handler.send_header("Content-Type", "text/html; charset=utf-8")
    handler.send_header("Content-Length", str(len(body)))
    handler.send_header("Cache-Control", "no-store")
    handler.send_header("X-Content-Type-Options", "nosniff")
    handler.send_header("Referrer-Policy", "no-referrer")
    handler.send_header(
        "Content-Security-Policy",
        f"default-src 'none'; style-src 'unsafe-inline'; script-src 'nonce-{script_nonce}'; "
        "script-src-attr 'none'; connect-src 'self'; img-src 'self' data:; "
        "base-uri 'none'; form-action 'none'; frame-ancestors 'none'",
    )
    handler.end_headers()
    handler.wfile.write(body)


def read_json_body(handler: BaseHTTPRequestHandler) -> dict[str, Any]:
    try:
        length = int(handler.headers.get("Content-Length") or "0")
    except ValueError as exc:
        raise ValueError("invalid content length") from exc
    if length < 0 or length > MAX_BODY_BYTES:
        raise ValueError("request body too large")
    if length == 0:
        return {}
    try:
        payload = json.loads(handler.rfile.read(length).decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("invalid JSON body") from exc
    if not isinstance(payload, dict):
        raise ValueError("JSON body must be an object")
    return payload


class PanelHandler(BaseHTTPRequestHandler):
    server: "PanelServer"

    def log_message(self, format: str, *args: Any) -> None:
        if self.server.verbose:
            super().log_message(format, *args)

    def log_request(self, code: int | str = "-", size: int | str = "-") -> None:
        # Log only the path. The access token lives in the URL fragment and is
        # never sent over HTTP, but query parameters must not leak either.
        self.log_message(
            '"%s %s" %s %s',
            self.command,
            urlparse(self.path).path,
            str(code),
            str(size),
        )

    def is_local_request(self) -> bool:
        try:
            return ipaddress.ip_address(str(self.client_address[0]).split("%", 1)[0]).is_loopback
        except ValueError:
            return False

    def has_valid_host(self) -> bool:
        values = self.headers.get_all("Host", [])
        return len(values) == 1 and parse_loopback_authority(values[0]) == self.server.loopback_authority

    def has_valid_origin(self) -> bool:
        values = self.headers.get_all("Origin", [])
        return len(values) == 1 and same_origin_loopback(values[0], self.server.loopback_authority)

    def reject_forbidden(self, error: str) -> None:
        # Close rejected writes because their unread body must not be parsed as a new request.
        self.close_connection = True
        response_json(self, HTTPStatus.FORBIDDEN, {"ok": False, "error": error})

    def authorize_transport(self) -> bool:
        if not self.has_valid_host():
            self.reject_forbidden("invalid_host")
            return False
        if not self.is_local_request():
            self.reject_forbidden("local_requests_only")
            return False
        return True

    def has_valid_session(self) -> bool:
        values = self.headers.get_all("Authorization", [])
        if len(values) != 1:
            return False
        scheme, separator, candidate = values[0].partition(" ")
        if separator != " " or scheme.casefold() != "bearer" or not candidate:
            return False
        try:
            return secrets.compare_digest(candidate, self.server.session_token)
        except TypeError:
            return False

    def has_json_content_type(self) -> bool:
        values = self.headers.get_all("Content-Type", [])
        return (
            len(values) == 1
            and values[0].split(";", 1)[0].strip().casefold() == "application/json"
        )

    def authorize_read(self) -> bool:
        if not self.authorize_transport():
            return False
        if not self.has_valid_session():
            self.close_connection = True
            response_json(self, HTTPStatus.UNAUTHORIZED, {"ok": False, "error": "authentication_required"})
            return False
        return True

    def authorize_write(self) -> bool:
        if not self.authorize_read():
            return False
        if not self.has_valid_origin():
            self.reject_forbidden("invalid_origin")
            return False
        values = self.headers.get_all("X-Self-Evolve-Nonce", [])
        try:
            valid_nonce = len(values) == 1 and secrets.compare_digest(values[0], self.server.nonce)
        except TypeError:
            valid_nonce = False
        if not valid_nonce:
            self.reject_forbidden("invalid_nonce")
            return False
        return True

    def do_GET(self) -> None:
        if not self.authorize_transport():
            return
        path = urlparse(self.path).path
        if path in {"/", "/index.html"}:
            script_nonce = secrets.token_urlsafe(18)
            response_html(
                self,
                render_panel.render_html(
                    {},
                    server_mode=True,
                    script_nonce=script_nonce,
                ),
                script_nonce=script_nonce,
            )
            return
        if not self.has_valid_session():
            self.close_connection = True
            response_json(self, HTTPStatus.UNAUTHORIZED, {"ok": False, "error": "authentication_required"})
            return
        if path == "/api/workmode-candidates":
            try:
                payload = render_panel.collect_workmode_candidates(self.server.workmode_store)
            except (OSError, ValueError):
                response_json(
                    self,
                    HTTPStatus.INTERNAL_SERVER_ERROR,
                    {"ok": False, "error": "workmode_store_corrupt"},
                )
                return
            response_json(self, HTTPStatus.OK, {"ok": True, **payload})
            return
        if path == "/api/review-documents":
            qs = parse_qs(urlparse(self.path).query)
            payload = render_panel.collect_review_documents(
                kind=qs.get("kind", [None])[0],
                sort=qs.get("sort", ["newest"])[0] or "newest",
            )
            response_json(self, HTTPStatus.OK, {"ok": True, **payload})
            return
        try:
            data = render_panel.build_panel_data(self.server.limit)
        except ProposalStoreCorruptionError:
            response_json(
                self,
                HTTPStatus.INTERNAL_SERVER_ERROR,
                {"ok": False, "error": "proposal_store_corrupt"},
            )
            return
        if path == "/api/panel":
            response_json(
                self,
                HTTPStatus.OK,
                {"ok": True, "data": data, "nonce": self.server.nonce},
            )
            return
        if path == "/api/status":
            response_json(
                self,
                HTTPStatus.OK,
                {
                    "ok": True,
                    "generated_at": data["generated_at"],
                    "skill": data["skill"],
                    "legacy_hook": data["legacy_hook"],
                    "metrics": data["metrics"],
                },
            )
            return
        if path == "/api/proposals":
            response_json(self, HTTPStatus.OK, {"ok": True, "items": data["proposals"]})
            return
        if path == "/api/tasks":
            response_json(self, HTTPStatus.OK, {"ok": True, "items": data["scheduler"]["tasks"]})
            return
        if path == "/api/runs":
            response_json(self, HTTPStatus.OK, {"ok": True, "items": data["scheduler"]["runs"]})
            return
        response_json(self, HTTPStatus.NOT_FOUND, {"ok": False, "error": "not_found"})

    def handle_auth(self) -> None:
        if not self.has_valid_origin():
            self.reject_forbidden("invalid_origin")
            return
        if not self.has_json_content_type():
            self.reject_forbidden("invalid_content_type")
            return
        try:
            payload = read_json_body(self)
        except ValueError as exc:
            response_json(self, HTTPStatus.BAD_REQUEST, {"ok": False, "error": str(exc)})
            return
        supplied = payload.get("token")
        if (
            set(payload) != {"token"}
            or not isinstance(supplied, str)
            or not self.server.consume_access_token(supplied)
        ):
            self.reject_forbidden("invalid_access_token")
            return
        response_json(
            self,
            HTTPStatus.OK,
            {"ok": True, "session_token": self.server.session_token},
        )

    def do_POST(self) -> None:
        path = urlparse(self.path).path
        if path == "/auth":
            if self.authorize_transport():
                self.handle_auth()
            return
        if not self.authorize_write():
            return
        if not self.has_json_content_type():
            self.reject_forbidden("invalid_content_type")
            return
        parts = [unquote(part) for part in path.split("/") if part]
        if len(parts) != 4 or parts[0] != "api":
            response_json(self, HTTPStatus.NOT_FOUND, {"ok": False, "error": "not_found"})
            return
        try:
            payload = read_json_body(self)
        except ValueError as exc:
            response_json(self, HTTPStatus.BAD_REQUEST, {"ok": False, "error": str(exc)})
            return

        if parts[1] == "proposals" and parts[3] == "decision":
            self.handle_proposal_decision(parts[2], payload)
            return
        if parts[1] == "workmode-candidates" and parts[3] == "decision":
            self.handle_workmode_decision(parts[2], payload)
            return
        response_json(self, HTTPStatus.NOT_FOUND, {"ok": False, "error": "not_found"})

    def handle_proposal_decision(self, proposal_id: str, payload: dict[str, Any]) -> None:
        decision = str(payload.get("decision", ""))
        if decision not in HUMAN_DECISIONS - {"pending"}:
            response_json(self, HTTPStatus.BAD_REQUEST, {"ok": False, "error": "invalid_decision"})
            return
        partial = payload.get("partial_items", [])
        if not isinstance(partial, list):
            response_json(self, HTTPStatus.BAD_REQUEST, {"ok": False, "error": "partial_items_must_be_list"})
            return
        try:
            record = self.server.store.decide(
                proposal_id,
                decision=decision,
                reason=str(payload.get("reason", "")),
                reviewer="local-panel",
                partial_items=[str(item) for item in partial],
                expected_revision_hash=str(payload.get("revision_hash", "")),
                expected_artifact_sha256=str(payload.get("artifact_sha256", "")),
            )
        except KeyError:
            response_json(self, HTTPStatus.NOT_FOUND, {"ok": False, "error": "proposal_not_found"})
            return
        except ProposalStoreCorruptionError:
            response_json(
                self,
                HTTPStatus.INTERNAL_SERVER_ERROR,
                {"ok": False, "error": "proposal_store_corrupt"},
            )
            return
        except ValueError as exc:
            response_json(self, HTTPStatus.CONFLICT, {"ok": False, "error": str(exc)})
            return
        response_json(
            self,
            HTTPStatus.OK,
            {
                "ok": True,
                "proposal_id": record["proposal_id"],
                "human_decision": record["human_decision"],
            },
        )

    def handle_workmode_decision(self, candidate_id: str, payload: dict[str, Any]) -> None:
        decision = str(payload.get("decision", ""))
        if decision not in WORKMODE_DECISIONS:
            response_json(self, HTTPStatus.BAD_REQUEST, {"ok": False, "error": "invalid_decision"})
            return
        try:
            record = self.server.workmode_store.decide(
                candidate_id,
                revision=str(payload.get("revision", "")),
                decision=decision,
                reason=str(payload.get("reason", "")),
            )
        except KeyError:
            response_json(self, HTTPStatus.NOT_FOUND, {"ok": False, "error": "candidate_not_found"})
            return
        except ValueError as exc:
            message = str(exc)
            # revision 变更 → 409(前端刷新);reason 隐私拒绝等其他 ValueError → 400
            status = HTTPStatus.CONFLICT if "revision" in message else HTTPStatus.BAD_REQUEST
            response_json(self, status, {"ok": False, "error": message})
            return
        response_json(
            self,
            HTTPStatus.OK,
            {
                "ok": True,
                "candidate_id": record["candidate_id"],
                "human_decision": record["human_decision"],
            },
        )

class PanelServer(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(
        self,
        address: tuple[str, int],
        *,
        nonce: str,
        access_token: str,
        session_token: str,
        limit: int,
        verbose: bool,
        store: ProposalStore | None = None,
        workmode_store: WorkmodeLedger | None = None,
    ) -> None:
        raw_host, port = address
        bind_host = "127.0.0.1" if raw_host.casefold() == "localhost" else raw_host
        if "%" in bind_host:
            raise ValueError("scoped IPv6 addresses are not supported")
        try:
            requested_address = ipaddress.ip_address(bind_host)
        except ValueError as exc:
            raise ValueError("panel address must be a numeric loopback address") from exc
        if not requested_address.is_loopback:
            raise ValueError("panel address must be loopback")
        self.address_family = socket.AF_INET6 if requested_address.version == 6 else socket.AF_INET
        super().__init__((requested_address.compressed, port), PanelHandler)
        actual_address = ipaddress.ip_address(str(self.server_address[0]).split("%", 1)[0])
        if not actual_address.is_loopback:
            self.server_close()
            raise ValueError("panel resolved to a non-loopback address")
        self.loopback_authority = (actual_address.compressed, int(self.server_address[1]))
        self.origin = f"http://{format_authority(*self.loopback_authority)}"
        if not AUTH_TOKEN_PATTERN.fullmatch(access_token):
            self.server_close()
            raise ValueError("invalid panel access token")
        if not AUTH_TOKEN_PATTERN.fullmatch(session_token):
            self.server_close()
            raise ValueError("invalid panel session token")
        self.nonce = nonce
        self.access_token = access_token
        self.session_token = session_token
        self._access_token_lock = threading.Lock()
        self.limit = limit
        self.verbose = verbose
        self.store = store or ProposalStore(PROPOSALS_ROOT)
        assert_external_write_path(self.store.root, label="proposal_root")
        self.workmode_store = workmode_store or WorkmodeLedger()

    def consume_access_token(self, candidate: str) -> bool:
        """Validate and invalidate the startup URL token exactly once."""
        with self._access_token_lock:
            if not self.access_token:
                return False
            try:
                valid = secrets.compare_digest(candidate, self.access_token)
            except TypeError:
                valid = False
            if valid:
                self.access_token = ""
            return valid


def main() -> int:
    parser = argparse.ArgumentParser(description="Serve the Self Evolve localhost review panel.")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--limit", type=int, default=80)
    parser.add_argument("--open", action="store_true")
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args()
    try:
        assert_runtime_ready()
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    if args.host not in {"127.0.0.1", "localhost", "::1"}:
        print("panel.py 只能绑定到本机回环地址", file=sys.stderr)
        return 2
    nonce = secrets.token_urlsafe(24)
    access_token = secrets.token_urlsafe(32)
    session_token = secrets.token_urlsafe(32)
    server = PanelServer(
        (args.host, args.port),
        nonce=nonce,
        access_token=access_token,
        session_token=session_token,
        limit=max(10, min(args.limit, 500)),
        verbose=args.verbose,
    )
    url = f"{server.origin}/#token={access_token}"
    print(f"Self Evolve authenticated panel URL (one-time fragment): {url}", flush=True)
    if args.open:
        webbrowser.open(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nSelf Evolve panel stopped.")
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
