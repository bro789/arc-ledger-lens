"""Regression tests for Arc-specific accounting errors; no network or wallet calls."""
import copy
import json
import unittest
from pathlib import Path
import arc_lens as a

ROOT = Path(__file__).resolve().parent
A = "0x" + "1" * 40
B = "0x" + "2" * 40
H = "0x" + "a" * 64
BH = "0x" + "b" * 64


def log(emitter, amount, index, sender=A, recipient=B):
    return {"address": emitter, "topics": [a.TRANSFER_TOPIC, "0x" + sender[2:].rjust(64, "0"), "0x" + recipient[2:].rjust(64, "0")],
            "data": "0x" + format(amount, "064x"), "logIndex": hex(index), "transactionHash": H,
            "blockHash": BH, "blockNumber": "0x1", "transactionIndex": "0x0", "removed": False}


def receipt_fixture(logs=None, status=1):
    receipt = {"transactionHash": H, "blockHash": BH, "blockNumber": "0x1", "transactionIndex": "0x0", "status": hex(status),
               "gasUsed": hex(21000), "effectiveGasPrice": hex(20 * 10**9), "logs": logs or []}
    transaction = {"hash": H, "blockHash": BH, "blockNumber": "0x1", "transactionIndex": "0x0", "gas": hex(21000),
                   "maxFeePerGas": hex(20 * 10**9), "value": "0x0"}
    block = {"hash": BH, "number": "0x1", "baseFeePerGas": hex(20 * 10**9)}
    return receipt, transaction, block


class AccountingTests(unittest.TestCase):
    def test_uint256_units_stay_exact(self):
        n = 2**256 - 1
        displayed = a.units(n, 18)
        whole, part = displayed.split(".")
        self.assertEqual(int(whole) * 10**18 + int(part.ljust(18, "0")), n)

    def test_dust_reconciles_without_double_counting(self):
        native = 5 * 10**18 + 987654321
        result = a.balance_math(native, 5 * 10**6)
        self.assertTrue(result["views_reconcile"])
        self.assertEqual(result["display_usdc"], "5")
        self.assertEqual(result["residual_native_units"], "987654321")
        self.assertEqual(result["double_counted_display_usdc"], "10")

    def test_native_dust_can_exist_when_erc20_is_zero(self):
        result = a.balance_math(999999999999, 0)
        self.assertTrue(result["views_reconcile"])
        self.assertEqual(result["display_usdc"], "0")
        self.assertEqual(result["native_gas_precision_usdc"], "0.000000999999999999")

    def test_real_mismatch_is_detected(self):
        self.assertFalse(a.balance_math(10**18, 2 * 10**6)["views_reconcile"])

    def test_budget_includes_gas(self):
        result = a.budget_math(10**18, 10**6, 21000, 20 * 10**9, 20 * 10**9)
        self.assertFalse(result["can_cover_budget_cap"])
        self.assertEqual(result["gas_budget_cap_usdc"], "0.00042")
        self.assertEqual(result["shortfall_usdc"], "0.00042")

    def test_low_fee_cap_not_disguised_as_affordable_execution(self):
        result = a.budget_math(10**18, 0, 21000, 1, 20 * 10**9)
        self.assertTrue(result["can_cover_budget_cap"])
        self.assertTrue(result["cap_below_20_gwei_submission_floor"])
        self.assertTrue(result["cap_below_observed_block_base_fee"])

    def test_usdc_amount_rejects_rounding_signs_and_exponents(self):
        for invalid in ("-1", "1e6", "1.0000001", "+1", "01", "nan", " "):
            with self.subTest(value=invalid), self.assertRaises(a.LensError):
                a.parse_usdc(invalid)

    def test_repeated_identical_transfers_pair_as_multiset(self):
        logs = [log(a.SYSTEM, 10**18, 0), log(a.USDC, 10**6, 1), log(a.SYSTEM, 10**18, 2), log(a.USDC, 10**6, 3)]
        result = a.reconcile_transfers(logs)
        self.assertEqual(result["canonical_gross_usdc"], "2")
        self.assertEqual(result["naive_two_stream_gross_usdc"], "4")
        self.assertEqual(result["paired_count"], 2)
        self.assertEqual(result["unmatched_erc20_count"], 0)

    def test_native_fraction_never_fuzzy_matches_erc20(self):
        result = a.reconcile_transfers([log(a.SYSTEM, 10**18 + 1, 0), log(a.USDC, 10**6, 1)])
        self.assertEqual(result["paired_count"], 0)
        self.assertEqual(result["canonical_gross_usdc"], "1.000000000000000001")

    def test_erc20_zero_and_self_are_legal_no_movement(self):
        result = a.reconcile_transfers([log(a.USDC, 0, 0), log(a.USDC, 10**6, 1, A, A)])
        self.assertEqual(result["unmatched_erc20_count"], 0)
        self.assertEqual(result["erc20_no_balance_movement_count"], 2)
        self.assertEqual(result["canonical_gross_usdc"], "0")

    def test_impossible_system_noops_are_flagged(self):
        result = a.reconcile_transfers([log(a.SYSTEM, 0, 0), log(a.SYSTEM, 10**18, 1, A, A)])
        self.assertEqual(result["system_count"], 0)
        self.assertEqual(result["malformed_or_removed_count"], 2)

    def test_failure_still_has_exact_fee_without_guessing_reason(self):
        result = a.receipt_math(*receipt_fixture(status=0))
        self.assertEqual(result["status"], "failed")
        self.assertEqual(result["fee_usdc"], "0.00042")
        self.assertIn("cannot establish", result["failure_diagnosis"])

    def test_failed_receipt_cannot_publish_reverted_flows(self):
        with self.assertRaises(a.LensError):
            a.receipt_math(*receipt_fixture([log(a.SYSTEM, 10**18, 0)], status=0))

    def test_duplicate_indices_and_cross_transaction_logs_rejected(self):
        receipt, tx, block = receipt_fixture([log(a.SYSTEM, 10**18, 0), log(a.USDC, 10**6, 0)])
        with self.assertRaises(a.LensError):
            a.receipt_math(receipt, tx, block)
        receipt["logs"] = [log(a.SYSTEM, 10**18, 0)]
        receipt["logs"][0]["transactionHash"] = "0x" + "c" * 64
        with self.assertRaises(a.LensError):
            a.receipt_math(receipt, tx, block)

    def test_wrong_receipt_identity_rejected(self):
        receipt, tx, block = receipt_fixture()
        receipt["blockHash"] = "0x" + "c" * 64
        with self.assertRaises(a.LensError):
            a.receipt_math(receipt, tx, block)

    def test_rpc_cannot_broadcast_or_switch_endpoint(self):
        with self.assertRaises(a.LensError):
            a.ReadOnlyRPC().call("eth_sendRawTransaction", ["0xdead"])
        with self.assertRaises(a.LensError):
            a.ReadOnlyRPC("https://example.com")


class EvidenceRegressionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.docs = {kind: json.loads((ROOT / "evidence" / f"{kind}-mainnet.json").read_text(encoding="utf-8"))
                    for kind in ("account", "transaction")}

    def test_actual_mainnet_account_and_receipt_verify(self):
        for kind, doc in self.docs.items():
            with self.subTest(kind=kind):
                self.assertTrue(a.verify_evidence(doc)["valid"])

    def test_changed_file_digest_fails(self):
        doc = copy.deepcopy(self.docs["account"])
        doc["payload"]["balance"]["display_usdc"] = "999999"
        with self.assertRaises(a.LensError):
            a.verify_evidence(doc)

    def test_rehashed_display_tampering_still_fails_source_binding(self):
        cases = [("transaction", "from", A), ("transaction", "to", B), ("transaction", "state", "failed"),
                 ("account", "erc20_decimals_observed", 18), ("account", "suggested_gas_price_native_units", "1"),
                 ("account", "block_identity_rechecked", False)]
        for kind, key, value in cases:
            with self.subTest(kind=kind, key=key):
                doc = copy.deepcopy(self.docs[kind])
                doc["payload"][key] = value
                doc["sha256"] = a.digest(doc)
                with self.assertRaises(a.LensError):
                    a.verify_evidence(doc)

    def test_rehashed_consensus_claim_and_endpoint_change_fail(self):
        for key, value in (("trust", "Consensus cryptographically proven"), ("endpoint", "https://fake.invalid"), ("mode", "verified_consensus")):
            with self.subTest(key=key):
                doc = copy.deepcopy(self.docs["transaction"])
                doc[key] = value
                doc["sha256"] = a.digest(doc)
                with self.assertRaises(a.LensError):
                    a.verify_evidence(doc)

    def test_rehashed_fee_result_change_fails(self):
        doc = copy.deepcopy(self.docs["transaction"])
        doc["payload"]["fee"]["fee_usdc"] = "0"
        doc["sha256"] = a.digest(doc)
        with self.assertRaises(a.LensError):
            a.verify_evidence(doc)


if __name__ == "__main__":
    unittest.main(verbosity=2)
