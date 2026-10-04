"""Container healthcheck for the arq worker: is its heartbeat sentinel present in Redis?

`arq --check` would do the same, but it imports the whole worker module (torch, transformers, faiss), which can
take longer than a healthcheck timeout on a small CI runner. This only needs the redis client.
"""

import os
import sys

import redis

QUEUE = os.environ.get("DOCAGENT_ARQ_QUEUE", "arq:queue")
KEY = f"{QUEUE}:health-check"  # arq: default_queue_name + health_check_key_suffix

try:
    client = redis.Redis.from_url(os.environ.get("DOCAGENT_REDIS_URL", "redis://localhost:6379"), socket_timeout=3)
    value = client.get(KEY)
except redis.RedisError as e:
    print(f"redis unavailable: {e}")
    sys.exit(1)
if not value:
    print("no worker heartbeat yet")
    sys.exit(1)
print(value.decode(errors="replace"))
