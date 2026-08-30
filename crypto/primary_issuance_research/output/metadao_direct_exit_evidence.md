# MetaDAO direct participant-exit evidence

Generated from finalized Solana RPC data on 2026-08-28.

## Strict success: UMBRA

- Launch: `9kx7UDFzFt7e2V4pFtawnupKKvRR3EhV7P1Pxmc5XCQj`
- Token: `PRVT6TB7uss3FrUd2D9xs2zqDBsa3GbMJMwCQsgmeta`
- Funder: `FZdn8C1wwq1dn4gQjBEjGNLM7bQJUdQ8eDt5LJrBagra`
- FundingRecord: `A2nh1G64kPkTNqWEsfr9gPn7G5Pm52bQy7mmJWkJWbXn`
- Current funder account is absent/system-like, rather than a program-owned account.
- Committed: **$6,902.00**
- Actual accepted cost after pro-rata refund: **$133.635598**
- Claimed participant tokens: **445.451990 UMBRA**
- Full-exit transaction: `5uVzxc9WmGKskroCzouof8zy5iaYWZvvqVWkBMGQFR2SqXpmfXJSY9fNFnMccsjK9YaGC3B1R9LUMwLgvdN6QVjB`
- Exit time: **2025-10-10 15:51:34 UTC**, about 1h 51m after launch close.
- Token balance change: **-445.451990 UMBRA** (exactly the allocation)
- USDC balance change: **+$687.820960**
- Whole-trade average execution: **$1.54410/UMBRA = 5.14699x** the $0.30 issue price.
- Participant-paid Solana fees: two 80,000-lamport funding transactions plus the 5,000-lamport sale; claim and refund were sponsored by another payer. Total: **165,000 lamports**.
- Coinbase SOL-USD minute close at exit: **$211.33**; participant gas: **$0.03487**.
- Net exit after an extra 100 bps haircut and participant gas: **$680.90788**.
- Net multiple on accepted allocation: **5.09526x**.
- Net profit on the temporarily committed $6,902, after adding the refund: **$547.27228 = 7.9292%**.

This passes the frozen mechanical `$100 accepted allocation -> >=$500 fully exited` gate and still exceeds 5x on the accepted slice after the haircut. It does **not** turn the entire committed principal into 5x because only 1.9367% of committed dollars were accepted.

## Second full exit, but below 5x on the accepted slice

- Funder: `2WRDn5Ad1c5WBwjWdrc9bBN9u1h2etBrGUD9nR6TCGXR`
- Actual accepted cost: **$232.342389**
- Exact allocation/full sale: **774.474627 UMBRA**
- USDC received: **$1,049.427063**
- Gross multiple: **4.51673x**
- Transaction: `4Sh4RjtCgpURXEHKTf7FZy7oJf29KWXiEjihbZC3HsDeAGsUf7ZUepBw7fSJHYiEdcj1d4vaqPsrfPV4TYtEbrQm`

It passes `$100 -> $500` but not a 5x-multiple rule.

## Sampling caveat

The wallets were selected deterministically by `sha256(funder)` from records with accepted cost $100-$250 and claimed tokens: four AVICI and four UMBRA. This was not outcome-selected, but `n=8` is only an execution proof, not a success-rate estimate. One additional UMBRA wallet sold more than its original allocation after later trading and is deliberately excluded from strict initial-allocation evidence.
