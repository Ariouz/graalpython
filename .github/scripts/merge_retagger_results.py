

# ================================
# 
# OK- Read No of retagger batches
# Artifact is exported as python-unittest-retagger-gate-batch{NO}-{OS}-{ARCH}-jdk-latest_logs
# 
# extract-matrix => if job.name = retagger => store in reports list
# list => new job => require_artifacts: reports list
# 
# Download all artifacts => extraxt => filter by name retagger-report
# Merge => report-merged.json
# run mx merge-tags-from-report => git diff => export git diff artifact
#
# ================================


if __name__ == "main":
    pass