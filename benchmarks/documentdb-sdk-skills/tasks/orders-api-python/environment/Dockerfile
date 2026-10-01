ARG DOCUMENTDB_BENCH_BASE=documentdb-orders-base:latest
FROM ${DOCUMENTDB_BENCH_BASE}

ENV SDK="python"

# Bake the reference implementation in. solve.sh copies it into /app when the
# oracle runs. The agent under evaluation never sees /reference.
COPY environment/reference /reference

# Pre-install the reference impl's dependencies from the vendored wheels, so
# the oracle's /app/build.sh works with NO internet access during grading —
# which is what the task instruction promises the agent.
COPY .wheels /opt/wheels
RUN pip3 install --no-cache-dir --no-index --find-links=/opt/wheels \
        -r /reference/requirements.txt

WORKDIR /app
