"""Tiny WebSocket sniffer — connects to /ws and dumps every event line-by-line.

Run via:
    .venv/Scripts/python.exe scripts/ws_sniffer.py
"""
import asyncio
import json
import sys
from datetime import datetime

import websockets


URL = "ws://127.0.0.1:8000/ws"


async def main() -> None:
    print(f"[sniffer] connecting to {URL}", flush=True)
    try:
        async with websockets.connect(URL) as ws:
            print("[sniffer] connected", flush=True)
            while True:
                raw = await ws.recv()
                try:
                    msg = json.loads(raw)
                except Exception:
                    msg = {"raw": raw}
                stamp = datetime.utcnow().strftime("%H:%M:%S")
                etype = msg.get("type", "?")
                # Compact one-line summary per event type
                if etype == "DOCUMENT_ANALYZED":
                    summary = f"{msg.get('progress','')} {msg.get('applicant_name')} cbs={msg.get('cbs_match_score'):.3f} tool={msg.get('origin_tool')}"
                elif etype == "RING_DETECTED":
                    summary = f"ring={msg.get('ring_id')} size={msg.get('ring_size')} action={msg.get('recommended_action')} conf={msg.get('phantom_confidence_pct')}%"
                elif etype == "BATCH_COMPLETE":
                    summary = f"rings={msg.get('ring_count')} nodes={len(msg.get('graph_data',{}).get('nodes',[]))} links={len(msg.get('graph_data',{}).get('links',[]))}"
                elif etype == "GRAPH_BUILT":
                    summary = f"nodes={msg.get('nodes')} edges={msg.get('total_edges')} breakdown={msg.get('edges_by_type')}"
                elif etype == "COMMUNITIES_DETECTED":
                    summary = f"communities={msg.get('communities')} suspicious={msg.get('suspicious')}"
                elif etype == "ANALYSIS_STARTED":
                    summary = f"batch={msg.get('batch_id')} total={msg.get('total')}"
                else:
                    summary = json.dumps({k: v for k, v in msg.items() if k != 'report'})[:120]
                print(f"[{stamp}] {etype:22s} {summary}", flush=True)
    except KeyboardInterrupt:
        pass
    except Exception as e:
        print(f"[sniffer] error: {e}", file=sys.stderr, flush=True)
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
