"""Capture actual public mainnet observations, never sign or submit a transaction."""
import json
import time
from pathlib import Path
from arc_lens import ReadOnlyRPC, LensError, USDC, SYSTEM, TRANSFER_TOPIC, quantity, account_evidence, transaction_evidence, verify_evidence

root = Path(__file__).resolve().parent
started = time.monotonic()
rpc = ReadOnlyRPC()
rpc.check_chain()
head = quantity(rpc.call("eth_blockNumber", []))
# A four-block offset reduces transient head-skew errors between RPC backends.
end = max(0, head - 4)
logs = rpc.call("eth_getLogs", [{"fromBlock": hex(max(0, end - 128)), "toBlock": hex(end),
                                "address": [USDC, SYSTEM], "topics": [TRANSFER_TOPIC]}])
hashes = []
for log in reversed(logs):
    if log["address"].lower() == USDC and log["transactionHash"] not in hashes:
        hashes.append(log["transactionHash"])
    if len(hashes) >= 8:
        break
selected = None
for value in hashes:
    try:
        doc = transaction_evidence(ReadOnlyRPC(), value)
        if doc["payload"].get("transfers", {}).get("paired_count", 0) > 0:
            selected = doc
            break
    except LensError:
        continue
if selected is None:
    raise SystemExit("No reconciled dual-emitter transaction found in the observed block window. No demo was fabricated.")
account = account_evidence(ReadOnlyRPC(), selected["payload"]["from"])
verify_evidence(account)
verify_evidence(selected)
bundle = {"description": "Recorded public Arc mainnet observations, not a synthetic fixture or a live page reading.",
          "captured_at_utc": selected["captured_at_utc"], "capture_elapsed_seconds": round(time.monotonic() - started, 3),
          "search_block_range": [max(0, end - 128), end], "account": account, "transaction": selected}
for folder in (root / "evidence", root / "web" / "evidence"):
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "demo-bundle.json").write_text(json.dumps(bundle, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
for kind, doc in (("account", account), ("transaction", selected)):
    (root / "evidence" / f"{kind}-mainnet.json").write_text(json.dumps(doc, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
print(json.dumps({"elapsed_seconds": bundle["capture_elapsed_seconds"], "account": account["payload"]["address"],
                  "transaction": selected["payload"]["hash"], "balance": account["payload"]["balance"],
                  "fee": selected["payload"]["fee"], "transfers": selected["payload"]["transfers"]}, indent=2))
