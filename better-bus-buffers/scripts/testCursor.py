import sqlite3
import time

SQLDbase = r'E:\TransitToolTests\LineFrequency\TANK.sql'
conn = sqlite3.connect(SQLDbase)
c = conn.cursor()

stoptimefetch = '''
    SELECT trip_id, stop_id, arrival_time, departure_time
    FROM stop_times
    ORDER BY trip_id, stop_sequence
    ;'''
c.execute(stoptimefetch)

# count = 0
# while True:
#     count += 1
#     if count > 10:
#         break
#     st = c.fetchone()
#     print(st)
#     if not st:
#         break

count = 0
t1 = time.time()
for st in c:
    continue
    # count += 1
    # if count > 10:
    #     break
    #print(st)
t2 = time.time()
print("Time to loop over all: ", t2-t1)

stoptimefetch = '''
    SELECT trip_id, stop_id, arrival_time, departure_time
    FROM stop_times
    ORDER BY trip_id, stop_sequence
    ;'''
c.execute(stoptimefetch)
t1 = time.time()
stoptimes = c.fetchall()
for st in stoptimes:
    continue
t2 = time.time()
print("Time to loop over all: ", t2-t1)