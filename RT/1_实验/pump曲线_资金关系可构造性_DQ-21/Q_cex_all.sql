/* DQ-21 R1a（提案，待批准）：Dune Solana 交易所地址表全表，供严格服务判定离线复用。平台单次费用上限：1 credit（请在 Dune 网页设置）。
   Dune 一次性额度约 09-29 过期，须在此之前运行。 */
SELECT address, cex_name, distinct_name, added_by, added_date
FROM cex_solana.addresses
