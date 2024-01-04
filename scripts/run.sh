#!/bin/bash

MAIL_DIRECTORY="${1}"
STORAGE_DIRECTORY="${2}"


if [ ! -d "${STORAGE_DIRECTORY}" ]; then
    mkdir -p "${STORAGE_DIRECTORY}"
fi

tb-dedup do --location "${MAIL_DIRECTORY}" --storage-location "${STORAGE_DIRECTORY}"
