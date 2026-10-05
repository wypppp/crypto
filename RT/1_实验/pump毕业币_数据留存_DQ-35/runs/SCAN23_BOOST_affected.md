# F132 受影响币的核对（10-06；总控第二十轮第二节）

- 新池：扫描段 a、b、c 里升级后建、有 InitBoost 的池 40980 个（base_mint 40980 个）。老池的 InitBoost 为 0，见 `SCAN23_BOOST_report.md`。
- 判定：币在升级后有了新池、且新池早于实验止日 → 可能受影响（待逐笔重算）；否则 → 已核，不受 F132 影响。止日按实验全局止日，偏保守。

| 实验 | 止日 | 币数 | 升级后有新池 | 新池早于止日（可能受影响） |
|---|---|---|---|---|
| DQ-1M（F55～F64） | 成交到 08-06／08-07 | 191192 | 24 | 20 |
| DQ-1F（F68～F70） | 成交到 08-07／08-14 | 29037 | 24 | 21 |
| DQ-8A（F82、F84、F87） | B 周成交止于 07-15 | 29024 | 24 | 0 |
| DQ-21 S1（F117、F120、F121） | 止于 07-15 | 10565 | 1 | 0 |
| DQ-18（F109～F111） | 估值最晚约 09-11 | 1341 | 0 | 0 |

## 可能受影响的币

| 实验 | 币 | 新池 | 新池建立（UTC） |
|---|---|---|---|
| DQ-1M | `4CUP1fa7beH36gwzMZEBK79r5FLaeXP9LQ5un3Pfpump` | `9PDERJARaBuikEGjd7aRUfySFUwY6SSFfKSLjk4ui1aJ` | 2026-07-22 17:13:18 |
| DQ-1M | `6rM9X7DYTv9o87rHeGj4CEXCD3XNCQTkXqD2Rifr3vL` | `EyPqFqBRPJjF8YvJVe1g43EvPnfZZ5ffB8n6UmGMLq2v` | 2026-07-22 17:19:40 |
| DQ-1M | `CqCGc1aYBw5Enek4e9zkAzarnzS2ZiwahiAoWrnCpump` | `EPDkRpirgz1TS8Y9SczUN5cZVCY7kBA2tTv5xCM7vDNg` | 2026-07-22 17:25:59 |
| DQ-1M | `GKKh3dy4TDHBdcHXbDHFQEHm7ojtPdqQge4qWJ75pump` | `3oBR3UQfibijk2w6c3oHgwYSeEzNDiJhE3V5fVc95Mmg` | 2026-07-22 17:27:18 |
| DQ-1M | `6Q14yCx1LPdRsAxXWhJEteQAqZRNgMTbps7UiLN9pump` | `7r7xSpFbX3CtBzmqxUVeX5LWrQyFTkYpsKDph67kVHx1` | 2026-07-22 17:30:20 |
| DQ-1M | `8XXTpaXATgtt4ewhRGYtqeJDqCp3rVvmF1TJQpdrpump` | `43jV2iRRHroCSxyKpjhE2gRNLzc2CuEyendG7A5juKYt` | 2026-07-22 17:38:55 |
| DQ-1M | `7hDdEtx8yh5vZyfRQQFFvgmxDQ8Zb2KQ3AQbr3wFpump` | `9y5LaWUfJzWJF1ZUvkSxacXyzRrT28VZozaq1Ar5j7Cm` | 2026-07-22 18:12:12 |
| DQ-1M | `BFFsYxopgNBNN4ixBHYbr39rcggTT285DBBZqvuxpump` | `4U4RMqgykzuUoy9nyMn4UfsmgrcKpjEFRntYJ67hg9Bb` | 2026-07-22 20:25:21 |
| DQ-1M | `HbZXzCNQKh8FE3C4FY1KwFtgTiDkAWAS74oyDZixpump` | `H7GFi84PTSkgcMGaYDYzDZrwPpuJZfMu7CwDLXiceRus` | 2026-07-22 21:14:43 |
| DQ-1M | `7QhyJCNbwspvPztg8aLpUTq4LEJESwGyJHZjCPdhpump` | `2AaJAeM6owNtZPXWJuXMkum6th1oUBCEvK3fBzrXwxJR` | 2026-07-23 02:20:05 |
| DQ-1M | `6pWCZe9NP5GnnZLkCNnzxaYpWycenxPmu5awgaQwpump` | `7pE2FswXxLCpokxbzh5aLS61JM1PiJFQa4Kuscc58A1g` | 2026-07-23 06:28:46 |
| DQ-1M | `5FnSKoWqgg8YK3PNbUFhz5Y6nLrkExteiBb2F7Fdpump` | `8q4rtHvwyQXuM6R4ym8tCBsNQ1dGDz4pViAt82BF7gTz` | 2026-07-23 10:25:11 |
| DQ-1M | `JGPcTzTt77UMjG4hAhvfd147z7PmmT7nGJBkKXJpump` | `Hq3eHhWkxnVovTwt72RfHTezTw9RrPjDBLF5cXnus9qD` | 2026-07-23 11:35:01 |
| DQ-1M | `BjGDvXbQbZbp4oLMLuP6pqceqr6ZbPopzMr4DW5Ypump` | `GLBBw5552f3R9rKvSe6afqxmUsF9YnTiB8daMqS5PQrA` | 2026-07-24 13:23:26 |
| DQ-1M | `5fzudcofZpT4xfnKeKB3oRBDpLdh8prpGcDAfyb3pump` | `J2DZcZomtbJHPz9RXHRR1gSynBpu1tMcSU3Lk2FZMBYA` | 2026-07-24 17:39:08 |
| DQ-1M | `5HxCPYC1nmG3UUTjfcAZd9p4bwvHXRWuKuazvdXJpump` | `ECZ4jup2Wh5unFFTT7s63WSpo9AkigrdriqBW4k7K3N9` | 2026-07-24 20:29:03 |
| DQ-1M | `BSpV71Ey1EaLBWM22FtN5LfwpgaxDn2HEvYUnaXrGXSv` | `GqrivtB28Q2EkFkYVwwTDRz8M162CZrgmmaDpKZeLxpf` | 2026-07-25 19:08:30 |
| DQ-1M | `EArV8YpjLHiEwDnP2BjeAyXpAsZ7Xa1tq388afjnpump` | `6Qa3FAaa3M4XuWWjgv3kKjkU1dWsEcUiiPceQFXw67kM` | 2026-07-25 20:57:00 |
| DQ-1M | `8RVu8CSqwdkcV2Y61H2DKo1fcskxbTwkHLjTeNngpump` | `44ZcbgTM3AXPnXnZ55k6NerVZ3pSh8prnvUnatAB9PTN` | 2026-07-25 22:51:05 |
| DQ-1M | `98VgQEKBCgJdHeC81HW9bDLSBoLbnS92fsABDp8Epump` | `9nzbeMpBWevzuz4VR1n3zhbhkNKhS8r7ttMzqxvc4vcf` | 2026-08-06 19:16:52 |
| DQ-1F | `8XXTpaXATgtt4ewhRGYtqeJDqCp3rVvmF1TJQpdrpump` | `43jV2iRRHroCSxyKpjhE2gRNLzc2CuEyendG7A5juKYt` | 2026-07-22 17:38:55 |
| DQ-1F | `8gQrtWXa3PiitU8t2uutjykQUE4VfUnGJ96kAX4Fpump` | `6bGDiTewq5vXQPGtvDbWXCUYVH7MhXNDoDxDAnfHdQDw` | 2026-07-22 18:10:12 |
| DQ-1F | `6ZwFcv37SqSesifRhsoHe1jXZvD9MyCUyBBYUhd7pump` | `27b8KzCqWteXF9SWQdFmSz5qMASULWRFUAVMrwgbHjK2` | 2026-07-22 18:55:29 |
| DQ-1F | `CTxn5vbTn5koqQd2ZF7JaTeA4V1bdcBbyVkcu4expump` | `4ZxYDhk4XXHdfR7Zs4zBQkFAyDGByaY6KGVFJKrWsUCh` | 2026-07-23 00:17:54 |
| DQ-1F | `7QhyJCNbwspvPztg8aLpUTq4LEJESwGyJHZjCPdhpump` | `2AaJAeM6owNtZPXWJuXMkum6th1oUBCEvK3fBzrXwxJR` | 2026-07-23 02:20:05 |
| DQ-1F | `BjHXqpWrSxWeidp3pRqMyYrV9WW2b2dFcVWPQpnWpump` | `VWAhhvPtDCJoKWQPpnp2wtFurxhfEgTXWtBPFjSGbbj` | 2026-07-23 05:35:40 |
| DQ-1F | `6pWCZe9NP5GnnZLkCNnzxaYpWycenxPmu5awgaQwpump` | `7pE2FswXxLCpokxbzh5aLS61JM1PiJFQa4Kuscc58A1g` | 2026-07-23 06:28:46 |
| DQ-1F | `EqJX6EMQbe1P9fDrDUGo57bAwBVGAkt6qiKCQJiapump` | `FmBHGNNxX39ypnpFb31nLTpGv1mKtHd113J4nLrjT14m` | 2026-07-23 07:25:36 |
| DQ-1F | `7fSBtstsGaHRxTLPReoB9FPBfGMTXBNDMUFXdRNDpump` | `9PSGLUwqTv6eAhPKydA36i7gRNJQK1XCP8we3wgP7ynA` | 2026-07-23 07:32:31 |
| DQ-1F | `CinUqNYvUbZ7vcejXBYPKZHed7tcx3uKqmemSP8ipump` | `EeZKAmWgFXZYKYzbPgqE8Xd4sCAkMijmc8cMKjpcGQQq` | 2026-07-24 10:06:21 |
| DQ-1F | `BjGDvXbQbZbp4oLMLuP6pqceqr6ZbPopzMr4DW5Ypump` | `GLBBw5552f3R9rKvSe6afqxmUsF9YnTiB8daMqS5PQrA` | 2026-07-24 13:23:26 |
| DQ-1F | `5fzudcofZpT4xfnKeKB3oRBDpLdh8prpGcDAfyb3pump` | `J2DZcZomtbJHPz9RXHRR1gSynBpu1tMcSU3Lk2FZMBYA` | 2026-07-24 17:39:08 |
| DQ-1F | `BSpV71Ey1EaLBWM22FtN5LfwpgaxDn2HEvYUnaXrGXSv` | `GqrivtB28Q2EkFkYVwwTDRz8M162CZrgmmaDpKZeLxpf` | 2026-07-25 19:08:30 |
| DQ-1F | `466vMA8L6PrXrYhRstEFTh4QCkqpYWwZULw7KheQpump` | `DGUStrv2YyNJojtWn9bgAJdVeGrHrWjQYfRq8Puvu9LK` | 2026-07-25 20:49:45 |
| DQ-1F | `EArV8YpjLHiEwDnP2BjeAyXpAsZ7Xa1tq388afjnpump` | `6Qa3FAaa3M4XuWWjgv3kKjkU1dWsEcUiiPceQFXw67kM` | 2026-07-25 20:57:00 |
| DQ-1F | `61EF5JtwQxenjWSxw9asiTWyjaD8cbarF1FyyC1zpump` | `3HVfoDmyScjuhwP8dYATMZTHPtqa9b98pqwBvNc6qYHc` | 2026-07-25 21:37:22 |
| DQ-1F | `8RVu8CSqwdkcV2Y61H2DKo1fcskxbTwkHLjTeNngpump` | `44ZcbgTM3AXPnXnZ55k6NerVZ3pSh8prnvUnatAB9PTN` | 2026-07-25 22:51:05 |
| DQ-1F | `3JThAEtdsjW4i1Uy3bfEga7xso8xjADuXSKvQh1rpump` | `9rJ2kjk4isCYt1BoASMhtEAfcrtvwHJWmmQQEmg89wLz` | 2026-07-25 23:27:32 |
| DQ-1F | `3HGJBX985EzVQFwnE1pAFY3Usvz2ZjjHv4eKppRCFUnY` | `Br73ohMAcPV2gha22job6KNKBr4pyQ1hWVT6ghrkZMx9` | 2026-07-30 15:35:36 |
| DQ-1F | `JDLYCKNB6tayyjXE2VJTCwugZ79YFpW49wPzQ3fipump` | `Eg9MigxHTiiJeWe23Nax3s3QC9HXDCGdrfwp8B33zXww` | 2026-08-08 09:26:12 |
| DQ-1F | `FVCmLKfNxcrKfJ4myTmTtYaWFzLTdMqXn6VBvEF7pump` | `FvwDYXcZBgHtdi7DZuPmMCkhXiG36qgXnc1vPiKbfHyy` | 2026-08-14 20:11:36 |
