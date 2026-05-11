#!/bin/bash
# Serial Reader for Rotary Encoder IOC
# Reads Arduino serial data and updates EPICS PVs via caput
# Usage: serial_reader.sh <PV_PREFIX> [PORT]
# Example: serial_reader.sh RE:ch0: /dev/ttyACM0

set -u

# Arguments
PV_PREFIX="${1:-RE:ch0:}"
SERIAL_PORT="${2:-/dev/ttyACM0}"
BAUD_RATE="${3:-115200}"

# EPICS base
EPICS_BASE=${EPICS_BASE:-/home/rpi/epics-base}
EPICS_BIN="${EPICS_BASE}/bin/linux-aarch64"

# Timeout for opening serial port
TIMEOUT=30

# Log file
LOG_DIR=$(dirname "$0")
LOG_FILE="${LOG_DIR}/serial_reader.log"

# Functions
log_info() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] INFO: $*" >> "$LOG_FILE"
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] INFO: $*"
}

log_error() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] ERROR: $*" >> "$LOG_FILE" >&2
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] ERROR: $*" >&2
}

# Check serial port
if [ ! -e "$SERIAL_PORT" ]; then
    log_error "Serial port $SERIAL_PORT not found"
    exit 1
fi

# Check caput availability
if ! command -v caput &> /dev/null; then
    if [ ! -x "${EPICS_BIN}/caput" ]; then
        log_error "caput not found in PATH or EPICS_BIN"
        exit 1
    fi
    export PATH="${EPICS_BIN}:${PATH}"
fi

log_info "Starting Serial Reader"
log_info "PV Prefix: $PV_PREFIX"
log_info "Serial Port: $SERIAL_PORT @ $BAUD_RATE baud"

# Open serial port and read data
# Format expected: ENC1:value,ENC2:value,MTR1:value,MTR2:value,SYNC:value
stdbuf -oL cat "$SERIAL_PORT" 2>/dev/null | while IFS= read -r line; do
    
    # Skip empty lines and debug output
    if [ -z "$line" ] || [ "${line:0:4}" != "ENC1" ]; then
        continue
    fi
    
    # Log raw data (debug)
    log_info "Raw: $line"
    
    # Parse CSV format: ENC1:120,ENC2:-45,MTR1:2400,MTR2:1500,SYNC:0
    IFS=',' read -ra FIELDS <<< "$line"
    
    for field in "${FIELDS[@]}"; do
        IFS=':' read -ra KV <<< "$field"
        if [ ${#KV[@]} -eq 2 ]; then
            key="${KV[0]}"
            value="${KV[1]}"
            
            case "$key" in
                ENC1)
                    PV="${PV_PREFIX}ENC1:POSITION"
                    caput "$PV" "$value" >/dev/null 2>&1 || log_error "Failed to update $PV"
                    ;;
                ENC2)
                    PV="${PV_PREFIX}ENC2:POSITION"
                    caput "$PV" "$value" >/dev/null 2>&1 || log_error "Failed to update $PV"
                    ;;
                MTR1)
                    PV="${PV_PREFIX}MTR1:POSITION"
                    caput "$PV" "$value" >/dev/null 2>&1 || log_error "Failed to update $PV"
                    ;;
                MTR2)
                    PV="${PV_PREFIX}MTR2:POSITION"
                    caput "$PV" "$value" >/dev/null 2>&1 || log_error "Failed to update $PV"
                    ;;
                SYNC)
                    PV="${PV_PREFIX}SYNC:MODE"
                    caput "$PV" "$value" >/dev/null 2>&1 || log_error "Failed to update $PV"
                    ;;
                *)
                    # Unknown key - ignore
                    ;;
            esac
        fi
    done
    
done

log_error "Serial reader loop ended"
