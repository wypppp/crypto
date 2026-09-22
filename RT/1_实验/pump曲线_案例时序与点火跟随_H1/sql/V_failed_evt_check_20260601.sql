-- V: do Dune decoded Pump/PumpAMM event tables include events from FAILED transactions? (extends F60, n=1)
-- 60 failed txs (B1C2xf..., YxUstM..., 06-01/02) whose logs contain Pump/PumpAMM events per local Helius archives
-- (RT/case_timing/failed_tx_events.csv), plus 10 successful controls from the same mints.
-- Expected if Dune excludes failed txs: failed_with_event -> 0 found; success_control -> 10 found.
-- Scans only evt_tx_id/evt_block_date of three event tables for two day-partitions. Record query/execution ID and cost.
WITH s(sig, kind) AS (VALUES
    ('J36Krr6HFV28B8dn5Kx2tKpkAVCyJ748b41FL4rx3WYP6HUgpWymYRzqFmC4B7Y47RG7LfXGq3LSbfTS4bc1dnW', 'failed_with_event'),
    ('5HqnFwk2ZygHLwBVHjxUq1KkLQPKZ18qvL7MjwgnRJR5owpAjMDupM2cc4q47oJoJGysdZTiK9VJsRrpzSvUTFLh', 'failed_with_event'),
    ('55XUUPCPEwtYfhTBYquzhQXDcq5F771zCsXf71or9X2RgHQRSwaYLrpxMjGhJn1LH7se17ZSimEwbvtbDyDBjXmm', 'failed_with_event'),
    ('2Sc62ZgijtUKUvR5wzneKCxRo2Z6pCYW7W6Y8PgUjajLiatTqLDDGSiGEXY2mSTjrxZ7cyZqqVTJQtp16QuFPSoE', 'failed_with_event'),
    ('4Etgz94U8thYze2AVnpGb1j6Bkg5RoNp5eW592Jgn1uk87sCGySWNNes379YHRuHM5F7w3dYHMKowNMghL3542rD', 'failed_with_event'),
    ('4pbzT9zVL1zEHWdH7uJykVXGTMcFvTf5wMLLRJCWSRkmixdei445YRgYKqmnEjasWncSaNBC1L9DBP8jbQ23H3DF', 'failed_with_event'),
    ('5AcZvE4H7JfmxKx4BLfEHyGMPGFM5Dm8Ay1D58dQQJFZDzj5HTXcDFFQuNZ2d8q9qfumACDfrdEtQPreGhuMwT8X', 'failed_with_event'),
    ('62okrESQfLz4QBuTvHPYDTXkvZQiC8dDwCj3G6H8pUVGu21bHVYqHADLUQ1WwjHGqfqEA2FKTeSCtWNtSX9uh28', 'failed_with_event'),
    ('47iM9qX3t1g18WzYcbMaGNejKN82H6vuP7sBHSHmYqyxtXQ6o5DX8VTDUtc3SMgAF9F3DUaJpykewCH9PCDT58RW', 'failed_with_event'),
    ('BxP5s3WQcB9e4ua4wAjLVQmW1B2r3DiAhxWKxLvbLu5biBBgRgbwAKA6VgZ1chamfQhATGixG31XxusDvn4LbMu', 'failed_with_event'),
    ('cnUqh6roAMhNaHNQtA3rzG7mJZkgPmPfETR15Y1yjNgteDYvof6X9XkA2Kba3dKmpir2mK16wAhVahVpo9PoKNm', 'failed_with_event'),
    ('5USzGmVkXUA7Bhe4ktiQDjtaT4gLuzKu6oyxkqs9aScwqW5gA4nvmdemop9AvcyaYp7ae9c7hqcPYgNMDuTJE7Dd', 'failed_with_event'),
    ('3gL3ZnbKuiZW3KquyKLrK4cqMfKTYmboHo3skC82daUVbCSHBNvkWzysyciKAEPFhNTTsX2zougZodTrQF1UxSdE', 'failed_with_event'),
    ('5bfnGpapiUsHNBmeuAXhM94QmBcwbkmuZDZfpJrCWMB7F6Gk5zwpnEYh8D6oXq1ckc4tJbeJGvGooAAFBx1XMVnm', 'failed_with_event'),
    ('4wxm8N5Aj8cMyp4djSodREQUKBA2WaA8LcC2GW9JxMncG8cdW6wvnWxbadp2yFomhxJEkMEFoKDzhGanv3AXJF9X', 'failed_with_event'),
    ('2SoUayGVV95AJAdgtGd2LcJXXg66nMxvjcxQFwGq7VtNKHQqzrJKWTZiDEL9XWhYhiaY6MfXaBFZeNrzkFcRtn2g', 'failed_with_event'),
    ('3ufknEj8dPpuFy1tJqRCq4iWm6BoH28HaQkopB9hQwL5sXp8W2RsLiYU9aURRfz3dQEPDAjqQ4375sQeTbUMm22j', 'failed_with_event'),
    ('MCyUkkS5yfQfV1MQ9wWZ2FsdAFASKAGgc8TgtHESi3KCEMNW7VN2QghN6HY5iqccBXPtoTRWjQrKhtvnTRcMcuA', 'failed_with_event'),
    ('4njvgXPjy1AAwkjC3fJXpEfCzf34RBBV8KNNfKpYAqfrobc5za6WHWz4WN4iV47yk2N16E52wUGVyEixjHxjzxZi', 'failed_with_event'),
    ('248bW8M4iK4TxUJYDuwfLKhMpL4eCWkNcNNHsYrfgkksJETVAWCEvPSYSY1LvFQoV3kAQgFrL6GsyPMtsNRA3kNP', 'failed_with_event'),
    ('5Dnf6fYdThcB19ew414rJwVcgvhyxg7bQW1ApQUJp6ZoSSpBqi9LXLHqtfn5ak7otRCT9AB4Yq7HXyQv7u6NsEXp', 'failed_with_event'),
    ('3CvuTfEHXvuq3WHEAMgB25Zjbc9MgnP54BqBrNxbgkhvBb7rfX5f2TiAuCrcEAHdTh9ZBNS44BE51g18AqueY3Vy', 'failed_with_event'),
    ('3qsxZTE1fzpMBsFqvoJ2htoJoR6WpjcYNDsvHNnn3XDfQ4monYFykni1E8cBaBSN97YnatZ5SErGD3dzpmgJNphc', 'failed_with_event'),
    ('46hG2fPHaa7vniprUm8F887uDwgn8yBcDXkfsFtLivj5zaQxd8BvQgiW1ufgdjsLDshfDDgBzAWSMQ8mE3V9jYU6', 'failed_with_event'),
    ('45quEbMs99WZ2uecpAHtYABCEi4dRutLAYuLGKSZ8as5TZi79w7PaGBj3fLD45SiHjyZtRwj4TrjM6sLHTUmZmWj', 'failed_with_event'),
    ('355TVHnDXTwvmmVK5NEQMW4roUVnjpm9jgpEAxTTYsruisJHLwv9gcGNYdM1jm7XSkLZ7MdoUZND5BqxxjHSQfVk', 'failed_with_event'),
    ('tub9xzbzrm76Gt6DrkWSEGgETSzLAAi1jiPYKBzuD818k8AXrEuF6Ek9X7pdw38SbmiSzkNGSsSkioPBPmFee6G', 'failed_with_event'),
    ('nRfUEUnYVEjtxZm8L1FamsgzVK112RVnm3Xfct4Wa7rL37a8spdBuNqXuj9f8c3XF4Uo9bcEBGsuy8M4ygP4tvT', 'failed_with_event'),
    ('29WzyUwYEL2Um3ua6AdA1b5VfHHsCETbdvrLg7n4JexaJjSE25yC6fVmzpUNwa4SKRrD1f7Yps29wjWoRTSVHVMm', 'failed_with_event'),
    ('3AbP7pg9JngMPgb48MZRWpA9w5AdYx4V7meQhsHyKFhTU3XFHn6Y1bEuVSPe6TASmtfPUkF7CP8aXwdyGPCRhHEt', 'failed_with_event'),
    ('2JFuqf3Qo73DN7WXFn4FfPsUQbJTepUBoPrxgs3bCxK2pk46o7tqfEmWssrJLYhJ3yGwMbEH1o4YPGby71rAD6dT', 'failed_with_event'),
    ('58xFFbCEqySLJgRubTbSVvuSdb4WFo1rq1fdoqsZKoRTh1brZ1ebufM1X99nYJG3vxTaQdqUDFXMSMqjZgRVnw4w', 'failed_with_event'),
    ('5uy5Sh9ryMBmzNgmfJwnwUHU2F3YvxckvRxkH93zNgRY6qE3Vz4BB9k1qXLcmr1PgUrRg4BN5gapYbiLf13sXNP5', 'failed_with_event'),
    ('4afMgsD3CDUA8TtfhHbAbC5Drvjhou6gKe2VcZqQoEcjqednhV3LHyboygXPkLgyfEgoku3cVLq4D1eTsUpLx7FS', 'failed_with_event'),
    ('4GngiDfqwrfAoLhfpbRqwGTxf9tDTEzkuh2NwtCxXjaq7zdr69KMaVqcN8qzKNMeEfTS7VAme4ZvXvcCvtgzaQio', 'failed_with_event'),
    ('Xcd8HTKbRYUX3KxGZMa9FDYeNZxNFQG4yyecJh5pucegMatXKkBmohEUunAKAELxBndyxABDUdt6qCufeJyt2oc', 'failed_with_event'),
    ('5V9Ho3cpEQBTiYWYxYS9CwFq4k3cQzVzf9Z23oPyddKi1aj4bZBGN9UujpfRJughPs3kbpQBVFqzRP4yYHAovKUV', 'failed_with_event'),
    ('275JkzGFK55yme23r5XZGFjUXXQftur2G6VZ9s6yQSE3ikNpHd918sXtUaT5C3Z5EtofWh6CvD31t2nsTox1z4yZ', 'failed_with_event'),
    ('4dwwLguGPskATLiWtndSjH4dWhyn9o4NXXoaWnhKRPdGg8vnstDHjCFCAKphkMqR8r9Gwty6QJCxipdFHG5P5aAR', 'failed_with_event'),
    ('4Lh5FfhYuwoe77rWDor4z6785kPpDUpjofPPqZThD49VwLrCcmJEDismiGaERPr132hKCVkssDkMCnbinfZADTJK', 'failed_with_event'),
    ('UCfqZ4QinqhGgn7gHaeh7xdbKU4SsFNHL2pVxHknnvdrGeUs586tH5KPWrzviej4KZxu1bHHK2gi8yjaGdgv3Uc', 'failed_with_event'),
    ('k4b9894XpBsx5UcRNzvDifqVwBLmZpvfM2KyFJriTAyATuovRd2oQ3eb6Ppko1nSkx7af7S5MhLtpDRmpcqQnis', 'failed_with_event'),
    ('5bKGHSeJjTffqwGBrPkS5WSncLiQPZAyjGQnHq1VTTgiQpnVMo1tCTx89H5XfaV2Z2q8HmbM1dwCskFCbQxxNkEp', 'failed_with_event'),
    ('4jshoU7GqKZ15yjcDoRojZe4vtpUPSsk8keXmQHSEz4hBPLfMwp32wsDLun2Wg1zQvFhkBNGNEwmLsVMTX5mqMqT', 'failed_with_event'),
    ('3G3ghELuGy1iH9QS8L2gxGcPVg4Au7XKgxtJuyUrh4jbgbFZXRBT7AvKYcAHij5h2Mou7568LbV18qdBygsveHp9', 'failed_with_event'),
    ('4BxdikUqb2nYEaZXahNLDUDFq64hbhXtUMrFHYymntKCeGci598knQditqHDVKXJyD9Q2iBXcZ1mwdWFdF8nKAw3', 'failed_with_event'),
    ('5Zn3LgCTxVAEyRVPyhYU2dfHKT31VnHJr7berqfhz9tFd2EZtaeE1WFifCPPnHQwB71WAxGchDaLWURZ35NScKZQ', 'failed_with_event'),
    ('2VgpWHqAuNM99ViFKmDVNPfnJErYqDQU3zfjTbs1xGBRAU3YWKTtTscVUHP6BPM6EAvZ2kX5KwNHdpYjf3JrnvFn', 'failed_with_event'),
    ('sgG1z9hTcehVsgjniMGjsum4BPLhXzJ1Qtm5PESk7JxzkCXv8DYz9VphR5TMz9rMy9g6kfaviwZQeWMxG1ac3JU', 'failed_with_event'),
    ('5Zp3pnbaSqb646kK1gJRxmWGJoqUFH5bHbWP5zZ7jfoUuMSbAWkMtHKhZiLUQqXWzEKqPEU3qAvrHeTN23n8Mxf7', 'failed_with_event'),
    ('YPEjZEKoRvsDKibpMeKuwaW9sR4abo7y7rX16qkCiQYKFFgeftw5toVPjQYt926tAgaXn1nnSzJ9Qnnz9xPVXvv', 'failed_with_event'),
    ('5Tdhnbo68MCGfPyvWHcJ1FCRpRD9BTEyYwWfKHGogE1kRbfVS35q2yvKYkuPR4jwFbxjX8AyXxMJSSCV3JG8rBNh', 'failed_with_event'),
    ('37cRYBTPscRiyMTHTweo63wJsUjeXwqngkodGAwphbuJth1uimWcCaE9W14NKhTuqS7fQnbMpynCHTqywb8rhdyK', 'failed_with_event'),
    ('ARk8pv89btHCvRdycWDUToM9dYQa89BGLmQoDnkzUGaDcxosnnfVZVYp1AoCfi5TryxCKyPqEyTBV42trMW2acx', 'failed_with_event'),
    ('4Z3FaWmvQ6xcGsJ6i2cqfZeS1cwq9uTEwUG6pvNsuKFyLyJxTvpzjjsDhDas1fWPoqb1h51fL5SvKhdQmGhm4EFC', 'failed_with_event'),
    ('4nAjg3hCFzt17kHTj2tA15L2eEKsfb5ycMmq3z1NcoWk5N2gpNan4UeLsNVFYw7fmYpzTdD31yqMB8phc6vuaLvM', 'failed_with_event'),
    ('5brr3pTa6wq7kUrjNbLaHAFtVEA9pth3erhutJ4ebgZr63yrBZfnZjQD92MBsuhA8QUrQbAekYmFLfKYgRAY8Vuf', 'failed_with_event'),
    ('SyXxvK9kAYRnPAHnsvb5J9R8cY4C7obs2QNoUvioTvZ8jh6Ta4TJn82ox18KoDTWv2fqSJ9RNrpqg4vqiUpMZ72', 'failed_with_event'),
    ('5h2xGBWYEy9WNc85SHbhKxmvCfki5XDnw2bUmUfgeVtBrK2s2Y87p839jDcAgd82qdqHfpTWoxZDzw8Wpn2B3GW7', 'failed_with_event'),
    ('4e4h5cQmYc5GjMZL2QZV1SrAznftv2K45C4a1cqMBw1w9GY7XydEp5nMXJzpQddpajie8YPLTPaYZg8kvefAKZah', 'failed_with_event'),
    ('4EvYAEUD5fpkzb7FirLcwA8AG4JZ2qjC7wAPGBH4mzZrw3K9ErJSeK3w3MhXQzvwyPBDcRPMQSyDeosJtKX3NjXd', 'success_control'),
    ('qzosEn6tmbaRRb1DreK9F4EBCPVqaLsAShexqPb2GALmyYyjnbXfmoFuGH9EZ6dtKGnSPt2mkv3ZVmmeBrfyuJc', 'success_control'),
    ('3Uy2R7bLp7BRbGiuQ72MYABNL8zsWtTrBK7drR2jrJBKcyDGoi4UbNdmj2SnKRVdXS94LvPsdg2uQ7AstTo5PQZT', 'success_control'),
    ('4RhvkyeHZCtCV4iksZavKLippRuDCUpSNP3kEtUSC6SYNWHafcoebBJhqXkJ8nzp9U6tAKaj3fN7hTptgkqDgKwm', 'success_control'),
    ('435Ln1NvyTT9UcosmPXwsF6F8riSYeKAveRGQRWZ4MvExrLjgz3h9KWY6Y51ZTuJ9SsoiTEMyGGEhUUQFXokB3hm', 'success_control'),
    ('5dFX2bXveQYpwTSF5EvaoeBJHTSzBxYiQXY6r8WdKfdc1hVS6BhFR5GZ4548aSbBmaH5CjAs7ZtvB3bSKFNpd3j9', 'success_control'),
    ('3V1yn8afso3fXXybGw56VuEbZmWXYJHqDmAyTZBH1ZtKzaf2Vm1SNpkBBSRTo42eMVoix1ahX2e9NKXi6PufGqcd', 'success_control'),
    ('584BS5hBwt46ThHvCLhBBWNXQGMD9S4ZKB9pbgNPEnZEjJvEzxWBFkaCjLPmtqaGHfEJsN1ji6JNdX2o3vm7z8mK', 'success_control'),
    ('4DxfiXeHWxmtGWYCUpNpSoLHCQiiS3Jdyt61LNdYHgwGx8hCUnMnv7Z1wvy1H7iJg3VK2atF9Xo2GUdxKKbPHyj8', 'success_control'),
    ('tqyWm5gvhkJnyUBHrAj4GNfiWk2Z5mRt5eZRyAhCaSij4i7PBWPqrTi6fa6xhv8CYhgX5X9T9RPYkowJV7QTRgC', 'success_control')
),
ev AS (
    SELECT evt_tx_id AS sig, 'tradeevent' AS tbl FROM pumpdotfun_solana.pump_evt_tradeevent
    WHERE evt_block_date BETWEEN DATE '2026-06-01' AND DATE '2026-06-02' AND evt_tx_id IN (SELECT sig FROM s)
    UNION ALL
    SELECT evt_tx_id, 'buyevent' FROM pumpdotfun_solana.pump_amm_evt_buyevent
    WHERE evt_block_date BETWEEN DATE '2026-06-01' AND DATE '2026-06-02' AND evt_tx_id IN (SELECT sig FROM s)
    UNION ALL
    SELECT evt_tx_id, 'sellevent' FROM pumpdotfun_solana.pump_amm_evt_sellevent
    WHERE evt_block_date BETWEEN DATE '2026-06-01' AND DATE '2026-06-02' AND evt_tx_id IN (SELECT sig FROM s)
)
SELECT s.kind, count(DISTINCT s.sig) AS n_sigs, count(DISTINCT ev.sig) AS n_sigs_found, count(ev.sig) AS n_event_rows
FROM s LEFT JOIN ev ON ev.sig = s.sig
GROUP BY 1
ORDER BY 1
