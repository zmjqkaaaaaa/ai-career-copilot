WEIGHTS = {"education": 10, "product": 25, "ai": 25, "data": 15, "practice": 20, "industry": 5}
EVIDENCE = {"verified": 1.0, "resume_supported": 0.8, "self_reported": 0.8, "inferred": 0.5}
# Relative to one hard requirement. Keep the denominator independent of resume evidence.
IMPORTANCE_WEIGHT = {"required": 8, "preferred": 4, "optional": 2, "unknown": 1}
VERSION = "job-match-v10"
DIMENSIONS = {"programming": "data", "communication": "product"}
