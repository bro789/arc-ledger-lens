"""Arc Ledger Lens. Standard-library-only, read-only Arc mainnet evidence collector."""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

CHAIN_ID = 5042
RPC_URL = "https://rpc.mainnet.arc.io"
USDC = "0x3600000000000000000000000000000000000000"
SYSTEM = "0xfffffffffffffffffffffffffffffffffffffffe"
TRANSFER_TOPIC = "0xddf252ad1be2c89b69c2b068fc378daa952ba7f163c4a11628f55a4df523b3ef"
SCALE = 10**12
NATIVE_UNIT = 10**18
ERC20_UNIT = 10**6
ZERO = "0x" + "0" * 40
ALLOWED_METHODS = frozenset({
    "eth_chainId", "eth_blockNumber", "eth_getBlockByNumber", "eth_getBlockByHash",
    "eth_getBalance", "eth_call", "eth_gasPrice", "eth_getTransactionReceipt",
    "eth_getTransactionByHash", "eth_getLogs",
})
SOURCES = [
    "https://docs.arc.io/arc/references/rpc-endpoints",
    "https://docs.arc.io/arc/references/usdc-system-events",
    "https://docs.arc.io/arc/references/gas-and-fees",
    "https://github.com/circlefin/skills/blob/master/plugins/circle/skills/use-arc/SKILL.md",
]
TRUST = "RPC observation. Digest proves file integrity only; no validator signatures, state proof or consensus certificate is verified."


class LensError(ValueError):
    pass


def address(value: str) -> str:
    if not isinstance(value, str) or not re.fullmatch(r"0x[0-9a-fA-F]{40}", value):
        raise LensError("Enter a 0x-prefixed 40-character EVM address.")
    return value.lower()


def tx_hash(value: str) -> str:
    if not isinstance(value, str) or not re.fullmatch(r"0x[0-9a-fA-F]{64}", value):
        raise LensError("Enter a 0x-prefixed 64-character transaction hash.")
    return value.lower()


def quantity(value: str) -> int:
    if not isinstance(value, str) or not re.fullmatch(r"0x[0-9a-fA-F]+", value):
        raise LensError("RPC returned a malformed non-negative hex quantity.")
    return int(value, 16)


def units(value: int, decimals: int) -> str:
    """No floats, exponent notation or precision loss for uint256 amounts."""
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise LensError("Amount must be a non-negative integer.")
    whole, fraction = divmod(value, 10**decimals)
    suffix = str(fraction).rjust(decimals, "0").rstrip("0")
    return str(whole) + (("." + suffix) if suffix else "")


def parse_usdc(value: str) -> int:
    if not isinstance(value, str) or not re.fullmatch(r"(?:0|[1-9][0-9]{0,71})(?:\.[0-9]{1,6})?", value):
        raise LensError("Use a non-negative USDC amount with at most 6 decimal places.")
    whole, _, fraction = value.partition(".")
    result = int(whole) * ERC20_UNIT + int(fraction.ljust(6, "0") or "0")
    if result * SCALE >= 2**256:
        raise LensError("Amount exceeds the native uint256 range.")
    return result


def balance_math(native: int, erc20: int) -> dict:
    expected, dust = divmod(native, SCALE)
    matched = expected == erc20
    return {
        "native_raw_18": str(native), "erc20_raw_6": str(erc20),
        "display_usdc": units(erc20, 6),
        "native_gas_precision_usdc": units(native, 18),
        "expected_erc20_raw_6": str(expected), "residual_native_units": str(dust),
        "residual_usdc": units(dust, 18), "views_reconcile": matched,
        "truncated_below_micro_usdc": dust != 0,
        "double_counted_display_usdc": units(erc20 * 2, 6),
        "explanation": (
            "These are two interfaces to one USDC balance. Display the ERC-20 view once; "
            "retain native precision for exact gas arithmetic. Never add the views."
        ),
    }


def budget_math(native: int, amount_6: int, gas_limit: int, max_fee_18: int, observed_base: int | None) -> dict:
    if not 21000 <= gas_limit <= 30000000:
        raise LensError("Gas limit must be between 21,000 and 30,000,000.")
    if max_fee_18 <= 0:
        raise LensError("The gas fee cap must be greater than zero.")
    transfer = amount_6 * SCALE
    fee_cap = gas_limit * max_fee_18
    required = transfer + fee_cap
    shortage = max(0, required - native)
    return {
        "amount_usdc": units(amount_6, 6), "amount_native_units": str(transfer),
        "gas_limit": gas_limit, "max_fee_per_gas_native_units": str(max_fee_18),
        "max_fee_gwei": units(max_fee_18, 9), "gas_budget_cap_usdc": units(fee_cap, 18),
        "total_budget_cap_usdc": units(required, 18), "shortfall_usdc": units(shortage, 18),
        "can_cover_budget_cap": shortage == 0,
        "cap_below_observed_block_base_fee": observed_base is not None and max_fee_18 < observed_base,
        "cap_below_20_gwei_submission_floor": max_fee_18 < 20 * 10**9,
        "note": "A budget ceiling, not an execution estimate or approval. Calldata, contract behavior, account restrictions and future fees are not simulated.",
    }


class ReadOnlyRPC:
    """No signing, wallets, keys, broadcast methods or caller-selected HTTP proxy."""

    def __init__(self, endpoint: str = RPC_URL, timeout: float = 12):
        if endpoint != RPC_URL:
            raise LensError("This build uses only Circle's official Arc mainnet endpoint.")
        self.endpoint, self.timeout = endpoint, timeout
        self.trace: list[dict] = []

    def call(self, method: str, params: list) -> object:
        if method not in ALLOWED_METHODS:
            raise LensError("The requested RPC method is outside the read-only allowlist.")
        request = {"jsonrpc": "2.0", "id": len(self.trace) + 1, "method": method, "params": params}
        started = time.monotonic()
        response = None
        for attempt in range(3):
            try:
                req = urllib.request.Request(
                    self.endpoint, json.dumps(request).encode(),
                    {"Content-Type": "application/json", "Accept": "application/json",
                     "User-Agent": "ArcLedgerLens/0.1 (read-only open-source tool)"},
                )
                with urllib.request.urlopen(req, timeout=self.timeout) as stream:
                    raw = stream.read(4 * 1024 * 1024 + 1)
                if len(raw) > 4 * 1024 * 1024:
                    raise LensError("RPC response exceeded the 4 MB bound.")
                response = json.loads(raw)
                if not isinstance(response, dict) or response.get("jsonrpc") != "2.0" or response.get("id") != request["id"]:
                    raise LensError("RPC returned an invalid response envelope.")
                error = response.get("error")
                if isinstance(error, dict) and error.get("code") == -32014 and attempt < 2:
                    time.sleep(0.3 * (attempt + 1))
                    continue
                break
            except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
                raise LensError("Arc RPC is unavailable or returned invalid JSON. Retry later; no chain request was written.") from exc
        self.trace.append({"request": request, "response": response,
                           "elapsed_ms": round((time.monotonic() - started) * 1000)})
        if response.get("error"):
            error = response["error"]
            raise LensError(f"RPC error {error.get('code')}: {error.get('message', 'unknown')}")
        if "result" not in response:
            raise LensError("RPC response omitted result.")
        return response["result"]

    def check_chain(self) -> None:
        actual = quantity(self.call("eth_chainId", []))
        if actual != CHAIN_ID:
            raise LensError(f"Wrong chain: expected Arc mainnet 5042, received {actual}.")


def _block_summary(block: dict) -> dict:
    return {"number": quantity(block["number"]), "number_hex": block["number"],
            "hash": tx_hash(block["hash"]), "timestamp_utc": datetime.fromtimestamp(
                quantity(block["timestamp"]), timezone.utc).isoformat(),
            "base_fee_native_units": str(quantity(block["baseFeePerGas"])) if block.get("baseFeePerGas") else None}


def _new_evidence(kind: str, payload: dict, rpc) -> dict:
    doc = {"schema": "arc-ledger-lens/1", "kind": kind, "chain_id": CHAIN_ID,
           "network": "Arc mainnet", "captured_at_utc": datetime.now(timezone.utc).isoformat(),
           "endpoint": rpc.endpoint, "mode": "live_read_only", "payload": payload,
           "rpc_trace": rpc.trace, "sources": SOURCES,
           "trust": TRUST}
    doc["sha256"] = digest(doc)
    return doc


def digest(doc: dict) -> str:
    content = {k: v for k, v in doc.items() if k != "sha256"}
    canonical = json.dumps(content, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def account_evidence(rpc, account: str, amount: str = "1", gas_limit: int = 21000, max_fee_gwei: str | None = None) -> dict:
    account = address(account)
    amount_6 = parse_usdc(amount)
    rpc.check_chain()
    block = rpc.call("eth_getBlockByNumber", ["latest", False])
    if not isinstance(block, dict):
        raise LensError("The RPC did not return a current block.")
    tag = block["number"]
    native = quantity(rpc.call("eth_getBalance", [account, tag]))
    erc20 = quantity(rpc.call("eth_call", [{"to": USDC, "data": "0x70a08231" + account[2:].rjust(64, "0")}, tag]))
    decimals = quantity(rpc.call("eth_call", [{"to": USDC, "data": "0x313ce567"}, tag]))
    if decimals != 6:
        raise LensError("USDC decimals() is not 6; refusing misleading balance reconciliation.")
    gas_price = quantity(rpc.call("eth_gasPrice", []))
    if max_fee_gwei is None:
        fee_cap = gas_price
    else:
        if not re.fullmatch(r"(?:0|[1-9][0-9]{0,20})(?:\.[0-9]{1,9})?", max_fee_gwei):
            raise LensError("Gas cap must be a non-negative Gwei amount with at most 9 decimal places.")
        whole, _, part = max_fee_gwei.partition(".")
        fee_cap = int(whole) * 10**9 + int(part.ljust(9, "0") or "0")
    after = rpc.call("eth_getBlockByNumber", [tag, False])
    if not isinstance(after, dict) or after.get("hash") != block["hash"]:
        raise LensError("Block identity changed while reading. Discarding this snapshot; retry.")
    state = balance_math(native, erc20)
    payload = {"address": account, "block": _block_summary(block), "block_identity_rechecked": True,
               "balance": state, "erc20_decimals_observed": decimals,
               "suggested_gas_price_native_units": str(gas_price),
               "budget": budget_math(native, amount_6, gas_limit, fee_cap,
                                     quantity(block["baseFeePerGas"]) if block.get("baseFeePerGas") else None),
               "warnings": [] if state["views_reconcile"] else ["USDC views do not reconcile at the pinned block. Do not use the balance for accounting until investigated."]}
    return _new_evidence("account", payload, rpc)


def reconcile_transfers(logs: list[dict]) -> dict:
    """System stream is canonical; ERC-20 matching never increases canonical amounts.

    Multiset matching avoids dropping equal repeated transfers. It does not assert
    call-level pairing when equal flows repeat; indices are evidence, not execution traces.
    """
    native, token, malformed = [], [], 0
    for log in logs:
        emitter = str(log.get("address", "")).lower()
        topics = log.get("topics", [])
        if emitter not in (SYSTEM, USDC) or not topics or str(topics[0]).lower() != TRANSFER_TOPIC:
            continue
        if log.get("removed"):
            malformed += 1
            continue
        try:
            if len(topics) != 3 or any(not re.fullmatch(r"0x[0-9a-fA-F]{64}", x) for x in topics):
                raise LensError("Malformed Transfer topic.")
            if any(int(x[2:26], 16) != 0 for x in topics[1:]):
                raise LensError("Non-canonical indexed address.")
            if not re.fullmatch(r"0x[0-9a-fA-F]{64}", log.get("data", "")):
                raise LensError("Malformed Transfer amount.")
            item = {"from": address("0x" + topics[1][-40:]), "to": address("0x" + topics[2][-40:]),
                    "amount": quantity(log["data"]), "log_index": quantity(log["logIndex"]), "emitter": emitter}
            if emitter == SYSTEM and (item["amount"] == 0 or item["from"] == item["to"]):
                raise LensError("System stream must not contain zero-value or self-transfer events.")
            (native if emitter == SYSTEM else token).append(item)
        except (LensError, KeyError, TypeError):
            malformed += 1
    native.sort(key=lambda x: x["log_index"])
    token.sort(key=lambda x: x["log_index"])
    consumed: set[int] = set()
    movements = []
    for item in native:
        match = None
        for i, candidate in enumerate(token):
            if i not in consumed and candidate["from"] == item["from"] and candidate["to"] == item["to"] and candidate["amount"] * SCALE == item["amount"]:
                match = candidate
                consumed.add(i)
                break
        movements.append({"from": item["from"], "to": item["to"], "amount_native_units": str(item["amount"]),
                          "amount_usdc": units(item["amount"], 18), "system_log_index": item["log_index"],
                          "erc20_log_index": match["log_index"] if match else None,
                          "kind": "mint" if item["from"] == ZERO else "burn" if item["to"] == ZERO else "transfer",
                          "dual_emitter_match": match is not None})
    native_total = sum(x["amount"] for x in native)
    token_total = sum(x["amount"] * SCALE for x in token)
    extras = [x for i, x in enumerate(token) if i not in consumed and x["amount"] != 0 and x["from"] != x["to"]]
    noops = [x for i, x in enumerate(token) if i not in consumed and (x["amount"] == 0 or x["from"] == x["to"])]
    return {
        "canonical_system_movements": movements,
        "system_count": len(native), "erc20_count": len(token), "paired_count": len(consumed),
        "unmatched_erc20_count": len(extras), "erc20_no_balance_movement_count": len(noops),
        "malformed_or_removed_count": malformed,
        "canonical_gross_usdc": units(native_total, 18),
        "naive_two_stream_gross_usdc": units(native_total + token_total, 18),
        "duplicate_overcount_usdc": units(sum(token[i]["amount"] * SCALE for i in consumed), 18),
        "note": "Gross movement volume is not a wallet balance delta. System events cover explicit transfers; receipt gas charges are separate. Matching repeated identical flows is a multiset reconciliation, not call-trace attribution.",
    }


def receipt_math(receipt: dict, transaction: dict, block: dict) -> dict:
    if tx_hash(receipt["transactionHash"]) != tx_hash(transaction["hash"]):
        raise LensError("Receipt and transaction hashes disagree.")
    if not (receipt.get("blockHash") == transaction.get("blockHash") == block.get("hash")):
        raise LensError("Receipt, transaction and block identities disagree.")
    if not (receipt.get("blockNumber") == transaction.get("blockNumber") == block.get("number")):
        raise LensError("Receipt, transaction and block numbers disagree.")
    if receipt.get("transactionIndex") != transaction.get("transactionIndex"):
        raise LensError("Receipt and transaction indices disagree.")
    used, effective = quantity(receipt["gasUsed"]), quantity(receipt["effectiveGasPrice"])
    limit = quantity(transaction["gas"])
    status = quantity(receipt["status"])
    if status not in (0, 1) or used > limit:
        raise LensError("Invalid receipt status or gas usage.")
    if status == 0 and receipt.get("logs"):
        raise LensError("Failed receipt contains logs; refusing apparent reverted transfers.")
    indices = set()
    for log in receipt.get("logs", []):
        index = quantity(log["logIndex"])
        if index in indices:
            raise LensError("Receipt contains duplicate log indices.")
        indices.add(index)
        if log.get("transactionHash") != receipt["transactionHash"] or log.get("blockHash") != receipt["blockHash"] or log.get("blockNumber") != receipt["blockNumber"]:
            raise LensError("Receipt log is not bound to this transaction and block.")
        if log.get("transactionIndex") != receipt.get("transactionIndex"):
            raise LensError("Receipt log transaction index disagrees.")
    fee = used * effective
    base = quantity(block["baseFeePerGas"]) if block.get("baseFeePerGas") else None
    if base is not None and effective < base:
        raise LensError("Effective gas price is below the containing block's base fee.")
    fee_cap = quantity(transaction.get("maxFeePerGas", transaction.get("gasPrice", "0x0")))
    if fee_cap and effective > fee_cap:
        raise LensError("Effective gas price exceeds the transaction fee cap.")
    return {
        "status": "succeeded" if status == 1 else "failed",
        "status_raw": status, "gas_used": used, "gas_limit": limit,
        "effective_gas_price_native_units": str(effective), "effective_gas_price_gwei": units(effective, 9),
        "fee_native_units": str(fee), "fee_usdc": units(fee, 18),
        "base_fee_component_usdc": units(used * base, 18) if base is not None else None,
        "tip_component_usdc": units(used * (effective - base), 18) if base is not None else None,
        "native_value_usdc": units(quantity(transaction.get("value", "0x0")), 18),
        "failure_diagnosis": (
            "Receipt proves execution failed. Gas use alone cannot establish whether this was out-of-gas or a contract revert; a trace is required for the exact cause."
            if status == 0 else None
        ),
        "gas_charge_is_separate_from_transfer_logs": True,
    }


def transaction_evidence(rpc, value: str) -> dict:
    value = tx_hash(value)
    rpc.check_chain()
    transaction = rpc.call("eth_getTransactionByHash", [value])
    receipt = rpc.call("eth_getTransactionReceipt", [value])
    if transaction is not None and tx_hash(transaction.get("hash", "")) != value:
        raise LensError("RPC returned the wrong transaction.")
    if transaction is not None and transaction.get("chainId") and quantity(transaction["chainId"]) != CHAIN_ID:
        raise LensError("Transaction belongs to a different chain.")
    if receipt is None:
        payload = {"hash": value, "state": "pending_or_unavailable" if transaction is not None else "not_found",
                   "transaction": transaction,
                   "note": "No receipt is not proof of failure, zero gas cost or never submitted. This endpoint may not have the transaction; some Arc blocklist rejection paths do not leave a standard receipt."}
        return _new_evidence("transaction", payload, rpc)
    if transaction is None:
        raise LensError("A receipt exists but its transaction is unavailable; refusing an incomplete fee audit.")
    block = rpc.call("eth_getBlockByNumber", [receipt["blockNumber"], False])
    if not isinstance(block, dict):
        raise LensError("The containing block is unavailable.")
    if value not in [str(x).lower() for x in block.get("transactions", [])]:
        raise LensError("Transaction hash is absent from the containing block's transaction list.")
    metrics = receipt_math(receipt, transaction, block)
    flows = reconcile_transfers(receipt.get("logs", []))
    warnings = []
    if flows["unmatched_erc20_count"] or flows["malformed_or_removed_count"]:
        warnings.append("Some USDC logs could not be reconciled. Canonical gross amount excludes unmatched ERC-20 logs; investigate before using this evidence for accounting.")
    if metrics["status"] == "failed":
        warnings.append(metrics["failure_diagnosis"])
    payload = {"hash": value, "state": "receipt_observed", "block": _block_summary(block),
               "from": address(transaction["from"]), "to": address(transaction["to"]) if transaction.get("to") else None,
               "fee": metrics, "transfers": flows, "warnings": warnings,
               "finality_scope": "Block and receipt identities checked through RPC. Independent consensus finality has not been cryptographically verified."}
    return _new_evidence("transaction", payload, rpc)


def _trace_result(doc: dict, method: str, predicate=lambda p: True):
    items = [x["response"]["result"] for x in doc["rpc_trace"]
             if x["request"]["method"] == method and predicate(x["request"]["params"])
             and "result" in x["response"]]
    if not items:
        raise LensError(f"Evidence is missing {method} observations.")
    return items[-1]


def verify_evidence(doc: dict) -> dict:
    """Verify integrity, source bindings and arithmetic. This is not a chain/state proof."""
    try:
        if doc.get("schema") != "arc-ledger-lens/1" or doc.get("chain_id") != CHAIN_ID:
            raise LensError("Unknown schema or chain.")
        if doc.get("endpoint") != RPC_URL or doc.get("network") != "Arc mainnet" or doc.get("mode") != "live_read_only" or doc.get("trust") != TRUST or doc.get("sources") != SOURCES:
            raise LensError("Unsupported evidence provenance or trust metadata.")
        if doc.get("sha256") != digest(doc):
            raise LensError("Evidence digest does not match: file was changed.")
        for item in doc["rpc_trace"]:
            req, res = item["request"], item["response"]
            if req["method"] not in ALLOWED_METHODS or req["id"] != res["id"] or res.get("jsonrpc") != "2.0" or not isinstance(item["elapsed_ms"], int):
                raise LensError("Trace contains a non-read-only method or mismatched ID.")
        if quantity(_trace_result(doc, "eth_chainId")) != CHAIN_ID:
            raise LensError("RPC chain observation disagrees.")
        payload = doc["payload"]
        if doc["kind"] == "account":
            account = address(payload["address"])
            tag = payload["block"]["number_hex"]
            native = quantity(_trace_result(doc, "eth_getBalance", lambda p: p == [account, tag]))
            data = "0x70a08231" + account[2:].rjust(64, "0")
            erc20 = quantity(_trace_result(doc, "eth_call", lambda p: p == [{"to": USDC, "data": data}, tag]))
            dec = quantity(_trace_result(doc, "eth_call", lambda p: p == [{"to": USDC, "data": "0x313ce567"}, tag]))
            block = _trace_result(doc, "eth_getBlockByNumber", lambda p: p == [tag, False])
            initial = _trace_result(doc, "eth_getBlockByNumber", lambda p: p == ["latest", False])
            if dec != 6 or initial["hash"] != block["hash"] or _block_summary(block) != payload["block"]:
                raise LensError("Pinned block or decimal observations disagree.")
            gas_price = quantity(_trace_result(doc, "eth_gasPrice"))
            if payload["erc20_decimals_observed"] != dec or payload["suggested_gas_price_native_units"] != str(gas_price) or payload["block_identity_rechecked"] is not True:
                raise LensError("Displayed decimals, gas suggestion or block recheck disagrees.")
            if balance_math(native, erc20) != payload["balance"]:
                raise LensError("Balance arithmetic does not match source observations.")
            budget = payload["budget"]
            expected = budget_math(native, parse_usdc(budget["amount_usdc"]), budget["gas_limit"],
                                   int(budget["max_fee_per_gas_native_units"]),
                                   quantity(block["baseFeePerGas"]) if block.get("baseFeePerGas") else None)
            if budget != expected:
                raise LensError("Budget arithmetic does not match.")
            expected_warnings = [] if payload["balance"]["views_reconcile"] else ["USDC views do not reconcile at the pinned block. Do not use the balance for accounting until investigated."]
            if payload["warnings"] != expected_warnings:
                raise LensError("Account warnings disagree.")
        elif doc["kind"] == "transaction":
            value = tx_hash(payload["hash"])
            transaction = _trace_result(doc, "eth_getTransactionByHash", lambda p: p == [value])
            receipt = _trace_result(doc, "eth_getTransactionReceipt", lambda p: p == [value])
            if transaction is not None and tx_hash(transaction["hash"]) != value:
                raise LensError("Source transaction hash disagrees.")
            if transaction is not None and transaction.get("chainId") and quantity(transaction["chainId"]) != CHAIN_ID:
                raise LensError("Source transaction chain disagrees.")
            if receipt is None:
                expected_state = "pending_or_unavailable" if transaction is not None else "not_found"
                if payload["state"] != expected_state or payload["transaction"] != transaction or payload["note"] != "No receipt is not proof of failure, zero gas cost or never submitted. This endpoint may not have the transaction; some Arc blocklist rejection paths do not leave a standard receipt.":
                    raise LensError("Missing-receipt state disagrees with trace.")
            else:
                block = _trace_result(doc, "eth_getBlockByNumber", lambda p: p == [receipt["blockNumber"], False])
                if value not in [str(x).lower() for x in block.get("transactions", [])]:
                    raise LensError("Containing block does not include the transaction.")
                if receipt_math(receipt, transaction, block) != payload["fee"]:
                    raise LensError("Fee arithmetic does not match source receipt.")
                if payload["state"] != "receipt_observed" or payload["from"] != address(transaction["from"]) or payload["to"] != (address(transaction["to"]) if transaction.get("to") else None):
                    raise LensError("Displayed receipt state or parties disagree with the transaction.")
                if reconcile_transfers(receipt.get("logs", [])) != payload["transfers"] or _block_summary(block) != payload["block"]:
                    raise LensError("Transfer reconciliation or block metadata disagrees.")
                expected_warnings = []
                if payload["transfers"]["unmatched_erc20_count"] or payload["transfers"]["malformed_or_removed_count"]:
                    expected_warnings.append("Some USDC logs could not be reconciled. Canonical gross amount excludes unmatched ERC-20 logs; investigate before using this evidence for accounting.")
                if payload["fee"]["status"] == "failed":
                    expected_warnings.append(payload["fee"]["failure_diagnosis"])
                if payload["warnings"] != expected_warnings or payload["finality_scope"] != "Block and receipt identities checked through RPC. Independent consensus finality has not been cryptographically verified.":
                    raise LensError("Warnings or finality claim disagree.")
        else:
            raise LensError("Unsupported evidence kind.")
        return {"valid": True, "scope": "File integrity, RPC source bindings and integer arithmetic verified. RPC authenticity and consensus finality are not independently proven.", "sha256": doc["sha256"]}
    except (KeyError, TypeError, AttributeError, OverflowError) as exc:
        raise LensError("Malformed evidence file.") from exc


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    account = sub.add_parser("account")
    account.add_argument("address")
    account.add_argument("--amount", default="1")
    account.add_argument("--gas-limit", type=int, default=21000)
    account.add_argument("--max-fee-gwei")
    account.add_argument("--out", type=Path)
    tx = sub.add_parser("transaction")
    tx.add_argument("hash")
    tx.add_argument("--out", type=Path)
    verify = sub.add_parser("verify")
    verify.add_argument("file", type=Path)
    args = parser.parse_args()
    try:
        if args.command == "verify":
            result = verify_evidence(json.loads(args.file.read_text(encoding="utf-8")))
        elif args.command == "account":
            result = account_evidence(ReadOnlyRPC(), args.address, args.amount, args.gas_limit, args.max_fee_gwei)
        else:
            result = transaction_evidence(ReadOnlyRPC(), args.hash)
        rendered = json.dumps(result, ensure_ascii=False, indent=2)
        if getattr(args, "out", None):
            args.out.parent.mkdir(parents=True, exist_ok=True)
            args.out.write_text(rendered + "\n", encoding="utf-8")
            print(json.dumps({"file": str(args.out), "sha256": result.get("sha256"), "kind": result.get("kind")}))
        else:
            print(rendered)
    except (LensError, OSError, json.JSONDecodeError) as exc:
        parser.exit(1, f"Arc Ledger Lens: {exc}\n")


if __name__ == "__main__":
    main()
