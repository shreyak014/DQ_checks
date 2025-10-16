CREATE OR REPLACE TABLE `GDH_GL.DS.dim_product` AS
SELECT
  t1.product_key,
  t1.sgs_product_key,
  t1.short_product_desc AS short_product_description,
  t1.age,
  t1.proof,
  t1.brand_level1_desc AS brand_level_1_description,
  t1.brand_level2_desc AS brand_level_2_description,
  t1.brand_level3_desc AS brand_level_3_description,
  t1.category_level2_desc AS category_level_2_description,
  t1.zmatstat,
  t1.spec_pricing_id AS special_pricing_id,
  t1.spec_pricing_desc AS special_pricing_description,
  t2.kpi_prestige,
  t2.kpi_luxury,
  t2.kpi_premium,
  t2.kpi_casual
FROM
  `bsi-gdh-mart-prod.GDH_US_VIEW.dim_product_fintech` AS t1
LEFT JOIN
  `sgs-ds-analytics-dev.SGS_DS.sgs_product_list` AS t2
ON
  t1.product_key = t2.product_key;
