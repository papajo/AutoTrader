"""CLI entrypoint to launch the AutoTrader Live Execution Desk."""

import argparse
import os
import sys
from desk.server import start_desk_server


def main():
    default_port = int(os.environ.get("PORT", "8585"))
    parser = argparse.ArgumentParser(description="AutoTrader Live Execution Desk Web Server")
    parser.add_argument("--port", type=int, default=default_port, help=f"Port to bind server (default: {default_port})")
    parser.add_argument("--host", type=str, default="127.0.0.1", help="Host interface (default: 127.0.0.1)")

    args = parser.parse_args()

    print("\n" + "=" * 70)
    print("🚀 AUTOTRADER: LIVE EXECUTION DESK")
    print("=" * 70)
    print(f"• Live Desk GUI       : http://{args.host}:{args.port}")
    print(f"• Backtest Reports    : http://{args.host}:{args.port}/reports/index.html")
    print(f"• WebSocket Stream    : ws://{args.host}:{args.port}/ws/live")
    print(f"• Emergency Controls  : Integrated Kill Switch & Laya Risk Gates")
    print("=" * 70 + "\n")

    start_desk_server(host=args.host, port=args.port)


if __name__ == "__main__":
    main()
