-- DQ-18 D 段路径块：2024-08～2024-09（生成器 make_d_block.py；口径见文件头）
-- 活跃样本信号 249 个（样本 raw/census/sample_D.csv，sha256 1ec965c0…）。不计算收益。
-- 运行时单条费用上限 100 credits。
WITH sig AS (
    SELECT mint, tier * 1000000 AS tier, from_unixtime(eh * 3600) AS signal_time
    FROM (VALUES
('5zgTYTDK836G2Fc4ZLQp4rsyi78pAbuDr4qaQUE1pump',1,477003),
('Bw7rU9vQVMhvgAtcdFYxXm2Ya2JCDzruifD5GE5WZvUb',1,477012),
('BEgBsVSKJSxreiCE1XmWWq8arnwit7xDqQXSWYgay9xP',1,477089),
('q181ST7rmrrZrXgKButYmTb7Wt2p34BvLuvPWaypump',1,477097),
('BX9yEgW8WkoWV8SvqTMMCynkQWreRTJ9ZS81dRXYnnR9',1,477099),
('146Pouk195TZZBFBc6f1gisFsgsKFviPbwbbV84AfMqt',1,477109),
('F6ExBzKdLRcJkCAknQgfbhRXX78EhqoNxPnegJWPpump',1,477128),
('CgMh3naYCdBoqt9yMvWirp7AwfgaM5SMn8HBNPVTpump',1,477129),
('62mALBEzUQWS3r8EzjnX1C2ricdTy9hkv8gs7mLtpump',1,477146),
('8NH3AfwkizHmbVd83SSxc2YbsFmFL4m2BeepvL6upump',1,477159),
('2fUFhZyd47Mapv9wcfXh5gnQwFXtqcYu9xAN4THBpump',1,477160),
('FWFEKXi3rj9UjiW4X32P3F4h5qipcCxqqHQCkgFLpump',1,477184),
('6MawjTSbkVDzyUKXgZLrPosSpFUUcb3zKzz8yr6Wpump',1,477213),
('4Cnk9EPnW5ixfLZatCPJjDB1PUtcRpVVgTQukm9epump',1,477214),
('25csXP6nGdyMdMUXA7KnAbgD1dhGR1kPCVJ7Qv1Lpump',1,477222),
('5GejeHFsM2NQ67QVGArYNj9iUTr3HacSDr1E4zeupump',1,477227),
('EqGMz1o1KiBs1wtotR4rnDADEHvUu39Emv46ZjBEpump',1,477236),
('2J5uSgqgarWoh7QDBmHSDA3d7UbfBKDZsdy1ypTSpump',1,477265),
('4gBDhgCqTtzyJocskewXARgcLoAfSxkmmoUwwfhbpump',1,477274),
('3Jjt8QhbqNoYfSQYHWf8ZsTJwE2CyvmUrzgzJD5Jpump',1,477290),
('8qYH37jFCVbGSjQPdMsf8TDwp1JHTjU1McA8GoCCpump',1,477300),
('HqH81vJiUqsiYgLbu6t2MRwY1XJBVhNXy2kuBM2Epump',1,477301),
('Rizz63Lw79uKZWSKRcCxrhZEA3MUQiy2MJ8GvYM2EQp',1,477356),
('7b36cKRYFZsMp3vLByVwfVQxW2ndcYth5rhPnyypump',1,477381),
('Bzu1nWVKRFEn7FRumTNrTC4qqxtBaMCMBNY1z7ejpump',1,477385),
('3B5wuUrMEi5yATD7on46hKfej3pfmd7t1RKgrsN3pump',1,477390),
('GkJxELgJXpQRm7dfc2yS18vBDRxP5SjVJgbrmTGgpump',1,477404),
('ERLqGWMsmyuRAmHWBM8MUGbokAj94GDX65dvKWxmpump',1,477465),
('4GFe6MBDorSy5bLbiUMrgETr6pZcjyfxMDm5ehSgpump',1,477475),
('F6TsRcjtLBzkdtZYqjTPVq9WtnwHMMc1WcQguEgCpump',1,477490),
('6SUryVEuDz5hqAxab6QrGfbzWvjN8dC7m29ezSvDpump',1,477554),
('F6s6hxSW6yWF4h5YBbW28JHLFEGXKYbEmungaTPtpump',1,477598),
('48yNDqabAvGNfnkhadsV1MAvtp44fFDdHBRBdFhvpump',1,477627),
('b1nkm6skdrwXoMku8CVx8Fk4LfC2jAqxV3m9VDNjYqz',1,477633),
('A6jYYUKaoxVo5uQtQNLUmfzrHBWL6vJFoFHdE17Jpump',1,477645),
('EDPL6LGZzTe1KQxeb5JXG9s1ExBWk9QgEJk2GKJvpump',1,477723),
('BreuhVohXX5fv6q41uyb3sojtAuGoGaiAhKBMtcrpump',1,477762),
('12d3KBU8GPk8aoZKceBCmxWXSkEpLNXYNSScS7QTpump',1,477764),
('Spc5hci4W1MGALk4xUFrN4y7iNFt1SJ6GkYsB34pump',1,477792),
('C57PMKgMZFhiYhGM6tA5HsTMosRH22ET3HhE6HJKpump',1,477846),
('6ZrYhkwvoYE4QqzpdzJ7htEHwT2u2546EkTNJ7qepump',1,477896),
('BVG3BJH4ghUPJT9mCi7JbziNwx3dqRTzgo9x5poGpump',1,477912),
('BU7zw2GvabhqGnrqMMH1m2KabafehanDmtnrCSZipump',1,477924),
('FsBPYiGZ4bhUxVSPP7XPJYfTPm5PsLJc2WGZaFaDpump',1,477933),
('3meWn4683ng7FgLVJJB2bYPaNSoqhWdritNdkd4Aw1aj',1,477953),
('A8iVH9ZpvVhXDqtbEpWfrvRd4fvZcQSGH2zmtAqEpump',1,477994),
('5SVG3T9CNQsm2kEwzbRq6hASqh1oGfjqTtLXYUibpump',1,477999),
('FPXjB2yjp4ef33ak7FZSMU4CLLEjgXA9dVwr5Nd4pump',1,478025),
('GK7TPZKpd8ZsXfipzcEaPnoSp2bDCZg5BU4GZwVzpump',1,478031),
('2BUZ19fT8TYvPzhuvtCCp9ceu9eNRCmY11S4vSATpump',1,478032),
('KMnDBXcPXoz6oMJW5XG4tXdwSWpmWEP2RQM1Uujpump',1,478034),
('7D7BRcBYepfi77vxySapmeqRNN1wsBBxnFPJGbH5pump',1,478073),
('BkVeSP2GsXV3AYoRJBSZTpFE8sXmcuGnRQcFgoWspump',1,478120),
('7iagMTDPfNSR5zVcERT1To7A9eaQoz58dJAh42EMHcCC',1,478140),
('LoL1RDQiUfifC2BX28xaef6r2G8ES8SEzgrzThJemMv',1,478152),
('3WXnaXnqeqF5NxyjhRosVqs4jPM8XXEVJbMmkD69pump',1,478191),
('CWtE52x8yKSXPEcnoYv2WXRwXZ4yKk8VErsh6dqr4oxa',1,478191),
('4JCaUehMpcpqZEwuuiDc6tVBKo9HaqrKDJf6NVSjpump',1,478208),
('6cvrZWgEUkr82yKAmxp5cQu7wgYYBPULf16EUBp4pump',1,478220),
('EsHgPT4w334ZBGwf5htrLScU8JSFhrMTTdXomjRApump',1,478242),
('GiG7Hr61RVm4CSUxJmgiCoySFQtdiwxtqf64MsRppump',1,478244),
('AEKUy9xPYaUPPbuh2K1koBCLrvyFTjD89xa3M9eRpump',1,478245),
('7VNuspmaSwjeVAgCSgPjwyma4ZV74jQcpm8mQv5wpump',1,478252),
('GUJznRQz7jcSGFA7pT3X7RpoLgazUAX8UhpJQQ8Fpump',1,478268),
('FYzAWUYqmu8kFzERPKkTgVYd4BSbedMjVhYPyLPdpump',1,478269),
('ANAuiz2JjRvNtyW8cd7UsQ4LRWB1PTGhyrgMWPxtpump',1,478272),
('Em4rcuhX6STfB7mxb66dUXDmZPYCjDiQFthvzSzpump',1,478278),
('8X9qhDd6dm6c8ePse7aXGaiJzSJENHak2LKVu3fYpump',1,478309),
('3G8gmuzyA91wC3PHVMptsVVPYd4zmZ4ZaxD3BYBapump',1,478316),
('CTJf74cTo3cw8acFP1YXF3QpsQUUBGBjh2k2e8xsZ6UL',1,478366),
('CTg3ZgYx79zrE1MteDVkmkcGniiFrK1hJ6yiabropump',1,478367),
('3KojMBrg1CEBbYokTxH3o7TwSgUs5AcWJ9XWjg4ppump',1,478406),
('A8C3xuqscfmyLrte3VmTqrAq8kgMASius9AFNANwpump',1,478420),
('5VwW1dT6a2sWvs4rt91wfduEwqY9cNwvur4jeuvEMXZ9',1,478434),
('DEJiPKx5GActUtB6qUssreUxkhXtL4hTQAAJZ7Ccw8se',1,478447),
('ELo6n1QgwQej2fq2Rf7mbPwbX3vWgMLDsqYfUv3pump',1,478448),
('piJgLh8axY1Q5bsgovRB3Nr4aVbHSHmpCbsTLahpump',1,478458),
('4A4fCRhahAviEXU9zmG7sAuYiPAAcbuPizkFC4Yxpump',1,478521),
('6iSxupoCQyiGwufKpvxjwntpxDCvmhnizBN3JYECpump',1,478541),
('GYKmdfcUmZVrqfcH1g579BGjuzSRijj3LBuwv79rpump',1,478585),
('BdNKUUo8vnvdhwi1Ejn4PXNfeeQF2374hCK3m91ppump',1,478601),
('7u6WirUYbf3kJdZQoPTCYjgU5rpVg21LuXLKmmCUpump',1,478668),
('AgWYFCK8mwCGhSbb1SVy2XyK9wbdaqGZ4SWrznqhB94X',1,478771),
('6CEjCg7Jo5RV9kFSgKx66rpW19nrsCmccD2bxfwpump',1,478821),
('984GBL7PhceChtN64NWLdBb49rSQXX7ozpdkEbR1pump',1,478821),
('8tgUbstKsTJREkQEwq9cJodPpjasSKNriveUkGD6waq3',1,478838),
('CKxE7K1fxYev77osZkt55n3JpEzLmq1rap2DLRFtrPvL',1,478840),
('GtWJpuTgyQBzo9kPbM7MBUa7UXJfTtPbWpsvXDEJpump',1,478866),
('7M9KJcPNC65ShLDmJmTNhVFcuY95Y1VMeYngKgt67D1t',1,478872),
('62CsquahdQ3J286G9UTqV6whxryfihdV4yg7kSJnpump',1,478878),
('ErVrf7WrMS8Rw4b6ZkYSVR5TvMjKRMjSLH8cwT7jmbgp',1,478890),
('3m8CHwfJ3TYaULkbi2uK2HdX2LNQdYgNm9UYKPBopump',1,478944),
('G3s49agBGCXqqhLXGXFtasQgAAMPvXQifyWL5M2Wpump',1,478953),
('3nMQMnsn5mzcMMt3jEP2NpKmb5nmYjrLEXmiXb6Mpump',1,479070),
('Gtg3TN8cKi5GmUvHS6CNrP8vzmYm1SU2yjTgbH5Cpump',1,479237),
('BSqMUYb6ePwKsby85zrXaDa4SNf6AgZ9YfA2c4mZpump',1,479280),
('3yhsQKMeFDo3FN5vxRZnEvvr9cN67aU9qwrMrpURgHVU',1,479374),
('TVZMHMzujTLJzDJ3Y8HXo33wUVU67sPS26eRuYNninj',1,479409),
('ED5nyyWEzpPPiWimP8vYm7sD7TD3LAt3Q3gRTWHzPJBY',1,479512),
('4yCuUMPFvaqxK71CK6SZc3wmtC2PDpDN9mcBzUkepump',1,479555),
('BQpGv6LVWG1JRm1NdjerNSFdChMdAULJr3x9t2Swpump',1,479583),
('EfBuJCMve4mBUPVgyjWrQzjXqfYyu23ThrY4bEXtpump',1,479628),
('34a8ALsPmbWxp7D3bQ6erERrCLz1ahr6u6o66Udmpump',1,479636),
('EtJcUdtVsDFQYhitUELnBE8PR3JvG1DPkYMT2xuZpump',1,479698),
('BTA9WWTu67ZCSwsc6MjvpWa5fJSDYk7cxT9TS37Mpump',1,479757),
('ESVRQ6phc55VCw7sWB6JgW3PeTB6N68kvwjfsMPcpump',1,479814),
('CS7LmjtuugEUWtFgfyto79nrksKigv7Fdcp9qPuigdLs',1,479817),
('2G8LH53fcr3aCrEsmAo73eunbZRbyjKrGH5qmur6pump',1,479840),
('7BMb4jNt2tQG81jX7W22H2h2UyL4SW9QJgz25HRhpump',1,479872),
('AiYhnwWiqbdSiEHgAzqrurcdoZx4V21mnuMt5ps2pump',1,479876),
('4j2gUEmfbSAacvSSd6yXo8yEzXCAUVeoXrqLVV3apump',1,479902),
('5zgTYTDK836G2Fc4ZLQp4rsyi78pAbuDr4qaQUE1pump',5,477004),
('Bw7rU9vQVMhvgAtcdFYxXm2Ya2JCDzruifD5GE5WZvUb',5,477048),
('BEgBsVSKJSxreiCE1XmWWq8arnwit7xDqQXSWYgay9xP',5,477096),
('BX9yEgW8WkoWV8SvqTMMCynkQWreRTJ9ZS81dRXYnnR9',5,477112),
('DtR4D9FtVoTX2569gaL837ZgrB6wNjj6tkmnX9Rdk9B2',5,477117),
('62mALBEzUQWS3r8EzjnX1C2ricdTy9hkv8gs7mLtpump',5,477147),
('8NH3AfwkizHmbVd83SSxc2YbsFmFL4m2BeepvL6upump',5,477160),
('2fUFhZyd47Mapv9wcfXh5gnQwFXtqcYu9xAN4THBpump',5,477162),
('F6ExBzKdLRcJkCAknQgfbhRXX78EhqoNxPnegJWPpump',5,477175),
('4Cnk9EPnW5ixfLZatCPJjDB1PUtcRpVVgTQukm9epump',5,477215),
('EqGMz1o1KiBs1wtotR4rnDADEHvUu39Emv46ZjBEpump',5,477236),
('2J5uSgqgarWoh7QDBmHSDA3d7UbfBKDZsdy1ypTSpump',5,477266),
('3Jjt8QhbqNoYfSQYHWf8ZsTJwE2CyvmUrzgzJD5Jpump',5,477291),
('4gBDhgCqTtzyJocskewXARgcLoAfSxkmmoUwwfhbpump',5,477294),
('3B5wuUrMEi5yATD7on46hKfej3pfmd7t1RKgrsN3pump',5,477392),
('GkJxELgJXpQRm7dfc2yS18vBDRxP5SjVJgbrmTGgpump',5,477406),
('4GFe6MBDorSy5bLbiUMrgETr6pZcjyfxMDm5ehSgpump',5,477497),
('6SUryVEuDz5hqAxab6QrGfbzWvjN8dC7m29ezSvDpump',5,477567),
('F6s6hxSW6yWF4h5YBbW28JHLFEGXKYbEmungaTPtpump',5,477600),
('48yNDqabAvGNfnkhadsV1MAvtp44fFDdHBRBdFhvpump',5,477640),
('A6jYYUKaoxVo5uQtQNLUmfzrHBWL6vJFoFHdE17Jpump',5,477646),
('F6TsRcjtLBzkdtZYqjTPVq9WtnwHMMc1WcQguEgCpump',5,477686),
('12d3KBU8GPk8aoZKceBCmxWXSkEpLNXYNSScS7QTpump',5,477764),
('Spc5hci4W1MGALk4xUFrN4y7iNFt1SJ6GkYsB34pump',5,477796),
('BreuhVohXX5fv6q41uyb3sojtAuGoGaiAhKBMtcrpump',5,477817),
('BVG3BJH4ghUPJT9mCi7JbziNwx3dqRTzgo9x5poGpump',5,477934),
('3meWn4683ng7FgLVJJB2bYPaNSoqhWdritNdkd4Aw1aj',5,477953),
('FsBPYiGZ4bhUxVSPP7XPJYfTPm5PsLJc2WGZaFaDpump',5,477997),
('2BUZ19fT8TYvPzhuvtCCp9ceu9eNRCmY11S4vSATpump',5,478034),
('KMnDBXcPXoz6oMJW5XG4tXdwSWpmWEP2RQM1Uujpump',5,478046),
('5SVG3T9CNQsm2kEwzbRq6hASqh1oGfjqTtLXYUibpump',5,478083),
('GK7TPZKpd8ZsXfipzcEaPnoSp2bDCZg5BU4GZwVzpump',5,478097),
('146Pouk195TZZBFBc6f1gisFsgsKFviPbwbbV84AfMqt',5,478113),
('LoL1RDQiUfifC2BX28xaef6r2G8ES8SEzgrzThJemMv',5,478165),
('CWtE52x8yKSXPEcnoYv2WXRwXZ4yKk8VErsh6dqr4oxa',5,478191),
('BkVeSP2GsXV3AYoRJBSZTpFE8sXmcuGnRQcFgoWspump',5,478194),
('6ZrYhkwvoYE4QqzpdzJ7htEHwT2u2546EkTNJ7qepump',5,478204),
('7D7BRcBYepfi77vxySapmeqRNN1wsBBxnFPJGbH5pump',5,478222),
('6cvrZWgEUkr82yKAmxp5cQu7wgYYBPULf16EUBp4pump',5,478237),
('EsHgPT4w334ZBGwf5htrLScU8JSFhrMTTdXomjRApump',5,478242),
('FYzAWUYqmu8kFzERPKkTgVYd4BSbedMjVhYPyLPdpump',5,478279),
('GiG7Hr61RVm4CSUxJmgiCoySFQtdiwxtqf64MsRppump',5,478288),
('3G8gmuzyA91wC3PHVMptsVVPYd4zmZ4ZaxD3BYBapump',5,478321),
('8X9qhDd6dm6c8ePse7aXGaiJzSJENHak2LKVu3fYpump',5,478323),
('CTJf74cTo3cw8acFP1YXF3QpsQUUBGBjh2k2e8xsZ6UL',5,478366),
('CTg3ZgYx79zrE1MteDVkmkcGniiFrK1hJ6yiabropump',5,478369),
('3WXnaXnqeqF5NxyjhRosVqs4jPM8XXEVJbMmkD69pump',5,478385),
('A8C3xuqscfmyLrte3VmTqrAq8kgMASius9AFNANwpump',5,478420),
('4A4fCRhahAviEXU9zmG7sAuYiPAAcbuPizkFC4Yxpump',5,478521),
('6iSxupoCQyiGwufKpvxjwntpxDCvmhnizBN3JYECpump',5,478542),
('GYKmdfcUmZVrqfcH1g579BGjuzSRijj3LBuwv79rpump',5,478589),
('BdNKUUo8vnvdhwi1Ejn4PXNfeeQF2374hCK3m91ppump',5,478602),
('ANAuiz2JjRvNtyW8cd7UsQ4LRWB1PTGhyrgMWPxtpump',5,478649),
('BU7zw2GvabhqGnrqMMH1m2KabafehanDmtnrCSZipump',5,478680),
('7u6WirUYbf3kJdZQoPTCYjgU5rpVg21LuXLKmmCUpump',5,478691),
('6CEjCg7Jo5RV9kFSgKx66rpW19nrsCmccD2bxfwpump',5,478824),
('8tgUbstKsTJREkQEwq9cJodPpjasSKNriveUkGD6waq3',5,478838),
('CKxE7K1fxYev77osZkt55n3JpEzLmq1rap2DLRFtrPvL',5,478841),
('984GBL7PhceChtN64NWLdBb49rSQXX7ozpdkEbR1pump',5,478870),
('GtWJpuTgyQBzo9kPbM7MBUa7UXJfTtPbWpsvXDEJpump',5,478878),
('62CsquahdQ3J286G9UTqV6whxryfihdV4yg7kSJnpump',5,478883),
('7M9KJcPNC65ShLDmJmTNhVFcuY95Y1VMeYngKgt67D1t',5,478891),
('3m8CHwfJ3TYaULkbi2uK2HdX2LNQdYgNm9UYKPBopump',5,478950),
('ErVrf7WrMS8Rw4b6ZkYSVR5TvMjKRMjSLH8cwT7jmbgp',5,479033),
('3nMQMnsn5mzcMMt3jEP2NpKmb5nmYjrLEXmiXb6Mpump',5,479072),
('DEJiPKx5GActUtB6qUssreUxkhXtL4hTQAAJZ7Ccw8se',5,479217),
('Gtg3TN8cKi5GmUvHS6CNrP8vzmYm1SU2yjTgbH5Cpump',5,479237),
('piJgLh8axY1Q5bsgovRB3Nr4aVbHSHmpCbsTLahpump',5,479255),
('TVZMHMzujTLJzDJ3Y8HXo33wUVU67sPS26eRuYNninj',5,479409),
('4yCuUMPFvaqxK71CK6SZc3wmtC2PDpDN9mcBzUkepump',5,479578),
('ED5nyyWEzpPPiWimP8vYm7sD7TD3LAt3Q3gRTWHzPJBY',5,479580),
('EfBuJCMve4mBUPVgyjWrQzjXqfYyu23ThrY4bEXtpump',5,479628),
('3yhsQKMeFDo3FN5vxRZnEvvr9cN67aU9qwrMrpURgHVU',5,479653),
('EtJcUdtVsDFQYhitUELnBE8PR3JvG1DPkYMT2xuZpump',5,479704),
('BTA9WWTu67ZCSwsc6MjvpWa5fJSDYk7cxT9TS37Mpump',5,479757),
('BQpGv6LVWG1JRm1NdjerNSFdChMdAULJr3x9t2Swpump',5,479782),
('34a8ALsPmbWxp7D3bQ6erERrCLz1ahr6u6o66Udmpump',5,479784),
('ESVRQ6phc55VCw7sWB6JgW3PeTB6N68kvwjfsMPcpump',5,479815),
('CS7LmjtuugEUWtFgfyto79nrksKigv7Fdcp9qPuigdLs',5,479847),
('G3s49agBGCXqqhLXGXFtasQgAAMPvXQifyWL5M2Wpump',5,479848),
('7BMb4jNt2tQG81jX7W22H2h2UyL4SW9QJgz25HRhpump',5,479873),
('AiYhnwWiqbdSiEHgAzqrurcdoZx4V21mnuMt5ps2pump',5,479881),
('5zgTYTDK836G2Fc4ZLQp4rsyi78pAbuDr4qaQUE1pump',20,477015),
('BX9yEgW8WkoWV8SvqTMMCynkQWreRTJ9ZS81dRXYnnR9',20,477118),
('BEgBsVSKJSxreiCE1XmWWq8arnwit7xDqQXSWYgay9xP',20,477145),
('62mALBEzUQWS3r8EzjnX1C2ricdTy9hkv8gs7mLtpump',20,477151),
('8NH3AfwkizHmbVd83SSxc2YbsFmFL4m2BeepvL6upump',20,477163),
('2fUFhZyd47Mapv9wcfXh5gnQwFXtqcYu9xAN4THBpump',20,477164),
('4Cnk9EPnW5ixfLZatCPJjDB1PUtcRpVVgTQukm9epump',20,477221),
('EqGMz1o1KiBs1wtotR4rnDADEHvUu39Emv46ZjBEpump',20,477248),
('3Jjt8QhbqNoYfSQYHWf8ZsTJwE2CyvmUrzgzJD5Jpump',20,477302),
('3B5wuUrMEi5yATD7on46hKfej3pfmd7t1RKgrsN3pump',20,477399),
('4gBDhgCqTtzyJocskewXARgcLoAfSxkmmoUwwfhbpump',20,477424),
('4GFe6MBDorSy5bLbiUMrgETr6pZcjyfxMDm5ehSgpump',20,477509),
('F6s6hxSW6yWF4h5YBbW28JHLFEGXKYbEmungaTPtpump',20,477602),
('6SUryVEuDz5hqAxab6QrGfbzWvjN8dC7m29ezSvDpump',20,477616),
('A6jYYUKaoxVo5uQtQNLUmfzrHBWL6vJFoFHdE17Jpump',20,477647),
('6yjNqPzTSanBWSa6dxVEgTjePXBrZ2FoHLDQwYwEsyM6',20,477759),
('DtR4D9FtVoTX2569gaL837ZgrB6wNjj6tkmnX9Rdk9B2',20,477878),
('BVG3BJH4ghUPJT9mCi7JbziNwx3dqRTzgo9x5poGpump',20,477960),
('2BUZ19fT8TYvPzhuvtCCp9ceu9eNRCmY11S4vSATpump',20,478038),
('FsBPYiGZ4bhUxVSPP7XPJYfTPm5PsLJc2WGZaFaDpump',20,478119),
('3meWn4683ng7FgLVJJB2bYPaNSoqhWdritNdkd4Aw1aj',20,478216),
('7D7BRcBYepfi77vxySapmeqRNN1wsBBxnFPJGbH5pump',20,478224),
('CWtE52x8yKSXPEcnoYv2WXRwXZ4yKk8VErsh6dqr4oxa',20,478230),
('BreuhVohXX5fv6q41uyb3sojtAuGoGaiAhKBMtcrpump',20,478233),
('EsHgPT4w334ZBGwf5htrLScU8JSFhrMTTdXomjRApump',20,478253),
('GiG7Hr61RVm4CSUxJmgiCoySFQtdiwxtqf64MsRppump',20,478299),
('3G8gmuzyA91wC3PHVMptsVVPYd4zmZ4ZaxD3BYBapump',20,478327),
('5SVG3T9CNQsm2kEwzbRq6hASqh1oGfjqTtLXYUibpump',20,478336),
('CTJf74cTo3cw8acFP1YXF3QpsQUUBGBjh2k2e8xsZ6UL',20,478367),
('CTg3ZgYx79zrE1MteDVkmkcGniiFrK1hJ6yiabropump',20,478378),
('A8C3xuqscfmyLrte3VmTqrAq8kgMASius9AFNANwpump',20,478424),
('BdNKUUo8vnvdhwi1Ejn4PXNfeeQF2374hCK3m91ppump',20,478605),
('GYKmdfcUmZVrqfcH1g579BGjuzSRijj3LBuwv79rpump',20,478609),
('7u6WirUYbf3kJdZQoPTCYjgU5rpVg21LuXLKmmCUpump',20,478694),
('BU7zw2GvabhqGnrqMMH1m2KabafehanDmtnrCSZipump',20,478850),
('GtWJpuTgyQBzo9kPbM7MBUa7UXJfTtPbWpsvXDEJpump',20,478882),
('3m8CHwfJ3TYaULkbi2uK2HdX2LNQdYgNm9UYKPBopump',20,478993),
('984GBL7PhceChtN64NWLdBb49rSQXX7ozpdkEbR1pump',20,479132),
('Gtg3TN8cKi5GmUvHS6CNrP8vzmYm1SU2yjTgbH5Cpump',20,479237),
('TVZMHMzujTLJzDJ3Y8HXo33wUVU67sPS26eRuYNninj',20,479410),
('4yCuUMPFvaqxK71CK6SZc3wmtC2PDpDN9mcBzUkepump',20,479614),
('ED5nyyWEzpPPiWimP8vYm7sD7TD3LAt3Q3gRTWHzPJBY',20,479620),
('EfBuJCMve4mBUPVgyjWrQzjXqfYyu23ThrY4bEXtpump',20,479754),
('BTA9WWTu67ZCSwsc6MjvpWa5fJSDYk7cxT9TS37Mpump',20,479757),
('EtJcUdtVsDFQYhitUELnBE8PR3JvG1DPkYMT2xuZpump',20,479799),
('34a8ALsPmbWxp7D3bQ6erERrCLz1ahr6u6o66Udmpump',20,479811),
('ESVRQ6phc55VCw7sWB6JgW3PeTB6N68kvwjfsMPcpump',20,479837),
('CS7LmjtuugEUWtFgfyto79nrksKigv7Fdcp9qPuigdLs',20,479868),
('3S8qX1MsMqRbiwKg2cQyx7nis1oHMgaCuc9c4VfvVdPN',100,477099),
('4Cnk9EPnW5ixfLZatCPJjDB1PUtcRpVVgTQukm9epump',100,477264),
('F6s6hxSW6yWF4h5YBbW28JHLFEGXKYbEmungaTPtpump',100,477603),
('A6jYYUKaoxVo5uQtQNLUmfzrHBWL6vJFoFHdE17Jpump',100,477648),
('3B5wuUrMEi5yATD7on46hKfej3pfmd7t1RKgrsN3pump',100,477750),
('GiG7Hr61RVm4CSUxJmgiCoySFQtdiwxtqf64MsRppump',100,478431),
('A8C3xuqscfmyLrte3VmTqrAq8kgMASius9AFNANwpump',100,479517),
('ED5nyyWEzpPPiWimP8vYm7sD7TD3LAt3Q3gRTWHzPJBY',100,479804)
    ) AS v(mint, tier, eh)
), sm AS (
    SELECT DISTINCT mint FROM sig
), sol_minute AS (
    SELECT minute, AVG(price) AS sol_usd FROM prices.usd
    WHERE blockchain = 'solana' AND symbol = 'SOL'
      AND minute >= TIMESTAMP '2024-08-01 00:00:00' AND minute < TIMESTAMP '2024-10-01 00:00:00'
    GROUP BY minute
), tr AS (
    SELECT t.block_time, t.tx_id, t.project_program_id AS pool, leg.mint,
           IF(t.token_bought_mint_address = leg.mint, t.token_sold_mint_address,
              t.token_bought_mint_address) AS quote_mint,
           IF(t.token_bought_mint_address = leg.mint, t.token_bought_amount,
              t.token_sold_amount) AS token_amount,
           IF(t.token_bought_mint_address = leg.mint, t.token_sold_amount,
              t.token_bought_amount) AS quote_amount
    FROM dex_solana.trades t
    CROSS JOIN UNNEST(ARRAY[t.token_bought_mint_address, t.token_sold_mint_address]) AS leg(mint)
    JOIN sm ON sm.mint = leg.mint
    WHERE t.block_month >= DATE '2024-08-01' AND t.block_month < DATE '2024-10-01'
      AND t.block_time >= TIMESTAMP '2024-08-01 00:00:00' AND t.block_time < TIMESTAMP '2024-10-01 00:00:00'
      AND t.project <> 'pumpdotfun'
      AND t.token_bought_mint_address <> t.token_sold_mint_address
), p1v AS (
    SELECT tr.mint, tr.block_time, tr.tx_id, tr.pool,
           CASE WHEN tr.quote_mint = 'So11111111111111111111111111111111111111112' THEN tr.quote_amount * s.sol_usd
                ELSE tr.quote_amount END AS quote_usd,
           tr.token_amount,
           1e9 * (CASE WHEN tr.quote_mint = 'So11111111111111111111111111111111111111112' THEN tr.quote_amount * s.sol_usd
                       ELSE tr.quote_amount END) / tr.token_amount AS cap
    FROM tr
    LEFT JOIN sol_minute s
      ON tr.quote_mint = 'So11111111111111111111111111111111111111112' AND s.minute = date_trunc('minute', tr.block_time)
    WHERE tr.token_amount > 0
      AND ((tr.quote_mint = 'So11111111111111111111111111111111111111112' AND tr.quote_amount >= 0.001 AND s.sol_usd > 0)
        OR (tr.quote_mint IN ('EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v', 'Es9vMFrzaCERmJfrF4H2FYD4KCoNkY11McCe8BenwNYB') AND tr.quote_amount >= 0.10))
), hp AS (
    SELECT mint, date_trunc('hour', block_time) AS h, pool, SUM(quote_usd) AS usd
    FROM p1v GROUP BY 1, 2, 3
), mainpool AS (
    SELECT mint, h, MAX_BY(pool, usd) AS pool FROM hp GROUP BY 1, 2
), hourly AS (
    SELECT mint, date_trunc('hour', block_time) AS h,
           1e9 * SUM(quote_usd) / SUM(token_amount) AS c, COUNT(*) AS n
    FROM p1v GROUP BY 1, 2
), pf AS (
    SELECT mint, pool, date_trunc('hour', block_time) AS h,
           MIN_BY(cap, block_time) AS fcap, MIN(block_time) AS ftime,
           MIN_BY(tx_id, block_time) AS ftx
    FROM p1v GROUP BY 1, 2, 3
), pn AS (
    SELECT mint, pool, h,
           LEAD(fcap) OVER (PARTITION BY mint, pool ORDER BY h) AS ncap,
           LEAD(ftime) OVER (PARTITION BY mint, pool ORDER BY h) AS ntime,
           LEAD(ftx) OVER (PARTITION BY mint, pool ORDER BY h) AS ntx
    FROM pf
), path AS (
    SELECT s.mint, s.tier, s.signal_time, hr.h, hr.c, hr.n
    FROM sig s JOIN hourly hr ON hr.mint = s.mint
    WHERE hr.h >= s.signal_time AND hr.h < s.signal_time + INTERVAL '180' DAY
), b1 AS (
    SELECT *,
           FIRST_VALUE(c) OVER (PARTITION BY mint, tier ORDER BY h
                                ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW) AS c0
    FROM path
), b2 AS (
    SELECT *, CAST(floor(ln(c / c0) / ln(1.02)) AS BIGINT) AS hb FROM b1
), b3 AS (
    SELECT *, COALESCE(MAX(hb) OVER (PARTITION BY mint, tier ORDER BY h
                        ROWS BETWEEN UNBOUNDED PRECEDING AND 1 PRECEDING), -1000000) AS prev_hb
    FROM b2
), b4 AS (
    SELECT *, SUM(CASE WHEN hb > prev_hb THEN 1 ELSE 0 END)
                OVER (PARTITION BY mint, tier ORDER BY h ROWS UNBOUNDED PRECEDING) AS seg,
              hb > prev_hb AS is_hi
    FROM b3
), b5 AS (
    SELECT *, MAX(c) OVER (PARTITION BY mint, tier, seg ORDER BY h
                           ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW) AS segmax
    FROM b4
), b6 AS (
    SELECT *, CAST(floor(ln(c / segmax) / ln(0.98)) AS BIGINT) AS lb FROM b5
), b7 AS (
    SELECT *, COALESCE(MAX(lb) OVER (PARTITION BY mint, tier, seg ORDER BY h
                        ROWS BETWEEN UNBOUNDED PRECEDING AND 1 PRECEDING), 0) AS prev_lb,
              MIN(CASE WHEN c <= 0.5 * segmax THEN h END)
                OVER (PARTITION BY mint, tier) AS certain_h
    FROM b6
), prow AS (
    SELECT b.mint, b.tier, b.signal_time, b.h, b.c, b.segmax, b.n,
           CASE WHEN b.is_hi THEN 'hi' WHEN b.c <= 0.5 * b.segmax THEN 'dd50' ELSE 'lo' END AS kind,
           x.ncap, x.ntime, x.ntx, m.pool
    FROM b7 b
    LEFT JOIN mainpool m ON m.mint = b.mint AND m.h = b.h
    LEFT JOIN pn x ON x.mint = b.mint AND x.pool = m.pool AND x.h = b.h
    WHERE (b.certain_h IS NULL OR b.h <= b.certain_h)
      AND (b.is_hi OR (b.lb > b.prev_lb AND b.lb >= 1))
), lags(lag_label, lag_s) AS (
    VALUES ('L10s', 10), ('L5m', 300), ('L60m', 3600)
), ent AS (
    SELECT s.mint, s.tier, s.signal_time, l.lag_label,
           MIN_BY(p.cap, p.block_time) AS ecap, MIN(p.block_time) AS etime,
           MIN_BY(p.tx_id, p.block_time) AS etx, MIN(m.pool) AS pool
    FROM sig s
    CROSS JOIN lags l
    JOIN mainpool m ON m.mint = s.mint AND m.h = s.signal_time - INTERVAL '1' HOUR
    JOIN p1v p ON p.mint = s.mint AND p.pool = m.pool
     AND p.block_time >= s.signal_time + l.lag_s * INTERVAL '1' SECOND
     AND p.block_time < s.signal_time + l.lag_s * INTERVAL '1' SECOND + INTERVAL '24' HOUR
    GROUP BY 1, 2, 3, 4
), hz(hz_label, hz_d) AS (
    VALUES ('D1', 1), ('D7', 7), ('D30', 30), ('D90', 90), ('D180', 180)
), hzr AS (
    SELECT p.mint, p.tier, p.signal_time, z.hz_label,
           MAX_BY(p.c, p.h) AS hc, MAX(p.h) AS hh
    FROM path p CROSS JOIN hz z
    WHERE p.h + INTERVAL '1' HOUR <= p.signal_time + z.hz_d * INTERVAL '1' DAY
      AND p.signal_time + z.hz_d * INTERVAL '1' DAY >= TIMESTAMP '2024-08-01 00:00:00'
      AND p.signal_time + z.hz_d * INTERVAL '1' DAY < TIMESTAMP '2024-10-01 00:00:00'
    GROUP BY 1, 2, 3, 4
), summ AS (
    SELECT mint, tier, signal_time, MAX(c) AS maxc, MAX_BY(h, c) AS maxh,
           MAX_BY(c, h) AS lastc, MAX(h) AS lasth, COUNT(*) AS nh
    FROM path GROUP BY 1, 2, 3
)
SELECT 'P' AS rt, mint, tier, signal_time, h AS t, kind AS k, c AS x1, segmax AS x2,
       ncap AS x3, ntime AS t2, ntx AS s1, pool AS s2, n AS i1
FROM prow
UNION ALL
SELECT 'E', mint, tier, signal_time, etime, lag_label, ecap, NULL, NULL, NULL, etx, pool, NULL
FROM ent
UNION ALL
SELECT 'H', mint, tier, signal_time, hh, hz_label, hc, NULL, NULL, NULL, NULL, NULL, NULL
FROM hzr
UNION ALL
SELECT 'S', mint, tier, signal_time, maxh, 'sum', maxc, lastc, NULL, lasth, NULL, NULL, nh
FROM summ
ORDER BY 2, 3, 4, 1, 5
