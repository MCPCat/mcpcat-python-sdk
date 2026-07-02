import os

# Belt-and-suspenders: force diagnostics off before any test imports/runs, so no
# test ordering or future change to the auto-disable detection can ever ship OTLP
# diagnostics to the live collector from our own suite. Diagnostics-specific tests
# opt back in explicitly with DISABLE_DIAGNOSTICS=false plus mocked HTTP.
os.environ["DISABLE_DIAGNOSTICS"] = "true"
