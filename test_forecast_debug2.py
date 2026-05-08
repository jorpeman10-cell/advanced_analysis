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

queries = [
    ("step6_ok", """
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
LIMIT 3
"""),
    ("step7a_add_openDate", """
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
    jo.openDate AS job_open_date
FROM forecastassignment fa
JOIN forecast f ON fa.forecast_id = f.id
LEFT JOIN joborder jo ON f.job_order_id = jo.id
LEFT JOIN client c ON jo.client_id = c.id
LEFT JOIN user ua ON fa.user_id = ua.id
LEFT JOIN user ub ON f.addedBy_id = ub.id
LEFT JOIN user uc ON f.lastUpdateBy_id = uc.id
WHERE f.close_date >= '2026-01-01' AND f.close_date <= '2026-12-31'
LIMIT 3
"""),
    ("step7b_add_max_interview", """
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
    jo.max_interview_round
FROM forecastassignment fa
JOIN forecast f ON fa.forecast_id = f.id
LEFT JOIN joborder jo ON f.job_order_id = jo.id
LEFT JOIN client c ON jo.client_id = c.id
LEFT JOIN user ua ON fa.user_id = ua.id
LEFT JOIN user ub ON f.addedBy_id = ub.id
LEFT JOIN user uc ON f.lastUpdateBy_id = uc.id
WHERE f.close_date >= '2026-01-01' AND f.close_date <= '2026-12-31'
LIMIT 3
"""),
    ("step7c_add_effective", """
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
    jo.effective_candidate_count
FROM forecastassignment fa
JOIN forecast f ON fa.forecast_id = f.id
LEFT JOIN joborder jo ON f.job_order_id = jo.id
LEFT JOIN client c ON jo.client_id = c.id
LEFT JOIN user ua ON fa.user_id = ua.id
LEFT JOIN user ub ON f.addedBy_id = ub.id
LEFT JOIN user uc ON f.lastUpdateBy_id = uc.id
WHERE f.close_date >= '2026-01-01' AND f.close_date <= '2026-12-31'
LIMIT 3
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
