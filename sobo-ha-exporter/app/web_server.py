"""Lightweight, safe Ingress Web Server for Home Assistant Add-on UI."""

import json
import logging
import threading
from collections.abc import Callable
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

from app.status_manager import StatusManager

logger = logging.getLogger(__name__)

STATIC_DIR = Path(__file__).parent / "static"


class IngressRequestHandler(BaseHTTPRequestHandler):
    """HTTP request handler for Home Assistant Ingress web interface."""

    server: "IngressHTTPServer"

    def log_message(self, format: str, *args: Any) -> None:
        """Redirect HTTP server logs to standard Python logger."""
        logger.debug("Ingress HTTP: %s", format % args)

    def _send_json(self, data: Any, status: int = HTTPStatus.OK) -> None:
        content = json.dumps(data, indent=2, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(content)))
        self.send_header("Cache-Control", "no-cache, no-store, must-revalidate")
        self.end_headers()
        self.wfile.write(content)

    def _send_file(self, file_path: Path, mime_type: str, as_attachment: bool = False) -> None:
        if not file_path.exists():
            self._send_json({"error": "File not found"}, status=HTTPStatus.NOT_FOUND)
            return

        try:
            content = file_path.read_bytes()
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", mime_type)
            self.send_header("Content-Length", str(len(content)))
            if as_attachment:
                self.send_header("Content-Disposition", f'attachment; filename="{file_path.name}"')
            self.end_headers()
            self.wfile.write(content)
        except Exception as e:
            logger.error("Error reading file %s: %s", file_path, e)
            self._send_json(
                {"error": "Internal server error"}, status=HTTPStatus.INTERNAL_SERVER_ERROR
            )

    def _resolve_clean_path(self) -> str:
        """Extract clean endpoint path stripped of Home Assistant Ingress prefix."""
        path = self.path.split("?")[0]
        ingress_header = self.headers.get("X-Ingress-Path", "").rstrip("/")
        if ingress_header and path.startswith(ingress_header):
            path = path[len(ingress_header) :]
        if not path:
            path = "/"
        return path

    def do_GET(self) -> None:
        clean_path = self._resolve_clean_path()

        if clean_path in ["/", "/index.html"]:
            self._send_file(STATIC_DIR / "index.html", "text/html; charset=utf-8")
        elif clean_path == "/style.css":
            self._send_file(STATIC_DIR / "style.css", "text/css; charset=utf-8")
        elif clean_path == "/app.js":
            self._send_file(STATIC_DIR / "app.js", "application/javascript; charset=utf-8")
        elif clean_path == "/api/status":
            self._send_json(self.server.status_mgr.get_status())
        elif clean_path == "/api/export-preview":
            self._handle_json_file(self.server.status_mgr.preview_file)
        elif clean_path == "/api/diagnostics":
            self._handle_json_file(self.server.status_mgr.failed_manifest_file)
        elif clean_path == "/api/generated-output":
            self._handle_json_file(self.server.status_mgr.output_file)
        elif clean_path == "/api/setup":
            self._handle_setup_request()
        elif clean_path == "/api/diagnostics/download":
            logger.info("Ingress user requested diagnostic manifest download.")
            self._send_file(
                self.server.status_mgr.failed_manifest_file,
                "application/json",
                as_attachment=True,
            )
        else:
            self._send_json({"error": "Not Found"}, status=HTTPStatus.NOT_FOUND)

    def do_POST(self) -> None:
        clean_path = self._resolve_clean_path()

        if clean_path == "/api/run-export":
            self._handle_run_export()
        elif clean_path == "/api/test-git":
            self._handle_test_git()
        else:
            self._send_json({"error": "Not Found"}, status=HTTPStatus.NOT_FOUND)

    def _handle_json_file(self, json_path: Path) -> None:
        if not json_path.exists():
            self._send_json({}, status=HTTPStatus.OK)
            return
        try:
            data = json.loads(json_path.read_text(encoding="utf-8"))
            self._send_json(data)
        except Exception as e:
            logger.error("Error serving %s: %s", json_path, e)
            self._send_json(
                {"error": "Failed to read data"}, status=HTTPStatus.INTERNAL_SERVER_ERROR
            )

    def _handle_setup_request(self) -> None:
        pub_key_path = self.server.data_dir / "ssh" / "id_ed25519.pub"
        pub_key = ""
        if pub_key_path.exists():
            pub_key = pub_key_path.read_text(encoding="utf-8").strip()

        status_data = self.server.status_mgr.get_status()
        setup_data = {
            "public_key": pub_key,
            "destination_repository": status_data.get("destination_repository", ""),
            "branch": status_data.get("branch", "main"),
            "connection_status": status_data.get("git_connection_status", "untested"),
        }
        self._send_json(setup_data)

    def _handle_run_export(self) -> None:
        logger.info("Manual export request received via Ingress UI.")
        acquired = self.server.export_lock.acquire(blocking=False)
        if not acquired:
            logger.warning("Concurrent export request rejected by export_lock.")
            self._send_json(
                {"success": False, "message": "An export run is already in progress."},
                status=HTTPStatus.CONFLICT,
            )
            return

        try:
            # Trigger export in a separate thread so HTTP response is returned immediately
            def _runner() -> None:
                try:
                    self.server.run_export_fn()
                finally:
                    self.server.export_lock.release()

            t = threading.Thread(target=_runner, daemon=True)
            t.start()

            self._send_json({"success": True, "message": "Manual export triggered successfully."})
        except Exception as e:
            self.server.export_lock.release()
            logger.error("Error launching manual export: %s", e)
            self._send_json(
                {"success": False, "message": f"Failed to trigger export: {e}"},
                status=HTTPStatus.INTERNAL_SERVER_ERROR,
            )

    def _handle_test_git(self) -> None:
        logger.info("Git connection test requested via Ingress UI.")
        try:
            res = self.server.test_git_fn()
            self._send_json(res)
        except Exception as e:
            logger.error("Git test failed: %s", e)
            self._send_json(
                {"success": False, "message": f"Git connection test failed: {e}"},
                status=HTTPStatus.INTERNAL_SERVER_ERROR,
            )


class IngressHTTPServer(ThreadingHTTPServer):
    """Custom ThreadingHTTPServer carrying application dependencies."""

    def __init__(
        self,
        server_address: tuple[str, int],
        RequestHandlerClass: type[BaseHTTPRequestHandler],
        status_mgr: StatusManager,
        data_dir: Path,
        export_lock: threading.Lock,
        run_export_fn: Callable[[], bool],
        test_git_fn: Callable[[], dict[str, Any]],
    ):
        super().__init__(server_address, RequestHandlerClass)
        self.status_mgr = status_mgr
        self.data_dir = data_dir
        self.export_lock = export_lock
        self.run_export_fn = run_export_fn
        self.test_git_fn = test_git_fn


class WebServer:
    """Manages starting and cleanly shutting down the Ingress HTTP Server."""

    def __init__(
        self,
        host: str,
        port: int,
        status_mgr: StatusManager,
        data_dir: Path,
        export_lock: threading.Lock,
        run_export_fn: Callable[[], bool],
        test_git_fn: Callable[[], dict[str, Any]],
    ):
        self.host = host
        self.port = port
        self.server = IngressHTTPServer(
            (host, port),
            IngressRequestHandler,
            status_mgr=status_mgr,
            data_dir=data_dir,
            export_lock=export_lock,
            run_export_fn=run_export_fn,
            test_git_fn=test_git_fn,
        )
        self.thread: threading.Thread | None = None

    def start(self) -> None:
        """Start the WebServer in a daemon background thread."""
        logger.info("Starting Ingress HTTP web server on %s:%d...", self.host, self.port)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        logger.info("Ingress HTTP web server is running.")

    def stop(self) -> None:
        """Shutdown the WebServer cleanly."""
        logger.info("Shutting down Ingress HTTP web server...")
        self.server.shutdown()
        self.server.server_close()
        if self.thread and self.thread.is_alive():
            self.thread.join(timeout=3)
        logger.info("Ingress HTTP web server stopped.")
