#!/usr/bin/env bash

# Shared command transport for DocumentDB diagnostics.
#
# Normal Linux invocation runs Docker from the host. The portable Python
# launcher copies the script into the DocumentDB container and sets
# DOCDB_DIRECT=1, so the same diagnostic logic calls mongosh/psql directly.

docdb_exec_as() {
    local user="$1"
    shift
    if [[ "${DOCDB_DIRECT:-0}" == "1" ]]; then
        "$@"
    elif [[ -n "$user" ]]; then
        docker exec -u "$user" "$CONTAINER_NAME" "$@"
    else
        docker exec "$CONTAINER_NAME" "$@"
    fi
}

docdb_exec_stdin_as() {
    local user="$1"
    shift
    if [[ "${DOCDB_DIRECT:-0}" == "1" ]]; then
        "$@"
    elif [[ -n "$user" ]]; then
        docker exec -i -u "$user" "$CONTAINER_NAME" "$@"
    else
        docker exec -i "$CONTAINER_NAME" "$@"
    fi
}
