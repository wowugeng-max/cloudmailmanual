from __future__ import annotations

from cloudmailmanual_app.config import parse_args, resolve_run_port
from cloudmailmanual_app.factory import create_app


app = create_app()


if __name__ == "__main__":
    args = parse_args()
    port = resolve_run_port(args.port)
    app.run(host=args.host, port=port, debug=args.debug)
