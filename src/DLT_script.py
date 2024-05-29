# Databricks notebook source
import dlt
from pyspark.sql import functions as F

# COMMAND ----------

# DBTITLE 1,Bronze Layer
@dlt.create_table(comment="New raw loan data incrementally ingested from cloud object storage landing zone")
def raw_txs():
  return (
    spark.readStream.format("cloudFiles")
      .option("cloudFiles.format", "json")
      .option("cloudFiles.inferColumnTypes", "true")
      .load("/demos/dlt/loans/raw_transactions"))
  
@dlt.create_table(comment="Lookup mapping for accounting codes")
def ref_accounting_treatment():
  return spark.read.format("delta").load("/demos/dlt/loans/ref_accounting_treatment")

# COMMAND ----------

# DBTITLE 1,Silver Layer
@dlt.create_view(comment="Livestream of new transactions")
def new_txs():
  txs = dlt.read_stream("raw_txs").alias("txs")
  ref = dlt.read("ref_accounting_treatment").alias("ref")
  return (
    txs.join(ref, F.col("txs.accounting_treatment_id") == F.col("ref.id"), "inner")
      .selectExpr("txs.*", "ref.accounting_treatment as accounting_treatment"))
  
@dlt.create_table(comment="Livestream of new transactions, cleaned and compliant")
@dlt.expect("Payments should be this year", "(next_payment_date > date('2020-12-31'))")
@dlt.expect_or_drop("Balance should be positive", "(balance > 0 AND arrears_balance > 0)")
@dlt.expect_or_fail("Cost center must be specified", "(cost_center_code IS NOT NULL)")
def cleaned_new_txs():
  return dlt.read_stream("new_txs")

# COMMAND ----------

# DBTITLE 1,Gold Layer
@dlt.create_table(
  comment="Live table of new loan balances for consumption by different cost centers")
def new_loan_balances_by_cost_center():
  return (
    dlt.read("cleaned_new_txs")
      .groupBy("cost_center_code")
      .agg(F.sum("balance").alias("sum_balance"))
  )