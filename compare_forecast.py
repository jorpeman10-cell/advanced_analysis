import pandas as pd
import json

# Read Excel
excel_path = r'C:\Users\EDY\recruiter_finance_tool\watched\forecast\forecastassignment_202604211141.xlsx'
df_excel = pd.read_excel(excel_path)

print("=" * 60)
print("EXCEL vs DATABASE FIELD MAPPING ANALYSIS")
print("=" * 60)

# Decode Chinese column names
columns = df_excel.columns.tolist()
print(f"\nExcel has {len(columns)} columns:")
for i, c in enumerate(columns):
    print(f"  {i+1}. {c}")

print(f"\nExcel total rows: {len(df_excel)}")

# Analyze first row
print("\n--- First Row Sample ---")
row = df_excel.iloc[0]
for c in columns:
    print(f"  {c}: {row[c]}")

# Check data types
print("\n--- Data Types ---")
for c in columns:
    print(f"  {c}: {df_excel[c].dtype}")

# Check for nulls
print("\n--- Null Counts ---")
for c in columns:
    null_count = df_excel[c].isna().sum()
    print(f"  {c}: {null_count} nulls")

print("\n" + "=" * 60)
print("FIELD MAPPING TO DATABASE")
print("=" * 60)

mapping = """
Excel Field              | Database Table.Field
-------------------------|---------------------------
添加时间                 | forecast.dateAdded
用户                     | user.englishName + chineseName
角色                     | forecastassignment.role
客户                     | client.name
项目                     | joborder.jobTitle
开始时间                 | joborder.openDate
职位编号                 | joborder.id
年薪级                   | joborder.positionLevel (or annualSalary)
合同                     | (not in DB, possibly clientcontract)
最新进展                 | forecast.last_stage
预计进展                 | NOT IN DATABASE (close_rate is NULL)
实际面试轮次             | joborder.max_interview_round
有效候选人数             | joborder.effective_candidate_count
收费基数                 | forecast.charge_package
费率                     | forecast.fee_rate (decimal, e.g. 0.2 = 20%)
Forecast * 成功率        | forecast.forecast_fee (pre-calculated)
成功率                   | NOT IN DATABASE (could derive from forecast_fee/charge_package/fee_rate)
比例                     | forecastassignment.ratio (e.g. 90 = 90%)
Forecast分配             | forecastassignment.amount_after_tax
预计成单时间             | forecast.close_date
更新时间                 | forecast.lastUpdateDate
更新人                   | user.englishName + chineseName
Forecast备注             | forecast.note
"""
print(mapping)

# Calculate success rate from data
print("\n--- Reverse Engineering Success Rate ---")
for i in range(min(5, len(df_excel))):
    row = df_excel.iloc[i]
    charge = row[columns[13]] if pd.notna(row[columns[13]]) else 0  # 收费基数
    fee_rate = row[columns[14]] if pd.notna(row[columns[14]]) else 0  # 费率
    forecast_val = row[columns[15]] if pd.notna(row[columns[15]]) else 0  # Forecast * 成功率
    ratio = row[columns[17]] if pd.notna(row[columns[17]]) else 0  # 比例
    allocation = row[columns[18]] if pd.notna(row[columns[18]]) else 0  # Forecast分配
    
    if charge > 0 and fee_rate > 0:
        total_fee = charge * fee_rate
        success_rate = forecast_val / total_fee if total_fee > 0 else 0
        check = forecast_val * (ratio / 100) if ratio > 0 else 0
        print(f"Row {i+1}: charge={charge}, fee_rate={fee_rate}, total_fee={total_fee:.0f}, forecast={forecast_val}, ratio={ratio}%, allocation={allocation}, implied_success_rate={success_rate:.2%}, check={check:.0f}")
