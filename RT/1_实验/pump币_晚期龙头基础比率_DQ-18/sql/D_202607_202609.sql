-- DQ-18 D 段路径块：2026-07～2026-09（生成器 make_d_block.py；口径见文件头）
-- 活跃样本信号 255 个（样本 raw/census/sample_D.csv，sha256 1ec965c0…）。不计算收益。
-- 运行时单条费用上限 100 credits。
WITH sig AS (
    SELECT mint, tier * 1000000 AS tier, from_unixtime(eh * 3600) AS signal_time
    FROM (VALUES
('AGdGTQa8iRnSx4fQJehWo4Xwbh1bzTazs55R6Jwupump',1,490984),
('2eCJENZedjLxRcCNuUnKEuKaiPWnQriCvuwC8aGQpump',1,490995),
('jk1T35eWK41MBMM8AWoYVaNbjHEEQzMDetTsfnqpump',1,490998),
('FquUHKWfMUdSMxxSU9ZWrSc98hvTXeMnQn9nksSKpump',1,491016),
('CzNMjTW6kQQNMSYksrc1reqEseey3ReQm8yro6jCpump',1,491032),
('2ho2rMakwEpFf8FsCfw9cMVUzSSjCoZ7RcctmqYFpump',1,491091),
('Cm6fNnMk7NfzStP9CZpsQA2v3jjzbcYGAxdJySmHpump',1,491109),
('8SePknMizxUWZFnyHcNLXy6wiqEWUKG1kgV9Z6N7BS6a',1,491111),
('AhmtLxRX4qr4cDCzHEHeWKK4bfwzaBs8AQiW5a9Npump',1,491117),
('FnsJqDbt4a2kiNbPxm4Pvm9ymThgoKTkokCVh3ZNpump',1,491139),
('2nP9yKQNSGQy851iyawDvBkzkK2R2aqKArQCKc2gpump',1,491177),
('59nzDoRyJ1QcLcFYFs4GVdeZ4qUEb16T2KNuHPWMpump',1,491209),
('8ojr8Pzs32b6Tpc2G5JToM2EmzkupD7ckoXe1jnNpump',1,491247),
('B8wEzfFu4DsU5cQAe7FqpPMhafULFtFAgWyVpSN9pump',1,491284),
('AGBegePeNtnBy1xLGBDcBDjxaVHaDhvebSNMduLapump',1,491334),
('8Jx8AAHj86wbQgUTjGuj6GTTL5Ps3cqxKRTvpaJApump',1,491378),
('EBsEkH2dfZ5jnzGPsLBVyBc3PU4PJVCTExQvpyrtpump',1,491379),
('YbN56nsSLsdsiB58nA5tzrg2n8vZajtcf5QmFVYpump',1,491394),
('8PC9MQMXYdLX34N16ZBZgZjpDe8iGkpNFSF6YFcPpump',1,491403),
('CzDeztwYX94UZh5mA2vAkn6vwJ1gxD1wd8m2ocswpump',1,491418),
('2LzLh5pHg3nDQz6goTLAvDXfDbSBgAR8qem3bdXdpump',1,491427),
('6eut3Ucs9JfdX9bHcF2njuHXQoDjuSB1UpVKyvgrpump',1,491454),
('7L9ScXRGyHrW8fyHaTBz51W6236pq879dgoxYE2hpump',1,491498),
('R2STA2czVfskdNjeaJ5aGaunbS9MZoXyvN4JYxKpump',1,491515),
('3B1ijcocM5EDga6XxQ7JLW7weocQPWWjuhBYG8Vepump',1,491545),
('FsXJHch6cj9TyZGm1kfMwt8S8oATCEr6ccqWFp3Xpump',1,491561),
('FVbMi3DznQjAGUUUsg3pkKmDcVT6rvq7UwbajKnWpump',1,491568),
('FadYMEEAarwkMHSjavdKDJt7uXqsnePTpn5cDWyGpump',1,491570),
('2akXpuyFXAVN5YofZpZMfBp2Vxognpmv9NooBMuHpump',1,491592),
('6cQzq7aaar3fEhXFuAHjT1kca94AitdNp7BwEnxypump',1,491596),
('CxoaKHTGYAUkHwzK5dazVYuG3vvEXExrGznMwX1ipump',1,491601),
('3Vf7nAjVUboUMAMY4Qw5iPmcxUzCuBRWSRZBQ8Lopump',1,491602),
('3AJoy35xaEVzdHCrE7GDgti1yikUaSyvZ2a1JvHBpump',1,491618),
('7EW5dDD6MYJK4PcZ89MGApJQwWeDEeNgH4NCVU4qpump',1,491620),
('5LswPW5k4vZRoK2a1qgJa3huGwpAXT6BaZ3bM4L6pump',1,491630),
('92tbcNAx7MhZbme3EP6BisYgD9SweTPsGvC7GbTdpump',1,491641),
('8nuBeqkiHwv4HFfFM6iFdH6bdjtKF1XcZXkEr9nCpump',1,491643),
('5swNWUaS57Sa8jvc5NLrt5ersrg7CYSbDPqy8Wkrpump',1,491665),
('9S8edqWxoWz5LYLnxWUmWBJnePg35WfdYQp7HQkUpump',1,491666),
('CWoQEk7PtczueUu5C2P1mvb3AhBKC1QiuzzfiUfVpump',1,491691),
('GDmSzyg3F3CqgusT4CcxhjaKKfaucN98L4EUePeqpump',1,491757),
('BcypSiV7KihjQaxTdmGpGPVUeWSEYNhA9UKPFYHtpump',1,491759),
('9jFP3WdkXMsfjQZx5af94Y5scQVVqKbsNNHmGisxpump',1,491764),
('3N9GyaUrt4UUdivvKfkSUiFX2qggzFFM31QQfPrApump',1,491786),
('AkZfKts6aUBw4cAKCmsDQWp8njyQ86134GF41MJYpump',1,491787),
('5Jr9hGmJgxBRjjF8XGcGgQzXUdsbpZNNMpigEv8Wpump',1,491791),
('54n4J8NLMCtNhcbUbTsoskQqkYfw8Vr5vefKHeqNpump',1,491808),
('1JdAaguQxPrepoTm6k5T5jWViZBAqpUajzFtgzEpump',1,491836),
('5Z9uaT6cxa22RgJ3An6iBCcJccEK5xovoY5z1VLepump',1,491858),
('5XUmwpwHscJsUfTRA7somtUCtfmUVi1Hz7YGH3H8pump',1,491891),
('BX42TCmtMyocJkShYg3CBgdZwvzD1oxA5rYxFGPwpump',1,491901),
('3LYm92Zt2yYQMe82QzwBw3rmBBVsGxyS4B8DXJ5Qpump',1,491904),
('HSx8Bd9WgcD7xozkocf3CzGuH52uHwmvKRdP56Cbpump',1,491930),
('FDJt4qTbBthNjqV8PLcC52QhMwYkm8gdveZYVrGbpump',1,491948),
('NV2RYH954cTJ3ckFUpvfqaQXU4ARqqDH3562nFSpump',1,491957),
('5fFzyj6Mc7A2ECT7ae18YvTT7d6JoPiY8KWoqXzXpump',1,491976),
('EMMiGudXs9cHBixn6PDohLo4vNvVhXwTfoBnApanpump',1,491981),
('9k6TEf1peTPkDbE8XfGaLZDNdTXAzMCBwmuUQzdtpump',1,491994),
('Exxd8raXFFRY3CUjyAnu8UiejuT1fQszTqmnvVUVpump',1,492002),
('BySPuRz3gNh4WYWWH8KxFzKcEc73YuubHKMPzHrppump',1,492004),
('Apuszvz62jtxXL7MHpmSCy9WQatacBdXo1ybTpohpump',1,492019),
('7sShzRXuv4Z19QdmJffJTnL6r2PC8EPTQ8aUndQipump',1,492025),
('9ZQC4Keh9G5e62ZnLcwW9MaDgPdBQQqcXmqgrLezpump',1,492026),
('HyPDU4sFeoJPntywVJXNtq5LBTZu2Y2aCpJuoranpump',1,492041),
('8TnbbiNsrpbF63jt56RyRj7EQfrZd45dpa2U92Wkpump',1,492051),
('G44FmBFYuEbNZSGRFx2Sjv5dcoLaYvaNaA3RMUsYpump',1,492052),
('DmxDBXTxEnNXVNNVVZe9QhgoKnr8anjE1b49dpZapump',1,492090),
('6kPvsfp31jE2VAg34d43YReY6g8oT5X7VqqaEKJPpump',1,492119),
('EsB5fiwoYB4AkxoDCHkKkNV6jVc8f15vKqnJZ3UMpump',1,492121),
('2QKrBtNECja4cJygxA7igwqxahs93GNmuQ2We2stpump',1,492127),
('HYhnRdn7nridbDUUcRsd3JtmvMCyKrVDew52CWGtpump',1,492142),
('Jjsx8XygF1WMQeTiQJajpFyj3kBreTnPBVzb2q8pump',1,492144),
('Ea27vRqcEyveBzxVqwx1xjV3US6RhCF5HdkufuRVpump',1,492148),
('8B44ouU62FXkjdChWZWLbuH4g57KSavgYMq9Vpd5pump',1,492150),
('CqEQBrm77irTktBqr8uB2k3DM72YwtX2jix7C4SLpump',1,492198),
('8eCAvyfT8mdXR2adGtnr4gnu88vu1c6nu7rPY8Bwpump',1,492202),
('G4Mx1ve3uvSt7dCyHAFhxg1j1SikUg7WM4FzMnmmpump',1,492221),
('BhFhSiozXfoRCxq2DsCH55QaJ4kyY4ia3epfSPFEpump',1,492247),
('GGgeTvk7i7yTv42qFYc7ZABP5xzffkNQ8Mu2tPckpump',1,492252),
('GWEdGq4X511cEUsGvkhn3UDDT2D6xJskNXjCwtVapump',1,492303),
('znKfSN92PgeKN2sPqM3tyCLWJtvSPZqn5KbRHQ5pump',1,492342),
('7vEFmuM4HvpMfFUwnt2sKpHyx9HtbzKYG4o4qzdrpump',1,492353),
('3reBmVkfEu6NLCjs4mYS8rcjiPZYTeGYPL82euHBpump',1,492399),
('G4Jy6beoBD2atotuaF7wWa2X5FMeSEGFoAtovuXipump',1,492409),
('9HkvDxrZ9zXhecCJMLMeW4J43feUQZ96f7QEj6uUpump',1,492419),
('EPuZ1X6pPzac3ELPsT59LStmgaSr4kBJvaAbL15Fpump',1,492547),
('C9dJfTGUzhuqPWxh9mcDr66JZN4uzXh2gh9EWnEdpump',1,492549),
('2RD1VgxCsRumXPZT4xeTPm3FdN9mG6414RLkDRHKpump',1,492560),
('HKbqQgxxetq95HuLksVBYDU6FSiguQLKGTVhUN9ppump',1,492578),
('A6z3ZZmHUa1bURTVt13YRWYV7zo1PUtv4D1cDpRBpump',1,492580),
('CXQFoXzx3DN74ShwesqunBXuoJEBaZn3ewTUyCUHpump',1,492580),
('CixGc8St4fdtRJPLirH5dnwAnjY8SxxfmPPQdjuUpump',1,492581),
('WVRfPU3aTzzX7dGbxFDqHPxuQGj47XEUAn5zGuzpump',1,492605),
('2N4Fp8SX7hkt6L7TyBUPymL1k7R9kZr6TjBqkFGjpump',1,492606),
('HVjK8sAKfbWLy3AQs19WNbig1vBwMmKBVDSS6528pump',1,492609),
('DAYSMAwjbjYvu2kyM49e9SE141eyGU9xYGLf7Pm7pump',1,492634),
('G9K6xToJafgVhWKZ8LVkyDfEn9q2t7Nh1RE9QD8Wpump',1,492638),
('iNKezFtQnxqjX8JMrez3pT6VaV8VwhA1SZXTbbzpump',1,492645),
('9EeNybtBTj1pRgksQEC4JnxhTXGKygubudYrrPWSpump',1,492649),
('4jydpWWkWiAp4Tiaxh2Rc9M7GJ91edBrC18YRHoUpump',1,492657),
('5jcVVTxLVvHoemZXundd2tA7bUmQjFNR6na5p7xCpump',1,492669),
('5tMkfHAXj5KxcVMqZUaomthTrqvjwNxWs3WwNg41pump',1,492670),
('2eCJENZedjLxRcCNuUnKEuKaiPWnQriCvuwC8aGQpump',5,490995),
('AGdGTQa8iRnSx4fQJehWo4Xwbh1bzTazs55R6Jwupump',5,490998),
('jk1T35eWK41MBMM8AWoYVaNbjHEEQzMDetTsfnqpump',5,491013),
('4TyZGqRLG3VcHTGMcLBoPUmqYitMVojXinAmkL8xpump',5,491090),
('2ho2rMakwEpFf8FsCfw9cMVUzSSjCoZ7RcctmqYFpump',5,491095),
('AhmtLxRX4qr4cDCzHEHeWKK4bfwzaBs8AQiW5a9Npump',5,491118),
('FnsJqDbt4a2kiNbPxm4Pvm9ymThgoKTkokCVh3ZNpump',5,491140),
('Cm6fNnMk7NfzStP9CZpsQA2v3jjzbcYGAxdJySmHpump',5,491160),
('2nP9yKQNSGQy851iyawDvBkzkK2R2aqKArQCKc2gpump',5,491181),
('8ojr8Pzs32b6Tpc2G5JToM2EmzkupD7ckoXe1jnNpump',5,491248),
('B8wEzfFu4DsU5cQAe7FqpPMhafULFtFAgWyVpSN9pump',5,491285),
('EBsEkH2dfZ5jnzGPsLBVyBc3PU4PJVCTExQvpyrtpump',5,491383),
('8PC9MQMXYdLX34N16ZBZgZjpDe8iGkpNFSF6YFcPpump',5,491406),
('CzDeztwYX94UZh5mA2vAkn6vwJ1gxD1wd8m2ocswpump',5,491419),
('8Jx8AAHj86wbQgUTjGuj6GTTL5Ps3cqxKRTvpaJApump',5,491421),
('6eut3Ucs9JfdX9bHcF2njuHXQoDjuSB1UpVKyvgrpump',5,491456),
('FVbMi3DznQjAGUUUsg3pkKmDcVT6rvq7UwbajKnWpump',5,491572),
('FadYMEEAarwkMHSjavdKDJt7uXqsnePTpn5cDWyGpump',5,491572),
('3B1ijcocM5EDga6XxQ7JLW7weocQPWWjuhBYG8Vepump',5,491574),
('FsXJHch6cj9TyZGm1kfMwt8S8oATCEr6ccqWFp3Xpump',5,491580),
('2akXpuyFXAVN5YofZpZMfBp2Vxognpmv9NooBMuHpump',5,491593),
('6cQzq7aaar3fEhXFuAHjT1kca94AitdNp7BwEnxypump',5,491597),
('3AJoy35xaEVzdHCrE7GDgti1yikUaSyvZ2a1JvHBpump',5,491618),
('CxoaKHTGYAUkHwzK5dazVYuG3vvEXExrGznMwX1ipump',5,491618),
('5LswPW5k4vZRoK2a1qgJa3huGwpAXT6BaZ3bM4L6pump',5,491631),
('92tbcNAx7MhZbme3EP6BisYgD9SweTPsGvC7GbTdpump',5,491642),
('8nuBeqkiHwv4HFfFM6iFdH6bdjtKF1XcZXkEr9nCpump',5,491643),
('7EW5dDD6MYJK4PcZ89MGApJQwWeDEeNgH4NCVU4qpump',5,491657),
('5swNWUaS57Sa8jvc5NLrt5ersrg7CYSbDPqy8Wkrpump',5,491666),
('CWoQEk7PtczueUu5C2P1mvb3AhBKC1QiuzzfiUfVpump',5,491692),
('9S8edqWxoWz5LYLnxWUmWBJnePg35WfdYQp7HQkUpump',5,491697),
('9jFP3WdkXMsfjQZx5af94Y5scQVVqKbsNNHmGisxpump',5,491764),
('3N9GyaUrt4UUdivvKfkSUiFX2qggzFFM31QQfPrApump',5,491786),
('AkZfKts6aUBw4cAKCmsDQWp8njyQ86134GF41MJYpump',5,491788),
('5Jr9hGmJgxBRjjF8XGcGgQzXUdsbpZNNMpigEv8Wpump',5,491793),
('54n4J8NLMCtNhcbUbTsoskQqkYfw8Vr5vefKHeqNpump',5,491809),
('5Z9uaT6cxa22RgJ3An6iBCcJccEK5xovoY5z1VLepump',5,491861),
('2LzLh5pHg3nDQz6goTLAvDXfDbSBgAR8qem3bdXdpump',5,491876),
('BX42TCmtMyocJkShYg3CBgdZwvzD1oxA5rYxFGPwpump',5,491904),
('3LYm92Zt2yYQMe82QzwBw3rmBBVsGxyS4B8DXJ5Qpump',5,491909),
('59nzDoRyJ1QcLcFYFs4GVdeZ4qUEb16T2KNuHPWMpump',5,491919),
('HSx8Bd9WgcD7xozkocf3CzGuH52uHwmvKRdP56Cbpump',5,491931),
('FDJt4qTbBthNjqV8PLcC52QhMwYkm8gdveZYVrGbpump',5,491949),
('NV2RYH954cTJ3ckFUpvfqaQXU4ARqqDH3562nFSpump',5,491971),
('5fFzyj6Mc7A2ECT7ae18YvTT7d6JoPiY8KWoqXzXpump',5,491976),
('EMMiGudXs9cHBixn6PDohLo4vNvVhXwTfoBnApanpump',5,491982),
('9k6TEf1peTPkDbE8XfGaLZDNdTXAzMCBwmuUQzdtpump',5,491995),
('Exxd8raXFFRY3CUjyAnu8UiejuT1fQszTqmnvVUVpump',5,492003),
('BySPuRz3gNh4WYWWH8KxFzKcEc73YuubHKMPzHrppump',5,492005),
('9ZQC4Keh9G5e62ZnLcwW9MaDgPdBQQqcXmqgrLezpump',5,492027),
('7sShzRXuv4Z19QdmJffJTnL6r2PC8EPTQ8aUndQipump',5,492029),
('HyPDU4sFeoJPntywVJXNtq5LBTZu2Y2aCpJuoranpump',5,492041),
('8TnbbiNsrpbF63jt56RyRj7EQfrZd45dpa2U92Wkpump',5,492052),
('G44FmBFYuEbNZSGRFx2Sjv5dcoLaYvaNaA3RMUsYpump',5,492052),
('6kPvsfp31jE2VAg34d43YReY6g8oT5X7VqqaEKJPpump',5,492120),
('Jjsx8XygF1WMQeTiQJajpFyj3kBreTnPBVzb2q8pump',5,492144),
('Ea27vRqcEyveBzxVqwx1xjV3US6RhCF5HdkufuRVpump',5,492149),
('8B44ouU62FXkjdChWZWLbuH4g57KSavgYMq9Vpd5pump',5,492152),
('8eCAvyfT8mdXR2adGtnr4gnu88vu1c6nu7rPY8Bwpump',5,492203),
('G4Mx1ve3uvSt7dCyHAFhxg1j1SikUg7WM4FzMnmmpump',5,492231),
('BhFhSiozXfoRCxq2DsCH55QaJ4kyY4ia3epfSPFEpump',5,492247),
('GGgeTvk7i7yTv42qFYc7ZABP5xzffkNQ8Mu2tPckpump',5,492253),
('2QKrBtNECja4cJygxA7igwqxahs93GNmuQ2We2stpump',5,492293),
('DmxDBXTxEnNXVNNVVZe9QhgoKnr8anjE1b49dpZapump',5,492313),
('G4Jy6beoBD2atotuaF7wWa2X5FMeSEGFoAtovuXipump',5,492411),
('9HkvDxrZ9zXhecCJMLMeW4J43feUQZ96f7QEj6uUpump',5,492420),
('C9dJfTGUzhuqPWxh9mcDr66JZN4uzXh2gh9EWnEdpump',5,492550),
('2RD1VgxCsRumXPZT4xeTPm3FdN9mG6414RLkDRHKpump',5,492561),
('EPuZ1X6pPzac3ELPsT59LStmgaSr4kBJvaAbL15Fpump',5,492572),
('A6z3ZZmHUa1bURTVt13YRWYV7zo1PUtv4D1cDpRBpump',5,492580),
('CXQFoXzx3DN74ShwesqunBXuoJEBaZn3ewTUyCUHpump',5,492580),
('CixGc8St4fdtRJPLirH5dnwAnjY8SxxfmPPQdjuUpump',5,492581),
('WVRfPU3aTzzX7dGbxFDqHPxuQGj47XEUAn5zGuzpump',5,492606),
('2N4Fp8SX7hkt6L7TyBUPymL1k7R9kZr6TjBqkFGjpump',5,492607),
('HVjK8sAKfbWLy3AQs19WNbig1vBwMmKBVDSS6528pump',5,492610),
('DAYSMAwjbjYvu2kyM49e9SE141eyGU9xYGLf7Pm7pump',5,492635),
('G9K6xToJafgVhWKZ8LVkyDfEn9q2t7Nh1RE9QD8Wpump',5,492639),
('9EeNybtBTj1pRgksQEC4JnxhTXGKygubudYrrPWSpump',5,492650),
('4jydpWWkWiAp4Tiaxh2Rc9M7GJ91edBrC18YRHoUpump',5,492658),
('iNKezFtQnxqjX8JMrez3pT6VaV8VwhA1SZXTbbzpump',5,492664),
('5jcVVTxLVvHoemZXundd2tA7bUmQjFNR6na5p7xCpump',5,492670),
('5tMkfHAXj5KxcVMqZUaomthTrqvjwNxWs3WwNg41pump',5,492671),
('2eCJENZedjLxRcCNuUnKEuKaiPWnQriCvuwC8aGQpump',20,491002),
('AGdGTQa8iRnSx4fQJehWo4Xwbh1bzTazs55R6Jwupump',20,491021),
('AhmtLxRX4qr4cDCzHEHeWKK4bfwzaBs8AQiW5a9Npump',20,491122),
('4TyZGqRLG3VcHTGMcLBoPUmqYitMVojXinAmkL8xpump',20,491140),
('FnsJqDbt4a2kiNbPxm4Pvm9ymThgoKTkokCVh3ZNpump',20,491140),
('2nP9yKQNSGQy851iyawDvBkzkK2R2aqKArQCKc2gpump',20,491186),
('jk1T35eWK41MBMM8AWoYVaNbjHEEQzMDetTsfnqpump',20,491262),
('B8wEzfFu4DsU5cQAe7FqpPMhafULFtFAgWyVpSN9pump',20,491288),
('3iC63FgnB7EhcPaiSaC51UkVweeBDkqu17SaRyy2pump',20,491346),
('CzDeztwYX94UZh5mA2vAkn6vwJ1gxD1wd8m2ocswpump',20,491420),
('8Jx8AAHj86wbQgUTjGuj6GTTL5Ps3cqxKRTvpaJApump',20,491447),
('FadYMEEAarwkMHSjavdKDJt7uXqsnePTpn5cDWyGpump',20,491578),
('FsXJHch6cj9TyZGm1kfMwt8S8oATCEr6ccqWFp3Xpump',20,491591),
('FVbMi3DznQjAGUUUsg3pkKmDcVT6rvq7UwbajKnWpump',20,491592),
('6cQzq7aaar3fEhXFuAHjT1kca94AitdNp7BwEnxypump',20,491597),
('3AJoy35xaEVzdHCrE7GDgti1yikUaSyvZ2a1JvHBpump',20,491619),
('5LswPW5k4vZRoK2a1qgJa3huGwpAXT6BaZ3bM4L6pump',20,491631),
('92tbcNAx7MhZbme3EP6BisYgD9SweTPsGvC7GbTdpump',20,491642),
('8nuBeqkiHwv4HFfFM6iFdH6bdjtKF1XcZXkEr9nCpump',20,491647),
('Cm6fNnMk7NfzStP9CZpsQA2v3jjzbcYGAxdJySmHpump',20,491664),
('5swNWUaS57Sa8jvc5NLrt5ersrg7CYSbDPqy8Wkrpump',20,491671),
('CWoQEk7PtczueUu5C2P1mvb3AhBKC1QiuzzfiUfVpump',20,491697),
('9jFP3WdkXMsfjQZx5af94Y5scQVVqKbsNNHmGisxpump',20,491773),
('AkZfKts6aUBw4cAKCmsDQWp8njyQ86134GF41MJYpump',20,491796),
('54n4J8NLMCtNhcbUbTsoskQqkYfw8Vr5vefKHeqNpump',20,491813),
('5Z9uaT6cxa22RgJ3An6iBCcJccEK5xovoY5z1VLepump',20,491867),
('3LYm92Zt2yYQMe82QzwBw3rmBBVsGxyS4B8DXJ5Qpump',20,491919),
('FDJt4qTbBthNjqV8PLcC52QhMwYkm8gdveZYVrGbpump',20,491964),
('EMMiGudXs9cHBixn6PDohLo4vNvVhXwTfoBnApanpump',20,491982),
('5fFzyj6Mc7A2ECT7ae18YvTT7d6JoPiY8KWoqXzXpump',20,491983),
('5Jr9hGmJgxBRjjF8XGcGgQzXUdsbpZNNMpigEv8Wpump',20,491998),
('Exxd8raXFFRY3CUjyAnu8UiejuT1fQszTqmnvVUVpump',20,492005),
('BySPuRz3gNh4WYWWH8KxFzKcEc73YuubHKMPzHrppump',20,492006),
('9ZQC4Keh9G5e62ZnLcwW9MaDgPdBQQqcXmqgrLezpump',20,492031),
('HyPDU4sFeoJPntywVJXNtq5LBTZu2Y2aCpJuoranpump',20,492049),
('8TnbbiNsrpbF63jt56RyRj7EQfrZd45dpa2U92Wkpump',20,492052),
('G44FmBFYuEbNZSGRFx2Sjv5dcoLaYvaNaA3RMUsYpump',20,492052),
('59nzDoRyJ1QcLcFYFs4GVdeZ4qUEb16T2KNuHPWMpump',20,492086),
('NV2RYH954cTJ3ckFUpvfqaQXU4ARqqDH3562nFSpump',20,492091),
('Ea27vRqcEyveBzxVqwx1xjV3US6RhCF5HdkufuRVpump',20,492149),
('8eCAvyfT8mdXR2adGtnr4gnu88vu1c6nu7rPY8Bwpump',20,492204),
('BhFhSiozXfoRCxq2DsCH55QaJ4kyY4ia3epfSPFEpump',20,492251),
('GGgeTvk7i7yTv42qFYc7ZABP5xzffkNQ8Mu2tPckpump',20,492253),
('G4Mx1ve3uvSt7dCyHAFhxg1j1SikUg7WM4FzMnmmpump',20,492317),
('9HkvDxrZ9zXhecCJMLMeW4J43feUQZ96f7QEj6uUpump',20,492424),
('DmxDBXTxEnNXVNNVVZe9QhgoKnr8anjE1b49dpZapump',20,492434),
('C9dJfTGUzhuqPWxh9mcDr66JZN4uzXh2gh9EWnEdpump',20,492550),
('2RD1VgxCsRumXPZT4xeTPm3FdN9mG6414RLkDRHKpump',20,492565),
('CXQFoXzx3DN74ShwesqunBXuoJEBaZn3ewTUyCUHpump',20,492581),
('CixGc8St4fdtRJPLirH5dnwAnjY8SxxfmPPQdjuUpump',20,492584),
('A6z3ZZmHUa1bURTVt13YRWYV7zo1PUtv4D1cDpRBpump',20,492591),
('WVRfPU3aTzzX7dGbxFDqHPxuQGj47XEUAn5zGuzpump',20,492606),
('2N4Fp8SX7hkt6L7TyBUPymL1k7R9kZr6TjBqkFGjpump',20,492607),
('HVjK8sAKfbWLy3AQs19WNbig1vBwMmKBVDSS6528pump',20,492610),
('DAYSMAwjbjYvu2kyM49e9SE141eyGU9xYGLf7Pm7pump',20,492635),
('G9K6xToJafgVhWKZ8LVkyDfEn9q2t7Nh1RE9QD8Wpump',20,492639),
('9EeNybtBTj1pRgksQEC4JnxhTXGKygubudYrrPWSpump',20,492650),
('4jydpWWkWiAp4Tiaxh2Rc9M7GJ91edBrC18YRHoUpump',20,492658),
('5jcVVTxLVvHoemZXundd2tA7bUmQjFNR6na5p7xCpump',20,492670),
('5tMkfHAXj5KxcVMqZUaomthTrqvjwNxWs3WwNg41pump',20,492672),
('a3W4qutoEJA4232T2gwZUfgYJTetr96pU4SJMwppump',100,491060),
('8Jx8AAHj86wbQgUTjGuj6GTTL5Ps3cqxKRTvpaJApump',100,491467),
('EMMiGudXs9cHBixn6PDohLo4vNvVhXwTfoBnApanpump',100,491986),
('BySPuRz3gNh4WYWWH8KxFzKcEc73YuubHKMPzHrppump',100,492011),
('GGgeTvk7i7yTv42qFYc7ZABP5xzffkNQ8Mu2tPckpump',100,492253),
('BhFhSiozXfoRCxq2DsCH55QaJ4kyY4ia3epfSPFEpump',100,492260),
('G4Mx1ve3uvSt7dCyHAFhxg1j1SikUg7WM4FzMnmmpump',100,492500),
('CXQFoXzx3DN74ShwesqunBXuoJEBaZn3ewTUyCUHpump',100,492602),
('CixGc8St4fdtRJPLirH5dnwAnjY8SxxfmPPQdjuUpump',100,492603),
('HVjK8sAKfbWLy3AQs19WNbig1vBwMmKBVDSS6528pump',100,492612),
('WVRfPU3aTzzX7dGbxFDqHPxuQGj47XEUAn5zGuzpump',100,492630)
    ) AS v(mint, tier, eh)
), sm AS (
    SELECT DISTINCT mint FROM sig
), sol_minute AS (
    SELECT minute, AVG(price) AS sol_usd FROM prices.usd
    WHERE blockchain = 'solana' AND symbol = 'SOL'
      AND minute >= TIMESTAMP '2026-07-01 00:00:00' AND minute < TIMESTAMP '2026-10-01 00:00:00'
    GROUP BY minute
), tr AS (
    SELECT t.block_time, t.tx_id, t.project_program_id AS pool, t.project, t.version, leg.mint,
           IF(t.token_bought_mint_address = leg.mint, t.token_sold_mint_address,
              t.token_bought_mint_address) AS quote_mint,
           IF(t.token_bought_mint_address = leg.mint, t.token_bought_amount,
              t.token_sold_amount) AS token_amount,
           IF(t.token_bought_mint_address = leg.mint, t.token_sold_amount,
              t.token_bought_amount) AS quote_amount
    FROM dex_solana.trades t
    CROSS JOIN UNNEST(ARRAY[t.token_bought_mint_address, t.token_sold_mint_address]) AS leg(mint)
    JOIN sm ON sm.mint = leg.mint
    WHERE t.block_month >= DATE '2026-07-01' AND t.block_month < DATE '2026-10-01'
      AND t.block_time >= TIMESTAMP '2026-07-01 00:00:00' AND t.block_time < TIMESTAMP '2026-10-01 00:00:00'
      AND t.project <> 'pumpdotfun'
      AND t.token_bought_mint_address <> t.token_sold_mint_address
), p1v AS (
    SELECT tr.mint, tr.block_time, tr.tx_id, tr.pool,
           (tr.project = 'pumpswap' OR (tr.project = 'raydium' AND tr.version IN (4, 5))) AS is_cp,
           CASE WHEN tr.quote_mint = 'So11111111111111111111111111111111111111112' THEN tr.quote_amount * s.sol_usd
                ELSE tr.quote_amount END AS quote_usd,
           tr.token_amount
    FROM tr
    LEFT JOIN sol_minute s
      ON tr.quote_mint = 'So11111111111111111111111111111111111111112' AND s.minute = date_trunc('minute', tr.block_time)
    WHERE tr.token_amount > 0
      AND ((tr.quote_mint = 'So11111111111111111111111111111111111111112' AND tr.quote_amount >= 0.001 AND s.sol_usd > 0)
        OR (tr.quote_mint IN ('EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v', 'Es9vMFrzaCERmJfrF4H2FYD4KCoNkY11McCe8BenwNYB') AND tr.quote_amount >= 0.10))
), ph AS (
    SELECT mint, pool, date_trunc('hour', block_time) AS h, bool_or(is_cp) AS is_cp,
           SUM(quote_usd) AS usd, SUM(token_amount) AS tok, COUNT(*) AS n,
           MIN_BY(1e9 * quote_usd / token_amount, block_time) AS f_cap,
           MIN(block_time) AS f_time, MIN_BY(tx_id, block_time) AS f_tx,
           MIN_BY(1e9 * quote_usd / token_amount, block_time)
               FILTER (WHERE block_time >= date_trunc('hour', block_time) + INTERVAL '10' SECOND) AS f10_cap,
           MIN(block_time) FILTER (WHERE block_time >= date_trunc('hour', block_time) + INTERVAL '10' SECOND) AS f10_time,
           MIN_BY(tx_id, block_time)
               FILTER (WHERE block_time >= date_trunc('hour', block_time) + INTERVAL '10' SECOND) AS f10_tx,
           MIN_BY(1e9 * quote_usd / token_amount, block_time)
               FILTER (WHERE block_time >= date_trunc('hour', block_time) + INTERVAL '5' MINUTE) AS f5_cap,
           MIN(block_time) FILTER (WHERE block_time >= date_trunc('hour', block_time) + INTERVAL '5' MINUTE) AS f5_time,
           MIN_BY(tx_id, block_time)
               FILTER (WHERE block_time >= date_trunc('hour', block_time) + INTERVAL '5' MINUTE) AS f5_tx
    FROM p1v GROUP BY 1, 2, 3
), ph2 AS (
    SELECT *,
           SUM(usd) OVER (PARTITION BY mint, h) AS h_usd,
           SUM(tok) OVER (PARTITION BY mint, h) AS h_tok,
           SUM(n) OVER (PARTITION BY mint, h) AS h_n,
           ROW_NUMBER() OVER (PARTITION BY mint, h ORDER BY is_cp DESC, usd DESC, pool) AS prk,
           LEAD(h, 1) OVER (PARTITION BY mint, pool ORDER BY h) AS h1,
           LEAD(f_cap, 1) OVER (PARTITION BY mint, pool ORDER BY h) AS n1_cap,
           LEAD(f_time, 1) OVER (PARTITION BY mint, pool ORDER BY h) AS n1_time,
           LEAD(f_tx, 1) OVER (PARTITION BY mint, pool ORDER BY h) AS n1_tx,
           LEAD(f10_cap, 1) OVER (PARTITION BY mint, pool ORDER BY h) AS n1_10_cap,
           LEAD(f10_time, 1) OVER (PARTITION BY mint, pool ORDER BY h) AS n1_10_time,
           LEAD(f10_tx, 1) OVER (PARTITION BY mint, pool ORDER BY h) AS n1_10_tx,
           LEAD(f5_cap, 1) OVER (PARTITION BY mint, pool ORDER BY h) AS n1_5_cap,
           LEAD(f5_time, 1) OVER (PARTITION BY mint, pool ORDER BY h) AS n1_5_time,
           LEAD(f5_tx, 1) OVER (PARTITION BY mint, pool ORDER BY h) AS n1_5_tx,
           LEAD(f_cap, 2) OVER (PARTITION BY mint, pool ORDER BY h) AS n2_cap,
           LEAD(f_time, 2) OVER (PARTITION BY mint, pool ORDER BY h) AS n2_time,
           LEAD(f_tx, 2) OVER (PARTITION BY mint, pool ORDER BY h) AS n2_tx
    FROM ph
), hm AS (
    SELECT mint, h, pool, is_cp, h_n, h_usd, 1e9 * h_usd / h_tok AS c,
           (h_n >= 5 AND h_usd >= 100.0) AS valid,
           -- 下一小时起点（h+1h）之后，本池第一笔：路径行的退出成交（延迟≈10 秒）
           CASE WHEN h1 = h + INTERVAL '1' HOUR THEN COALESCE(n1_10_cap, n2_cap) ELSE n1_cap END AS x_cap,
           CASE WHEN h1 = h + INTERVAL '1' HOUR THEN COALESCE(n1_10_time, n2_time) ELSE n1_time END AS x_time,
           CASE WHEN h1 = h + INTERVAL '1' HOUR THEN COALESCE(n1_10_tx, n2_tx) ELSE n1_tx END AS x_tx,
           -- 入场：本行若是穿越小时（h = t_s - 1h），t_s = h + 1h
           CASE WHEN h1 = h + INTERVAL '1' HOUR THEN COALESCE(n1_5_cap, n2_cap) ELSE n1_cap END AS e5_cap,
           CASE WHEN h1 = h + INTERVAL '1' HOUR THEN COALESCE(n1_5_time, n2_time) ELSE n1_time END AS e5_time,
           CASE WHEN h1 = h + INTERVAL '1' HOUR THEN COALESCE(n1_5_tx, n2_tx) ELSE n1_tx END AS e5_tx,
           CASE WHEN h1 = h + INTERVAL '1' HOUR THEN n2_cap ELSE n1_cap END AS e60_cap,
           CASE WHEN h1 = h + INTERVAL '1' HOUR THEN n2_time ELSE n1_time END AS e60_time,
           CASE WHEN h1 = h + INTERVAL '1' HOUR THEN n2_tx ELSE n1_tx END AS e60_tx
    FROM ph2 WHERE prk = 1
), j AS (
    SELECT s.mint, s.tier, s.signal_time, m.*,
           m.h = s.signal_time - INTERVAL '1' HOUR AS is_entry,
           m.h >= s.signal_time AND m.valid AS is_path
    FROM sig s JOIN hm m
      ON m.mint = s.mint
     AND m.h >= s.signal_time - INTERVAL '1' HOUR
     AND m.h < s.signal_time + INTERVAL '180' DAY
    WHERE m.h = s.signal_time - INTERVAL '1' HOUR OR (m.h >= s.signal_time AND m.valid)
), b1 AS (
    SELECT *,
           FIRST_VALUE(c) OVER (PARTITION BY mint, tier, is_path ORDER BY h
                                ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW) AS c0,
           LEAD(h) OVER (PARTITION BY mint, tier, is_path ORDER BY h) AS next_h,
           MAX(c) OVER (PARTITION BY mint, tier, is_path) AS maxc,
           MAX_BY(h, c) OVER (PARTITION BY mint, tier, is_path) AS maxh,
           COUNT(*) OVER (PARTITION BY mint, tier, is_path) AS nh
    FROM j
), b2 AS (
    SELECT *, CAST(floor(ln(c / c0) / ln(1.02)) AS BIGINT) AS hb FROM b1
), b3 AS (
    SELECT *, COALESCE(MAX(hb) OVER (PARTITION BY mint, tier, is_path ORDER BY h
                        ROWS BETWEEN UNBOUNDED PRECEDING AND 1 PRECEDING), -1000000) AS prev_hb
    FROM b2
), b4 AS (
    SELECT *, SUM(CASE WHEN hb > prev_hb THEN 1 ELSE 0 END)
                OVER (PARTITION BY mint, tier, is_path ORDER BY h ROWS UNBOUNDED PRECEDING) AS seg,
              hb > prev_hb AS is_hi
    FROM b3
), b5 AS (
    SELECT *, MAX(c) OVER (PARTITION BY mint, tier, is_path, seg ORDER BY h
                           ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW) AS segmax
    FROM b4
), b6 AS (
    SELECT *, CAST(floor(ln(c / segmax) / ln(0.98)) AS BIGINT) AS lb FROM b5
), b7 AS (
    SELECT *, COALESCE(MAX(lb) OVER (PARTITION BY mint, tier, is_path, seg ORDER BY h
                        ROWS BETWEEN UNBOUNDED PRECEDING AND 1 PRECEDING), 0) AS prev_lb,
              MIN(CASE WHEN c <= 0.5 * segmax THEN h END)
                OVER (PARTITION BY mint, tier, is_path) AS certain_h,
              concat_ws(',',
                IF(h + INTERVAL '1' HOUR <= signal_time + INTERVAL '1' DAY
                   AND (next_h IS NULL OR next_h + INTERVAL '1' HOUR > signal_time + INTERVAL '1' DAY), 'D1', NULL),
                IF(h + INTERVAL '1' HOUR <= signal_time + INTERVAL '7' DAY
                   AND (next_h IS NULL OR next_h + INTERVAL '1' HOUR > signal_time + INTERVAL '7' DAY), 'D7', NULL),
                IF(h + INTERVAL '1' HOUR <= signal_time + INTERVAL '30' DAY
                   AND (next_h IS NULL OR next_h + INTERVAL '1' HOUR > signal_time + INTERVAL '30' DAY), 'D30', NULL),
                IF(h + INTERVAL '1' HOUR <= signal_time + INTERVAL '90' DAY
                   AND (next_h IS NULL OR next_h + INTERVAL '1' HOUR > signal_time + INTERVAL '90' DAY), 'D90', NULL),
                IF(h + INTERVAL '1' HOUR <= signal_time + INTERVAL '180' DAY
                   AND (next_h IS NULL OR next_h + INTERVAL '1' HOUR > signal_time + INTERVAL '180' DAY), 'D180', NULL)
              ) AS hz
    FROM b6
)
SELECT CASE WHEN is_entry THEN 'E' ELSE 'P' END AS rt,
       mint, tier, signal_time, h, pool, is_cp, h_n, h_usd, c,
       CASE WHEN is_entry THEN 'entry' WHEN is_hi THEN 'hi' WHEN c <= 0.5 * segmax THEN 'dd50'
            WHEN lb > prev_lb AND lb >= 1 THEN 'lo' ELSE 'keep' END AS kind,
       segmax, CASE WHEN is_entry THEN '' ELSE hz END AS hz,
       CASE WHEN is_entry THEN FALSE ELSE next_h IS NULL END AS is_last, maxc, maxh, nh,
       x_cap, x_time, x_tx,
       e5_cap, e5_time, e5_tx, e60_cap, e60_time, e60_tx
FROM b7
WHERE is_entry
   OR (is_path AND (
          ((certain_h IS NULL OR h <= certain_h) AND (is_hi OR (lb > prev_lb AND lb >= 1)))
          OR hz <> '' OR next_h IS NULL))
ORDER BY mint, tier, h
