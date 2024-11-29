#!/bin/bash

CLEANUP_DIR="${1}"

function cleanup_links()
    {
    local DIRECTORY_TO_CLEAN="${1}"
    local IFS="
"
    for A_FILE in $(find "${DIRECTORY_TO_CLEAN}" -type l)
    do
    rm "${A_FILE}"
    done
    }

function cleanup_files()
    {
    local DIRECTORY_TO_CLEAN="${1}"
    local IFS="
"
    for A_FILE in $(find "${DIRECTORY_TO_CLEAN}" -type f)
    do
        rm "${A_FILE}"
    done
    }


function cleanup_directories()
    {
    local DIRECTORY_TO_CLEAN="${1}"
    printf "Cleaning directory: ${DIRECTORY_TO_CLEAN}\n"

    local IFS="
"
    for A_DIR in $(find "${DIRECTORY_TO_CLEAN}" -maxdepth 1 -type d)
    do
        if [ "${A_DIR}" != "${DIRECTORY_TO_CLEAN}" ]; then
            printf "\tFound Directory ${A_DIR}\n"
            cleanup_directories "${A_DIR}"
        fi
    done
    printf "Removing directory: ${DIRECTORY_TO_CLEAN}\n"
    rmdir "${DIRECTORY_TO_CLEAN}"
    }

cleanup_links "${CLEANUP_DIR}"
cleanup_files "${CLEANUP_DIR}"
cleanup_directories "${CLEANUP_DIR}"
