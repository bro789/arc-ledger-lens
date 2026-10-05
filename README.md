# Arc Ledger Lens

Arc-native USDC accounting evidence for developers, wallet teams and indexer builders.

[Open the live application](https://bro789.github.io/arc-ledger-lens/) · [Public source repository](https://github.com/bro789/arc-ledger-lens) · [Builder profile](https://github.com/bro789)

Arc exposes one USDC balance through native 18-decimal and ERC-20 6-decimal interfaces. It also emits two transfer streams for ERC-20 interface calls. Conventional EVM integration code can double a balance or count a transfer twice. Ledger Lens makes those errors visible against actual mainnet data, preserves gas precision, and exports source observations with independently checkable arithmetic.

## Run locally

No package installation, wallet, private key, AI API, RPC key or paid service is needed.

```powershell
cd dorahacks/arc
python server.py --port 8787
```

Open `http://127.0.0.1:8787`. Alternatively, use a static-only server:

```powershell
python -m http.server 8786 --bind 127.0.0.1 --directory web
```

The browser reads Circle's public Arc mainnet RPC directly. The complete `web/` directory can be hosted on a free static host; its relative asset paths also work below a project subdirectory, such as GitHub Pages. Python is a separate CLI verifier and optional local API server, not a requirement for the hosted app.

## What works

- Read a public address without connecting a wallet. Both balance calls are pinned to one block, with a subsequent block-hash identity recheck. `decimals()` must report 6 before any reconciliation is shown.
- Display a single ERC-20 USDC balance. Check `native18 // 10^12 == token6`, preserving the sub-micro-USDC residual for exact gas math. A zero ERC-20 balance can coexist with native gas dust.
- Compute a hypothetical transfer plus gas-reserve ceiling. The tool checks coverage and warns about a fee cap below the observed base fee or the documented 20 Gwei submission floor. It does not estimate contract execution or approve a transfer.
- Audit an existing transaction: cross-check transaction, receipt and containing-block identity, calculate `gasUsed × effectiveGasPrice`, and show the exact USDC fee with base/tip components.
- Reconcile system-emitter and ERC-20 Transfer logs as a multiset. Two identical movements stay two movements; a mirrored ERC-20 log does not increase canonical system-stream volume. ERC-20 zero/self transfers are classified as no balance movement. Impossible system noops, duplicate log indices, cross-transaction logs and failed receipts containing apparent transfers are flagged or rejected.
- Export a JSON evidence bundle with all RPC requests/responses, raw integer amounts, block identity, source references, calculations and a SHA-256 digest. Verify it offline in either Python or browser JavaScript.

All amounts use Python integers or JavaScript BigInt. There is no floating-point currency arithmetic, token routing, signing, key storage, trading or transaction-broadcast code.

## Real mainnet demonstration

`evidence/account-mainnet.json` and `evidence/transaction-mainnet.json` are actual public RPC observations collected on October 5, 2026 in China (UTC time is stored in the files). `web/evidence/demo-bundle.json` is their recorded browser demo, explicitly labelled **recorded mainnet, not live**. It never fabricates activity.

Observed transaction:

`0x8a71064735a0e234f2bef95dd102f76d5e700a36ebb2e9554ff4cfd7db9ecc27`

| Observation | Actual result |
|---|---|
| Canonical system gross movement | 62.241328 USDC |
| Naive sum of both event streams | 124.482656 USDC |
| Reconciled mirror pairs | 2 |
| Receipt gas used | 217,364 |
| Effective gas price | 23 Gwei in native USDC units |
| Exact gas charge | 0.004999372 USDC |

Observed account:

`0x796c8de657bf0a6624a6dcdc041c1131129e6869`

ERC-20 display was `67.985508 USDC`; the native view retained `0.000000165763383109 USDC` of smaller precision. These are historical public-chain observations, not a statement of current balances or ownership. This project did not execute the sample transaction.

Refresh the recorded demonstration using public reads only:

```powershell
python capture_demo.py
```

The capture searches a bounded recent block range and requires a genuine transaction with matched dual-emitter logs. If none is found, it exits without creating synthetic proof. The recorded sample values above would need updating after a refresh.

## CLI and verification

```powershell
python arc_lens.py account 0x796c8de657bf0a6624a6dcdc041c1131129e6869 --out evidence/fresh-account.json
python arc_lens.py transaction 0x8a71064735a0e234f2bef95dd102f76d5e700a36ebb2e9554ff4cfd7db9ecc27 --out evidence/fresh-transaction.json
python arc_lens.py verify evidence/transaction-mainnet.json
python -m unittest test_arc_lens -v
node --test test_browser_core.js
python arc_lens.py verify evidence/js-roundtrip.json
```

The offline suite contains 21 Python tests and 13 Node tests. It covers large uint256 precision, dust, double counting, gas budgeting, repeated transfer matching, legal ERC-20 noops, impossible system events, receipt identity, rehashed display tampering, unsupported proof claims and read-only method enforcement. Python-generated observations are verified by JavaScript, and JavaScript-generated observations are verified by Python. Node is used only for development tests.

## Trust boundary

Evidence verifies file integrity, bindings between displayed values and recorded RPC responses, and deterministic arithmetic. It is **not** a validator-signature verifier, Merkle/state proof, transaction-signature verifier, independent full node or consensus certificate. A malicious party could fabricate an entire RPC trace and recompute the digest. Re-query a trusted RPC or use an independent node for stronger assurance.

Receipt status 0 proves failed execution but does not identify its exact cause. Missing receipts remain unavailable/pending/not found; the tool never infers zero cost or a blocklist rejection from absence alone. Gross movement volume is not a wallet balance delta; gas and block rewards are outside the Transfer stream.

Circle's public RPC may observe queried public identifiers, rate limit or be unavailable. No analytics or third-party script is loaded. Imported evidence stays in the browser for verification. The optional local server binds to loopback, validates the Host/Origin and serves an explicit file allowlist.

## Arc Microgrants readiness

This is a working **publicly hosted, mainnet-connected read-only application** at [bro789.github.io/arc-ledger-lens](https://bro789.github.io/arc-ledger-lens/), with its [source repository](https://github.com/bro789/arc-ledger-lens) published. Anonymous mainnet account and transaction reads were checked through the public site. No wallet has been created and no contract has been deployed by this project. The owner has separately registered for the Arc program; a grant Build has not been submitted by this project task.

The official program requires a working Arc mainnet deployment, a public app URL, public repository, builder profile and (after selection) private payout verification. Whether a hosted read-only mainnet tool satisfies its deployment wording remains unknown. Once the real public URLs and genuine builder profile are ready, the project can be submitted with an accurate description of its read-only integration for the program to judge. It must not claim a deployed contract or confirmed eligibility. A contract deployment would require mainnet USDC gas, for which no approved zero-budget route is established; this project does not spend funds to manufacture deployment evidence.

The app URL, source repository and genuine [builder profile](https://github.com/bro789) are ready. Remaining external steps are to submit the Build once through an authorized account with honest deployment status, and complete recipient/wallet verification only if conditionally selected. Any terms required at submission still need the owner's appropriate confirmation. The submission copy and short demo script are in `submission/`. Organizer clearance has not been requested and is not treated as a prerequisite for submitting an honestly described read-only candidate.

## Sources and licenses

Network configuration and behavior were checked against primary sources on October 5, 2026:

- [Arc RPC endpoints](https://docs.arc.io/arc/references/rpc-endpoints): mainnet chain ID 5042, anonymous Circle endpoint and head-skew retry behavior.
- [Arc USDC system events](https://docs.arc.io/arc/references/usdc-system-events): emitter identities, Transfer topic/precision, mirror events, zero/self system suppression and gas outside logs.
- [Circle Arc reference](https://github.com/circlefin/skills/blob/master/plugins/circle/skills/use-arc/SKILL.md): one-balance/two-interface model and native18/ERC20-6 conventions.
- [Arc gas and fees](https://docs.arc.io/arc/references/gas-and-fees): USDC fee display and fee math. Its parameter table still contains a testnet caveat; the tool reads the actual mainnet block base fee rather than assuming a hard-coded current mainnet fee.
- [Arc Microgrants program](https://community.arc.io/public/events/arc-microgrants-f8tijfjhyq): entry requirements; no eligibility or award claim is implied by this prototype.

Original project code and geometric project logo are MIT-licensed. The full notice is included in both source and hosted static distributions (`LICENSE` and `web/LICENSE`). There are no runtime package dependencies and no copied SDK/contracts/templates. Python's standard library and browser runtime are used under their respective upstream licenses; links to third-party documentation remain those owners' materials. Public transaction data is preserved as observational evidence with source provenance.

The original ledger/inspection/check artwork is at `assets/logo.svg` (editable) and `assets/logo.png` (480×480 RGB, suitable for the Build profile). Both are also included in the hosted `web/` bundle. It is project artwork, not a Circle or Arc trademark. Regenerate with `python build_logo.py`; this optional development-only script uses Pillow primitives and has no effect on runtime dependencies or accounting. No third-party image assets or fonts are used.
