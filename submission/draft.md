# Arc Ledger Lens — submission draft, not submitted

**Tagline:** One USDC balance. One canonical movement stream. Inspectable accounting evidence.

**Short description:** Arc Ledger Lens is a wallet-free accounting workbench for wallet and indexer developers using Arc mainnet. It reconciles native 18-decimal and ERC-20 6-decimal balances at one pinned block, preserves gas dust, matches mirrored native/ERC-20 transfer logs without double counting, and derives exact USDC gas charges from transaction receipts. Exportable JSON includes the raw readings and can be checked offline using separate Python and JavaScript implementations. Verification checks recorded-data consistency and arithmetic; it does not independently prove consensus.

**Why Arc:** This addresses Arc's stablecoin-native accounting behavior directly. Treating native USDC as another token doubles displayed funds. Summing the two Transfer emitters doubles ERC-20 movement volume. Gas charges are separate from both event streams. Ledger Lens shows these errors with real mainnet observations and makes integration mistakes reproducible before they reach user ledgers.

**Developer workflow:** Before integrating Arc, a developer can check a public address's two balance views at one block, audit an existing receipt for mirrored movements and gas, then export the observations for a reproducible regression fixture. The focus is Arc accounting reconciliation and portable evidence, rather than transaction browsing or asset trading.

**Working proof:** A real public sample has 2 native system movements and 2 ERC-20 mirrors. Correct gross movement is 62.241328 USDC; a naive sum is 124.482656 USDC. The exact receipt gas charge is 0.004999372 USDC. The captured account also demonstrates a native precision residual smaller than one micro-USDC. Fresh public RPC reads, recorded evidence export and offline verification are implemented. No sample transactions were created by this project.

**Future work:** Optional independent-node/certificate verification and a small reconciliation library for wallet/indexer pipelines. These are planned extensions, not current functionality.

**Required fields not filled:**

- Live public app URL: **not published yet**.
- Public repository: **not published yet**.
- Public builder profile: **owner profile required; do not invent one**.
- Mainnet deployment status: **the app reads real Arc mainnet through the official public RPC. It is currently local; after static hosting, enter the real hosted URL. No new smart contract or transaction was deployed by this project. Whether a hosted read-only app satisfies this program's deployment clause remains unconfirmed**.
- Recipient wallet and conditional payout verification: **owner-only external step**.

Before submission, replace the missing fields with the actual public app, repository and builder-profile URLs. Describe the read-only mainnet integration exactly as implemented and let the program assess that route; prior organizer confirmation has not been obtained. Do not claim a custom mainnet contract deployment, confirmed eligibility, a submitted application or an award.
