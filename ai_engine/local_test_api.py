import json
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import parse_qs, urlparse


RETRY_ONCE_REQUESTS = 0


class LocalTestAPIHandler(BaseHTTPRequestHandler):

    def send_json(self, status_code, data, headers=None):
        body = json.dumps(data).encode("utf-8")

        self.send_response(status_code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))

        for key, value in (headers or {}).items():
            self.send_header(key, value)

        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        global RETRY_ONCE_REQUESTS

        parsed = urlparse(self.path)
        query = parse_qs(parsed.query)

        if parsed.path != "/products":
            self.send_json(404, {"error_type": "not_found"})
            return

        # Return 429 once, then 200 for the retry test.
        if query.get("scenario") == ["retry_once"]:
            RETRY_ONCE_REQUESTS += 1

            if RETRY_ONCE_REQUESTS == 1:
                self.send_json(
                    429,
                    {"error_type": "rate_limit_exceeded"},
                    {"Retry-After": "1"},
                )
            else:
                self.send_json(
                    200,
                    {"message": "Retry succeeded"},
                )

            return

        # Simulate a rate-limited request on every call.
        if query.get("scenario") == ["rate_limit"]:
            self.send_json(
                429,
                {"error_type": "rate_limit_exceeded"},
                {"Retry-After": "1"},
            )
            return

        # Validate the requested page size.
        try:
            limit = int(query.get("limit", ["20"])[0])
        except ValueError:
            self.send_json(
                400,
                {"error_type": "validation_error"},
            )
            return

        if limit < 1:
            self.send_json(
                400,
                {"error_type": "validation_error"},
            )
            return

        # Handle cursor-based pagination.
        cursor = query.get("cursor", [None])[0]

        if limit == 20:

            if cursor is None:
                self.send_json(
                    200,
                    {
                        "default_page_size": 20,
                        "has_next_page": True,
                        "next_cursor": "page-2",
                        "products": [
                            {
                                "id": 1,
                                "price": 100,
                                "currency": "INR",
                            }
                        ],
                    },
                )
                return

            if cursor == "page-2":
                self.send_json(
                    200,
                    {
                        "default_page_size": 20,
                        "has_next_page": False,
                        "next_cursor": None,
                        "products": [
                            {
                                "id": 2,
                                "price": 200,
                                "currency": "INR",
                            }
                        ],
                    },
                )
                return

            self.send_json(
                400,
                {"error_type": "invalid_cursor"},
            )
            return

        # Semantic-invariant test response.
        self.send_json(
            200,
            {
                "price_minimum": 0,
                "currency": "INR",
                "unit": "rupees",
                "products": [
                    {
                        "id": 1,
                        "price": 100,
                        "currency": "INR",
                    }
                ],
            },
        )

    def log_message(self, format_string, *args):
        print(f"[local-api] {args[0]}")


if __name__ == "__main__":
    server = HTTPServer(
        ("127.0.0.1", 8765),
        LocalTestAPIHandler,
    )

    print("KintsuTech local test API: http://127.0.0.1:8765")
    print("Press Ctrl+C to stop.")

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopping local test API.")
    finally:
        server.server_close()
