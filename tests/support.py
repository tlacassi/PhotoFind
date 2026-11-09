"""Keep application import and startup migrations away from real local data."""
import os
import tempfile

application_data = tempfile.TemporaryDirectory(prefix='photofind-tests-')
os.environ['DATA_DIR'] = application_data.name
