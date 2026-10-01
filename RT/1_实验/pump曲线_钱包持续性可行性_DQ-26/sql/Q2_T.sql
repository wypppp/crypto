/* DQ-26 Q2 外部跟随（卡片_Q2_执行_v1.md）；由 sql/build_q2_sql.py 生成（T）。
   币：2026-08-17～2026-08-30 创建的 SOL 计价 pump 币；成交（曲线＋PumpSwap）截至 2026-09-06 24:00 UTC；只读 2026-08-17～2026-09-06 的分区。
   触发＝冻结的 146 个钱包（前 50 实体）的首次买入；延迟 2/5/15/30 秒；跟随退出与 2 秒 b50；估值同 S1 s9/s10（口径 A/B）。 */
WITH
sel(usr, entity) AS (
    SELECT usr, entity FROM (VALUES
        ('135DN9oH9vU4CLbKiC1Rj4vByAsyRstAdjrwngYLHz86', '135DN9oH9vU4CLbKiC1Rj4vByAsyRstAdjrwngYLHz86'),
        ('236jX1xJfX7vP9KuXy3uiuE4Y77wr4mmMue5i85eiGaZ', '135DN9oH9vU4CLbKiC1Rj4vByAsyRstAdjrwngYLHz86'),
        ('27VSifqHkBVNCGsVVbda64onBZmRhGpB2Zg4pZwf3jZs', '27VSifqHkBVNCGsVVbda64onBZmRhGpB2Zg4pZwf3jZs'),
        ('2HMdJbv9bUQUL5zZCBG35kkUwYrfzvH5r5vkaVqAanmj', '2HMdJbv9bUQUL5zZCBG35kkUwYrfzvH5r5vkaVqAanmj'),
        ('2NwJxx3ZY3HPAe51zgcPAvMehrhKA9qvL1zcRwZPkfL3', '2NwJxx3ZY3HPAe51zgcPAvMehrhKA9qvL1zcRwZPkfL3'),
        ('2UmkmsL7myuAX6NbYU2UyDiKR5g4w7qcJCGaNKsZnvcy', '2UmkmsL7myuAX6NbYU2UyDiKR5g4w7qcJCGaNKsZnvcy'),
        ('2X6rVA7KuqEdmftbzyoCVRSWnSbqdtdeSzUS8BnUhfFy', '2X6rVA7KuqEdmftbzyoCVRSWnSbqdtdeSzUS8BnUhfFy'),
        ('2ZVMUZteEmL6NQ1oDimiWFWTrUALp2G325X4EDFFRkXV', '2ZVMUZteEmL6NQ1oDimiWFWTrUALp2G325X4EDFFRkXV'),
        ('2aBqiwtWi3oxJ9DFLytGieRTu4YaxpuCUrkQmpC7Tyus', '2aBqiwtWi3oxJ9DFLytGieRTu4YaxpuCUrkQmpC7Tyus'),
        ('2u2tU5RgCBdphiRFpMWYtYBtnmvz2aG7QJ93U4C8NfdD', '2u2tU5RgCBdphiRFpMWYtYBtnmvz2aG7QJ93U4C8NfdD'),
        ('31HPt5v1zLzBM9CvfnHj467e1q7bvieJk8845kP6M8HF', '31HPt5v1zLzBM9CvfnHj467e1q7bvieJk8845kP6M8HF'),
        ('32XV2kVEEeTDThf4Q6CT6s1Rj9oCXP49ftPHdy9kJrP1', '32XV2kVEEeTDThf4Q6CT6s1Rj9oCXP49ftPHdy9kJrP1'),
        ('344cpTXRKLraLapQ1FCPJErPuieCab8ucxncehU7zqD3', '2HMdJbv9bUQUL5zZCBG35kkUwYrfzvH5r5vkaVqAanmj'),
        ('35dqGKaadurAZegL6Kn3SHRBfAh6mHU7x5W4P2DYdovT', '135DN9oH9vU4CLbKiC1Rj4vByAsyRstAdjrwngYLHz86'),
        ('38Fgtgr65fZD1dyTGZ8eHMNoJiP9ArHQXKLAnQxF4PuC', '38Fgtgr65fZD1dyTGZ8eHMNoJiP9ArHQXKLAnQxF4PuC'),
        ('3ALf59Yc96VJFHGT599DXvi6gNKh2kQwcG4f7PnDH2k4', '135DN9oH9vU4CLbKiC1Rj4vByAsyRstAdjrwngYLHz86'),
        ('3MGGxpGBQDRtjtNpZhk3NQGrmrJRnGTgVzfrNyZuhgxN', '3MGGxpGBQDRtjtNpZhk3NQGrmrJRnGTgVzfrNyZuhgxN'),
        ('3bbDEL917JkpMSCBTf43azASbkttCYNYaNoQpzPLPV8X', '3bbDEL917JkpMSCBTf43azASbkttCYNYaNoQpzPLPV8X'),
        ('3eVEdULqvgtS12hTXeHeBECPyKMwCygo3s4Lc9MVSyYy', '27VSifqHkBVNCGsVVbda64onBZmRhGpB2Zg4pZwf3jZs'),
        ('3neM8FZ2nJK1P3MuaQEDQKF5Vs9tXe85dJjbZpyuTuJy', '3neM8FZ2nJK1P3MuaQEDQKF5Vs9tXe85dJjbZpyuTuJy'),
        ('3p3pFJqJK2A8wFfYtfSEiemFe9KzaPA1G9GkZdMCx8u7', '38Fgtgr65fZD1dyTGZ8eHMNoJiP9ArHQXKLAnQxF4PuC'),
        ('3wB1dT7Bc9as5oceJHVAQ2fS6GR6J8WmJBgH3671vSUE', '3wB1dT7Bc9as5oceJHVAQ2fS6GR6J8WmJBgH3671vSUE'),
        ('3wEvLZkv9HScezTauYVPvAgYHat3PJziA6CHUrNBKknj', '3wEvLZkv9HScezTauYVPvAgYHat3PJziA6CHUrNBKknj'),
        ('3yhbf9PB63KEiC21oUapjGYtB5ibxuk27uFd44G946n7', '3bbDEL917JkpMSCBTf43azASbkttCYNYaNoQpzPLPV8X'),
        ('42XQtUAskX2ynmDDRUbBnrw6zNvXXeCyotdxEqyV2ZTj', '31HPt5v1zLzBM9CvfnHj467e1q7bvieJk8845kP6M8HF'),
        ('4bmKm96NWgewGShedE85TS9TjYYDVYjAEbFL5hK3Kh4s', '135DN9oH9vU4CLbKiC1Rj4vByAsyRstAdjrwngYLHz86'),
        ('4niCnz6JgFf6HFmi4zG9E9W1fqTFwvavJNp5QZTorLdp', '27VSifqHkBVNCGsVVbda64onBZmRhGpB2Zg4pZwf3jZs'),
        ('4qbJH9zkQYyR6rLqo4N8rkpvepoeJpewSp39pFwmBL2H', '135DN9oH9vU4CLbKiC1Rj4vByAsyRstAdjrwngYLHz86'),
        ('4sraryXgNHVdeFuPDabBTjSfvxU58UZTz1c71ShPK56E', '4sraryXgNHVdeFuPDabBTjSfvxU58UZTz1c71ShPK56E'),
        ('4z8NksQVKosHL99AJadPw8U21BeoZ3WX7nwdrVyLTBwM', '2HMdJbv9bUQUL5zZCBG35kkUwYrfzvH5r5vkaVqAanmj'),
        ('5QwZhBxQs45TyF4NVFucQwHwD6MswL7S9q4iFo2hdyb4', '5QwZhBxQs45TyF4NVFucQwHwD6MswL7S9q4iFo2hdyb4'),
        ('5enFLaV3ZBNhU8M5CdVGMeNSMjbcjFERAxgwoi6DSDL', '5enFLaV3ZBNhU8M5CdVGMeNSMjbcjFERAxgwoi6DSDL'),
        ('5huujHCxeNiXDsiojAZWyzQkebYAbUpULaWy5Vzh7bGL', '3bbDEL917JkpMSCBTf43azASbkttCYNYaNoQpzPLPV8X'),
        ('5k1FHzqdgX85md8iAV9NFnFmY2Myk8aY1VVM7RHskqeM', '135DN9oH9vU4CLbKiC1Rj4vByAsyRstAdjrwngYLHz86'),
        ('5kPoHufB5fkuB8y1nRdYo4YMM5sdL9XJhcRDW2VHVnUd', '135DN9oH9vU4CLbKiC1Rj4vByAsyRstAdjrwngYLHz86'),
        ('5mmkeLVVLqjNEC6UU8J8z8XAjk6fRMVqTnGJxtvbup3h', '2HMdJbv9bUQUL5zZCBG35kkUwYrfzvH5r5vkaVqAanmj'),
        ('5qFyx4UQg5dwW66JTXSkTn4Pvwu8YA37P1FkUPNWfNEw', '5qFyx4UQg5dwW66JTXSkTn4Pvwu8YA37P1FkUPNWfNEw'),
        ('5srEZNTkdSB4bm9n62Qp7RYWhxyJRg3rSksGu58u3G9t', '3wB1dT7Bc9as5oceJHVAQ2fS6GR6J8WmJBgH3671vSUE'),
        ('629VCB8Kxp3NBV7BGNoYRFks4SsBY1Ku1sx35GTLThYm', '135DN9oH9vU4CLbKiC1Rj4vByAsyRstAdjrwngYLHz86'),
        ('6GAx18kw1gKN4bankfvoUv3oVdj2AVrd3BAtWUqfUDYu', '27VSifqHkBVNCGsVVbda64onBZmRhGpB2Zg4pZwf3jZs'),
        ('6JjsD628YyuZNfvaZmjwkCioQGpThRP7bPrVwbBcg9bq', '3bbDEL917JkpMSCBTf43azASbkttCYNYaNoQpzPLPV8X'),
        ('6KEjEtqtqtkYNUtxu37h9jipx1oZ2gTJCyXdrXRuJDaU', '135DN9oH9vU4CLbKiC1Rj4vByAsyRstAdjrwngYLHz86'),
        ('6LSw2UF2BA2Jckdv6LRoHh9frFLJpoiZW2dwTTgRjNwb', '6LSw2UF2BA2Jckdv6LRoHh9frFLJpoiZW2dwTTgRjNwb'),
        ('6MAeDcSNcDUQjg5XaBeRZd1xwE3o53bEUMJno7KcUsfk', '27VSifqHkBVNCGsVVbda64onBZmRhGpB2Zg4pZwf3jZs'),
        ('6N3PPe9kqfyCPRKT8h6WSddJBfugtcKVkB5JX6868zvp', '27VSifqHkBVNCGsVVbda64onBZmRhGpB2Zg4pZwf3jZs'),
        ('6Y1yzrVBtyfpDDgDQqTB9sRTqh5SHiJnjkbVnmyruXAk', '2HMdJbv9bUQUL5zZCBG35kkUwYrfzvH5r5vkaVqAanmj'),
        ('6fDmfTP8WwceuzpjdcsQov9FyRz8mTMTZzm1uEg1ViK1', '135DN9oH9vU4CLbKiC1Rj4vByAsyRstAdjrwngYLHz86'),
        ('6gbRF3iu89hpq6ewz2u53vWvnijttkNwvmQQwsr42fcS', '6gbRF3iu89hpq6ewz2u53vWvnijttkNwvmQQwsr42fcS'),
        ('6xpZ6m7iWXTT2daNtBXPZa73iwFLVEsiJdHYMYtdf7kP', '2HMdJbv9bUQUL5zZCBG35kkUwYrfzvH5r5vkaVqAanmj'),
        ('73zm5te9V3yLoiESNy1qC7Trq2yXP8zMfK19HHNdiZFr', '73zm5te9V3yLoiESNy1qC7Trq2yXP8zMfK19HHNdiZFr'),
        ('7Jcd536CXi6XVShSnu4Z1WYK3yDSHe2ejZDT2Rn5UXyT', '2HMdJbv9bUQUL5zZCBG35kkUwYrfzvH5r5vkaVqAanmj'),
        ('7m1b6bPcddT34575Hd4SZavB7oLUkzsDjRciUCUmHyXo', '27VSifqHkBVNCGsVVbda64onBZmRhGpB2Zg4pZwf3jZs'),
        ('7rKgXpowBVH2v8wjKcvSqdqaky5m5QFpL3qMixw9jbL', '27VSifqHkBVNCGsVVbda64onBZmRhGpB2Zg4pZwf3jZs'),
        ('7ufmve7ZSFCzuNcKRunYrGtyb2Ka1MXzkWwf7jZhVsmL', '7ufmve7ZSFCzuNcKRunYrGtyb2Ka1MXzkWwf7jZhVsmL'),
        ('7ymbHaQptDPSNvkMFGQdJ2niEsFgUD6GfGiYmb76pjAH', '7ymbHaQptDPSNvkMFGQdJ2niEsFgUD6GfGiYmb76pjAH'),
        ('81RWVKqrgKGmP11esLs8o5p2GJD3J92zKXeWnvdm5QTL', '81RWVKqrgKGmP11esLs8o5p2GJD3J92zKXeWnvdm5QTL'),
        ('88upcVeh8KEAG7nun3DtSEMJuCqi7YfqUhG7vzonQz3F', '27VSifqHkBVNCGsVVbda64onBZmRhGpB2Zg4pZwf3jZs'),
        ('88wCwQCWYHU61vXDBFswSp9LcMwjH6uitnriYswtmosV', '135DN9oH9vU4CLbKiC1Rj4vByAsyRstAdjrwngYLHz86'),
        ('8Ci6sU6TYsL5GVUYxfRLXPvivtFpKXXhvZw6viS3gB8u', '135DN9oH9vU4CLbKiC1Rj4vByAsyRstAdjrwngYLHz86'),
        ('8HcYptCBAaPFWkmupiSAmysZ6Z8jB7N1c4YhVjhX7zbg', '3bbDEL917JkpMSCBTf43azASbkttCYNYaNoQpzPLPV8X'),
        ('8Z7WThW881z3K6pVKkUBxmcKytyBAwoJNZFbnZ3o3bHF', '27VSifqHkBVNCGsVVbda64onBZmRhGpB2Zg4pZwf3jZs'),
        ('8ii79M5ajgVAviT6Pn8Ex3pxtcKXNw4aQUZ2Qfz7WwGV', '2HMdJbv9bUQUL5zZCBG35kkUwYrfzvH5r5vkaVqAanmj'),
        ('8kFF2gCpvaRWNRkaDQ9MndFuqymngTXwiQLxgDiG9Rw1', '27VSifqHkBVNCGsVVbda64onBZmRhGpB2Zg4pZwf3jZs'),
        ('8yjJWPUhWfBRqh4bfQoGdf5Zj56iLtYnss18gVD6GoEu', '27VSifqHkBVNCGsVVbda64onBZmRhGpB2Zg4pZwf3jZs'),
        ('93XWAYFzXa9paNnXMz6pB1Ti6hxidHupbKCdFDsR1Rbh', '2NwJxx3ZY3HPAe51zgcPAvMehrhKA9qvL1zcRwZPkfL3'),
        ('9JCgmqafGG7tnZiW3kBaynmmNXba1XEu3RConuGHX835', '135DN9oH9vU4CLbKiC1Rj4vByAsyRstAdjrwngYLHz86'),
        ('9Rito26QRmbLVJTx4iQUh62rJTzPFjkS319L5yjMS7mm', '3bbDEL917JkpMSCBTf43azASbkttCYNYaNoQpzPLPV8X'),
        ('9TfTr7LkXYQ5W3ib7JXwzw6JeXFShg4YgRttrsoxqz1H', '27VSifqHkBVNCGsVVbda64onBZmRhGpB2Zg4pZwf3jZs'),
        ('9kHEy3i8APPrKcTRJw7aJyXDKwevkvQo3Lbx7m46adcV', '135DN9oH9vU4CLbKiC1Rj4vByAsyRstAdjrwngYLHz86'),
        ('9kyzre4zUxNdD71DqysPGn6KebmHJoqYtd3AzP6MA97a', '2NwJxx3ZY3HPAe51zgcPAvMehrhKA9qvL1zcRwZPkfL3'),
        ('9oTWV5qnPNRaAPDmTiP8Gvebe4GcrjCHYKcUDm9YaNec', '3bbDEL917JkpMSCBTf43azASbkttCYNYaNoQpzPLPV8X'),
        ('9zWbVh6Gx4sAq6Nv3MPmmBV5TGfd6F2Zhp4XGwyAmYtN', '9zWbVh6Gx4sAq6Nv3MPmmBV5TGfd6F2Zhp4XGwyAmYtN'),
        ('9zm39oGQNs1KMRnD7Q2BbezKtoAs7wKMzgUVKSynKi1B', '27VSifqHkBVNCGsVVbda64onBZmRhGpB2Zg4pZwf3jZs'),
        ('A4eLD8Jme4DgfZ2xCsiPnxcGjHfqLwPMD8bWKQgBMLsu', 'A4eLD8Jme4DgfZ2xCsiPnxcGjHfqLwPMD8bWKQgBMLsu'),
        ('A9nEmy5rjeGCMWFo39rhyuXeeoVaAv98u5D3tzdKwmd1', '135DN9oH9vU4CLbKiC1Rj4vByAsyRstAdjrwngYLHz86'),
        ('AHPFBcVbVBu7s7YHgx93tq8BXBYoZuWwLeGVKnsmCKvW', '135DN9oH9vU4CLbKiC1Rj4vByAsyRstAdjrwngYLHz86'),
        ('ARxCck4HSRKopb6KnWmtMATmMknQvDpXZvf2cBQRyiaN', '27VSifqHkBVNCGsVVbda64onBZmRhGpB2Zg4pZwf3jZs'),
        ('AU12PsGK3sz1ZPQ8vRgXZXb4t6KgvzWMtA3dRMvsTTyP', '135DN9oH9vU4CLbKiC1Rj4vByAsyRstAdjrwngYLHz86'),
        ('AXTEMsgorjcHFbsFXs8d86fA9YiSTRw7YLM98JPpiXbo', '5enFLaV3ZBNhU8M5CdVGMeNSMjbcjFERAxgwoi6DSDL'),
        ('AYNYUwcz5cBjbhrfd5GCuLVzXLDqhSRFdWKa2NQ48byW', '2HMdJbv9bUQUL5zZCBG35kkUwYrfzvH5r5vkaVqAanmj'),
        ('AaXkcUY8e7RbaFk62gypiQ15JpWgCSKJ1J9mAd59LJiG', '38Fgtgr65fZD1dyTGZ8eHMNoJiP9ArHQXKLAnQxF4PuC'),
        ('ArpFRpuzjvzzsnUm6NsZCKKUKmQaRURq2iiv7QFpyqBL', 'ArpFRpuzjvzzsnUm6NsZCKKUKmQaRURq2iiv7QFpyqBL'),
        ('Au9ZiT6FjaDjFghvbUJb3VbZzKkGmNcKWrJTAxMMsABY', '2NwJxx3ZY3HPAe51zgcPAvMehrhKA9qvL1zcRwZPkfL3'),
        ('AyAHoyzsSFWUhnNJdfNeDUfxn9kB4pLSibkSgkxyxnKc', '38Fgtgr65fZD1dyTGZ8eHMNoJiP9ArHQXKLAnQxF4PuC'),
        ('B5ek2LjoozkLPgEdLzqHHmWrR9UqJuGoyp7L7uAvgnVP', '27VSifqHkBVNCGsVVbda64onBZmRhGpB2Zg4pZwf3jZs'),
        ('BCMbtr3X7JzSvRxceeERkJMuJq4gEmxy123S2vfBvttv', 'BCMbtr3X7JzSvRxceeERkJMuJq4gEmxy123S2vfBvttv'),
        ('BTDbDTSho5nuyhV7z6mUTzQg9EiURiMEWk33JdJYUX6', '2NwJxx3ZY3HPAe51zgcPAvMehrhKA9qvL1zcRwZPkfL3'),
        ('BWzwdMydAm5ZpxKGVkD75datXmEYpA3tPDQ7nvybAuHQ', '3wB1dT7Bc9as5oceJHVAQ2fS6GR6J8WmJBgH3671vSUE'),
        ('BbHjD6y2cwzNefXq1krkUyuDVbdkCzVP6RshSeAbvoxZ', 'BbHjD6y2cwzNefXq1krkUyuDVbdkCzVP6RshSeAbvoxZ'),
        ('BwsEFashuP7ufEqYBi4Zr8eBWHFbGL5E8AvVRsJpoTQc', '81RWVKqrgKGmP11esLs8o5p2GJD3J92zKXeWnvdm5QTL'),
        ('C32zAgk1ESr1u7WHBSjroBwETNkMvQnfwu66UhHPn6Gu', '3bbDEL917JkpMSCBTf43azASbkttCYNYaNoQpzPLPV8X'),
        ('C3irJJnfcioeyFQ7nhNQrEV9jShQiqfFKG7bvcf11JwH', 'C3irJJnfcioeyFQ7nhNQrEV9jShQiqfFKG7bvcf11JwH'),
        ('C57pQk1nBnyhK2jTjb41qjwdv11sj72vJrH6c3FXgpSQ', '3bbDEL917JkpMSCBTf43azASbkttCYNYaNoQpzPLPV8X'),
        ('CEmNJy9m9QmBYQKUyHFtdFQNo3yUGhtSU8bzo88Dg46V', '3bbDEL917JkpMSCBTf43azASbkttCYNYaNoQpzPLPV8X'),
        ('CKjrQ9nQNEFQp3PZ9oVrHXeiobxxyxAzsjyDyabHvnwp', 'CKjrQ9nQNEFQp3PZ9oVrHXeiobxxyxAzsjyDyabHvnwp'),
        ('CQyBKhJMvj32irbUGw5i7Bomj6SgxHZMcsnb4HbXM3Mc', 'CQyBKhJMvj32irbUGw5i7Bomj6SgxHZMcsnb4HbXM3Mc'),
        ('CXTC4M5W7Ls1s1be5rHhkRtzgE4k8N4iypxJDp4bEQq3', '38Fgtgr65fZD1dyTGZ8eHMNoJiP9ArHQXKLAnQxF4PuC'),
        ('CfE3PpB4cyVbDCarQTYVFAfSuLLCW2iZEL79mKf4qva2', '3bbDEL917JkpMSCBTf43azASbkttCYNYaNoQpzPLPV8X'),
        ('CioasYXrvrASharcrnW7ZmcWQM6ZvUvRnpJEqJ3tQkY8', '3wB1dT7Bc9as5oceJHVAQ2fS6GR6J8WmJBgH3671vSUE'),
        ('CqjfeCdULLGMSHn4FTt5fwftLD3GMDWQfLcLJ9kDoq7w', '27VSifqHkBVNCGsVVbda64onBZmRhGpB2Zg4pZwf3jZs'),
        ('CwDT38indM1jwMWjY52y88itB6PUA44RauwjdX9R1j8a', '2NwJxx3ZY3HPAe51zgcPAvMehrhKA9qvL1zcRwZPkfL3'),
        ('D7W2emckCA6A6ErJmfZiUpZYYDessVrUb9zbgo85zy3g', '135DN9oH9vU4CLbKiC1Rj4vByAsyRstAdjrwngYLHz86'),
        ('DHUCRj3A2xc6zCW52DYpGbJ6f1Sg1yN5UUzBdaXKxXDv', '2HMdJbv9bUQUL5zZCBG35kkUwYrfzvH5r5vkaVqAanmj'),
        ('DQ4i3ZZvtJpKdtrPU94oJn99N8tx4XtsmmRd9k9MA5vk', '38Fgtgr65fZD1dyTGZ8eHMNoJiP9ArHQXKLAnQxF4PuC'),
        ('DYJTG67gKdYfjRQvfemGzLrGidmPbLT5EPTnJ5RuVrJk', 'DYJTG67gKdYfjRQvfemGzLrGidmPbLT5EPTnJ5RuVrJk'),
        ('DgAX3kHhszsyNG9sS5P7aRj5bkT3iZLvphivRvGB1Hk', '3bbDEL917JkpMSCBTf43azASbkttCYNYaNoQpzPLPV8X'),
        ('E4EzXdwf7NNdqM2XGswWaWHfxgucVCo24PTCcrimTKBz', 'E4EzXdwf7NNdqM2XGswWaWHfxgucVCo24PTCcrimTKBz'),
        ('EC8XFdGbKPu76SewvXGDHh2oqhpYViicGLY6ddgafzWn', 'EC8XFdGbKPu76SewvXGDHh2oqhpYViicGLY6ddgafzWn'),
        ('EGXj5MEx4bC9wP9uo5iGAGREZUuPQsnVzhg6WxKtYfuX', '27VSifqHkBVNCGsVVbda64onBZmRhGpB2Zg4pZwf3jZs'),
        ('ELGNVYE7X1R1uQSuVqFN8TxbV7AipcQ23HmmqNhCVUMy', '3bbDEL917JkpMSCBTf43azASbkttCYNYaNoQpzPLPV8X'),
        ('ESmuGe6WuNudyAhh99AaFMAHP9Bo2oqSHUhNb1Tkg6JD', '135DN9oH9vU4CLbKiC1Rj4vByAsyRstAdjrwngYLHz86'),
        ('ET2J6MpTzDjBRcUuzFwjsUcBrHFRN8DwfPCxnHAVf8LH', '135DN9oH9vU4CLbKiC1Rj4vByAsyRstAdjrwngYLHz86'),
        ('EdrsiufCNBkF3krnmramuQZvRC9VpZQpMzxjbLtYWEeb', '27VSifqHkBVNCGsVVbda64onBZmRhGpB2Zg4pZwf3jZs'),
        ('EgBRgL9Sf2XgpWvmhj8T5BaDXZwR9CRr4RBCivQVCpRG', '135DN9oH9vU4CLbKiC1Rj4vByAsyRstAdjrwngYLHz86'),
        ('EkZmGH5r4VrBUf4Df4TB6vbguNLbsFMNpZy4ksjZHdUz', '2NwJxx3ZY3HPAe51zgcPAvMehrhKA9qvL1zcRwZPkfL3'),
        ('EvD5TvP8qhhNP6K14YEkQkFtGhCvkjsKmM1iQkArmxGF', 'EvD5TvP8qhhNP6K14YEkQkFtGhCvkjsKmM1iQkArmxGF'),
        ('F3i1cr6MnAn7Xq6rGN6DRDzLSCqYiy2fbarcTztoKqVP', 'F3i1cr6MnAn7Xq6rGN6DRDzLSCqYiy2fbarcTztoKqVP'),
        ('F9vmGpRrhEpENTUSmoEtneGTCsNMpM2mbHtxF8WM9DPW', 'F9vmGpRrhEpENTUSmoEtneGTCsNMpM2mbHtxF8WM9DPW'),
        ('FDXqTBNF53ysMRmKcJwq3bcFm1QqpmD8s5WDELhDpy1f', '135DN9oH9vU4CLbKiC1Rj4vByAsyRstAdjrwngYLHz86'),
        ('FGotS5zW14fJaoTXMdpZsuooowWomJ3skySF2cEt3LR', '3bbDEL917JkpMSCBTf43azASbkttCYNYaNoQpzPLPV8X'),
        ('FQV4vfF9DvAwfNwrg9F9mHxBQYCP9PMN8wrxr4fPT2xU', '27VSifqHkBVNCGsVVbda64onBZmRhGpB2Zg4pZwf3jZs'),
        ('FYX5JQ2kP7TD8gWb9WP1tjmwWWUAzi8edEZTr5Z8F1ck', 'FYX5JQ2kP7TD8gWb9WP1tjmwWWUAzi8edEZTr5Z8F1ck'),
        ('FcwdLrF6t8NNfRS3wheLuB3cNUeCHn2twZ251mufD2YF', '135DN9oH9vU4CLbKiC1Rj4vByAsyRstAdjrwngYLHz86'),
        ('ForapMTg4SKR9rHxrfRHL3p1ZD9UeVnStXMEqHY5Ws4C', 'ForapMTg4SKR9rHxrfRHL3p1ZD9UeVnStXMEqHY5Ws4C'),
        ('G3rfSianfqVWjSUptPE9CbqCr47fayoRTPK1K4oeTG5C', 'G3rfSianfqVWjSUptPE9CbqCr47fayoRTPK1K4oeTG5C'),
        ('G5wXHMBbWgquSKgRhJDLUhNt6qJygBT8sQShc3X35FrC', '3bbDEL917JkpMSCBTf43azASbkttCYNYaNoQpzPLPV8X'),
        ('GB1FuwDP4X4kiWiEnR4xXbmiPWCzSZyXwdH14mUFmfqE', '2HMdJbv9bUQUL5zZCBG35kkUwYrfzvH5r5vkaVqAanmj'),
        ('GMWBrhES3DmveSMAtZnA7pWvGNWgBpKcq3xhcxA4qptC', 'GMWBrhES3DmveSMAtZnA7pWvGNWgBpKcq3xhcxA4qptC'),
        ('GNu5i1HXqpB3zQchEY2LVHNAdei4P97qfZEfJcUBuqRT', 'GNu5i1HXqpB3zQchEY2LVHNAdei4P97qfZEfJcUBuqRT'),
        ('GV5tv4bRucmzm39UdsGXEuf6nDQSyr51btJqDwnTbQvi', '27VSifqHkBVNCGsVVbda64onBZmRhGpB2Zg4pZwf3jZs'),
        ('GWpXfC5Kt1q8zZxuHojddydZ99sPKSzPCWiTzxTX8kMc', '2HMdJbv9bUQUL5zZCBG35kkUwYrfzvH5r5vkaVqAanmj'),
        ('GZch34j75hi796ZgQgjrYj8EXQ2NTcGcBGEdsgp5DAnj', '27VSifqHkBVNCGsVVbda64onBZmRhGpB2Zg4pZwf3jZs'),
        ('GczmdQsxY2xB32LC88Z1ewbUd4RfonNxxMCfpGzxthaz', '2NwJxx3ZY3HPAe51zgcPAvMehrhKA9qvL1zcRwZPkfL3'),
        ('GghmQaR563bQxEQwnob3TFmUmFzcJNgppcyMST7RVysr', 'GghmQaR563bQxEQwnob3TFmUmFzcJNgppcyMST7RVysr'),
        ('Gy7e4mi5Rem7pt84SRHuJSLsauzDyAAWHLMqqFS5c9zF', 'Gy7e4mi5Rem7pt84SRHuJSLsauzDyAAWHLMqqFS5c9zF'),
        ('HQHmUBS9E7nnhG3v9H339TRn9RjxDj4dzBngZxi7uC6z', '2HMdJbv9bUQUL5zZCBG35kkUwYrfzvH5r5vkaVqAanmj'),
        ('HSnB2SAmRVjHCeuLgpBPmjdyg3r2fBXQYrjdeXPS24mP', '3bbDEL917JkpMSCBTf43azASbkttCYNYaNoQpzPLPV8X'),
        ('HWTefYGGrkfd4fMqYBsjedd8daow5xecf8odUE4a3G7R', '38Fgtgr65fZD1dyTGZ8eHMNoJiP9ArHQXKLAnQxF4PuC'),
        ('HXuSaaZ6QjnyX4mQLZQGoVSwb83uNyJpYTMUAuPcnbht', '135DN9oH9vU4CLbKiC1Rj4vByAsyRstAdjrwngYLHz86'),
        ('HYnNfsB8PammnVBbg2WGF1uNPNE75adEEeLhuu59f89h', '2HMdJbv9bUQUL5zZCBG35kkUwYrfzvH5r5vkaVqAanmj'),
        ('Hhcu1xXi2han6ee7cCpqB1uZ7Wh8MofqGt7yYirb2Wgh', '135DN9oH9vU4CLbKiC1Rj4vByAsyRstAdjrwngYLHz86'),
        ('HjH7yUgUeznQTNzFsYBq4hSeKgNtEc4K5PfYJNcwAUfh', '38Fgtgr65fZD1dyTGZ8eHMNoJiP9ArHQXKLAnQxF4PuC'),
        ('J8xvjzq2sXyi5JwBhM9dsbFEBYn7Cd6z2ZMotCxaqTto', '38Fgtgr65fZD1dyTGZ8eHMNoJiP9ArHQXKLAnQxF4PuC'),
        ('XuyUmJTJqyFfvt88LP1Fj5fP2RH9kJbPvAixUfBQHhB', '135DN9oH9vU4CLbKiC1Rj4vByAsyRstAdjrwngYLHz86'),
        ('itiXvAsc4sZWyisWVvG6FdAfRvJa1nvh8DwgGDbGtWW', 'itiXvAsc4sZWyisWVvG6FdAfRvJa1nvh8DwgGDbGtWW'),
        ('t3sipR2q5TH1GafmfvqEwbfrjf6eJc5NdPYNRjTq35D', 't3sipR2q5TH1GafmfvqEwbfrjf6eJc5NdPYNRjTq35D')
    ) AS v(usr, entity)
),
cohort AS (
    SELECT
        mint,
        min(evt_block_time) AS created_at,
        min(evt_block_slot) AS created_slot,
        max(CAST("user" AS varchar)) AS dev,
        max(quote_mint) AS quote_mint
    FROM pumpdotfun_solana.pump_evt_createevent
    WHERE evt_block_date BETWEEN DATE '2026-08-17' AND DATE '2026-08-30'
    GROUP BY 1
),
sol_cohort AS (
    SELECT mint, created_at, created_slot, dev
    FROM cohort
    WHERE quote_mint IS NULL OR quote_mint = '11111111111111111111111111111111'
),
mig AS (
    SELECT mint, min_by(pool, evt_block_slot) AS pool
    FROM pumpdotfun_solana.pump_evt_completepumpammmigrationevent
    WHERE evt_block_date BETWEEN DATE '2026-08-17' AND DATE '2026-09-06'
      AND mint IN (SELECT mint FROM sol_cohort)
    GROUP BY 1
),
cp AS (
    SELECT
        pool,
        max(base_mint) AS base_mint,
        max(quote_mint) AS quote_mint,
        max(base_mint_decimals) AS bd,
        max(quote_mint_decimals) AS qd,
        min(evt_block_slot) AS pool_created_slot,
        COALESCE(bool_or(evt_outer_executing_account = '6EF8rrecthR5Dkzon8Nwu78hRvfCKubJ14M5uBEwF6P' AND index = 0), false) AS by_pump
    FROM pumpdotfun_solana.pump_amm_evt_createpoolevent
    WHERE evt_block_date BETWEEN DATE '2026-08-17' AND DATE '2026-09-06'
      AND (
          base_mint IN (SELECT mint FROM sol_cohort)
          OR quote_mint IN (SELECT mint FROM sol_cohort)
      )
    GROUP BY 1
),
cp_norm AS (
    SELECT
        pool,
        CASE
            WHEN quote_mint = 'So11111111111111111111111111111111111111112' THEN base_mint
            WHEN base_mint = 'So11111111111111111111111111111111111111112' THEN quote_mint
        END AS mint,
        base_mint = 'So11111111111111111111111111111111111111112' AS pool_reversed,
        CASE WHEN base_mint = 'So11111111111111111111111111111111111111112' THEN qd ELSE bd END AS td,
        CASE WHEN base_mint = 'So11111111111111111111111111111111111111112' THEN bd ELSE qd END AS sd,
        pool_created_slot,
        by_pump
    FROM cp
    WHERE (
        quote_mint = 'So11111111111111111111111111111111111111112'
        AND base_mint IN (SELECT mint FROM sol_cohort)
    ) OR (
        base_mint = 'So11111111111111111111111111111111111111112'
        AND quote_mint IN (SELECT mint FROM sol_cohort)
    )
),
fallback_pool AS (
    SELECT mint, min_by(pool, pool_created_slot) AS pool
    FROM cp_norm
    WHERE by_pump
    GROUP BY 1
),
mapping0 AS (
    SELECT c.mint, COALESCE(m.pool, f.pool) AS pool
    FROM sol_cohort c
    LEFT JOIN mig m ON m.mint = c.mint
    LEFT JOIN fallback_pool f ON f.mint = c.mint
),
mapping AS (
    SELECT m.mint, m.pool, p.pool_reversed, p.td, p.sd
    FROM mapping0 m
    JOIN cp_norm p ON p.pool = m.pool AND p.mint = m.mint
),
amm_raw AS (
    SELECT
        m.mint, m.pool_reversed, m.td, m.sd,
        a.evt_block_time AS ts, a.evt_block_slot AS slot, a.evt_tx_index AS txi,
        COALESCE(a.evt_outer_instruction_index, 0) AS oix,
        COALESCE(a.evt_inner_instruction_index, -1) AS iix,
        CAST(a."user" AS varchar) AS usr,
        NOT m.pool_reversed AS is_buy,
        CASE WHEN m.pool_reversed THEN CAST(a.base_amount_out AS DOUBLE) / power(10, m.sd)
             ELSE CAST(a.user_quote_amount_in AS DOUBLE) / power(10, m.sd) END AS sol_user,
        CASE WHEN m.pool_reversed THEN CAST(a.user_quote_amount_in AS DOUBLE) / power(10, m.td)
             ELSE CAST(a.base_amount_out AS DOUBLE) / power(10, m.td) END AS tok,
        IF(m.pool_reversed, CAST(NULL AS DOUBLE), CAST(a.protocol_fee AS DOUBLE) / power(10, m.sd)) AS fee_proto,
        IF(m.pool_reversed, CAST(NULL AS DOUBLE), CAST(a.coin_creator_fee AS DOUBLE) / power(10, m.sd)) AS fee_creator,
        IF(m.pool_reversed, CAST(NULL AS DOUBLE), CAST(a.lp_fee AS DOUBLE) / power(10, m.sd)) AS fee_lp,
        CASE WHEN m.pool_reversed THEN CAST(a.pool_base_token_reserves AS DOUBLE)
             ELSE CAST(a.pool_quote_token_reserves AS DOUBLE) END AS sol_pre_raw,
        CASE WHEN m.pool_reversed THEN CAST(a.pool_quote_token_reserves AS DOUBLE)
             ELSE CAST(a.pool_base_token_reserves AS DOUBLE) END AS target_pre_raw,
        CASE WHEN m.pool_reversed THEN -CAST(a.base_amount_out AS DOUBLE)
             ELSE CAST(a.quote_amount_in_with_lp_fee AS DOUBLE) END AS dsol_raw,
        CASE WHEN m.pool_reversed THEN CAST(a.quote_amount_in_with_lp_fee AS DOUBLE)
             ELSE -CAST(a.base_amount_out AS DOUBLE) END AS dtarget_raw
    FROM pumpdotfun_solana.pump_amm_evt_buyevent a
    JOIN mapping m ON m.pool = a.pool
    WHERE a.evt_block_date BETWEEN DATE '2026-08-17' AND DATE '2026-09-06'
    UNION ALL
    SELECT
        m.mint, m.pool_reversed, m.td, m.sd,
        a.evt_block_time, a.evt_block_slot, a.evt_tx_index,
        COALESCE(a.evt_outer_instruction_index, 0), COALESCE(a.evt_inner_instruction_index, -1),
        CAST(a."user" AS varchar),
        m.pool_reversed,
        CASE WHEN m.pool_reversed THEN CAST(a.base_amount_in AS DOUBLE) / power(10, m.sd)
             ELSE CAST(a.user_quote_amount_out AS DOUBLE) / power(10, m.sd) END,
        CASE WHEN m.pool_reversed THEN CAST(a.user_quote_amount_out AS DOUBLE) / power(10, m.td)
             ELSE CAST(a.base_amount_in AS DOUBLE) / power(10, m.td) END,
        IF(m.pool_reversed, CAST(NULL AS DOUBLE), CAST(a.protocol_fee AS DOUBLE) / power(10, m.sd)),
        IF(m.pool_reversed, CAST(NULL AS DOUBLE), CAST(a.coin_creator_fee AS DOUBLE) / power(10, m.sd)),
        IF(m.pool_reversed, CAST(NULL AS DOUBLE), CAST(a.lp_fee AS DOUBLE) / power(10, m.sd)),
        CASE WHEN m.pool_reversed THEN CAST(a.pool_base_token_reserves AS DOUBLE)
             ELSE CAST(a.pool_quote_token_reserves AS DOUBLE) END,
        CASE WHEN m.pool_reversed THEN CAST(a.pool_quote_token_reserves AS DOUBLE)
             ELSE CAST(a.pool_base_token_reserves AS DOUBLE) END,
        CASE WHEN m.pool_reversed THEN CAST(a.base_amount_in AS DOUBLE)
             ELSE -(CAST(a.quote_amount_out AS DOUBLE) - COALESCE(CAST(a.lp_fee AS DOUBLE), 0)) END,
        CASE WHEN m.pool_reversed THEN -(CAST(a.quote_amount_out AS DOUBLE) - COALESCE(CAST(a.lp_fee AS DOUBLE), 0))
             ELSE CAST(a.base_amount_in AS DOUBLE) END
    FROM pumpdotfun_solana.pump_amm_evt_sellevent a
    JOIN mapping m ON m.pool = a.pool
    WHERE a.evt_block_date BETWEEN DATE '2026-08-17' AND DATE '2026-09-06'
),
ev AS (
    SELECT
        t.mint, 0 AS venue, t.evt_block_time AS ts, t.evt_block_slot AS slot, t.evt_tx_index AS txi,
        COALESCE(t.evt_outer_instruction_index, 0) AS oix,
        COALESCE(t.evt_inner_instruction_index, -1) AS iix,
        CAST(t."user" AS varchar) AS usr,
        COALESCE(t.is_buy, t.isBuy) AS is_buy,
        CASE WHEN COALESCE(t.is_buy, t.isBuy)
             THEN CAST(COALESCE(t.sol_amount, t.solAmount) AS DOUBLE) + ceiling(CAST(COALESCE(t.sol_amount, t.solAmount) AS DOUBLE) * (COALESCE(CAST(t.fee_basis_points AS DOUBLE), 0) + COALESCE(CAST(t.creator_fee_basis_points AS DOUBLE), 0)) / 1e4)
             ELSE CAST(COALESCE(t.sol_amount, t.solAmount) AS DOUBLE) - ceiling(CAST(COALESCE(t.sol_amount, t.solAmount) AS DOUBLE) * (COALESCE(CAST(t.fee_basis_points AS DOUBLE), 0) + COALESCE(CAST(t.creator_fee_basis_points AS DOUBLE), 0)) / 1e4) END / 1e9 AS sol_user,
        CAST(COALESCE(t.sol_amount, t.solAmount) AS DOUBLE) / 1e9 AS sol_gross,
        CAST(COALESCE(t.token_amount, t.tokenAmount) AS DOUBLE) / 1e6 AS tok,
        ceiling(CAST(COALESCE(t.sol_amount, t.solAmount) AS DOUBLE) * (COALESCE(CAST(t.fee_basis_points AS DOUBLE), 0) + COALESCE(CAST(t.creator_fee_basis_points AS DOUBLE), 0)) / 1e4) / 1e9 AS fee_all,
        (COALESCE(CAST(t.fee_basis_points AS DOUBLE), 0) + COALESCE(CAST(t.creator_fee_basis_points AS DOUBLE), 0)) AS fee_bps,
        CAST(COALESCE(t.virtual_sol_reserves, t.virtualSolReserves) AS DOUBLE) / 1e9 AS x,
        CAST(COALESCE(t.virtual_token_reserves, t.virtualTokenReserves) AS DOUBLE) / 1e6 AS y,
        CAST(t.real_sol_reserves AS DOUBLE) / 1e9 AS xr
    FROM pumpdotfun_solana.pump_evt_tradeevent t
    WHERE t.evt_block_date BETWEEN DATE '2026-08-17' AND DATE '2026-09-06'
      AND t.mint IN (SELECT mint FROM sol_cohort)
    UNION ALL
    SELECT
        mint, 1, ts, slot, txi, oix, iix, usr, is_buy, sol_user,
        IF(is_buy, sol_user - COALESCE(fee_proto, 0) - COALESCE(fee_creator, 0) - COALESCE(fee_lp, 0),
                   sol_user + COALESCE(fee_proto, 0) + COALESCE(fee_creator, 0) + COALESCE(fee_lp, 0)),
        tok,
        COALESCE(fee_proto, 0) + COALESCE(fee_creator, 0) + COALESCE(fee_lp, 0),
        CAST(NULL AS DOUBLE),
        (sol_pre_raw + dsol_raw) / power(10, sd), (target_pre_raw + dtarget_raw) / power(10, td),
        CAST(NULL AS DOUBLE)
    FROM amm_raw
),
ev2 AS (
    SELECT
        e.*, c.created_at, c.created_slot, c.dev,
        row_number() OVER (PARTITION BY e.mint ORDER BY e.slot, e.txi, e.oix, e.iix, e.venue) AS rn,
        date_diff('second', c.created_at, max(e.ts) OVER (
            PARTITION BY e.mint ORDER BY e.slot, e.txi, e.oix, e.iix, e.venue
            ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
        )) AS dt
    FROM ev e
    JOIN sol_cohort c ON c.mint = e.mint
    WHERE e.ts >= c.created_at
      AND e.ts < DATE '2026-09-06' + INTERVAL '1' DAY
),
q1 AS (
    SELECT
        *,
        min(CASE WHEN is_buy AND sol_gross >= 0.1 AND usr IS NOT NULL AND usr <> dev THEN rn END)
          OVER (PARTITION BY mint, usr) AS first_q_rn
    FROM ev2
),
q2 AS (
    SELECT
        *,
        rn = first_q_rn AS q_new,
        sum(IF(rn = first_q_rn, 1, 0)) OVER (
            PARTITION BY mint ORDER BY rn ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
        ) AS q_count,
        max_by(venue, rn) OVER (PARTITION BY mint) AS v_end,
        max_by(x, rn) OVER (PARTITION BY mint) AS x_end,
        max_by(y, rn) OVER (PARTITION BY mint) AS y_end,
        max_by(IF(venue = 0, xr), IF(venue = 0, rn)) OVER (PARTITION BY mint) AS xr_end,
        max_by(IF(venue = 0, fee_bps), IF(venue = 0, rn)) OVER (PARTITION BY mint) AS fee_end,
        sum(IF(venue = 1, fee_all)) OVER (PARTITION BY mint)
          / sum(IF(venue = 1, sol_gross)) OVER (PARTITION BY mint) AS amm_fee_rate
    FROM q1
),
q3 AS (
    SELECT
        *,
        max(IF(q_new AND q_count = 3, dt)) OVER (PARTITION BY mint) AS t3_s
    FROM q2
),
ent AS (
    SELECT
        q.mint, s.entity, q.rn, q.dt, q.is_buy, q.slot, q.created_slot, q.created_at, q.t3_s,
        q.sol_user, q.venue,
        min(IF(q.is_buy, q.rn)) OVER (PARTITION BY q.mint, s.entity) AS b_rn0
    FROM q3 q
    JOIN sel s ON s.usr = q.usr
),
trig AS (
    SELECT
        mint, entity,
        max(b_rn0) AS b_rn,
        max(IF(rn = b_rn0, dt)) AS b_dt,
        bool_or(rn = b_rn0 AND slot = created_slot) AS b_same_slot,
        max(IF(rn = b_rn0, venue)) AS b_venue,
        max(IF(rn = b_rn0, sol_user)) AS b_sol,
        min_by(dt, rn) FILTER (WHERE NOT is_buy AND rn > b_rn0) AS s_dt,
        max(t3_s) AS t3_s,
        max(created_at) AS created_at,
        count_if(is_buy) AS ent_n_buy,
        count_if(NOT is_buy) AS ent_n_sell,
        sum(IF(is_buy, sol_user, 0)) AS ent_buy_sol
    FROM ent
    WHERE b_rn0 IS NOT NULL
    GROUP BY 1, 2
),
path AS (
    SELECT
        t.mint, t.entity, t.b_rn, t.b_dt, t.s_dt,
        t.created_at, t.t3_s, t.b_same_slot, t.b_venue, t.b_sol,
        t.ent_n_buy, t.ent_n_sell, t.ent_buy_sol,
        q.rn, q.dt, q.venue, q.x, q.y, q.xr,
        CASE WHEN q.venue = 0 THEN q.fee_bps
             WHEN q.fee_all > 0 AND q.sol_gross > 0 THEN q.fee_all / q.sol_gross * 1e4
             ELSE 125 END AS fee_bps,
        q.x / q.y AS price
    FROM trig t
    JOIN q3 q ON q.mint = t.mint AND q.rn >= t.b_rn AND q.dt <= t.b_dt + 604800
    WHERE q.x > 0 AND q.y > 0
),
p1 AS (
    SELECT
        *,
        max(IF(dt <= b_dt + 2, rn)) OVER (PARTITION BY mint, entity) AS e2,
        max(IF(dt <= LEAST(COALESCE(s_dt + 2, b_dt + 604800), b_dt + 604800), rn)) OVER (PARTITION BY mint, entity) AS x2,
        max(IF(dt <= b_dt + 5, rn)) OVER (PARTITION BY mint, entity) AS e5,
        max(IF(dt <= LEAST(COALESCE(s_dt + 5, b_dt + 604800), b_dt + 604800), rn)) OVER (PARTITION BY mint, entity) AS x5,
        max(IF(dt <= b_dt + 15, rn)) OVER (PARTITION BY mint, entity) AS e15,
        max(IF(dt <= LEAST(COALESCE(s_dt + 15, b_dt + 604800), b_dt + 604800), rn)) OVER (PARTITION BY mint, entity) AS x15,
        max(IF(dt <= b_dt + 30, rn)) OVER (PARTITION BY mint, entity) AS e30,
        max(IF(dt <= LEAST(COALESCE(s_dt + 30, b_dt + 604800), b_dt + 604800), rn)) OVER (PARTITION BY mint, entity) AS x30
    FROM path
),
p2 AS (
    SELECT
        *,
        max(IF(rn = e2, x)) OVER (PARTITION BY mint, entity) AS ex2, max(IF(rn = e2, y)) OVER (PARTITION BY mint, entity) AS ey2, max(IF(rn = e2, fee_bps)) OVER (PARTITION BY mint, entity) AS ef2, max(IF(rn = e2, dt)) OVER (PARTITION BY mint, entity) AS edt2,
        max(IF(rn = e5, x)) OVER (PARTITION BY mint, entity) AS ex5, max(IF(rn = e5, y)) OVER (PARTITION BY mint, entity) AS ey5, max(IF(rn = e5, fee_bps)) OVER (PARTITION BY mint, entity) AS ef5, max(IF(rn = e5, dt)) OVER (PARTITION BY mint, entity) AS edt5,
        max(IF(rn = e15, x)) OVER (PARTITION BY mint, entity) AS ex15, max(IF(rn = e15, y)) OVER (PARTITION BY mint, entity) AS ey15, max(IF(rn = e15, fee_bps)) OVER (PARTITION BY mint, entity) AS ef15, max(IF(rn = e15, dt)) OVER (PARTITION BY mint, entity) AS edt15,
        max(IF(rn = e30, x)) OVER (PARTITION BY mint, entity) AS ex30, max(IF(rn = e30, y)) OVER (PARTITION BY mint, entity) AS ey30, max(IF(rn = e30, fee_bps)) OVER (PARTITION BY mint, entity) AS ef30, max(IF(rn = e30, dt)) OVER (PARTITION BY mint, entity) AS edt30,
        max(IF(rn = e2, venue)) OVER (PARTITION BY mint, entity) AS evenue_b,
        max(IF(rn = e2, x / y)) OVER (PARTITION BY mint, entity) AS eprice_b
    FROM p1
),
p3 AS (
    SELECT
        *,
        ey2 - ex2 * ey2 / (ex2 + 0.5 * (1 - ef2 / 1e4)) AS tok2,
        ey5 - ex5 * ey5 / (ex5 + 0.5 * (1 - ef5 / 1e4)) AS tok5,
        ey15 - ex15 * ey15 / (ex15 + 0.5 * (1 - ef15 / 1e4)) AS tok15,
        ey30 - ex30 * ey30 / (ex30 + 0.5 * (1 - ef30 / 1e4)) AS tok30,
        price / NULLIF(eprice_b, 0) AS pm_b
    FROM p2
),
p4 AS (
    SELECT
        *,
        LEAST(
            CASE WHEN venue = 0 THEN (x * tok2 / (y + tok2)) * (1 - fee_bps / 1e4)
                 ELSE (x - x * y / (y + tok2)) * (1 - fee_bps / 1e4) END,
            IF(venue = 0, xr + 0.5 * (1 - ef2 / 1e4), 1e18)) AS m_ab,
        LEAST(
            CASE WHEN venue = 0 THEN CASE WHEN y > tok2 THEN (x * y / (y - tok2) - x) * (1 - fee_bps / 1e4) END
                 ELSE (x - x * y / (y + tok2)) * (1 - fee_bps / 1e4) END,
            IF(venue = 0, xr + 0.5 * (1 - ef2 / 1e4), 1e18)) AS m_bb,
        max(IF(rn >= e2, pm_b)) OVER (
            PARTITION BY mint, entity ORDER BY rn ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
        ) AS runmax_b
    FROM p3
),
res AS (
    SELECT
        mint, entity,
    max(created_at) AS created_at, max(t3_s) AS t3_s, max(b_dt) AS b_dt, max(s_dt) AS s_dt,
    bool_or(b_same_slot) AS b_same_slot, max(b_venue) AS b_venue, max(b_sol) AS b_sol,
    max(ent_n_buy) AS ent_n_buy, max(ent_n_sell) AS ent_n_sell, max(ent_buy_sol) AS ent_buy_sol,
    max(IF(rn = x2, LEAST(
            CASE WHEN venue = 0 THEN (x * tok2 / (y + tok2)) * (1 - fee_bps / 1e4)
                 ELSE (x - x * y / (y + tok2)) * (1 - fee_bps / 1e4) END,
            IF(venue = 0, xr + 0.5 * (1 - ef2 / 1e4), 1e18)))) AS sell_a_d2,
    max(IF(rn = x2, LEAST(
            CASE WHEN venue = 0 THEN CASE WHEN y > tok2 THEN (x * y / (y - tok2) - x) * (1 - fee_bps / 1e4) END
                 ELSE (x - x * y / (y + tok2)) * (1 - fee_bps / 1e4) END,
            IF(venue = 0, xr + 0.5 * (1 - ef2 / 1e4), 1e18)))) AS sell_b_d2,
    max(edt2) AS edt2, max(IF(rn = x2, dt)) AS xdt2,
    max(IF(rn = x2, venue)) AS xvenue2,
    max(IF(rn = x5, LEAST(
            CASE WHEN venue = 0 THEN (x * tok5 / (y + tok5)) * (1 - fee_bps / 1e4)
                 ELSE (x - x * y / (y + tok5)) * (1 - fee_bps / 1e4) END,
            IF(venue = 0, xr + 0.5 * (1 - ef5 / 1e4), 1e18)))) AS sell_a_d5,
    max(IF(rn = x5, LEAST(
            CASE WHEN venue = 0 THEN CASE WHEN y > tok5 THEN (x * y / (y - tok5) - x) * (1 - fee_bps / 1e4) END
                 ELSE (x - x * y / (y + tok5)) * (1 - fee_bps / 1e4) END,
            IF(venue = 0, xr + 0.5 * (1 - ef5 / 1e4), 1e18)))) AS sell_b_d5,
    max(edt5) AS edt5, max(IF(rn = x5, dt)) AS xdt5,
    max(IF(rn = x5, venue)) AS xvenue5,
    max(IF(rn = x15, LEAST(
            CASE WHEN venue = 0 THEN (x * tok15 / (y + tok15)) * (1 - fee_bps / 1e4)
                 ELSE (x - x * y / (y + tok15)) * (1 - fee_bps / 1e4) END,
            IF(venue = 0, xr + 0.5 * (1 - ef15 / 1e4), 1e18)))) AS sell_a_d15,
    max(IF(rn = x15, LEAST(
            CASE WHEN venue = 0 THEN CASE WHEN y > tok15 THEN (x * y / (y - tok15) - x) * (1 - fee_bps / 1e4) END
                 ELSE (x - x * y / (y + tok15)) * (1 - fee_bps / 1e4) END,
            IF(venue = 0, xr + 0.5 * (1 - ef15 / 1e4), 1e18)))) AS sell_b_d15,
    max(edt15) AS edt15, max(IF(rn = x15, dt)) AS xdt15,
    max(IF(rn = x15, venue)) AS xvenue15,
    max(IF(rn = x30, LEAST(
            CASE WHEN venue = 0 THEN (x * tok30 / (y + tok30)) * (1 - fee_bps / 1e4)
                 ELSE (x - x * y / (y + tok30)) * (1 - fee_bps / 1e4) END,
            IF(venue = 0, xr + 0.5 * (1 - ef30 / 1e4), 1e18)))) AS sell_a_d30,
    max(IF(rn = x30, LEAST(
            CASE WHEN venue = 0 THEN CASE WHEN y > tok30 THEN (x * y / (y - tok30) - x) * (1 - fee_bps / 1e4) END
                 ELSE (x - x * y / (y + tok30)) * (1 - fee_bps / 1e4) END,
            IF(venue = 0, xr + 0.5 * (1 - ef30 / 1e4), 1e18)))) AS sell_b_d30,
    max(edt30) AS edt30, max(IF(rn = x30, dt)) AS xdt30,
    max(IF(rn = x30, venue)) AS xvenue30,
    NULLIF(min_by(COALESCE(m_ab, -1.0), rn) FILTER (WHERE rn >= e2 AND pm_b <= 0.5 * greatest(1.0, runmax_b)), -1.0) AS b50_stop_a,
    NULLIF(min_by(COALESCE(m_bb, -1.0), rn) FILTER (WHERE rn >= e2 AND pm_b <= 0.5 * greatest(1.0, runmax_b)), -1.0) AS b50_stop_b,
    min(dt) FILTER (WHERE rn >= e2 AND pm_b <= 0.5 * greatest(1.0, runmax_b)) AS b50_stop_dt,
    NULLIF(max_by(COALESCE(m_ab, -1.0), rn), -1.0) AS hor_a,
    NULLIF(max_by(COALESCE(m_bb, -1.0), rn), -1.0) AS hor_b,
    2 AS b50_delay,
    max(dt) AS last_dt,
    max(evenue_b) AS e_venue_b,
    max(tok2) AS tok_b,
    count(*) AS n_path
    FROM p4
    GROUP BY 1, 2
)
SELECT *
FROM res
