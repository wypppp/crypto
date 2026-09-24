-- DQ-18 第 2 步 B 段：2025-05..2025-07 完整前史的一块。
-- Cohort: 2025-12. 候选 mint 来自已落盘的 A 段月内首达标结果。
-- 本查询只求历史小时市值最大值；本块最大值 >= 某门槛即证明此前已穿越。
-- 必须把每个候选从创建月到信号月前一月的所有块跑完，才可判历史首次。
-- 一块 SQL 同时核所有候选和四档门槛，dex 月分区只写一次。
-- 单次 Dune 上限 50 credits；预计费用未经实测。不要导出大表。

WITH candidates(cohort_start, mint, created_at) AS (
    VALUES
        (DATE '2025-12-01', '1xdtu7y3LkkrVCAbm5KGKfYzq1qgKhxxk5AaJBqpump', TIMESTAMP '2025-02-26 21:28:10.000'),
        (DATE '2025-12-01', '2Dynh7je6trhm2Sam1SrBxX9vb1gBruczymWujQ5pump', TIMESTAMP '2025-03-21 15:42:44.000'),
        (DATE '2025-12-01', '2HZdRs4Cxkg1WbiPxPZcramcEPo22dzeemMAYZhZpump', TIMESTAMP '2025-02-21 02:09:57.000'),
        (DATE '2025-12-01', '2JcXacFwt9mVAwBQ5nZkYwCyXQkRcdsYrDXn6hj22SbP', TIMESTAMP '2024-04-30 00:57:38.000'),
        (DATE '2025-12-01', '2URzn4j6SYXUQVZ8DqxsrSVPbpNP8xRQPbGBLtm1BV47', TIMESTAMP '2024-11-26 15:15:18.000'),
        (DATE '2025-12-01', '2Yufe8mbyi75Zrye56KYz7CVKoX7oCtDZRksd8tQpump', TIMESTAMP '2024-11-13 08:02:03.000'),
        (DATE '2025-12-01', '2eXamy7t3kvKhfV6aJ6Uwe3eh8cuREFcTKs1mFKZpump', TIMESTAMP '2025-01-23 18:27:17.000'),
        (DATE '2025-12-01', '2fUFhZyd47Mapv9wcfXh5gnQwFXtqcYu9xAN4THBpump', TIMESTAMP '2024-06-07 14:09:05.000'),
        (DATE '2025-12-01', '2hXQn7nJbh2XFTxvtyKb5mKfnScuoiC1Sm8rnWydpump', TIMESTAMP '2025-02-10 16:31:48.000'),
        (DATE '2025-12-01', '2mzhfoHiXGkSqKMtnLUAwfKbeg67wSa26F6UPanvpump', TIMESTAMP '2024-12-02 22:29:29.000'),
        (DATE '2025-12-01', '2nCeHpECQvnMfzjU5fDMAKws1vBxMzxvWr6qqLpApump', TIMESTAMP '2024-11-28 22:08:22.000'),
        (DATE '2025-12-01', '2qEHjDLDLbuBgRYvsxhc5D6uDWAivNFZGan56P1tpump', TIMESTAMP '2024-10-31 14:21:40.000'),
        (DATE '2025-12-01', '2z1p8xCEjRzpBHjXWrx4tJnz7BFL6z7NnvbCxH7bpump', TIMESTAMP '2024-12-28 02:40:53.000'),
        (DATE '2025-12-01', '38PgzpJYu2HkiYvV8qePFakB8tuobPdGm2FFEn7Dpump', TIMESTAMP '2025-04-30 20:24:57.000'),
        (DATE '2025-12-01', '3B5wuUrMEi5yATD7on46hKfej3pfmd7t1RKgrsN3pump', TIMESTAMP '2024-06-17 01:27:58.000'),
        (DATE '2025-12-01', '3DFnwGLJUfxc4eMxDgQwW6oWaeKBrJ1iwA26YjTfpump', TIMESTAMP '2025-01-18 23:40:32.000'),
        (DATE '2025-12-01', '3S8qX1MsMqRbiwKg2cQyx7nis1oHMgaCuc9c4VfvVdPN', TIMESTAMP '2024-05-28 21:00:43.000'),
        (DATE '2025-12-01', '3qq54YqAKG3TcrwNHXFSpMCWoL8gmMuPceJ4FG9npump', TIMESTAMP '2024-10-16 14:55:13.000'),
        (DATE '2025-12-01', '3s4AK2x2nGkKP8ZADbcKuhdPr3coSuh1XnwZEzWgpump', TIMESTAMP '2024-11-19 01:16:07.000'),
        (DATE '2025-12-01', '3yhsQKMeFDo3FN5vxRZnEvvr9cN67aU9qwrMrpURgHVU', TIMESTAMP '2024-09-02 02:36:20.000'),
        (DATE '2025-12-01', '43YakhC3TcSuTgSXnxFgw8uKL8VkuLuFa4M6Bninpump', TIMESTAMP '2025-01-26 23:02:12.000'),
        (DATE '2025-12-01', '48eKhwwadm7LJ57msuDYdq36CXx23Ratdbu74Pa1NULL', TIMESTAMP '2025-04-07 21:14:52.000'),
        (DATE '2025-12-01', '4AkCN6KLeCmUDjWLg4XyQpuZuWtwBdPcbtBQjsA2pump', TIMESTAMP '2025-02-10 22:32:30.000'),
        (DATE '2025-12-01', '4Cnk9EPnW5ixfLZatCPJjDB1PUtcRpVVgTQukm9epump', TIMESTAMP '2024-06-09 20:13:34.000'),
        (DATE '2025-12-01', '4FdojUmXeaFMBG6yUaoufAC5Bz7u9AwnSAMizkx5pump', TIMESTAMP '2025-06-06 03:19:14.000'),
        (DATE '2025-12-01', '4HBQm2EhdpUWZkTYxttxNDnsoWi5beRAGWHpjVo8pump', TIMESTAMP '2025-01-27 00:37:45.000'),
        (DATE '2025-12-01', '4J5HoZWoKcbo2JQxEEVCKRBfUQtEroY1QdRrKtZFpump', TIMESTAMP '2024-10-29 01:49:29.000'),
        (DATE '2025-12-01', '4NBTf8PfLH4oLFnwf3knv46FY9i5oXjDxffCetXRpump', TIMESTAMP '2025-02-18 00:30:33.000'),
        (DATE '2025-12-01', '4TBi66vi32S7J8X1A6eWfaLHYmUXu7CStcEmsJQdpump', TIMESTAMP '2025-03-26 09:45:26.000'),
        (DATE '2025-12-01', '4ULzSrTKnD8jTQuRRTgrDYqNsCoMV2fFEjYkssczpump', TIMESTAMP '2025-05-22 00:49:52.000'),
        (DATE '2025-12-01', '4VagEcTvGM6DSTgQdFQCHQPi6pEJMwGFK5XRwxtvpump', TIMESTAMP '2025-01-19 19:53:25.000'),
        (DATE '2025-12-01', '4ikwYoNvoGEwtMbziUyYBTz1zRM6nmxspsfw9G7Bpump', TIMESTAMP '2025-04-14 23:08:23.000'),
        (DATE '2025-12-01', '5KDo6FVidZQd9WJuqAUSTHotBBXfuDpMuawuY68Lpump', TIMESTAMP '2025-07-14 01:38:13.000'),
        (DATE '2025-12-01', '5PsnNwPmMtsGZgG6ZqMoDJJi28BR5xpAotXHHiQhpump', TIMESTAMP '2024-11-03 20:34:08.000'),
        (DATE '2025-12-01', '5RRV6yHhNFDFYvA3aZnXLx1Hu8BzoLyvgcFceKD6pump', TIMESTAMP '2025-04-09 05:50:49.000'),
        (DATE '2025-12-01', '5SVG3T9CNQsm2kEwzbRq6hASqh1oGfjqTtLXYUibpump', TIMESTAMP '2024-07-11 19:48:29.000'),
        (DATE '2025-12-01', '5TynNxgkJ1AhjbLC4zXGATwJfZqqngSCsZLcrPU5pump', TIMESTAMP '2024-12-02 22:31:36.000'),
        (DATE '2025-12-01', '61V8vBaqAGMpgDQi4JcAwo1dmBGHsyhzodcPqnEVpump', TIMESTAMP '2024-12-10 21:09:11.000'),
        (DATE '2025-12-01', '62CsquahdQ3J286G9UTqV6whxryfihdV4yg7kSJnpump', TIMESTAMP '2024-08-17 23:52:42.000'),
        (DATE '2025-12-01', '66bHtzcXqmLgkn668EG4ETzHL3RLz5ybdckqvrPppump', TIMESTAMP '2025-02-14 07:11:19.000'),
        (DATE '2025-12-01', '69G8CpUVZAxbPMiEBrfCCCH445NwFxH6PzVL693Xpump', TIMESTAMP '2024-10-27 19:52:20.000'),
        (DATE '2025-12-01', '69LjZUUzxj3Cb3Fxeo1X4QpYEQTboApkhXTysPpbpump', TIMESTAMP '2025-04-24 20:14:58.000'),
        (DATE '2025-12-01', '6AJcP7wuLwmRYLBNbi825wgguaPsWzPBEHcHndpRpump', TIMESTAMP '2025-01-23 00:17:11.000'),
        (DATE '2025-12-01', '6MQpbiTC2YcogidTmKqMLK82qvE9z5QEm7EP3AEDpump', TIMESTAMP '2025-05-29 14:24:15.000'),
        (DATE '2025-12-01', '6NcdiK8B5KK2DzKvzvCfqi8EHaEqu48fyEzC8Mm9pump', TIMESTAMP '2025-01-23 00:15:17.000'),
        (DATE '2025-12-01', '6Neft4334Hqi2ak59K3SActWD3jWuhLvXuFHhGTpump', TIMESTAMP '2025-05-27 08:30:17.000'),
        (DATE '2025-12-01', '6d5zHW5B8RkGKd51Lpb9RqFQSqDudr9GJgZ1SgQZpump', TIMESTAMP '2024-10-27 17:26:05.000'),
        (DATE '2025-12-01', '6yjNqPzTSanBWSa6dxVEgTjePXBrZ2FoHLDQwYwEsyM6', TIMESTAMP '2024-05-05 06:18:01.000'),
        (DATE '2025-12-01', '71Jvq4Epe2FCJ7JFSF7jLXdNk1Wy4Bhqd9iL6bEFELvg', TIMESTAMP '2025-06-18 22:48:48.000'),
        (DATE '2025-12-01', '73UdJevxaNKXARgkvPHQGKuv8HCZARszuKW2LTL3pump', TIMESTAMP '2024-11-12 05:50:36.000'),
        (DATE '2025-12-01', '74SBV4zDXxTRgv1pEMoECskKBkZHc2yGPnc7GYVepump', TIMESTAMP '2024-12-17 23:30:38.000'),
        (DATE '2025-12-01', '76EDL5qNcte2ZH29quTaFzagXjWAEY83CATEjyA6pump', TIMESTAMP '2025-04-07 21:13:50.000'),
        (DATE '2025-12-01', '7BMb4jNt2tQG81jX7W22H2h2UyL4SW9QJgz25HRhpump', TIMESTAMP '2024-09-28 12:08:51.000'),
        (DATE '2025-12-01', '7D1iYWfhw2cr9yBZBFE6nZaaSUvXHqG5FizFFEZwpump', TIMESTAMP '2024-12-19 21:53:26.000'),
        (DATE '2025-12-01', '7QZ1tsRGcTa6Jmq5UZZUQqtxwVpma2an5VYjTTCbpump', TIMESTAMP '2024-12-26 15:18:34.000'),
        (DATE '2025-12-01', '7Tx8qTXSakpfaSFjdztPGQ9n2uyT1eUkYz7gYxxopump', TIMESTAMP '2025-05-14 03:29:16.000'),
        (DATE '2025-12-01', '7a8JSTTMnynE689y1AvxHTywdQVFdpfdE61rPvgzpump', TIMESTAMP '2025-03-12 02:30:52.000'),
        (DATE '2025-12-01', '7auPKdQfU25akfQDen4FJjqfcKmoxafBumZVexpRpump', TIMESTAMP '2024-12-14 23:31:49.000'),
        (DATE '2025-12-01', '7d1vpt5eri79nETcL74Punhp3mGkeBgUkMdPWep6pump', TIMESTAMP '2025-01-26 21:32:30.000'),
        (DATE '2025-12-01', '7d5uLATMiAoRC1n9yNc7VCrhx44H6bjEzDx7Gxuhpump', TIMESTAMP '2025-01-19 09:30:59.000'),
        (DATE '2025-12-01', '7gbEP2TAy5wM3TmMp5utCrRvdJ3FFqYjgN5KDpXiWPmo', TIMESTAMP '2024-05-04 23:37:55.000'),
        (DATE '2025-12-01', '7oBYdEhV4GkXC19ZfgAvXpJWp2Rn9pm1Bx2cVNxFpump', TIMESTAMP '2025-02-09 22:27:51.000'),
        (DATE '2025-12-01', '83mCRQJzvKMeQd9wJbZDUCTPgRbZMDoPdMSx5Sf1pump', TIMESTAMP '2025-05-04 05:25:39.000'),
        (DATE '2025-12-01', '89q6aHpZ1fXhuwpnrBgqmCvuAX4GaCrRPQNp5xVHpump', TIMESTAMP '2025-01-11 23:29:34.000'),
        (DATE '2025-12-01', '8BtoThi2ZoXnF7QQK1Wjmh2JuBw9FjVvhnGMVZ2vpump', TIMESTAMP '2024-11-24 07:50:04.000'),
        (DATE '2025-12-01', '8C4RygkxmePm9ys1qCcAB46dUCXNQYTaqfxS5mBrpump', TIMESTAMP '2024-07-30 20:42:59.000'),
        (DATE '2025-12-01', '8Hg96R1AGDe5vKABwniVPT2LHdhZHmCTFijZAXXZpump', TIMESTAMP '2025-01-31 17:39:11.000'),
        (DATE '2025-12-01', '8YiB8B43EwDeSx5Jp91VQjgBU4mfCgVvyNahadtzpump', TIMESTAMP '2024-10-30 19:29:33.000'),
        (DATE '2025-12-01', '8i51XNNpGaKaj4G4nDdmQh95v4FKAxw8mhtaRoKd9tE8', TIMESTAMP '2024-12-02 04:15:10.000'),
        (DATE '2025-12-01', '8ncucXv6U6epZKHPbgaEBcEK399TpHGKCquSt4RnmX4f', TIMESTAMP '2025-04-24 09:10:09.000'),
        (DATE '2025-12-01', '8oosbx7jJrZxm5m4ThKhBpvwwG4QpoAe6i4GiG19pump', TIMESTAMP '2025-04-09 15:51:51.000'),
        (DATE '2025-12-01', '8x5VqbHA8D7NkD52uNuS5nnt3PwA8pLD34ymskeSo2Wn', TIMESTAMP '2024-10-25 05:55:11.000'),
        (DATE '2025-12-01', '92cRC6kV5D7TiHX1j56AbkPbffo9jwcXxSDQZ8Mopump', TIMESTAMP '2024-11-22 21:23:38.000'),
        (DATE '2025-12-01', '984GBL7PhceChtN64NWLdBb49rSQXX7ozpdkEbR1pump', TIMESTAMP '2024-08-15 15:31:49.000'),
        (DATE '2025-12-01', '98mb39tPFKQJ4Bif8iVg9mYb9wsfPZgpgN1sxoVTpump', TIMESTAMP '2025-01-08 08:20:04.000'),
        (DATE '2025-12-01', '9BB6NFEcjBCtnNLFko2FqVQBq8HHM13kCyYcdQbgpump', TIMESTAMP '2024-10-18 06:05:05.000'),
        (DATE '2025-12-01', '9CBP3zCHWXmsuaGDXrpw3heL2NjUvCnRVBke6Uv6pump', TIMESTAMP '2025-02-10 07:09:00.000'),
        (DATE '2025-12-01', '9DHe3pycTuymFk4H4bbPoAJ4hQrr2kaLDF6J6aAKpump', TIMESTAMP '2025-01-03 02:09:57.000'),
        (DATE '2025-12-01', '9HSMssrVecFSs494Zw1QBZL5m3Wjtnic4o1nX6u7pump', TIMESTAMP '2024-06-07 21:29:33.000'),
        (DATE '2025-12-01', '9JhFqCA21MoAXs2PTaeqNQp2XngPn1PgYr2rsEVCpump', TIMESTAMP '2024-10-13 10:55:46.000'),
        (DATE '2025-12-01', '9PR7nCP9DpcUotnDPVLUBUZKu5WAYkwrCUx9wDnSpump', TIMESTAMP '2024-10-25 14:04:17.000'),
        (DATE '2025-12-01', '9RjwNo6hBPkxayWHCqQD1VjaH8igSizEseNZNbddpump', TIMESTAMP '2025-01-25 16:39:56.000'),
        (DATE '2025-12-01', '9UNqoPEXXxEnEphmyYsZYdL5dnmAUtdiKRUchpnUF5Ph', TIMESTAMP '2024-06-08 21:59:56.000'),
        (DATE '2025-12-01', '9XWUzTYsRdyWdcQsJ7qibwgaJSNAm8aMKLLe2zbapump', TIMESTAMP '2024-12-03 04:26:18.000'),
        (DATE '2025-12-01', '9ZFfZwZDfoSqj7HFD7BNGy57XVNkd1BR2UrNYKsnpump', TIMESTAMP '2025-06-03 09:50:08.000'),
        (DATE '2025-12-01', '9daJ5eq5sbC5s99cey4Uo33mCjzKcVQJhY2mL7cPpump', TIMESTAMP '2024-12-07 20:53:37.000'),
        (DATE '2025-12-01', '9doRRAik5gvhbEwjbZDbZR6GxXSAfdoomyJR57xKpump', TIMESTAMP '2024-12-20 05:40:03.000'),
        (DATE '2025-12-01', '9gyfbPVwwZx4y1hotNSLcqXCQNpNqqz6ZRvo8yTLpump', TIMESTAMP '2025-03-12 02:19:09.000'),
        (DATE '2025-12-01', '9qriMjPPAJTMCtfQnz7Mo9BsV2jAWTr2ff7yc3JWpump', TIMESTAMP '2024-10-18 17:38:42.000'),
        (DATE '2025-12-01', '9raUVuzeWUk53co63M4WXLWPWE4Xc6Lpn7RS9dnkpump', TIMESTAMP '2024-09-27 14:18:41.000'),
        (DATE '2025-12-01', '9vBFh7Qzv4469GKXWxiw1JGVkkDnNLyJrzRx8ejJpump', TIMESTAMP '2025-06-14 14:58:15.000'),
        (DATE '2025-12-01', '9x5CLPb3SeYSBKvautqpJWPjX9TUCVcWTS12Xawapump', TIMESTAMP '2024-12-28 14:43:27.000'),
        (DATE '2025-12-01', 'A8C3xuqscfmyLrte3VmTqrAq8kgMASius9AFNANwpump', TIMESTAMP '2024-07-30 01:22:14.000'),
        (DATE '2025-12-01', 'A8YHuvQBMAxXoZAZE72FyC8B7jKHo8RJyByXRRffpump', TIMESTAMP '2025-05-15 23:44:07.000'),
        (DATE '2025-12-01', 'AUuCEHQ7sm2i5GmaHrpE961voWcTY8U6mgrkhcV7pump', TIMESTAMP '2025-02-24 19:02:58.000'),
        (DATE '2025-12-01', 'AY1Ww6MxwC3cCiyrandHqLrp4FXvzgcwQTZpJ2FEpump', TIMESTAMP '2025-05-19 22:59:05.000'),
        (DATE '2025-12-01', 'Ac3JwtAfpAMorNPiWn48ZF6KThhMHeLiJaUf3rhVmNVp', TIMESTAMP '2025-07-17 18:45:54.000'),
        (DATE '2025-12-01', 'AhBh6hkFjL8iYGSXhi6zhHkdDE6NVtnQ3y6q8euspump', TIMESTAMP '2025-07-05 20:00:44.000'),
        (DATE '2025-12-01', 'Ai4CL1SAxVRigxQFwBH8S2JkuL7EqrdiGwTC7JpCpump', TIMESTAMP '2024-12-05 23:47:43.000'),
        (DATE '2025-12-01', 'AjgSvYmJLhvt3FteiyTqQf8XBj1SVs6T6AmSUfkHpump', TIMESTAMP '2025-05-18 21:53:25.000'),
        (DATE '2025-12-01', 'ArUyEVWGCzZMtAxcPmNH8nDFZ4kMjxrMbpsQf3NEpump', TIMESTAMP '2025-02-18 14:00:04.000'),
        (DATE '2025-12-01', 'AxriehR6Xw3adzHopnvMn7GcpRFcD41ddpiTWMg6pump', TIMESTAMP '2025-02-07 21:35:55.000'),
        (DATE '2025-12-01', 'AyrQpt5xsVYiN4BqgZdd2tZJAWswT9yLUZmP1jKqpump', TIMESTAMP '2025-04-14 21:43:58.000'),
        (DATE '2025-12-01', 'B1oEzGes1QxVZoxR3abiwAyL4jcPRF2s2ok5Yerrpump', TIMESTAMP '2025-06-17 16:50:47.000'),
        (DATE '2025-12-01', 'BBnXP9MYW7JXqWyChgLvFNy28q1jCqvVRaYyGUwCpump', TIMESTAMP '2025-01-20 01:02:28.000'),
        (DATE '2025-12-01', 'BKphf9EBtyhGUDqUvdQUBE2KqmLfgdZxHS3bCbyFpump', TIMESTAMP '2025-07-05 13:08:34.000'),
        (DATE '2025-12-01', 'BQQzEvYT4knThhkSPBvSKBLg1LEczisWLhx5ydJipump', TIMESTAMP '2025-03-28 03:06:48.000'),
        (DATE '2025-12-01', 'BQX1cjcRHXmrqNtoFWwmE5bZj7RPneTmqXB979b2pump', TIMESTAMP '2025-03-02 16:36:33.000'),
        (DATE '2025-12-01', 'BTr5SwWSKPBrdUzboi2SVr1QvSjmh1caCYUkxsxLpump', TIMESTAMP '2025-02-09 14:34:20.000'),
        (DATE '2025-12-01', 'BUUB7DpQT1mcTrs55oXawgEbxm5khAozsbmyhMdRpump', TIMESTAMP '2025-03-20 13:37:05.000'),
        (DATE '2025-12-01', 'BbbwE8rudhjK4husSRc37X54mYyDBRcykJ7fk5oHpump', TIMESTAMP '2025-06-11 23:37:10.000'),
        (DATE '2025-12-01', 'Bhu2wBWxfWkRJ6pFn5NodnEvMCqj9DLfCU5qMvt7pump', TIMESTAMP '2025-01-13 03:13:43.000'),
        (DATE '2025-12-01', 'Bj26Rs4W5H6DPxpvLPfZxF2ZVCCos8J93ikPe8ERpump', TIMESTAMP '2025-02-16 12:07:47.000'),
        (DATE '2025-12-01', 'BjjvKX5k7gQoGRmvQAA5WMr7EkQ2cirGTSGxAznDpump', TIMESTAMP '2024-10-29 03:27:30.000'),
        (DATE '2025-12-01', 'BkYAUVMar1gLwuFLv2n5cmB6HhcNtvd86kU3gqAypump', TIMESTAMP '2024-12-20 16:05:11.000'),
        (DATE '2025-12-01', 'BreuhVohXX5fv6q41uyb3sojtAuGoGaiAhKBMtcrpump', TIMESTAMP '2024-06-28 20:15:39.000'),
        (DATE '2025-12-01', 'C3DwDjT17gDvvCYC2nsdGHxDHVmQRdhKfpAdqQ29pump', TIMESTAMP '2025-03-24 22:34:36.000'),
        (DATE '2025-12-01', 'C4j7kPx9PqDnfvxe2uycJQRTAeyGwmU4DyGf21Xgpump', TIMESTAMP '2024-10-17 22:19:50.000'),
        (DATE '2025-12-01', 'C7heQqfNzdMbUFQwcHkL9FvdwsFsDRBnfwZDDyWYCLTZ', TIMESTAMP '2025-01-30 20:17:40.000'),
        (DATE '2025-12-01', 'CB9dDufT3ZuQXqqSfa1c5kY935TEreyBw9XJXxHKpump', TIMESTAMP '2025-05-18 22:14:09.000'),
        (DATE '2025-12-01', 'CBdCxKo9QavR9hfShgpEBG3zekorAeD7W1jfq2o3pump', TIMESTAMP '2024-10-28 16:13:09.000'),
        (DATE '2025-12-01', 'CJD1adkwHSWauapWdU46MmQR2GSJshGM2ayCycs1pump', TIMESTAMP '2025-07-15 23:48:07.000'),
        (DATE '2025-12-01', 'CN162nCPpq3DxPCyKLbAvEJeB1aCxsnVTEG4ZU8vpump', TIMESTAMP '2025-01-28 15:22:17.000'),
        (DATE '2025-12-01', 'CNvitvFnSM5ed6K28RUNSaAjqqz5tX1rA5HgaBN9pump', TIMESTAMP '2024-10-31 21:44:35.000'),
        (DATE '2025-12-01', 'CRAMvzDsSpXYsFpcoDr6vFLJMBeftez1E7277xwPpump', TIMESTAMP '2024-11-27 02:19:31.000'),
        (DATE '2025-12-01', 'CTg3ZgYx79zrE1MteDVkmkcGniiFrK1hJ6yiabropump', TIMESTAMP '2024-07-27 19:55:25.000'),
        (DATE '2025-12-01', 'CboMcTUYUcy9E6B3yGdFn6aEsGUnYV6yWeoeukw6pump', TIMESTAMP '2024-12-28 00:09:07.000'),
        (DATE '2025-12-01', 'CdGRXAgJ8HLD2F7GiyZ1UagrGbg24Hqe7GfXf7B2pump', TIMESTAMP '2025-01-07 08:48:33.000'),
        (DATE '2025-12-01', 'Ce2gx9KGXJ6C9Mp5b5x1sn9Mg87JwEbrQby4Zqo3pump', TIMESTAMP '2025-04-27 00:31:59.000'),
        (DATE '2025-12-01', 'CnGb7hJsGdsFyQP2uXNWrUgT5K1tovBA3mNnUZcTpump', TIMESTAMP '2024-12-22 19:59:50.000'),
        (DATE '2025-12-01', 'CniPCE4b3s8gSUPhUiyMjXnytrEqUrMfSsnbBjLCpump', TIMESTAMP '2025-03-02 21:00:46.000'),
        (DATE '2025-12-01', 'Cq16t8jRSxtQDcPyANothLYemBDkN6SVKjqSDZ99pump', TIMESTAMP '2024-08-26 01:50:55.000'),
        (DATE '2025-12-01', 'CreiuhfwdWCN5mJbMJtA9bBpYQrQF2tCBuZwSPWfpump', TIMESTAMP '2024-12-26 14:00:25.000'),
        (DATE '2025-12-01', 'Cy1GS2FqefgaMbi45UunrUzin1rfEmTUYnomddzBpump', TIMESTAMP '2025-01-13 18:02:37.000'),
        (DATE '2025-12-01', 'Cz7LGKdZPpAxonXx23ZYPW3RtDQvjcf17ZDCZEzFpump', TIMESTAMP '2025-06-23 22:07:31.000'),
        (DATE '2025-12-01', 'CzLSujWBLFsSjncfkh59rUFqvafWcY5tzedWJSuypump', TIMESTAMP '2024-10-10 21:08:26.000'),
        (DATE '2025-12-01', 'DKu9kykSfbN5LBfFXtNNDPaX35o4Fv6vJ9FKk7pZpump', TIMESTAMP '2024-11-13 18:41:36.000'),
        (DATE '2025-12-01', 'DQnkBM4eYYMnVE8Qy2K3BB7uts1fh2EwBVktEz6jpump', TIMESTAMP '2025-06-06 14:10:31.000'),
        (DATE '2025-12-01', 'DVrgc51Y5Wxb9oF63y9m5rwXhua8r2c4MYzUsHXhpump', TIMESTAMP '2025-06-13 12:22:27.000'),
        (DATE '2025-12-01', 'DYCLLejhtfyCDUY8ygBx7YuwfcdaRzLo7nHHVGdApump', TIMESTAMP '2025-04-14 08:26:24.000'),
        (DATE '2025-12-01', 'Df6yfrKC8kZE3KNkrHERKzAetSxbrWeniQfyJY4Jpump', TIMESTAMP '2024-10-06 00:31:12.000'),
        (DATE '2025-12-01', 'Dfh5DzRgSvvCFDoYc2ciTkMrbDfRKybA4SoFbPmApump', TIMESTAMP '2024-11-09 20:15:49.000'),
        (DATE '2025-12-01', 'DitHyRMQiSDhn5cnKMJV2CDDt6sVct96YrECiM49pump', TIMESTAMP '2025-03-24 16:44:42.000'),
        (DATE '2025-12-01', 'DtR4D9FtVoTX2569gaL837ZgrB6wNjj6tkmnX9Rdk9B2', TIMESTAMP '2024-05-30 19:54:07.000'),
        (DATE '2025-12-01', 'Dv4FD3WksCDjF8W5r2wU5onnPQzRgpb2hJ3gpQx4pump', TIMESTAMP '2024-08-13 19:20:54.000'),
        (DATE '2025-12-01', 'DyarzvpJ4zMqAiKEr5YbPLMg4D4XMgBwgcTFGDMnpump', TIMESTAMP '2024-09-11 00:44:31.000'),
        (DATE '2025-12-01', 'E2FFz8scZKeaEiobiqTbkdtde1pbBbRbZLeMDnx9pump', TIMESTAMP '2025-07-16 21:15:44.000'),
        (DATE '2025-12-01', 'ED5nyyWEzpPPiWimP8vYm7sD7TD3LAt3Q3gRTWHzPJBY', TIMESTAMP '2024-09-10 17:25:27.000'),
        (DATE '2025-12-01', 'EHmZM5QD7NFpu6hm3o8yYSA6EhYYunHL21fzN2ucpump', TIMESTAMP '2025-01-25 21:50:32.000'),
        (DATE '2025-12-01', 'EdhTCqUxXRWQcUd5Fonyz9rapHAB6mABAuVkmPrtpump', TIMESTAMP '2024-09-17 03:14:02.000'),
        (DATE '2025-12-01', 'EebvSxfGbjyHMJ2bu1jhtNidbhVbQJtcg9y561Kipump', TIMESTAMP '2025-07-08 23:58:06.000'),
        (DATE '2025-12-01', 'EfgEGG9PxLhyk1wqtqgGnwgfVC7JYic3vC9BCWLvpump', TIMESTAMP '2025-02-01 04:32:55.000'),
        (DATE '2025-12-01', 'EiRfZeWLW1NymAfjKUePz3jwtq5rZ69XM3zLDS1Npump', TIMESTAMP '2024-11-07 14:08:11.000'),
        (DATE '2025-12-01', 'EsP4kJfKUDLfX274WoBSiiEy74Sh4tZKUCDjfULHpump', TIMESTAMP '2024-11-25 06:41:43.000'),
        (DATE '2025-12-01', 'F7BW1wJsDHrHUkNPcoYkgYcKD1o2DsUooML9kjajpump', TIMESTAMP '2025-01-11 09:48:51.000'),
        (DATE '2025-12-01', 'FK9nD3fv3zhDm5JpaKhVXz6F1MBRwESRdBoCJwQNpump', TIMESTAMP '2025-05-24 03:48:59.000'),
        (DATE '2025-12-01', 'FKNfAwb8TmjYkj11V4NiTz4TgrLWTWgm2NRwAD9epump', TIMESTAMP '2025-04-10 14:19:41.000'),
        (DATE '2025-12-01', 'FWAr6oWa6CHg6WUcXu8CqkmsdbhtEqL8t31QTonppump', TIMESTAMP '2025-03-13 04:11:06.000'),
        (DATE '2025-12-01', 'FWxN8Rp1XxKcn5jQLbZAGMpW4n61ssPR4R98JtpUpump', TIMESTAMP '2024-08-01 00:05:46.000'),
        (DATE '2025-12-01', 'FXJAdx38aXJdQd3ABAVu7fQ7Bjh9oMN92eTxszFNpump', TIMESTAMP '2024-08-15 09:36:37.000'),
        (DATE '2025-12-01', 'Fd8TNp5GhhTk6Uq6utMvK13vfQdLN1yUUHCnapWvpump', TIMESTAMP '2025-07-02 14:04:30.000'),
        (DATE '2025-12-01', 'FeR8VBqNRSUD5NtXAj2n3j1dAHkZHfyDktKuLXD4pump', TIMESTAMP '2025-01-29 23:29:10.000'),
        (DATE '2025-12-01', 'Fhk3qjyq8tSJ3xouig6rMXBaSptfGC1m3rmxU6aApump', TIMESTAMP '2024-07-04 00:41:18.000'),
        (DATE '2025-12-01', 'FtUEW73K6vEYHfbkfpdBZfWpxgQar2HipGdbutEhpump', TIMESTAMP '2025-03-06 16:55:02.000'),
        (DATE '2025-12-01', 'GCVrbnhVGfXD36asyfTAxK9o7R3ACUwiQJcTktCppump', TIMESTAMP '2025-01-20 12:29:42.000'),
        (DATE '2025-12-01', 'GEuuznWpn6iuQAJxLKQDVGXPtrqXHNWTk3gZqqvJpump', TIMESTAMP '2025-02-15 02:21:13.000'),
        (DATE '2025-12-01', 'GHichsGq8aPnqJyz6Jp1ASTK4PNLpB5KrD6XrfDjpump', TIMESTAMP '2024-11-24 11:55:25.000'),
        (DATE '2025-12-01', 'GJAFwWjJ3vnTsrQVabjBVK2TYB1YtRCQXRDfDgUnpump', TIMESTAMP '2024-10-19 11:27:09.000'),
        (DATE '2025-12-01', 'GMTXVdP5Uc9Eqn8MJYhC8Tg18T1unAWaN1Qf4BuES5Cb', TIMESTAMP '2024-05-17 15:47:40.000'),
        (DATE '2025-12-01', 'GMzuntWYJLpNuCizrSR7ZXggiMdDzTNiEmSNHHunpump', TIMESTAMP '2025-01-19 14:23:37.000'),
        (DATE '2025-12-01', 'GiG7Hr61RVm4CSUxJmgiCoySFQtdiwxtqf64MsRppump', TIMESTAMP '2024-07-20 23:35:19.000'),
        (DATE '2025-12-01', 'GkyPYa7NnCFbduLknCfBfP7p8564X1VZhwZYJ6CZpump', TIMESTAMP '2025-04-25 21:50:55.000'),
        (DATE '2025-12-01', 'GnM6XZ7DN9KSPW2ZVMNqCggsxjnxHMGb2t4kiWrUpump', TIMESTAMP '2025-04-28 15:37:22.000'),
        (DATE '2025-12-01', 'GqXX9MfkURBZ5cFym9HDzqTL7uZkjtCSqLkUSe2xpump', TIMESTAMP '2025-07-16 14:21:46.000'),
        (DATE '2025-12-01', 'Gu3LDkn7Vx3bmCzLafYNKcDxv2mH7YN44NJZFXnypump', TIMESTAMP '2024-10-21 02:35:12.000'),
        (DATE '2025-12-01', 'H2c31USxu35MDkBrGph8pUDUnmzo2e4Rf4hnvL2Upump', TIMESTAMP '2024-10-16 14:08:28.000'),
        (DATE '2025-12-01', 'H8xQ6poBjB9DTPMDTKWzWPrnxu4bDEhybxiouF8Ppump', TIMESTAMP '2025-06-06 22:03:21.000'),
        (DATE '2025-12-01', 'HFezjcQMm3Q9tR2RVyPa6n2ovDZ35Wfe3AbjN6Phpump', TIMESTAMP '2025-07-16 22:33:46.000'),
        (DATE '2025-12-01', 'HNg5PYJmtqcmzXrv6S9zP1CDKk5BgDuyFBxbvNApump', TIMESTAMP '2024-11-27 17:53:26.000'),
        (DATE '2025-12-01', 'HZNnmhAY6xfq2iKRyBTEvTVeoTYJzpkK8mfnfG8Ppump', TIMESTAMP '2024-08-14 12:02:38.000'),
        (DATE '2025-12-01', 'HgBRWfYxEfvPhtqkaeymCQtHCrKE46qQ43pKe8HCpump', TIMESTAMP '2024-09-30 22:36:40.000'),
        (DATE '2025-12-01', 'Hjw6bEcHtbHGpQr8onG3izfJY5DJiWdt7uk2BfdSpump', TIMESTAMP '2024-12-20 19:07:46.000'),
        (DATE '2025-12-01', 'HwKE9CPg9Z9WzAeQSj6jeLBizK7LJs5m6LTVx6pLpump', TIMESTAMP '2024-11-23 15:15:43.000'),
        (DATE '2025-12-01', 'HyDKNdnhZNVYQMruBevbNsUWruA9STmAQrS4srXApump', TIMESTAMP '2024-12-10 09:13:56.000'),
        (DATE '2025-12-01', 'J1Wpmugrooj1yMyQKrdZ2vwRXG5rhfx3vTnYE39gpump', TIMESTAMP '2024-07-23 19:54:22.000'),
        (DATE '2025-12-01', 'J1wsY5rqFesHmQojnzBNs4Bhk5vEtCb9GU5xv7A7pump', TIMESTAMP '2025-05-29 08:59:34.000'),
        (DATE '2025-12-01', 'JB2wezZLdzWfnaCfHxLg193RS3Rh51ThiXxEDWQDpump', TIMESTAMP '2024-10-03 07:05:20.000'),
        (DATE '2025-12-01', 'KENJSUYLASHUMfHyy5o4Hp2FdNqZg1AsUPhfH2kYvEP', TIMESTAMP '2024-11-02 23:37:45.000'),
        (DATE '2025-12-01', 'Pj3sX83x2gsxwwfzhUuszdA8EWcJvkJ4g3k3LCfpump', TIMESTAMP '2024-11-04 19:41:50.000'),
        (DATE '2025-12-01', 'VaxZxmFXV8tmsd72hUn22ex6GFzZ5uq9DVJ5wA5pump', TIMESTAMP '2024-09-30 22:29:39.000'),
        (DATE '2025-12-01', 'bZqP1p2mUd9ftH6AFBmoyQqsAFcG5mddMMh3Y8mpump', TIMESTAMP '2025-01-31 12:39:53.000'),
        (DATE '2025-12-01', 'ch7rTovcUK7C1zNFM7F93kXU2CByYUsJT4pwYx7pump', TIMESTAMP '2025-02-12 21:26:19.000'),
        (DATE '2025-12-01', 'dTzEP9JU2NRDPuWtM32gaVKip2fTHBqjheU1APBpump', TIMESTAMP '2025-07-14 17:25:34.000'),
        (DATE '2025-12-01', 'eL5fUxj2J4CiQsmW85k5FG9DvuQjjUoBHoQBi2Kpump', TIMESTAMP '2024-12-17 01:41:55.000'),
        (DATE '2025-12-01', 'kAPrttEmNLdevPHeV8schaZpTDP1YtgoK3FZ8gApump', TIMESTAMP '2024-12-13 06:24:26.000'),
        (DATE '2025-12-01', 'tGSHqcbojd4uSmirz9iXHvuRBBFwbHaDjSatbuupump', TIMESTAMP '2024-12-24 01:41:10.000'),
        (DATE '2025-12-01', 'tWKHzXd5PRmxTF5cMfJkm2Ua3TcjwNNoSRUqx6Apump', TIMESTAMP '2025-01-24 19:37:05.000'),
        (DATE '2025-12-01', 'vRseBFqTy9QLmmo5qGiwo74AVpdqqMTnxPqWoWMpump', TIMESTAMP '2025-06-09 18:24:08.000'),
        (DATE '2025-12-01', 'zGh48JtNHVBb5evgoZLXwgPD2Qu4MhkWdJLGDAupump', TIMESTAMP '2024-10-13 23:53:56.000')
), sol_minute AS (
    SELECT minute, AVG(price) AS sol_usd
    FROM prices.usd
    WHERE blockchain = 'solana' AND symbol = 'SOL'
      AND minute >= TIMESTAMP '2025-05-01 00:00:00'
      AND minute < TIMESTAMP '2025-08-01 00:00:00'
    GROUP BY minute
), historical_trades AS (
    SELECT block_time, token_bought_mint_address, token_sold_mint_address,
           token_bought_amount, token_sold_amount
    FROM dex_solana.trades
    WHERE block_month >= DATE '2025-05-01'
      AND block_month < DATE '2025-08-01'
      AND block_time >= TIMESTAMP '2025-05-01 00:00:00'
      AND block_time < TIMESTAMP '2025-08-01 00:00:00'
      AND token_bought_mint_address <> token_sold_mint_address
), candidate_legs AS (
    SELECT c.cohort_start, c.mint, t.block_time,
           IF(t.token_bought_mint_address = c.mint,
              t.token_sold_mint_address, t.token_bought_mint_address) AS quote_mint,
           IF(t.token_bought_mint_address = c.mint,
              t.token_bought_amount, t.token_sold_amount) AS token_amount,
           IF(t.token_bought_mint_address = c.mint,
              t.token_sold_amount, t.token_bought_amount) AS quote_amount
    FROM historical_trades t
    CROSS JOIN UNNEST(ARRAY[t.token_bought_mint_address,
                            t.token_sold_mint_address]) AS leg(mint)
    JOIN candidates c ON c.mint = leg.mint
    WHERE t.block_time >= c.created_at
      AND t.block_time < CAST(c.cohort_start AS timestamp)
), valued AS (
    SELECT l.*,
           CASE
             WHEN l.quote_mint = 'So11111111111111111111111111111111111111112'
                  THEN l.quote_amount * s.sol_usd
             WHEN l.quote_mint IN (
                 'EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v',
                 'Es9vMFrzaCERmJfrF4H2FYD4KCoNkY11McCe8BenwNYB'
             ) THEN l.quote_amount
             ELSE NULL
           END AS quote_usd
    FROM candidate_legs l
    LEFT JOIN sol_minute s
      ON l.quote_mint = 'So11111111111111111111111111111111111111112'
     AND s.minute = date_trunc('minute', l.block_time)
), hourly AS (
    SELECT cohort_start, mint, date_trunc('hour', block_time) AS hour_start,
           COUNT(*) AS n_all_trades,
           COUNT_IF(token_amount > 0 AND quote_usd > 0) AS n_price_trades,
           SUM(IF(token_amount > 0 AND quote_usd > 0, token_amount, 0))
               AS valid_token_volume,
           SUM(IF(token_amount > 0 AND quote_usd > 0, quote_usd, 0))
               AS valid_usd_volume
    FROM valued
    GROUP BY cohort_start, mint, date_trunc('hour', block_time)
), by_mint AS (
    SELECT cohort_start, mint,
           MAX(1000000000.0 * valid_usd_volume /
               NULLIF(valid_token_volume, 0)) AS prior_max_marketcap_usd,
           COUNT_IF(valid_token_volume > 0) AS n_priced_hours,
           SUM(n_all_trades) AS n_all_trades,
           SUM(n_price_trades) AS n_price_trades
    FROM hourly
    GROUP BY cohort_start, mint
)
SELECT c.cohort_start, c.mint, c.created_at,
       b.prior_max_marketcap_usd,
       COALESCE(b.n_priced_hours, 0) AS n_priced_hours,
       COALESCE(b.n_all_trades, 0) AS n_all_trades,
       COALESCE(b.n_price_trades, 0) AS n_price_trades
FROM candidates c
LEFT JOIN by_mint b ON b.cohort_start = c.cohort_start AND b.mint = c.mint
ORDER BY c.cohort_start, c.mint
