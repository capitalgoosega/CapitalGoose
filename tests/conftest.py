import os
import sys

# Pure-logic tests need none of this; integration tests set up a throwaway DB.
os.environ.setdefault("DISABLE_WEBHOOK_WORKER", "1")
os.environ.setdefault("ADMIN_API_KEY", "test-admin-key")
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
