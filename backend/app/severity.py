def classify_severity(log: str) -> str:
    log_lower = log.lower()

    if "critical" in log_lower or "fatal" in log_lower:
        return "HIGH"
    elif "error" in log_lower:
        return "HIGH"
    elif "warn" in log_lower or "warning" in log_lower:
        return "MEDIUM"
    elif "timeout" in log_lower or "failed" in log_lower:
        return "MEDIUM"
    else:
        return "LOW"