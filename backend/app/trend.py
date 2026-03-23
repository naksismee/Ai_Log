from collections import defaultdict
from datetime import datetime

def extract_timestamp(log):
    try:
        return datetime.strptime(log[:19], "%Y-%m-%d %H:%M:%S")
    except:
        return None

def analyze_trends(logs):
    time_buckets = defaultdict(int)

    for log in logs:
        ts = extract_timestamp(log)
        if ts:
            key = ts.strftime("%Y-%m-%d %H:00")
            time_buckets[key] += 1

    return dict(time_buckets)