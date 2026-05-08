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

# Step by step debug
queries = [
    ("step1_add_joborder", """
SELECT fa.id, f.id AS forecast_id, f.last_stage, jo.jobTitle
FROM forecastassignment fa
JOIN forecast f ON fa.forecast_id = f.id
LEFT JOIN joborder jo ON f.job_order_id = jo.id
WHERE f.close_date >= '2026-01-01' AND f.close_date <= '2026-12-31'
LIMIT 3
"""),
    ("step2_add_client", """
SELECT fa.id, f.id AS forecast_id, f.last_stage, jo.jobTitle, c.name
FROM forecastassignment fa
JOIN forecast f ON fa.forecast_id = f.id
LEFT JOIN joborder jo ON f.job_order_id = jo.id
LEFT JOIN client c ON jo.client_id = c.id
WHERE f.close_date >= '2026-01-01' AND f.close_date <= '2026-12-31'
LIMIT 3
"""),
    ("step3_add_user", """
SELECT fa.id, f.id AS forecast_id, f.last_stage, jo.jobTitle, c.name, ua.englishName
FROM forecastassignment fa
JOIN forecast f ON fa.forecast_id = f.id
LEFT JOIN joborder jo ON f.job_order_id = jo.id
LEFT JOIN client c ON jo.client_id = c.id
LEFT JOIN user ua ON fa.user_id = ua.id
WHERE f.close_date >= '2026-01-01' AND f.close_date <= '2026-12-31'
LIMIT 3
"""),
    ("step4_add_fields", """
SELECT 
    fa.id AS assignment_id,
    f.id AS forecast_id,
    jo.id AS joborder_id,
    jo.jobTitle AS position_name,
    c.name AS client_name,
    f.charge_package,
    f.fee_rate,
    f.forecast_fee,
    f.close_date,
    f.last_stage AS stage,
    fa.role AS assignment_role,
    fa.ratio AS assignment_ratio,
    fa.amount_after_tax AS assignment_amount,
    CONCAT(IFNULL(ua.englishName, ''), ' ', IFNULL(ua.chineseName, '')) AS consultant
FROM forecastassignment fa
JOIN forecast f ON fa.forecast_id = f.id
LEFT JOIN joborder jo ON f.job_order_id = jo.id
LEFT JOIN client c ON jo.client_id = c.id
LEFT JOIN user ua ON fa.user_id = ua.id
WHERE f.close_date >= '2026-01-01' AND f.close_date <= '2026-12-31'
LIMIT 5
"""),
    ("step5_add_more_users", """
SELECT 
    fa.id AS assignment_id,
    f.id AS forecast_id,
    jo.id AS joborder_id,
    jo.jobTitle AS position_name,
    c.name AS client_name,
    f.charge_package,
    f.fee_rate,
    f.forecast_fee,
    f.close_date,
    f.last_stage AS stage,
    fa.role AS assignment_role,
    fa.ratio AS assignment_ratio,
    fa.amount_after_tax AS assignment_amount,
    CONCAT(IFNULL(ua.englishName, ''), ' ', IFNULL(ua.chineseName, '')) AS consultant,
    CONCAT(IFNULL(ub.englishName, ''), ' ', IFNULL(ub.chineseName, '')) AS added_by
FROM forecastassignment fa
JOIN forecast f ON fa.forecast_id = f.id
LEFT JOIN joborder jo ON f.job_order_id = jo.id
LEFT JOIN client c ON jo.client_id = c.id
LEFT JOIN user ua ON fa.user_id = ua.id
LEFT JOIN user ub ON f.addedBy_id = ub.id
WHERE f.close_date >= '2026-01-01' AND f.close_date <= '2026-12-31'
LIMIT 5
"""),
    ("step6_add_last_update", """
SELECT 
    fa.id AS assignment_id,
    f.id AS forecast_id,
    jo.id AS joborder_id,
    jo.jobTitle AS position_name,
    c.name AS client_name,
    f.charge_package,
    f.fee_rate,
    f.forecast_fee,
    f.close_date,
    f.last_stage AS stage,
    fa.role AS assignment_role,
    fa.ratio AS assignment_ratio,
    fa.amount_after_tax AS assignment_amount,
    CONCAT(IFNULL(ua.englishName, ''), ' ', IFNULL(ua.chineseName, '')) AS consultant,
    CONCAT(IFNULL(ub.englishName, ''), ' ', IFNULL(ub.chineseName, '')) AS added_by,
    CONCAT(IFNULL(uc.englishName, ''), ' ', IFNULL(uc.chineseName, '')) AS last_update_by
FROM forecastassignment fa
JOIN forecast f ON fa.forecast_id = f.id
LEFT JOIN joborder jo ON f.job_order_id = jo.id
LEFT JOIN client c ON jo.client_id = c.id
LEFT JOIN user ua ON fa.user_id = ua.id
LEFT JOIN user ub ON f.addedBy_id = ub.id
LEFT JOIN user uc ON f.lastUpdateBy_id = uc.id
WHERE f.close_date >= '2026-01-01' AND f.close_date <= '2026-12-31'
LIMIT 5
"""),
    ("step7_add_joborder_fields", """
SELECT 
    fa.id AS assignment_id,
    f.id AS forecast_id,
    jo.id AS joborder_id,
    jo.jobTitle AS position_name,
    c.name AS client_name,
    f.charge_package,
    f.fee_rate,
    f.forecast_fee,
    f.close_date,
    f.last_stage AS stage,
    fa.role AS assignment_role,
    fa.ratio AS assignment_ratio,
    fa.amount_after_tax AS assignment_amount,
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
