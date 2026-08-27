# Robinhood CCA 峰值分钟：方向级卖出容量

> 这是历史成交证据，不是最终 `first_exec_5x`。0.04/0.20 ETH 仅按 ETH=$2,500 近似 $100/$500。

- 持久 5x 候选：9
- 峰值分钟存在平均成交价 >=5x 的 token→ETH 卖单：8/9
- 存在单笔同时覆盖 >=0.04 ETH 入场等价 token、并收到 >=0.20 ETH：2/9
- 链上逐笔 native volume / Gecko 分钟 volume 的中位比：1.0000

| token | swaps | sells >=5x | max sell ETH | max issue-notional ETH | 0.04→0.20 evidence | poolId |
|---|---:|---:|---:|---:|---:|---|
| `0x4a6eec8a30b49d289b9fc865fd374b4d61eab8fb` | 56 | 28 | 2.8764 | 0.0042 | false | `0x1f00bab0dfb60102287e2508b7d41a0a97a9dec2c9317bc9c81a4fb91a731be3` |
| `0xff0a037e3ecd3560b93e6b2163fea48b81feefd1` | 43 | 16 | 1.6127 | 0.0165 | false | `0xc38ad275369425047272f9b96f87c564005f2e1935ea89dfbce361b325fda901` |
| `0xbe4f4bc2ecdca72a6e0d9c963ad71a5869a9fa65` | 694 | 378 | 1.4144 | 0.0149 | false | `0x4dfca89eb922ce39226d9f004fa737b8ce0959d68c509f7ddb711477350f53a1` |
| `0x7d7285afa84703021eb63ce75910b155b824c9c2` | 3 | 2 | 1.3398 | 0.0141 | false | `0xddcfc96c1929a96302f9a6eef7a8ff621927228b7b15def509bded85f3b4b226` |
| `0xddb55e8e4990293d59e948b0b15bb5d3b096ea79` | 414 | 236 | 1.1244 | 0.0555 | true | `0x08395d90abab0bfb8a7281e5f2f56e3efd957d96726efaabcb2cccf7cb109021` |
| `0x38673a2ea3a527214422c9dc0c83ac3bbd83bc72` | 54 | 35 | 0.9149 | 0.0365 | false | `0xb9c092777fe7fe978ab4dc7bac7b4f637c487a7aee97a51d2e36069099f53aec` |
| `0x688db8ab311e39a9e3343e861ff5420b1b7bdde8` | 418 | 166 | 0.7191 | 0.1153 | true | `0x529d1c9db233b932c9e06328dc579bfd51671e19b7dda6a811cc7a78d9e4f171` |
| `0x8ad265268d66a551cf282cc1fdd0af2231accb0c` | 277 | 154 | 0.5314 | 0.0053 | false | `0xcf58708b8003d0ed4d493b02b3607d7a5facb854244808b2e080fd9201a004e2` |
| `0x85be654b61303dd91897a754972e5f8600ac0416` | 1 | 0 | 0.0000 | 0.0000 | false | `0x17677bb6507416bc4741135d8220d252c2515ba957e17a942ee76173de5a925a` |

仍需重建普通公开投标者的真实分配/成本，并加入历史 ETH/USD、费用与 100 bps 执行折损。
