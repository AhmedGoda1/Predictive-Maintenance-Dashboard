from db_manager import init_db, insert_machine, insert_reading, insert_alert, get_recent_readings, get_latest_alert

# 1. Initialize tables
init_db()

# 2. Add sample machine matching the wood-processing context
insert_machine("MTR_01", "Sawmill Main Drive", "Electric Motor", "Line A")

# 3. Insert mock readings
insert_reading("MTR_01", vibration=1.45, temperature=52.3, current=11.2)
insert_reading("MTR_01", vibration=2.85, temperature=67.1, current=13.8)

# 4. Insert a mock warning
insert_alert(
    machine_id="MTR_01",
    status_level="Warning",
    detected_issue="High vibration and temperature trend",
    suggested_action="Inspect bearing lubrication and alignment"
)

# 5. Fetch and print the records
print("--- Recent Readings ---")
print(get_recent_readings("MTR_01"))

print("\n--- Latest Alert ---")
print(get_latest_alert("MTR_01"))