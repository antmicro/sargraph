#!/bin/bash

set -e

tuttest README.md | grep -v '^\$' | bash -
