# Copyright 2026 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     https://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import os

# =====================================================================
# Model Config
# =====================================================================
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")

# =====================================================================
# Deterministic Low-Risk Triage Settings
# =====================================================================

# Extensions that are considered low-risk (e.g. docs, configs, locks)
LOW_RISK_EXTENSIONS = {".md", ".txt", ".json", ".lock", ".yaml", ".yml"}

# PR title/description prefixes that flag low-risk changes
LOW_RISK_PREFIXES = ["docs:", "doc:", "chore:", "formatting:", "style:"]

# Thresholds to ensure a PR isn't too large to be auto-approved
MAX_FILES_FOR_LOW_RISK = 5
MAX_LINES_CHANGED_FOR_LOW_RISK = 50

# =====================================================================
# High-Risk / Security Sensitive Settings
# =====================================================================

# Substrings in file paths that immediately flag a PR as high-risk
SECURITY_SENSITIVE_PATHS = {
    "auth",
    "security",
    "login",
    "payment",
    "billing",
    "private",
    "key",
    "secret",
}
