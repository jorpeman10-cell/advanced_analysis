from gllue_db_client import GllueDBConfig, GllueDBClient

config = GllueDBConfig(
    db_type="mysql",
    host="127.0.0.1",
    port=3306,
    database="gllue",
    username="debian-sys-maint",
    password="IfUntY7bQZN5kDsk",
    use_ssh=True,
    ssh_host="118.190.96.172",
    ssh_port=9998,
    ssh_user="root",
    ssh_password="Tstar2026!"
)

client = GllueDBClient(config)

# Test the full query step by step
queries = [
    ("basic_join", """
SELECT fa.id, f.id AS forecast_id, f.last_stage
FROM forecastassignment fa
JOIN forecast f ON fa.forecast_id = f.id
WHERE f.close_date >= '2026-01-01' AND f.close_date <= '2026-12-31'
LIMIT 3
"""),
    ("with_case", """
SELECT 
    fa.id, f.id AS forecast_id, f.last_stage,
    CASE 
        WHEN f.last_stage LIKE '%Shortlist%' THEN 10
        WHEN f.last_stage LIKE '%CCM 1st%' THEN 25
        ELSE 10
    END AS success_rate
FROM forecastassignment fa
JOIN forecast f ON fa.forecast_id = f.id
WHERE f.close_date >= '2026-01-01' AND f.close_date <= '2026-12-31'
LIMIT 3
"""),
    ("full_query", """
SELECT 
    fa.id AS assignment_id,
    f.id AS forecast_id,
    jo.id AS joborder_id,
    jo.jobTitle AS position_name,
    c.name AS client_name,
    f.charge_package,
    f.fee_rate,
    f.forecast_fee,
    f.forecast_fee_after_tax,
    f.forecast_one_hundred_percent,
    f.close_date,
    f.last_stage AS stage,
    CASE 
        WHEN f.last_stage LIKE '%Shortlist%' OR f.last_stage LIKE '%简历推荐%' OR f.last_stage LIKE '%Longlist%' THEN 10
        WHEN f.last_stage LIKE '%CCM 1st%' OR f.last_stage LIKE '%客户1面%' OR f.last_stage LIKE '%1st%' THEN 25
        WHEN f.last_stage LIKE '%CCM 2nd%' OR f.last_stage LIKE '%客户2面%' OR f.last_stage LIKE '%2nd%' THEN 30
        WHEN f.last_stage LIKE '%CCM 3rd%' OR f.last_stage LIKE '%客户3面%' OR f.last_stage LIKE '%3rd%' THEN 40
        WHEN f.last_stage LIKE '%Final%' OR f.last_stage LIKE '%终面%' THEN 50
        WHEN f.last_stage LIKE '%Offer%' AND f.last_stage NOT LIKE '%签署%' THEN 80
        WHEN f.last_stage LIKE '%Onboard%' OR f.last_stage LIKE '%入职%' THEN 100
        WHEN f.last_stage LIKE '%加入项目%' OR f.last_stage LIKE '%New%' THEN 5
        ELSE 10
    END AS success_rate,
    f.tax_rate,
    f.dateAdded AS date_added,
    f.lastUpdateDate AS last_update_date,
    f.note,
    fa.role AS assignment_role,
    fa.ratio AS assignment_ratio,
    fa.amount_after_tax AS assignment_amount,
    fa.amount_before_tax AS assignment_amount_before_tax,
    fa.amount_one_hundred_percent AS assignment_amount_100,
    CONCAT(IFNULL(ua.englishName, ''), ' ', IFNULL(ua.chineseName, '')) AS consultant,
    CONCAT(IFNULL(ub.englishName, ''), ' ', IFNULL(ub.chineseName, '')) AS added_by,
    CONCAT(IFNULL(uc.englishName, ''), ' ', IFNULL(uc.chineseName, '')) AS last_update_by,
    jo.openDate AS job_open_date,
    jo.max_interview_round,
    jo.effective_candidate_count
FROM forecastassignment fa
JOIN forecast f ON fa.forecast_id = f.id
LEFT JOIN joborder jo ON f.job_order_id = jo.id
LEFT JOIN client c ON jo.client_id = c.id
LEFT JOIN user ua ON fa.user_id = ua.id
LEFT JOIN user ub ON f.addedBy_id = ub.id
LEFT JOIN user uc ON f.lastUpdateBy_id = uc.id
WHERE f.close_date >= '2026-01-01' AND f.close_date <= '2026-12-31'
ORDER BY f.close_date DESC
LIMIT 5
"""),
]

for name, sql in queries:
    print(f"\n=== {name} ===")
    try:
        df = client.query(sql)
        print(f"Rows: {len(df)}")
        if not df.empty:
            print(df.to_string())
    except Exception as e:
        print(f"ERROR: {e}")
