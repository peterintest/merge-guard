# Copyright 2026 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import asyncio
import logging
import os
import time
from typing import Any

import google.auth
import google.auth.transport.requests
import requests
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse
from google.adk.sessions.vertex_ai_session_service import VertexAiSessionService
from pydantic import BaseModel

# Configure Logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Environment Configuration
PROJECT_ID = os.environ.get("GOOGLE_CLOUD_PROJECT", "gen-lang-client-0530918788")
LOCATION = (
    os.environ.get("GOOGLE_CLOUD_LOCATION")
    or os.environ.get("GOOGLE_CLOUD_AGENT_ENGINE_LOCATION")
    or "us-central1"
)
AGENT_RUNTIME_ID = os.environ.get("AGENT_RUNTIME_ID", "429054176169820160")

# Server-Side Cache for Triage History Logs to maximize API speed
HISTORY_CACHE = {
    "timestamp": 0.0,
    "data": None
}
CACHE_TTL = 10.0  # Cache history logs for 10 seconds

logger.info(
    f"Loaded GCP Configuration - Project: {PROJECT_ID}, Location: {LOCATION}, EngineID: {AGENT_RUNTIME_ID}"
)

app = FastAPI(
    title="Engineering Quality Dashboard Service",
    description="Quality dashboard and API middleware for the Pull Request Triage Agent.",
)

# Enable CORS for local development
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Pydantic Schemas for Actions
class ActionRequest(BaseModel):
    approved: bool
    comments: str = ""


# Inline Gorgeous Glassmorphism HTML/CSS/JS Dashboard
DASHBOARD_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>MergeGuard: PR Triage &amp; Quality Agent</title>
    <!-- Outfit & Fira Code Google Fonts -->
    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
    <link href="https://fonts.googleapis.com/css2?family=Fira+Code:wght@400;500&family=Outfit:wght@300;400;500;600;700;800&display=swap" rel="stylesheet">
    <style>
        :root {
            --bg-base: #090a10;
            --bg-radial: radial-gradient(circle at 50% 50%, #1e1b4b 0%, #090a10 70%);
            --glass-bg: rgba(255, 255, 255, 0.03);
            --glass-border: rgba(255, 255, 255, 0.08);
            --glass-border-hover: rgba(255, 255, 255, 0.18);
            --text-primary: #f8fafc;
            --text-secondary: #94a3b8;
            --text-muted: #64748b;
            --accent-primary: #818cf8;
            --accent-glow: rgba(129, 140, 248, 0.15);
            --danger-bg: rgba(239, 68, 68, 0.12);
            --danger-text: #f87171;
            --danger-border: rgba(239, 68, 68, 0.25);
            --warning-bg: rgba(245, 158, 11, 0.12);
            --warning-text: #fbbf24;
            --warning-border: rgba(245, 158, 11, 0.25);
            --success-bg: rgba(16, 185, 129, 0.12);
            --success-text: #34d399;
            --success-border: rgba(16, 185, 129, 0.25);
        }

        /* Modal Main Tabs (Unified Flat Navigation) */
        .modal-main-tabs {
            display: flex;
            border-bottom: 1px solid var(--glass-border);
            margin-bottom: 1.25rem;
            gap: 1.5rem;
            overflow-x: auto;
            white-space: nowrap;
            scrollbar-width: none; /* Firefox */
            flex-shrink: 0;
            height: 48px;
            align-items: center;
        }

        .modal-main-tabs::-webkit-scrollbar {
            display: none; /* Chrome/Safari */
        }

        .main-tab-btn {
            background: transparent;
            border: none;
            border-bottom: 2px solid transparent;
            padding: 0.75rem 0.5rem;
            color: var(--text-muted);
            font-size: 0.92rem;
            font-weight: 600;
            cursor: pointer;
            display: flex;
            align-items: center;
            gap: 0.5rem;
            transition: all 0.2s cubic-bezier(0.4, 0, 0.2, 1);
            outline: none;
            flex-shrink: 0;
        }

        .main-tab-btn:hover {
            color: var(--text-secondary);
        }

        .main-tab-btn.active {
            color: var(--accent-primary);
            border-bottom-color: var(--accent-primary);
        }

        .main-tab-btn.active .tab-icon {
            fill: var(--accent-primary) !important;
        }

        .main-tab-btn .tab-icon {
            width: 16px;
            height: 16px;
            fill: currentColor;
            transition: fill 0.2s ease;
        }

        .main-panel {
            display: none;
            flex-direction: column;
            flex: 1;
            min-height: 0;
            overflow-y: auto;
            animation: panelFadeIn 0.25s cubic-bezier(0.4, 0, 0.2, 1);
        }

        .main-panel.active {
            display: flex;
        }

        @keyframes panelFadeIn {
            from { opacity: 0; transform: scale(0.995); }
            to { opacity: 1; transform: scale(1); }
        }

        * {
            box-sizing: border-box;
            margin: 0;
            padding: 0;
        }

        body {
            font-family: 'Outfit', sans-serif;
            background-color: var(--bg-base);
            background-image: var(--bg-radial);
            color: var(--text-primary);
            min-height: 100vh;
            overflow-x: hidden;
            line-height: 1.5;
            -webkit-font-smoothing: antialiased;
        }

        /* Scrollbar styling */
        ::-webkit-scrollbar {
            width: 8px;
            height: 8px;
        }
        ::-webkit-scrollbar-track {
            background: rgba(0, 0, 0, 0.2);
        }
        ::-webkit-scrollbar-thumb {
            background: rgba(255, 255, 255, 0.1);
            border-radius: 4px;
        }
        ::-webkit-scrollbar-thumb:hover {
            background: rgba(255, 255, 255, 0.2);
        }

        /* App Layout */
        header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            padding: 1rem 3rem;
            border-bottom: 1px solid var(--glass-border);
            backdrop-filter: blur(8px);
            background: rgba(9, 10, 16, 0.6);
            position: sticky;
            top: 0;
            z-index: 100;
        }

        .header-title-area {
            display: flex;
            align-items: center;
            gap: 0.5rem;
        }

        .header-title-area h1 {
            font-size: 1.8rem;
            font-weight: 700;
            background: linear-gradient(135deg, #fff 40%, #818cf8 100%);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
            letter-spacing: -0.02em;
        }

        .status-pill {
            background: rgba(16, 185, 129, 0.1);
            border: 1px solid rgba(16, 185, 129, 0.2);
            color: #34d399;
            padding: 0.3rem 0.8rem;
            border-radius: 9999px;
            font-size: 0.8rem;
            font-weight: 600;
            display: flex;
            align-items: center;
            gap: 0.5rem;
        }

        .status-dot {
            width: 8px;
            height: 8px;
            background: #10b981;
            border-radius: 50%;
            display: inline-block;
            box-shadow: 0 0 8px #10b981;
            animation: pulse 2s infinite;
        }

        @keyframes pulse {
            0% { transform: scale(0.9); opacity: 0.6; }
            50% { transform: scale(1.15); opacity: 1; }
            100% { transform: scale(0.9); opacity: 0.6; }
        }

        main {
            padding: 3rem 4rem;
            max-width: 1600px;
            margin: 0 auto;
        }

        .section-header {
            margin-bottom: 2.5rem;
            display: flex;
            justify-content: space-between;
            align-items: center;
        }

        .section-header h2 {
            font-size: 1.4rem;
            font-weight: 600;
            color: var(--text-primary);
            letter-spacing: -0.01em;
        }

        .refresh-btn,
        .help-btn {
            background: var(--glass-bg);
            border: 1px solid var(--glass-border);
            color: var(--text-primary);
            padding: 0.6rem 1.2rem;
            border-radius: 12px;
            cursor: pointer;
            font-weight: 500;
            display: flex;
            align-items: center;
            gap: 0.6rem;
            transition: all 0.3s cubic-bezier(0.16, 1, 0.3, 1);
        }

        .refresh-btn:hover,
        .help-btn:hover {
            background: rgba(255, 255, 255, 0.08);
            border-color: var(--glass-border-hover);
            transform: translateY(-2px);
        }

        @keyframes spin {
            from { transform: rotate(0deg); }
            to { transform: rotate(360deg); }
        }

        .refresh-btn.loading svg {
            animation: spin 1s linear infinite;
        }

        .refresh-btn.loading {
            pointer-events: none;
            opacity: 0.6;
            transform: none !important;
        }

        /* PR Cards Grid */
        .cards-grid {
            display: grid;
            grid-template-columns: repeat(auto-fill, minmax(400px, 1fr));
            gap: 2rem;
        }

        .pr-card {
            background: var(--glass-bg);
            border: 1px solid var(--glass-border);
            border-radius: 20px;
            padding: 2rem;
            display: flex;
            flex-direction: column;
            justify-content: space-between;
            min-height: 280px;
            backdrop-filter: blur(16px);
            -webkit-backdrop-filter: blur(16px);
            transition: all 0.4s cubic-bezier(0.16, 1, 0.3, 1);
            position: relative;
            overflow: hidden;
        }

        .pr-card::before {
            content: '';
            position: absolute;
            top: 0;
            left: 0;
            width: 100%;
            height: 4px;
            background: transparent;
            transition: background 0.3s;
        }

        .pr-card.high-risk::before { background: var(--danger-text); }
        .pr-card.medium-risk::before { background: var(--warning-text); }
        .pr-card.low-risk::before { background: var(--success-text); }

        .pr-card:hover {
            transform: translateY(-6px);
            border-color: var(--glass-border-hover);
            box-shadow: 0 12px 30px rgba(0, 0, 0, 0.3), 0 0 2px rgba(255, 255, 255, 0.1);
        }

        .card-top {
            display: flex;
            justify-content: space-between;
            align-items: flex-start;
            margin-bottom: 1.2rem;
        }

        .repo-badge {
            display: flex;
            align-items: center;
            gap: 0.5rem;
            font-size: 0.85rem;
            color: var(--text-secondary);
            font-weight: 500;
        }

        .repo-link {
            text-decoration: none;
            color: var(--text-secondary) !important;
            display: inline-flex;
            align-items: center;
            gap: 0.5rem;
            cursor: pointer;
            transition: color 0.2s, opacity 0.2s;
        }
        .repo-link:hover {
            color: var(--accent-primary) !important;
            opacity: 0.9;
        }
        .repo-link span {
            border-bottom: 1px dashed rgba(255, 255, 255, 0.2);
            transition: border-color 0.2s;
        }
        .repo-link:hover span {
            border-bottom-color: var(--accent-primary);
        }

        .repo-icon {
            width: 16px;
            height: 16px;
            fill: var(--text-muted);
        }

        .risk-badge {
            padding: 0.4rem 0.8rem;
            border-radius: 8px;
            font-size: 0.75rem;
            font-weight: 700;
            letter-spacing: 0.05em;
        }

        .risk-badge.high { background: var(--danger-bg); color: var(--danger-text); border: 1px solid var(--danger-border); }
        .risk-badge.medium { background: var(--warning-bg); color: var(--warning-text); border: 1px solid var(--warning-border); }
        .risk-badge.low { background: var(--success-bg); color: var(--success-text); border: 1px solid var(--success-border); }

        .score-badge {
            padding: 0.25rem 0.6rem;
            border-radius: 6px;
            font-size: 0.72rem;
            font-weight: 700;
            letter-spacing: 0.05em;
            display: inline-flex;
            align-items: center;
        }

        .score-badge.quality.high-val { background: var(--success-bg); color: var(--success-text); border: 1px solid var(--success-border); }
        .score-badge.quality.med-val { background: var(--warning-bg); color: var(--warning-text); border: 1px solid var(--warning-border); }
        .score-badge.quality.low-val { background: var(--danger-bg); color: var(--danger-text); border: 1px solid var(--danger-border); }

        .score-badge.testing.high-val { background: var(--danger-bg); color: var(--danger-text); border: 1px solid var(--danger-border); }
        .score-badge.testing.med-val { background: var(--warning-bg); color: var(--warning-text); border: 1px solid var(--warning-border); }
        .score-badge.testing.low-val { background: var(--success-bg); color: var(--success-text); border: 1px solid var(--success-border); }

        .pr-info {
            margin-bottom: 1.8rem;
        }

        .pr-title {
            font-size: 1.15rem;
            font-weight: 600;
            color: var(--text-primary);
            line-height: 1.4;
            margin-bottom: 0.4rem;
            display: -webkit-box;
            -webkit-line-clamp: 2;
            -webkit-box-orient: vertical;
            overflow: hidden;
            text-overflow: ellipsis;
            max-width: 100%;
        }

        .pr-description {
            font-size: 0.86rem;
            color: var(--text-secondary);
            opacity: 0.8;
            line-height: 1.45;
            margin-bottom: 0.8rem;
            display: -webkit-box;
            -webkit-line-clamp: 2;
            -webkit-box-orient: vertical;
            overflow: hidden;
            text-overflow: ellipsis;
        }

        .pr-description img {
            max-height: 18px;
            vertical-align: middle;
            display: inline-block;
            margin: 0 2px;
        }

        .pr-meta {
            display: flex;
            align-items: center;
            gap: 1rem;
            font-size: 0.85rem;
            color: var(--text-muted);
        }

        .pr-author {
            display: flex;
            align-items: center;
            gap: 0.4rem;
            color: var(--text-secondary);
        }

        /* Score Rings/Bars */
        .score-row {
            display: flex;
            gap: 1.5rem;
            margin-bottom: 2rem;
            background: rgba(0, 0, 0, 0.15);
            padding: 1rem;
            border-radius: 12px;
            border: 1px solid rgba(255, 255, 255, 0.02);
        }

        .score-box {
            flex: 1;
            display: flex;
            flex-direction: column;
            gap: 0.25rem;
        }

        .score-label {
            font-size: 0.75rem;
            color: var(--text-muted);
            font-weight: 600;
            text-transform: uppercase;
            letter-spacing: 0.03em;
        }

        .score-value-bar {
            display: flex;
            align-items: center;
            gap: 0.75rem;
        }

        .score-num {
            font-size: 1.2rem;
            font-weight: 700;
            color: var(--text-primary);
        }

        .progress-track {
            height: 6px;
            background: rgba(255, 255, 255, 0.06);
            border-radius: 999px;
            flex-grow: 1;
            overflow: hidden;
        }

        .progress-fill {
            height: 100%;
            border-radius: 999px;
            background: var(--accent-primary);
            width: 0%;
            transition: width 0.8s cubic-bezier(0.16, 1, 0.3, 1);
        }

        .progress-fill.high-val { background: var(--success-text); }
        .progress-fill.med-val { background: var(--warning-text); }
        .progress-fill.low-val { background: var(--danger-text); }

        .score-card-detail {
            background: rgba(255, 255, 255, 0.03);
            border: 1px solid var(--glass-border);
            border-radius: 12px;
            padding: 1rem;
            display: flex;
            flex-direction: column;
            gap: 0.4rem;
        }
        .score-card-title {
            font-size: 0.72rem;
            font-weight: 600;
            color: var(--text-muted);
            text-transform: uppercase;
            letter-spacing: 0.05em;
        }
        .score-card-value {
            font-size: 1.5rem;
            font-weight: 700;
            color: var(--text-primary);
        }
        .score-card-bar-container {
            height: 6px;
            background: rgba(255, 255, 255, 0.08);
            border-radius: 3px;
            overflow: hidden;
            width: 100%;
            margin-top: 0.25rem;
        }

        /* Diff file explorer sidebar styles */
        .file-select-btn {
            background: transparent;
            border: 1px solid transparent;
            color: var(--text-secondary);
            padding: 0.5rem 0.6rem;
            border-radius: 8px;
            text-align: left;
            font-size: 0.78rem;
            cursor: pointer;
            display: flex;
            justify-content: space-between;
            align-items: center;
            width: 100%;
            transition: all 0.2s ease;
            gap: 0.5rem;
        }

        .file-select-btn:hover {
            background: rgba(255, 255, 255, 0.03);
            color: var(--text-primary);
        }

        .file-select-btn.active {
            background: rgba(255, 255, 255, 0.05);
            border-color: var(--glass-border);
            color: var(--text-primary);
            font-weight: 500;
        }

        .file-name-text {
            white-space: nowrap;
            overflow: hidden;
            text-overflow: ellipsis;
            flex: 1;
        }

        .file-changes-badge {
            font-size: 0.68rem;
            font-weight: 600;
            white-space: nowrap;
        }

        .card-actions {
            display: flex;
            gap: 1rem;
        }

        .btn {
            padding: 0.75rem 1.5rem;
            border-radius: 12px;
            font-weight: 600;
            font-size: 0.9rem;
            cursor: pointer;
            transition: all 0.3s cubic-bezier(0.16, 1, 0.3, 1);
            display: flex;
            align-items: center;
            justify-content: center;
            gap: 0.5rem;
            text-align: center;
            border: 1px solid transparent;
        }

        .btn-primary {
            background: var(--accent-primary);
            color: #fff;
            box-shadow: 0 4px 15px rgba(129, 140, 248, 0.2);
            flex-grow: 2;
        }

        .btn-primary:hover {
            background: #6366f1;
            transform: translateY(-2px);
            box-shadow: 0 6px 20px rgba(129, 140, 248, 0.35);
        }

        .btn-secondary {
            background: var(--glass-bg);
            border-color: var(--glass-border);
            color: var(--text-secondary);
            flex-grow: 1;
        }

        .btn-secondary:hover {
            background: rgba(255, 255, 255, 0.08);
            border-color: var(--glass-border-hover);
            color: var(--text-primary);
            transform: translateY(-2px);
        }

        /* Empty State */
        .empty-state {
            grid-column: 1 / -1;
            background: var(--glass-bg);
            border: 1px dashed var(--glass-border);
            border-radius: 24px;
            padding: 6rem 2rem;
            text-align: center;
            display: flex;
            flex-direction: column;
            align-items: center;
            justify-content: center;
            backdrop-filter: blur(12px);
        }

        .empty-icon-wrap {
            width: 80px;
            height: 80px;
            background: rgba(129, 140, 248, 0.05);
            border: 1px solid rgba(129, 140, 248, 0.1);
            border-radius: 24px;
            display: flex;
            align-items: center;
            justify-content: center;
            margin-bottom: 2rem;
            position: relative;
        }

        .empty-icon-wrap::after {
            content: '';
            position: absolute;
            width: 100%;
            height: 100%;
            background: rgba(129, 140, 248, 0.1);
            filter: blur(15px);
            z-index: -1;
        }

        .empty-icon {
            width: 40px;
            height: 40px;
            stroke: var(--accent-primary);
        }

        .empty-state h3 {
            font-size: 1.4rem;
            font-weight: 600;
            margin-bottom: 0.5rem;
        }

        .empty-state p {
            color: var(--text-secondary);
            max-width: 400px;
            font-size: 0.95rem;
        }

        /* Slide-Out Detail Modal */
        .modal-overlay {
            position: fixed;
            top: 0;
            left: 0;
            width: 100%;
            height: 100%;
            background: rgba(5, 6, 10, 0.5);
            backdrop-filter: blur(4px);
            z-index: 200;
            opacity: 0;
            visibility: hidden;
            transition: all 0.4s cubic-bezier(0.16, 1, 0.3, 1);
        }

        .modal-overlay.active {
            opacity: 1;
            visibility: visible;
        }

        /* Help Modal Dialog Styles */
        .help-modal-card {
            position: absolute;
            top: 50%;
            left: 50%;
            transform: translate(-50%, -50%) scale(0.95);
            width: 700px;
            max-width: 90%;
            max-height: 85vh;
            background: rgba(9, 10, 16, 0.98);
            border: 1px solid var(--glass-border);
            border-radius: 16px;
            box-shadow: 0 20px 50px rgba(0, 0, 0, 0.5);
            display: flex;
            flex-direction: column;
            overflow: hidden;
            transition: all 0.4s cubic-bezier(0.16, 1, 0.3, 1);
            color: var(--text-primary);
        }

        .modal-overlay.active .help-modal-card {
            transform: translate(-50%, -50%) scale(1);
        }

        .detail-modal {
            position: fixed;
            top: 0;
            right: 0;
            width: 1400px;
            max-width: 95%;
            height: 100%;
            background: rgba(9, 10, 16, 0.95);
            border-left: 1px solid var(--glass-border);
            box-shadow: -15px 0 40px rgba(0, 0, 0, 0.6);
            z-index: 201;
            transform: translateX(100%);
            transition: transform 0.45s cubic-bezier(0.16, 1, 0.3, 1);
            display: flex;
            flex-direction: column;
            backdrop-filter: blur(30px);
            -webkit-backdrop-filter: blur(30px);
        }

        .detail-modal.active {
            transform: translateX(0);
        }

        .modal-header {
            padding: 2.5rem 3rem 1.5rem;
            border-bottom: 1px solid var(--glass-border);
            display: flex;
            justify-content: space-between;
            align-items: flex-start;
        }

        .modal-header-info {
            display: flex;
            flex-direction: column;
            gap: 0.5rem;
            max-width: 85%;
        }

        .modal-header-top {
            display: flex;
            align-items: center;
            gap: 1rem;
        }

        .modal-header h3 {
            font-size: 1.4rem;
            font-weight: 700;
            color: var(--text-primary);
            line-height: 1.3;
        }

        .close-modal-btn {
            background: var(--glass-bg);
            border: 1px solid var(--glass-border);
            width: 40px;
            height: 40px;
            border-radius: 12px;
            display: flex;
            align-items: center;
            justify-content: center;
            cursor: pointer;
            color: var(--text-secondary);
            transition: all 0.3s cubic-bezier(0.16, 1, 0.3, 1);
        }

        .close-modal-btn:hover {
            background: rgba(255, 255, 255, 0.08);
            border-color: var(--glass-border-hover);
            color: var(--text-primary);
        }

        .modal-body {
            padding: 2rem 3rem;
            overflow-y: hidden;
            flex: 1;
            display: flex;
            flex-direction: column;
            gap: 1.5rem;
            min-height: 0;
        }

        /* Info Banners */
        .alert-banner {
            border-radius: 14px;
            padding: 1.25rem 1.5rem;
            display: flex;
            gap: 1rem;
            align-items: flex-start;
            font-size: 0.95rem;
            line-height: 1.5;
        }

        .alert-banner.security {
            background: var(--danger-bg);
            color: var(--danger-text);
            border: 1px solid var(--danger-border);
        }

        .alert-banner.recommendation {
            background: rgba(129, 140, 248, 0.07);
            color: var(--text-primary);
            border: 1px solid rgba(129, 140, 248, 0.2);
        }

        .alert-banner-icon {
            width: 20px;
            height: 20px;
            flex-shrink: 0;
            margin-top: 2px;
        }

        .alert-banner-icon.security { fill: var(--danger-text); }
        .alert-banner-icon.recommendation { fill: var(--accent-primary); }

        .report-section {
            display: flex;
            flex-direction: column;
            gap: 0.75rem;
            border-bottom: 1px solid rgba(255, 255, 255, 0.05);
            padding-bottom: 1rem;
        }

        .report-section:last-of-type {
            border-bottom: none;
            padding-bottom: 0;
        }

        .report-section-header {
            font-size: 0.95rem;
            font-weight: 700;
            color: var(--text-secondary);
            text-transform: uppercase;
            letter-spacing: 0.05em;
            display: flex;
            align-items: center;
            justify-content: space-between;
            user-select: none;
            padding: 0.5rem 0;
            outline: none;
        }

        .report-header-left {
            display: flex;
            align-items: center;
            gap: 0.6rem;
        }

        .section-icon {
            width: 16px;
            height: 16px;
            fill: var(--text-muted);
        }

        .report-box {
            background: rgba(255, 255, 255, 0.015);
            border: 1px solid var(--glass-border);
            border-radius: 16px;
            padding: 1.5rem;
            font-size: 0.95rem;
            color: var(--text-secondary);
            line-height: 1.6;
        }

        .report-box ul {
            padding-left: 1.5rem;
            display: flex;
            flex-direction: column;
            gap: 0.5rem;
        }

        /* Review Input Action Footer */
        .modal-footer {
            padding: 1rem 2rem;
            border-top: 1px solid var(--glass-border);
            background: rgba(9, 10, 16, 0.96);
            display: flex;
            flex-direction: column;
            gap: 0.75rem;
        }

        .comment-area {
            width: 100%;
            background: rgba(0, 0, 0, 0.2);
            border: 1px solid var(--glass-border);
            border-radius: 10px;
            color: var(--text-primary);
            padding: 0.6rem 0.8rem;
            font-family: inherit;
            font-size: 0.88rem;
            resize: none;
            height: 44px;
            transition: all 0.3s;
        }

        .comment-area:focus {
            outline: none;
            border-color: var(--accent-primary);
            box-shadow: 0 0 10px rgba(129, 140, 248, 0.15);
        }

        .footer-actions {
            display: flex;
            gap: 1.5rem;
        }

        .footer-actions .btn {
            flex: 1;
            padding: 1rem 2rem;
            font-size: 1rem;
            position: relative;
        }

        .btn-approve {
            background: var(--success-text);
            color: #090a10;
            box-shadow: 0 4px 15px rgba(52, 211, 153, 0.25);
        }

        .btn-approve:hover {
            background: #10b981;
            transform: translateY(-2px);
            box-shadow: 0 6px 20px rgba(52, 211, 153, 0.4);
        }

        .btn-reject {
            background: transparent;
            border-color: var(--danger-border);
            color: var(--danger-text);
        }

        .btn-reject:hover {
            background: rgba(239, 68, 68, 0.08);
            border-color: var(--danger-text);
            transform: translateY(-2px);
        }

        /* Loading / Toast Elements */
        .toast-notification {
            position: fixed;
            bottom: 2.5rem;
            right: 2.5rem;
            padding: 1rem 1.5rem;
            border-radius: 12px;
            backdrop-filter: blur(12px);
            display: flex;
            align-items: center;
            gap: 0.75rem;
            z-index: 300;
            transform: translateY(150%);
            transition: transform 0.4s cubic-bezier(0.175, 0.885, 0.32, 1.275);
            font-weight: 500;
            font-size: 0.95rem;
            box-shadow: 0 10px 25px rgba(0, 0, 0, 0.3);
        }

        .toast-notification.active {
            transform: translateY(0);
        }

        .toast-notification.success {
            background: rgba(16, 185, 129, 0.9);
            border: 1px solid rgba(16, 185, 129, 0.2);
            color: #fff;
        }

        .toast-notification.error {
            background: rgba(239, 68, 68, 0.9);
            border: 1px solid rgba(239, 68, 68, 0.2);
            color: #fff;
        }

        .spinner {
            width: 20px;
            height: 20px;
            border: 3px solid rgba(255, 255, 255, 0.3);
            border-radius: 50%;
            border-top-color: #fff;
            animation: spin 0.8s linear infinite;
            display: none;
        }

        @keyframes spin {
            to { transform: rotate(360deg); }
        }

        .btn.loading .spinner {
            display: inline-block;
        }
        .btn.loading span {
            display: none;
        }
        .btn:disabled {
            opacity: 0.6;
            cursor: not-allowed;
            transform: none !important;
            box-shadow: none !important;
        }

        /* 2-Column Layout Modal */
        .modal-grid {
            display: grid;
            grid-template-columns: 1fr 1.2fr;
            gap: 3rem;
            flex: 1;
            min-height: 0;
            overflow: hidden;
        }

        .modal-col-left {
            overflow-y: auto;
            padding-right: 1rem;
            display: flex;
            flex-direction: column;
            gap: 2rem;
            height: 100%;
        }

        .modal-col-right {
            border-left: 1px solid var(--glass-border);
            padding-left: 3rem;
            overflow-y: auto;
            display: flex;
            flex-direction: column;
            gap: 1.5rem;
            height: 100%;
        }

        /* Diff Viewer */
        .diff-viewer {
            background: rgba(0, 0, 0, 0.4);
            border: 1px solid var(--glass-border);
            border-radius: 12px;
            padding: 1.5rem;
            font-family: 'Fira Code', 'Courier New', Courier, monospace;
            font-size: 0.85rem;
            line-height: 1.5;
            color: var(--text-secondary);
            overflow-x: auto;
            white-space: pre-wrap;
            margin: 0;
            flex-grow: 1;
        }

        .diff-line-add {
            display: block;
            background-color: rgba(16, 185, 129, 0.12);
            color: #34d399;
            padding: 0.1rem 0.3rem;
            border-radius: 3px;
        }

        .diff-line-del {
            display: block;
            background-color: rgba(239, 68, 68, 0.12);
            color: #f87171;
            padding: 0.1rem 0.3rem;
            border-radius: 3px;
        }

        .diff-line-chunk {
            display: block;
            color: #60a5fa;
            opacity: 0.85;
            font-weight: 600;
        }

        .diff-line-meta {
            display: block;
            color: #a78bfa;
            font-weight: 600;
        }

        /* History Log Table */
        .history-table-container {
            background: var(--glass-bg);
            border: 1px solid var(--glass-border);
            border-radius: 20px;
            padding: 1.5rem;
            backdrop-filter: blur(16px);
            -webkit-backdrop-filter: blur(16px);
            overflow-x: auto;
            margin-top: 1rem;
        }

        .history-table {
            width: 100%;
            border-collapse: collapse;
            text-align: left;
            font-size: 0.95rem;
        }

        .history-table th,
        .history-table td {
            padding: 1rem 1.25rem;
            border-bottom: 1px solid var(--glass-border);
        }

        .history-table th {
            color: var(--text-secondary);
            font-weight: 600;
            text-transform: uppercase;
            font-size: 0.75rem;
            letter-spacing: 0.05em;
        }

        .history-table td {
            color: var(--text-primary);
        }

        .history-table tr:last-child td {
            border-bottom: none;
        }

        .history-table tr {
            transition: background 0.2s;
        }

        .history-table tr:hover {
            background: rgba(255, 255, 255, 0.02);
        }

        /* Badges inside Table */
        .status-badge {
            display: inline-flex;
            align-items: center;
            padding: 0.25rem 0.75rem;
            border-radius: 9999px;
            font-size: 0.8rem;
            font-weight: 500;
        }

        .status-badge.awaiting {
            background: rgba(245, 158, 11, 0.1);
            color: var(--warning-text);
            border: 1px solid rgba(245, 158, 11, 0.2);
        }

        .status-badge.approved {
            background: rgba(16, 185, 129, 0.1);
            color: var(--success-text);
            border: 1px solid rgba(16, 185, 129, 0.2);
        }

        .status-badge.rejected {
            background: rgba(239, 68, 68, 0.1);
            color: var(--danger-text);
            border: 1px solid rgba(239, 68, 68, 0.2);
        }

        .status-badge.processing {
            background: rgba(59, 130, 246, 0.1);
            color: var(--info-text);
            border: 1px solid rgba(59, 130, 246, 0.2);
        }
    </style>
    <script src="https://cdn.jsdelivr.net/npm/marked/marked.min.js"></script>
</head>
<body>

    <!-- Header Navigation -->
    <header>
        <div class="header-title-area">
            <!-- Custom Image Logo -->
            <img src="/logo.png" alt="MergeGuard Logo" style="width: 72px; height: 72px; border-radius: 12px; object-fit: cover; flex-shrink: 0;">
            <div style="display: flex; flex-direction: column; gap: 0.15rem;">
                <h1 style="margin: 0; line-height: 1.1;">MergeGuard</h1>
                <span style="font-size: 1.05rem; color: var(--text-secondary); font-weight: 500; letter-spacing: 0.01em; margin: 0;">PR Triage &amp; Quality Agent</span>
            </div>
        </div>
        <!-- Page Navigation Links -->
        <nav class="nav-links" style="display: flex; gap: 1.5rem; margin-right: auto; margin-left: 2.5rem;">
            <button class="nav-tab active" id="tab-dashboard" onclick="switchPage('dashboard')" style="background: none; border: none; color: var(--text-primary); font-family: inherit; font-size: 1.05rem; font-weight: 600; cursor: pointer; padding: 0.5rem 1rem; border-bottom: 2px solid var(--accent-primary); transition: all 0.2s; outline: none;">
                Pending Reviews
            </button>
            <button class="nav-tab" id="tab-history" onclick="switchPage('history')" style="background: none; border: none; color: var(--text-secondary); font-family: inherit; font-size: 1.05rem; font-weight: 500; cursor: pointer; padding: 0.5rem 1rem; border-bottom: 2px solid transparent; transition: all 0.2s; outline: none;">
                Triage History
            </button>
        </nav>
        <div style="display: flex; align-items: center; gap: 0.75rem;">
            <button class="refresh-btn" id="sync-pipeline-btn" onclick="fetchPending(true)">
                <svg style="width: 16px; height: 16px; fill: currentColor;" viewBox="0 0 24 24">
                    <path d="M17.65 6.35C16.2 4.9 14.21 4 12 4c-4.42 0-7.99 3.58-7.99 8s3.57 8 7.99 8c3.73 0 6.84-2.55 7.73-6h-2.08c-.82 2.33-3.04 4-5.65 4-3.31 0-6-2.69-6-6s2.69-6 6-6c1.66 0 3.14.69 4.22 1.78L13 11h7V4l-2.35 2.35z"/>
                </svg>
                <span>Sync</span>
            </button>
            <button class="help-btn" onclick="openHelpModal()">
                <svg style="width: 16px; height: 16px; fill: currentColor;" viewBox="0 0 24 24">
                    <path d="M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm1 16h-2v-2h2v2zm1.07-7.75l-.9.92C12.45 11.9 12 12.5 12 14h-2v-.5c0-1.1.45-2.1 1.17-2.83l1.24-1.26c.37-.36.59-.86.59-1.41 0-1.1-.9-2-2-2s-2 .9-2 2H7c0-2.76 2.24-5 5-5s5 2.24 5 5c0 1.04-.42 1.99-1.07 2.75z"/>
                </svg>
                <span>Help</span>
            </button>
        </div>
    </header>

    <!-- Main Container -->
    <main>
        <div id="page-dashboard">
            <div class="section-header">
                <h2>Pending Pull Request Reviews</h2>
            </div>

            <!-- Cards Grid Container -->
            <div class="cards-grid" id="cards-container">
                <!-- Cards populated dynamically via JS -->
                <div class="empty-state">
                    <div class="empty-icon-wrap">
                        <svg class="empty-icon" viewBox="0 0 24 24" fill="none" stroke-width="2">
                            <circle cx="12" cy="12" r="10"></circle>
                            <path d="M12 6v6l4 2"></path>
                        </svg>
                    </div>
                    <h3>Scanning Repository Events...</h3>
                    <p>Establishing connection with the Agent Runtime. Retrieving historical pull request sessions.</p>
                </div>
            </div>
        </div>

        <!-- History Section -->
        <div id="page-history" style="display: none;">
            <div class="section-header">
                <h2>Recent Triage History (Last 10)</h2>
            </div>
            <div class="history-table-container">
                <table class="history-table">
                    <thead>
                        <tr>
                            <th>Pull Request</th>
                            <th>Repository</th>
                            <th>Author</th>
                            <th>Risk Level</th>
                            <th>Status</th>
                            <th>Triage Decision</th>
                            <th>Timestamp</th>
                        </tr>
                    </thead>
                    <tbody id="history-table-body">
                        <!-- Loaded dynamically -->
                    </tbody>
                </table>
            </div>
        </div>
    </main>

    <!-- Slide-Out Details Panel -->
    <div class="modal-overlay" id="modal-overlay" onclick="closeModal()"></div>
    <div class="detail-modal" id="detail-modal">
        <div class="modal-header">
            <div class="modal-header-info">
                <div class="modal-header-top" style="display: flex; gap: 0.5rem; flex-wrap: wrap;">
                    <span class="repo-badge" id="modal-repo"></span>
                    <span class="score-badge quality" id="modal-quality-badge"></span>
                </div>
                <h3 id="modal-pr-title"></h3>
            </div>
            <button class="close-modal-btn" onclick="closeModal()">
                <svg style="width: 20px; height: 20px; fill: currentColor;" viewBox="0 0 24 24">
                    <path d="M19 6.41L17.59 5 12 10.59 6.41 5 5 6.41 10.59 12 5 17.59 6.41 19 12 13.41 17.59 19 19 17.59 13.41 12z"/>
                </svg>
            </button>
        </div>

        <!-- Modal Body scrollable area -->
        <div class="modal-body" id="modal-body">
            <!-- High-Level Main Tabs (Unified Flat Navigation) -->
            <div class="modal-main-tabs">
                <button class="main-tab-btn active" onclick="switchMainTab(this, 'panel-overview')">
                    <svg class="tab-icon" width="16" height="16" viewBox="0 0 24 24"><path d="M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm1 17h-2v-2h2v2zm0-4h-2V7h2v8z"/></svg>
                    <span>Overview</span>
                </button>
                <button class="main-tab-btn" onclick="switchMainTab(this, 'panel-testing-qa')">
                    <svg class="tab-icon" width="16" height="16" viewBox="0 0 24 24"><path d="M19 19L13 8V4H15V2H9V4H11V8L5 19C4.27 20.3 5.21 22 6.73 22H17.27C18.79 22 19.73 20.3 19 19ZM7.46 18L11 11.58V4H13V11.58L16.54 18H7.46Z"/></svg>
                    <span>Testing &amp; QA</span>
                </button>
                <button class="main-tab-btn" onclick="switchMainTab(this, 'panel-security-audit')">
                    <svg class="tab-icon" width="16" height="16" viewBox="0 0 24 24"><path d="M12 1L3 5v6c0 5.55 3.84 10.74 9 12 5.16-1.26 9-6.45 9-12V5l-9-4zm0 10.99h7c-.53 4.12-3.28 7.79-7 8.94V12H5V6.3l7-3.11v8.8z"/></svg>
                    <span>Security Audit</span>
                </button>
                <button class="main-tab-btn" onclick="switchMainTab(this, 'panel-performance-impact')">
                    <svg class="tab-icon" width="16" height="16" viewBox="0 0 24 24"><path d="M11 21h-1l1-7H7.5c-.83 0-1.2-.42-1.07-.94.13-.53.53-1.26.55-1.29l3.52-6.3h1.01l-1 7h3.5c.76 0 .97.43.83.94l-3.41 6.3c-.22.4-.64.59-.93.59z"/></svg>
                    <span>Performance &amp; Impact</span>
                </button>
                <button class="main-tab-btn" onclick="switchMainTab(this, 'panel-code-diff')">
                    <svg class="tab-icon" width="16" height="16" viewBox="0 0 24 24"><path d="M9.4 16.6L4.8 12l4.6-4.6L8 6l-6 6 6 6 1.4-1.4zm5.2 0l4.6-4.6-4.6-4.6L16 6l6 6-6 6-1.4-1.4z"/></svg>
                    <span>Code Changes Diff</span>
                </button>
            </div>

            <!-- Unified Panel Contents -->
            <div id="panel-overview" class="main-panel active">
                <div class="modal-col-left" style="width: 100%; border-right: none; padding-right: 0; display: flex; flex-direction: column; gap: 1.5rem;">
                    <!-- Criteria Scores Grid -->
                    <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 1rem; margin-top: 0.5rem;">
                        <div class="score-card-detail">
                            <span class="score-card-title">Overall Quality</span>
                            <div class="score-card-value" id="detail-score-overall">--/10</div>
                            <div class="score-card-bar-container">
                                <div class="progress-fill" id="detail-score-bar-overall" style="width: 0%; height: 100%; border-radius: 3px;"></div>
                            </div>
                        </div>
                        <div class="score-card-detail">
                            <span class="score-card-title">Testing &amp; QA</span>
                            <div class="score-card-value" id="detail-score-testing">--/10</div>
                            <div class="score-card-bar-container">
                                <div class="progress-fill" id="detail-score-bar-testing" style="width: 0%; height: 100%; border-radius: 3px;"></div>
                            </div>
                        </div>
                        <div class="score-card-detail">
                            <span class="score-card-title">Security Posture</span>
                            <div class="score-card-value" id="detail-score-security">--/10</div>
                            <div class="score-card-bar-container">
                                <div class="progress-fill" id="detail-score-bar-security" style="width: 0%; height: 100%; border-radius: 3px;"></div>
                            </div>
                        </div>
                        <div class="score-card-detail">
                            <span class="score-card-title">Performance &amp; Stability</span>
                            <div class="score-card-value" id="detail-score-performance">--/10</div>
                            <div class="score-card-bar-container">
                                <div class="progress-fill" id="detail-score-bar-performance" style="width: 0%; height: 100%; border-radius: 3px;"></div>
                            </div>
                        </div>
                    </div>

                    <!-- Recommendation Banner -->
                    <div class="alert-banner recommendation" id="modal-recommendation-box" style="margin-bottom: 0;">
                        <svg class="alert-banner-icon recommendation" viewBox="0 0 24 24">
                            <path d="M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm1 17h-2v-2h2v2zm0-4h-2V7h2v8z"/>
                        </svg>
                        <div>
                            <strong style="display: block; margin-bottom: 0.25rem;">Recommendation</strong>
                            <span id="modal-recommendation"></span>
                        </div>
                    </div>
                </div>
            </div>

            <div id="panel-testing-qa" class="main-panel">
                <div class="modal-col-left" style="width: 100%; border-right: none; padding-right: 0; display: flex; flex-direction: column; gap: 1.5rem;">
                    <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: -0.5rem; background: rgba(255,255,255,0.02); border: 1px solid var(--glass-border); padding: 0.75rem 1.25rem; border-radius: 8px;">
                        <span style="font-size: 0.9rem; font-weight: 600; color: var(--text-primary);">Testing &amp; QA Dimension Analysis</span>
                        <span class="score-badge quality" id="tab-score-testing" style="font-size: 0.85rem; padding: 0.25rem 0.5rem; border-radius: 4px;">--/10</span>
                    </div>
                    <div>
                        <div class="report-section-header">Testing Gaps &amp; Target Verification</div>
                        <div class="report-box" id="modal-testing-gaps"></div>
                    </div>
                    <div>
                        <div class="report-section-header">Regression Risks &amp; Code Integrity</div>
                        <div class="report-box" id="modal-regression-risks"></div>
                    </div>
                    <div>
                        <div class="report-section-header">Suggested Edge Cases &amp; Scenarios</div>
                        <div class="report-box" id="modal-edge-cases"></div>
                    </div>
                </div>
            </div>

            <div id="panel-security-audit" class="main-panel">
                <div class="modal-col-left" style="width: 100%; border-right: none; padding-right: 0; display: flex; flex-direction: column; gap: 1.5rem;">
                    <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: -0.5rem; background: rgba(255,255,255,0.02); border: 1px solid var(--glass-border); padding: 0.75rem 1.25rem; border-radius: 8px;">
                        <span style="font-size: 0.9rem; font-weight: 600; color: var(--text-primary);">Security Auditing &amp; Access Controls</span>
                        <span class="score-badge quality" id="tab-score-security" style="font-size: 0.85rem; padding: 0.25rem 0.5rem; border-radius: 4px;">--/10</span>
                    </div>
                    <div>
                        <div class="report-section-header">Security Audit &amp; Trust Boundaries</div>
                        <div class="report-box" id="modal-security-audit-content"></div>
                    </div>
                </div>
            </div>

            <div id="panel-performance-impact" class="main-panel">
                <div class="modal-col-left" style="width: 100%; border-right: none; padding-right: 0; display: flex; flex-direction: column; gap: 1.5rem;">
                    <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: -0.5rem; background: rgba(255,255,255,0.02); border: 1px solid var(--glass-border); padding: 0.75rem 1.25rem; border-radius: 8px;">
                        <span style="font-size: 0.9rem; font-weight: 600; color: var(--text-primary);">Performance, Resource Usage &amp; Impact</span>
                        <span class="score-badge quality" id="tab-score-performance" style="font-size: 0.85rem; padding: 0.25rem 0.5rem; border-radius: 4px;">--/10</span>
                    </div>
                    <div>
                        <div class="report-section-header">Performance &amp; Production Impact</div>
                        <div class="report-box" id="modal-production-impact"></div>
                    </div>
                </div>
            </div>

            <div id="panel-code-diff" class="main-panel">
                <div style="display: flex; width: 100%; height: 100%; gap: 1rem;">
                    <!-- Diff File Sidebar -->
                    <div class="diff-sidebar" style="width: 240px; flex-shrink: 0; background: rgba(0,0,0,0.15); border: 1px solid var(--glass-border); border-radius: 12px; padding: 1rem; display: flex; flex-direction: column; gap: 0.75rem; overflow-y: auto;">
                        <h4 style="font-size: 0.76rem; font-weight: 600; color: var(--text-muted); text-transform: uppercase; letter-spacing: 0.05em; margin: 0;">Changed Files</h4>
                        <div id="diff-file-list" style="display: flex; flex-direction: column; gap: 0.4rem;">
                            <!-- File buttons populated dynamically via JS -->
                        </div>
                    </div>
                    <!-- Diff Viewer Content -->
                    <div style="flex: 1; display: flex; flex-direction: column; overflow: hidden; background: rgba(0,0,0,0.15); border: 1px solid var(--glass-border); border-radius: 12px; padding: 1rem;">
                        <div id="diff-active-file-header" style="font-size: 0.85rem; font-weight: 500; color: var(--text-primary); padding: 0.25rem 0 0.75rem 0; border-bottom: 1px solid var(--glass-border); margin-bottom: 0.75rem; display: flex; align-items: center; gap: 0.5rem; justify-content: space-between;">
                            <span style="display: flex; align-items: center; gap: 0.5rem;">
                                <svg class="file-icon" style="width: 16px; height: 16px; fill: var(--text-secondary);" viewBox="0 0 24 24"><path d="M14 2H6c-1.1 0-1.99.9-1.99 2L4 20c0 1.1.89 2 1.99 2H18c1.1 0 2-.9 2-2V8l-6-6zm2 16H8v-2h8v2zm0-4H8v-2h8v2zm-3-5V3.5L18.5 9H13z"/></svg>
                                <span id="diff-active-file-name" style="font-family: monospace;">Select a file</span>
                            </span>
                        </div>
                        <pre class="diff-viewer" id="modal-diff-content" style="flex: 1; margin: 0; overflow-y: auto; background: transparent; border: none; padding: 0;"></pre>
                    </div>
                </div>
            </div>
        </div>

        <!-- Action Comments Area -->
        <div class="modal-footer">
            <textarea class="comment-area" id="modal-comment" placeholder="Optional review comment or request criteria..."></textarea>
            <div class="footer-actions">
                <button class="btn btn-reject" id="btn-request-changes" onclick="submitAction(false)">
                    <div class="spinner"></div>
                    <span>Request Changes</span>
                </button>
                <button class="btn btn-approve" id="btn-approve" onclick="submitAction(true)">
                    <div class="spinner"></div>
                    <span>Approve Triage</span>
                </button>
            </div>
        </div>
    </div>

    <!-- Help Modal Overlay -->
    <div class="modal-overlay" id="help-modal-overlay">
        <div class="help-modal-card">
            <div class="modal-header" style="padding: 1.25rem 1.75rem 0.75rem 1.75rem; border-bottom: 1px solid var(--glass-border); display: flex; justify-content: space-between; align-items: center;">
                <div style="display: flex; align-items: center; gap: 0.6rem;">
                    <svg style="width: 20px; height: 20px; fill: var(--accent-primary);" viewBox="0 0 24 24"><path d="M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm1 16h-2v-2h2v2zm1.07-7.75l-.9.92C12.45 11.9 12 12.5 12 14h-2v-.5c0-1.1.45-2.1 1.17-2.83l1.24-1.26c.37-.36.59-.86.59-1.41 0-1.1-.9-2-2-2s-2 .9-2 2H7c0-2.76 2.24-5 5-5s5 2.24 5 5c0 1.04-.42 1.99-1.07 2.75z"/></svg>
                    <h2 class="modal-title" style="font-size: 1.1rem; margin: 0; font-weight: 600; color: var(--text-primary);">MergeGuard Dashboard Guide</h2>
                </div>
                <button class="close-btn" onclick="closeHelpModal()" style="font-size: 1.5rem; background: transparent; border: none; color: var(--text-secondary); cursor: pointer; display: flex; align-items: center; justify-content: center; padding: 0.25rem;">&times;</button>
            </div>

            <div class="modal-body" style="padding: 1.5rem 1.75rem; overflow-y: auto; display: flex; flex-direction: column; gap: 1.25rem; max-height: calc(85vh - 60px);">
                <section>
                    <h3 style="font-size: 0.85rem; color: var(--accent-primary); margin: 0 0 0.5rem 0; text-transform: uppercase; letter-spacing: 0.05em; font-weight: 600;">System Overview</h3>
                    <p style="font-size: 0.82rem; color: var(--text-secondary); line-height: 1.5; margin: 0;">
                        The <strong>PR Triage Agent</strong> runs automated pipeline scans for all repository pull requests. Any PR that fails static risk filters is suspended in the human-in-the-loop gate and appears here for your manual override.
                    </p>
                </section>

                <section>
                    <h3 style="font-size: 0.85rem; color: var(--accent-primary); margin: 0 0 0.5rem 0; text-transform: uppercase; letter-spacing: 0.05em; font-weight: 600;">Criteria Dimensions Explanations</h3>
                    <div style="display: flex; flex-direction: column; gap: 0.75rem;">
                        <div style="background: rgba(255,255,255,0.02); border: 1px solid var(--glass-border); padding: 0.75rem 1rem; border-radius: 8px;">
                            <div style="font-size: 0.8rem; font-weight: 600; color: var(--accent-primary); margin-bottom: 0.25rem;">OVERALL QUALITY (1 - 10)</div>
                            <p style="font-size: 0.78rem; color: var(--text-secondary); line-height: 1.45; margin: 0;">
                                General assessment of code structure, clean coding principles, and consistency.
                                <span style="color: var(--text-muted); display: block; margin-top: 0.2rem;">• <strong>8 - 10 (High)</strong>: Exceptionally clean, follows standard design patterns.</span>
                                <span style="color: var(--text-muted); display: block;">• <strong>5 - 7 (Medium)</strong>: Ready to merge, minor formatting or documentation improvements possible.</span>
                                <span style="color: var(--text-muted); display: block;">• <strong>1 - 4 (Low)</strong>: Clear structural defects, missing separation of concerns.</span>
                            </p>
                        </div>
                        <div style="background: rgba(255,255,255,0.02); border: 1px solid var(--glass-border); padding: 0.75rem 1rem; border-radius: 8px;">
                            <div style="font-size: 0.8rem; font-weight: 600; color: var(--accent-primary); margin-bottom: 0.25rem;">TESTING &amp; QA (1 - 10)</div>
                            <p style="font-size: 0.78rem; color: var(--text-secondary); line-height: 1.45; margin: 0;">
                                Evaluates regression risk, automated unit test coverage, and mock correctness.
                                <span style="color: var(--text-muted); display: block; margin-top: 0.2rem;">• <strong>8 - 10 (High)</strong>: Comprehensive test coverage, robust boundary logic mockups.</span>
                                <span style="color: var(--text-muted); display: block;">• <strong>5 - 7 (Medium)</strong>: Basic unit tests present, lacking edge case / error path checks.</span>
                                <span style="color: var(--text-muted); display: block;">• <strong>1 - 4 (Low)</strong>: Significant modifications without testing, high regression risk.</span>
                            </p>
                        </div>
                        <div style="background: rgba(255,255,255,0.02); border: 1px solid var(--glass-border); padding: 0.75rem 1rem; border-radius: 8px;">
                            <div style="font-size: 0.8rem; font-weight: 600; color: var(--accent-primary); margin-bottom: 0.25rem;">SECURITY POSTURE (1 - 10)</div>
                            <p style="font-size: 0.78rem; color: var(--text-secondary); line-height: 1.45; margin: 0;">
                                Inspects threat vectors, RBAC impersonation, data boundaries, and credentials.
                                <span style="color: var(--text-muted); display: block; margin-top: 0.2rem;">• <strong>8 - 10 (Secure)</strong>: Proper RBAC context, no vulnerable packages, credentials protected.</span>
                                <span style="color: var(--text-muted); display: block;">• <strong>5 - 7 (Needs Review)</strong>: Safe logic, but with minor security configuration adjustments possible.</span>
                                <span style="color: var(--text-muted); display: block;">• <strong>1 - 4 (Vulnerable)</strong>: Direct privilege leak risks, API secrets exposed, or unparameterized queries.</span>
                            </p>
                        </div>
                        <div style="background: rgba(255,255,255,0.02); border: 1px solid var(--glass-border); padding: 0.75rem 1rem; border-radius: 8px;">
                            <div style="font-size: 0.8rem; font-weight: 600; color: var(--accent-primary); margin-bottom: 0.25rem;">PERFORMANCE &amp; STABILITY (1 - 10)</div>
                            <p style="font-size: 0.78rem; color: var(--text-secondary); line-height: 1.45; margin: 0;">
                                Gauges execution speed, memory allocations, and overall resource footprint.
                                <span style="color: var(--text-muted); display: block; margin-top: 0.2rem;">• <strong>8 - 10 (Optimal)</strong>: Minimum complexity overhead, efficient queries, no resource leaks.</span>
                                <span style="color: var(--text-muted); display: block;">• <strong>5 - 7 (Acceptable)</strong>: Stable runtime, with potential minor latency optimizations.</span>
                                <span style="color: var(--text-muted); display: block;">• <strong>1 - 4 (Deficient)</strong>: CPU/memory bloating, dangerous blocking I/O, or resource leak hazards.</span>
                            </p>
                        </div>
                    </div>
                </section>

                <section>
                    <h3 style="font-size: 0.85rem; color: var(--accent-primary); margin: 0 0 0.5rem 0; text-transform: uppercase; letter-spacing: 0.05em; font-weight: 600;">Manual Intervention Decisions</h3>
                    <p style="font-size: 0.82rem; color: var(--text-secondary); line-height: 1.5; margin: 0;">
                        • <strong>Approve Triage</strong>: Submits the human override decision to release the pipeline.
                        <br>• <strong>Request Changes</strong>: Halts the pipeline run, sending structured review feedback back to the contributor.
                    </p>
                </section>
            </div>
        </div>
    </div>

    <!-- Toast Notification -->
    <div class="toast-notification" id="toast">
        <span id="toast-text"></span>
    </div>

    <script>
        let currentPR = null;
        let isSubmitting = false;
        let pendingSessionsMap = {};

        function switchPage(pageId) {
            // Update active navigation tab styling
            document.querySelectorAll('.nav-tab').forEach(tab => {
                tab.classList.remove('active');
                tab.style.color = 'var(--text-secondary)';
                tab.style.borderBottomColor = 'transparent';
                tab.style.fontWeight = '500';
            });
            const activeTab = document.getElementById(`tab-${pageId}`);
            if (activeTab) {
                activeTab.classList.add('active');
                activeTab.style.color = 'var(--text-primary)';
                activeTab.style.borderBottomColor = 'var(--accent-primary)';
                activeTab.style.fontWeight = '600';
            }

            // Toggle page content view visibility
            const pageDashboard = document.getElementById('page-dashboard');
            const pageHistory = document.getElementById('page-history');
            if (pageId === 'dashboard') {
                if (pageDashboard) pageDashboard.style.display = 'block';
                if (pageHistory) pageHistory.style.display = 'none';
                window.location.hash = 'dashboard';
                fetchPending();
            } else if (pageId === 'history') {
                if (pageDashboard) pageDashboard.style.display = 'none';
                if (pageHistory) pageHistory.style.display = 'block';
                window.location.hash = 'history';
                fetchHistory();
            }
        }

        // Handle browser URL hash changes for navigation sync
        window.addEventListener('hashchange', () => {
            const hash = window.location.hash.substring(1);
            if (hash === 'history') {
                switchPage('history');
            } else {
                switchPage('dashboard');
            }
        });

        function openHelpModal() {
            document.getElementById('help-modal-overlay').classList.add('active');
        }

        function closeHelpModal() {
            document.getElementById('help-modal-overlay').classList.remove('active');
        }

        async function fetchPending(isSync = false) {
            const container = document.getElementById('cards-container');
            const syncBtn = document.getElementById('sync-pipeline-btn');
            if (syncBtn) syncBtn.classList.add('loading');

            if (isSync) {
                showToast('Syncing pipeline with Agent Runtime...', 'success');
            }

            try {
                const response = await fetch('/api/pending');
                const data = await response.json();

                if (!data || data.length === 0) {
                    container.innerHTML = `
                        <div class="empty-state">
                            <div class="empty-icon-wrap">
                                <svg class="empty-icon" viewBox="0 0 24 24" fill="none" stroke-width="2">
                                    <path d="M22 11.08V12a10 10 0 1 1-5.93-9.14"></path>
                                    <polyline points="22 4 12 14.01 9 11.01"></polyline>
                                </svg>
                            </div>
                            <h3>All Clean! No Pending Actions</h3>
                            <p>All pull request quality scans have been resolved or auto-approved by the rules engine.</p>
                        </div>
                    `;
                    return;
                }

                container.innerHTML = '';
                pendingSessionsMap = {};
                data.forEach(pr => {
                    pendingSessionsMap[pr.session_id] = pr;
                    const calculatedRisk = pr.testing_risk_score >= 7 ? 'HIGH' : pr.testing_risk_score >= 4 ? 'MEDIUM' : 'LOW';
                    const card = document.createElement('div');
                    card.className = `pr-card ${calculatedRisk.toLowerCase()}-risk`;

                    const qualityFillClass = pr.quality_score >= 7 ? 'high-val' : pr.quality_score >= 4 ? 'med-val' : 'low-val';
                    const testingFillClass = pr.testing_risk_score >= 7 ? 'low-val' : pr.testing_risk_score >= 4 ? 'med-val' : 'high-val';

                    card.innerHTML = `
                        <div>
                            <div class="card-top">
                                <a class="repo-link repo-badge" href="https://github.com/${pr.repository}/pull/${pr.pr_number}" target="_blank" rel="noopener noreferrer">
                                    <svg class="repo-icon" viewBox="0 0 24 24"><path d="M12 2C6.477 2 2 6.477 2 12c0 4.42 2.865 8.166 6.839 9.489.5.092.682-.217.682-.482 0-.237-.008-.866-.013-1.7-2.782.603-3.369-1.34-3.369-1.34-.454-1.156-1.11-1.462-1.11-1.462-.908-.62.069-.608.069-.608 1.003.07 1.531 1.03 1.531 1.03.892 1.529 2.341 1.087 2.91.832.092-.647.35-1.088.636-1.338-2.22-.253-4.555-1.11-4.555-4.943 0-1.091.39-1.984 1.029-2.683-.103-.253-.446-1.27.098-2.647 0 0 .84-.269 2.75 1.025A9.564 9.564 0 0112 6.844c.85.004 1.705.115 2.504.337 1.909-1.294 2.747-1.025 2.747-1.025.546 1.377.203 2.394.1 2.647.64.699 1.028 1.592 1.028 2.683 0 3.842-2.339 4.687-4.566 4.935.359.309.678.919.678 1.852 0 1.336-.012 2.415-.012 2.743 0 .267.18.579.688.481C19.137 20.162 22 16.418 22 12c0-5.523-4.523-10-10-10z"/></svg>
                                    <span>${pr.repository}</span>
                                </a>
                                <span class="risk-badge ${calculatedRisk.toLowerCase()}">${calculatedRisk} RISK</span>
                            </div>
                            <div class="pr-info">
                                <h3 class="pr-title">#${pr.pr_number}: ${pr.pr_title}</h3>
                                <div class="pr-description">${(pr.state && pr.state.pr_description) ? marked.parseInline(pr.state.pr_description.replace(/\\\\n/g, '\\n').replace(/\\n/g, '\\n')) : 'No description provided.'}</div>
                                <div class="pr-meta">
                                    <span class="pr-author">
                                        <svg style="width: 14px; height: 14px; fill: currentColor;" viewBox="0 0 24 24"><path d="M12 12c2.21 0 4-1.79 4-4s-1.79-4-4-4-4 1.79-4 4 1.79 4 4 4zm0 2c-2.67 0-8 1.34-8 4v2h16v-2c0-2.66-5.33-4-8-4z"/></svg>
                                        <span>${pr.pr_author}</span>
                                    </span>
                                    <span>•</span>
                                    <span>${pr.workflow_status}</span>
                                </div>
                            </div>
                            <div class="score-row">
                                <div class="score-box" style="width: 100%;">
                                    <span class="score-label">Quality Score</span>
                                    <div class="score-value-bar">
                                        <span class="score-num">${pr.quality_score}/10</span>
                                        <div class="progress-track">
                                            <div class="progress-fill ${qualityFillClass}" style="width: ${pr.quality_score * 10}%"></div>
                                        </div>
                                    </div>
                                </div>
                            </div>
                        </div>
                        <div class="card-actions">
                            <button class="btn btn-primary" onclick="openModal('${pr.session_id}')">Review Quality Report</button>
                        </div>
                    `;
                    container.appendChild(card);
                });
            } catch (error) {
                console.error('Failed to fetch pending reviews:', error);
                showToast('Failed to connect to backend engine.', 'error');
            } finally {
                if (syncBtn) syncBtn.classList.remove('loading');
                fetchHistory();
            }
        }

        async function fetchHistory() {
            const tableBody = document.getElementById('history-table-body');
            if (!tableBody) return;

            // Show loading placeholder
            tableBody.innerHTML = `
                <tr id="history-loading-row">
                    <td colspan="7" style="text-align: center; color: var(--text-muted); padding: 2rem; border-bottom: none;">
                        <span class="loading-spinner" style="display: inline-block; width: 1.2rem; height: 1.2rem; border: 2px solid rgba(255,255,255,0.1); border-radius: 50%; border-top-color: var(--accent-primary); animation: spin 1s linear infinite; margin-right: 0.75rem; vertical-align: middle;"></span>
                        Loading triage history logs...
                    </td>
                </tr>
            `;

            try {
                const response = await fetch('/api/history');
                const data = await response.json();

                if (!data || data.length === 0) {
                    tableBody.innerHTML = `
                        <tr>
                            <td colspan="7" style="text-align: center; color: var(--text-muted); padding: 2rem;">
                                No historical triage sessions found.
                            </td>
                        </tr>
                    `;
                    return;
                }

                tableBody.innerHTML = '';
                data.forEach(item => {
                    const row = document.createElement('tr');

                    // Determine risk level class
                    const riskClass = item.risk_level === 'HIGH' ? 'high' : item.risk_level === 'MEDIUM' ? 'medium' : 'low';
                    
                    // Determine status class
                    let statusClass = 'processing';
                    if (item.status === 'Awaiting Review') statusClass = 'awaiting';
                    else if (item.status.includes('Approved')) statusClass = 'approved';
                    else if (item.status.includes('Rejected')) statusClass = 'rejected';

                    row.innerHTML = `
                        <td style="font-weight: 600;">
                            <a href="https://github.com/${item.repository}/pull/${item.pr_number}" target="_blank" rel="noopener noreferrer" style="color: var(--text-primary); text-decoration: none; display: flex; align-items: center; gap: 0.5rem;">
                                <span>#${item.pr_number}: ${item.pr_title}</span>
                            </a>
                        </td>
                        <td style="color: var(--text-secondary);">${item.repository}</td>
                        <td>${item.pr_author}</td>
                        <td><span class="risk-badge ${riskClass}" style="padding: 0.2rem 0.5rem; font-size: 0.7rem; border-radius: 6px;">${item.risk_level}</span></td>
                        <td><span class="status-badge ${statusClass}">${item.status}</span></td>
                        <td style="max-width: 250px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;" title="${item.comments || 'No feedback details.'}">
                            <span style="font-weight: 500;">${item.reviewer}</span>
                            <span style="color: var(--text-secondary); font-size: 0.85rem;">${item.comments ? ' - ' + item.comments : ''}</span>
                        </td>
                        <td style="color: var(--text-secondary); font-size: 0.85rem;">${item.timestamp}</td>
                    `;
                    tableBody.appendChild(row);
                });
            } catch (error) {
                console.error('Failed to fetch history:', error);
            }
        }

        function formatDiff(diffText) {
            if (!diffText) return '<div class="empty-state" style="padding: 2rem;">No diff contents available.</div>';

            const lines = diffText.split('\\n');
            const formatted = lines.map(line => {
                const escaped = line
                    .replace(/&/g, '&amp;')
                    .replace(/</g, '&lt;')
                    .replace(/>/g, '&gt;');

                if (escaped.startsWith('+') && !escaped.startsWith('+++')) {
                    return `<span class="diff-line-add">${escaped}</span>`;
                } else if (escaped.startsWith('-') && !escaped.startsWith('---')) {
                    return `<span class="diff-line-del">${escaped}</span>`;
                } else if (escaped.startsWith('@@')) {
                    return `<span class="diff-line-chunk">${escaped}</span>`;
                } else if (escaped.startsWith('diff') || escaped.startsWith('index') || escaped.startsWith('---') || escaped.startsWith('+++')) {
                    return `<span class="diff-line-meta">${escaped}</span>`;
                }
                return escaped;
            }).join('\\n');

            return formatted;
        }

        function openModal(sessionId) {
            const pr = pendingSessionsMap[sessionId];
            if (!pr) return;
            currentPR = pr;

            document.getElementById('modal-repo').innerHTML = `
                <a class="repo-link" href="https://github.com/${pr.repository}/pull/${pr.pr_number}" target="_blank" rel="noopener noreferrer">
                    <svg class="repo-icon" viewBox="0 0 24 24" style="fill: currentColor;"><path d="M12 2C6.477 2 2 6.477 2 12c0 4.42 2.865 8.166 6.839 9.489.5.092.682-.217.682-.482 0-.237-.008-.866-.013-1.7-2.782.603-3.369-1.34-3.369-1.34-.454-1.156-1.11-1.462-1.11-1.462-.908-.62.069-.608.069-.608 1.003.07 1.531 1.03 1.531 1.03.892 1.529 2.341 1.087 2.91.832.092-.647.35-1.088.636-1.338-2.22-.253-4.555-1.11-4.555-4.943 0-1.091.39-1.984 1.029-2.683-.103-.253-.446-1.27.098-2.647 0 0 .84-.269 2.75 1.025A9.564 9.564 0 0112 6.844c.85.004 1.705.115 2.504.337 1.909-1.294 2.747-1.025 2.747-1.025.546 1.377.203 2.394.1 2.647.64.699 1.028 1.592 1.028 2.683 0 3.842-2.339 4.687-4.566 4.935.359.309.678.919.678 1.852 0 1.336-.012 2.415-.012 2.743 0 .267.18.579.688.481C19.137 20.162 22 16.418 22 12c0-5.523-4.523-10-10-10z"/></svg>
                    <span>${pr.repository} #${pr.pr_number}</span>
                </a>
                <span style="margin-left: 0.4rem; margin-right: 0.4rem;">•</span>
                <span style="color: var(--text-muted); font-size: 0.82rem; font-weight: 500;">by ${pr.pr_author}</span>
            `;

            const qBadge = document.getElementById('modal-quality-badge');
            const qClass = pr.quality_score >= 7 ? 'high-val' : pr.quality_score >= 4 ? 'med-val' : 'low-val';
            qBadge.className = `score-badge quality ${qClass}`;
            qBadge.innerText = `QUALITY: ${pr.quality_score}/10`;

            // Testing risk header badge removed

            document.getElementById('modal-pr-title').innerText = pr.pr_title;

            // Formulate HTML from markdown using marked.js
            const formatContent = (text) => {
                if (!text) return "No findings reported.";
                // Replace escaped newlines if any
                const normalized = text.replace(/\\\\n/g, '\\n');
                return marked.parse(normalized);
            };

            const ga = pr.gemini_analysis || {};
            document.getElementById('modal-recommendation').innerHTML = formatContent(ga.recommendation);

            document.getElementById('modal-testing-gaps').innerHTML = formatContent(ga.testing_gaps);
            document.getElementById('modal-regression-risks').innerHTML = formatContent(ga.regression_risk);
            document.getElementById('modal-edge-cases').innerHTML = formatContent(ga.missing_edge_cases);
            document.getElementById('modal-security-audit-content').innerHTML = formatContent(ga.security_concerns);
            document.getElementById('modal-production-impact').innerHTML = formatContent(ga.production_impact);

            // Populate criteria sub-scores on overview tab
            const testingScore = ga.testing_score !== undefined ? parseInt(ga.testing_score) : null;
            const securityScore = ga.security_score !== undefined ? parseInt(ga.security_score) : null;
            const performanceScore = ga.performance_score !== undefined ? parseInt(ga.performance_score) : null;

            const updateScoreCard = (barId, valId, score) => {
                const bar = document.getElementById(barId);
                const val = document.getElementById(valId);
                bar.classList.remove('high-val', 'med-val', 'low-val');
                if (score === null || score === undefined) {
                    val.innerText = `--/10`;
                    bar.style.width = `0%`;
                } else {
                    val.innerText = `${score}/10`;
                    bar.style.width = `${score * 10}%`;
                    const colorClass = score >= 7 ? 'high-val' : score >= 4 ? 'med-val' : 'low-val';
                    bar.classList.add(colorClass);
                }
            };

            updateScoreCard('detail-score-bar-overall', 'detail-score-overall', pr.quality_score);
            updateScoreCard('detail-score-bar-testing', 'detail-score-testing', testingScore);
            updateScoreCard('detail-score-bar-security', 'detail-score-security', securityScore);
            updateScoreCard('detail-score-bar-performance', 'detail-score-performance', performanceScore);

            const updateTabBadge = (badgeId, prefix, score) => {
                const el = document.getElementById(badgeId);
                el.classList.remove('high-val', 'med-val', 'low-val');
                if (score === null || score === undefined) {
                    el.innerText = `${prefix}: --/10`;
                    el.className = `score-badge quality`;
                } else {
                    el.innerText = `${prefix}: ${score}/10`;
                    el.className = `score-badge quality ${score >= 7 ? 'high-val' : score >= 4 ? 'med-val' : 'low-val'}`;
                }
            };

            updateTabBadge('tab-score-testing', 'Testing Score', testingScore);
            updateTabBadge('tab-score-security', 'Security Score', securityScore);
            updateTabBadge('tab-score-performance', 'Performance Score', performanceScore);

            // Populate diff content with interactive file selector sidebar
            const parseDiff = (rawDiff) => {
                const files = {};
                if (!rawDiff) return files;

                const lines = rawDiff.split('\\n');
                let currentFile = null;
                let currentContent = [];

                for (let i = 0; i < lines.length; i++) {
                    const line = lines[i];
                    if (line.startsWith('diff --git ')) {
                        if (currentFile && currentContent.length > 0) {
                            files[currentFile] = currentContent.join('\\n');
                        }
                        const match = line.match(/b\\/(.+)$/);
                        currentFile = match ? match[1] : 'Unknown';
                        currentContent = [line];
                    } else {
                        if (!currentFile && line.trim()) {
                            currentFile = 'Changes';
                            currentContent = [line];
                        } else if (currentFile) {
                            currentContent.push(line);
                        }
                    }
                }
                if (currentFile && currentContent.length > 0) {
                    files[currentFile] = currentContent.join('\\n');
                }
                return files;
            };

            const fileDiffs = parseDiff(pr.pr_diff);
            const fileListContainer = document.getElementById('diff-file-list');
            fileListContainer.innerHTML = '';

            const fileNames = Object.keys(fileDiffs);
            if (fileNames.length === 0) {
                fileListContainer.innerHTML = '<div style="font-size: 0.8rem; color: var(--text-muted); padding: 0.5rem 0;">No file changes found.</div>';
                document.getElementById('modal-diff-content').innerHTML = "No diff available.";
                document.getElementById('diff-active-file-name').innerText = "None";
            } else {
                fileNames.forEach((fileName, index) => {
                    const btn = document.createElement('button');
                    btn.className = `file-select-btn${index === 0 ? ' active' : ''}`;

                    const fileContent = fileDiffs[fileName];
                    const additions = fileContent.split('\\n').filter(l => l.startsWith('+') && !l.startsWith('+++')).length;
                    const deletions = fileContent.split('\\n').filter(l => l.startsWith('-') && !l.startsWith('---')).length;

                    const baseName = fileName.split('/').pop();
                    btn.innerHTML = `
                        <span class="file-name-text" title="${fileName}">${baseName}</span>
                        <span class="file-changes-badge">
                            <span style="color: var(--accent-primary);">+${additions}</span>
                            <span style="color: var(--danger-text); margin-left: 0.25rem;">-${deletions}</span>
                        </span>
                    `;

                    btn.onclick = () => {
                        fileListContainer.querySelectorAll('.file-select-btn').forEach(b => b.classList.remove('active'));
                        btn.classList.add('active');
                        document.getElementById('diff-active-file-name').innerText = fileName;
                        document.getElementById('modal-diff-content').innerHTML = formatDiff(fileDiffs[fileName]);
                    };
                    fileListContainer.appendChild(btn);
                });

                document.getElementById('diff-active-file-name').innerText = fileNames[0];
                document.getElementById('modal-diff-content').innerHTML = formatDiff(fileDiffs[fileNames[0]]);
            }

            // Security findings warning box removed

            document.getElementById('modal-comment').value = '';

            // Reset main tab to Overview on open
            const firstMainTab = document.querySelector('.modal-main-tabs .main-tab-btn');
            if (firstMainTab) {
                switchMainTab(firstMainTab, 'panel-overview');
            }

            document.getElementById('modal-overlay').classList.add('active');
            document.getElementById('detail-modal').classList.add('active');
        }

        function closeModal() {
            document.getElementById('modal-overlay').classList.remove('active');
            document.getElementById('detail-modal').classList.remove('active');
        }

        function switchMainTab(btn, targetPanelId) {
            // Remove active class from all main tabs
            const tabs = btn.parentNode.querySelectorAll('.main-tab-btn');
            tabs.forEach(t => t.classList.remove('active'));

            // Add active class to clicked tab
            btn.classList.add('active');

            // Hide all main panels
            const panels = btn.parentNode.parentNode.querySelectorAll('.main-panel');
            panels.forEach(p => p.classList.remove('active'));

            // Show target panel
            document.getElementById(targetPanelId).classList.add('active');
        }

        async function submitAction(approved) {
            if (!currentPR || isSubmitting) return;

            const comments = document.getElementById('modal-comment').value;
            const targetSessionId = currentPR.session_id;

            isSubmitting = true;
            closeModal(); // Close modal immediately to avoid blocking the user
            showToast(approved ? 'Submitting pull request approval...' : 'Submitting change request...', 'success');

            try {
                const response = await fetch(`/api/action/${targetSessionId}`, {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                    },
                    body: JSON.stringify({
                        approved: approved,
                        comments: comments
                    })
                });

                const resData = await response.json();

                if (response.status === 200) {
                    showToast(approved ? 'Pull request successfully approved!' : 'Review changes requested.', 'success');
                    // Refetch list in background
                    setTimeout(() => fetchPending(), 1000);
                } else {
                    showToast(resData.detail || 'Action failed.', 'error');
                }
            } catch (error) {
                console.error(error);
                showToast('Failed to post decision to reasoning engine.', 'error');
            } finally {
                isSubmitting = false;
            }
        }

        function showToast(text, type) {
            const toast = document.getElementById('toast');
            const toastText = document.getElementById('toast-text');

            toastText.innerText = text;
            toast.className = `toast-notification ${type} active`;

            setTimeout(() => {
                toast.classList.remove('active');
            }, 3000);
        }

        // Initial Load
        document.addEventListener('DOMContentLoaded', () => {
            // Sync page view with location hash on load
            const hash = window.location.hash.substring(1);
            if (hash === 'history') {
                switchPage('history');
            } else {
                switchPage('dashboard');
            }

            // Auto-refresh every 30 seconds, unless user is actively reviewing details in the modal
            setInterval(() => {
                const modal = document.getElementById('detail-modal');
                if (modal && !modal.classList.contains('active')) {
                    const activeHash = window.location.hash.substring(1);
                    if (activeHash === 'history') {
                        fetchHistory();
                    } else {
                        fetchPending();
                    }
                }
            }, 30000);
        });
    </script>
</body>
</html>
"""

RESOLVED_SESSIONS = set()


@app.get("/logo.png")
async def get_logo():
    import os

    logo_path = os.path.join(os.path.dirname(__file__), "logo.png")
    if os.path.exists(logo_path):
        return FileResponse(logo_path)
    raise HTTPException(status_code=404, detail="Logo file not found")


@app.get("/", response_class=HTMLResponse)
async def get_dashboard():
    """Serves the dashboard single page web application."""
    return DASHBOARD_HTML


@app.get("/api/history", response_model=list[dict[str, Any]])
async def get_triage_history():
    """Queries the session service database to extract recent pull requests and their triage decisions."""
    current_time = time.time()
    if HISTORY_CACHE["data"] is not None and (current_time - HISTORY_CACHE["timestamp"]) < CACHE_TTL:
        logger.info("Serving triage history logs from memory cache")
        return HISTORY_CACHE["data"]

    try:
        session_service = VertexAiSessionService(
            project=PROJECT_ID, location=LOCATION, agent_engine_id=AGENT_RUNTIME_ID
        )
        list_response = await session_service.list_sessions(app_name="merge_guard")
        # Sort sessions by last_update_time descending (newest first)
        sorted_sessions = sorted(
            list_response.sessions,
            key=lambda x: getattr(x, "last_update_time", 0.0),
            reverse=True,
        )
        # Limit history fetch size to 10 to cut down database load and latency
        sessions = sorted_sessions[:10]
    except Exception as e:
        logger.exception("Failed to list sessions from Vertex AI Session Service")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to list sessions from Vertex AI Session Service: {e}",
        ) from e

    history_list = []
    seen_prs = set()

    async def process_history_session(s):
        try:
            session_detail = await session_service.get_session(
                app_name="merge_guard", user_id=s.user_id, session_id=s.id
            )
        except Exception as e:
            logger.warning(f"Skipping history lookup for session {s.id}: {e}")
            return None

        if not session_detail:
            return None

        state = session_detail.state or {}
        repository = state.get("repository") or "Unknown"
        pr_number = state.get("pr_number") or 0

        # Don't show sessions that have no repository set (i.e. empty/uninitialized)
        if repository == "Unknown" and pr_number == 0:
            return None

        # Determine the triage decision and current status
        decision = state.get("decision")
        reviewer = state.get("reviewer")
        comments = state.get("comments") or ""

        # Figure out if there are pending interrupts
        pending_interrupts = {}
        if session_detail.events:
            for event in session_detail.events:
                content = event.content
                if not content:
                    continue
                parts = (
                    getattr(content, "parts", None) or content.get("parts", [])
                    if isinstance(content, dict)
                    else getattr(content, "parts", [])
                )
                for part in parts:
                    function_call = getattr(part, "function_call", None) or (
                        part.get("function_call") if isinstance(part, dict) else None
                    )
                    function_response = getattr(part, "function_response", None) or (
                        part.get("function_response") if isinstance(part, dict) else None
                    )
                    if function_call:
                        f_name = function_call.get("name") if isinstance(function_call, dict) else getattr(function_call, "name", None)
                        if f_name == "adk_request_input":
                            f_args = function_call.get("args") or {} if isinstance(function_call, dict) else getattr(function_call, "args", {}) or {}
                            if not isinstance(f_args, dict):
                                try:
                                    f_args = dict(f_args)
                                except Exception:
                                    f_args = {}
                            interrupt_id = (
                                function_call.get("id") if isinstance(function_call, dict) else getattr(function_call, "id", None)
                            ) or f_args.get("interruptId") or f_args.get("interrupt_id")
                            pending_interrupts[interrupt_id] = True
                    elif function_response:
                        f_name = function_response.get("name") if isinstance(function_response, dict) else getattr(function_response, "name", None)
                        if f_name == "adk_request_input":
                            interrupt_id = function_response.get("id") if isinstance(function_response, dict) else getattr(function_response, "id", None)
                            pending_interrupts.pop(interrupt_id, None)

        display_reviewer = reviewer or "N/A"
        if display_reviewer == "System":
            display_reviewer = "Agent"
        elif display_reviewer == "System (Security Checkpoint)":
            display_reviewer = "Agent (Security Checkpoint)"

        if pending_interrupts:
            status = "Awaiting Review"
        elif decision == "approved":
            status = "Agent Approved" if display_reviewer == "Agent" else "Approved"
        elif decision == "changes_requested" or decision == "rejected":
            status = "Agent Rejected" if display_reviewer == "Agent (Security Checkpoint)" else "Rejected"
        else:
            status = "Processing" if not decision else "Completed"

        # Resolve last update time formatting
        import datetime
        update_ts = getattr(s, "last_update_time", None)
        if update_ts:
            dt = datetime.datetime.fromtimestamp(update_ts, datetime.timezone.utc)
            formatted_time = dt.strftime("%Y-%m-%d %H:%M:%S UTC")
        else:
            formatted_time = "Unknown"

        # Calculate quality-based risk rating to align with pending cards
        gemini_analysis = state.get("gemini_analysis") or {}
        testing_score = int(gemini_analysis.get("testing_score", 10))
        security_score = int(gemini_analysis.get("security_score", 10))
        performance_score = int(gemini_analysis.get("performance_score", 10))
        quality_score = int((testing_score + security_score + performance_score) / 3.0)
        testing_risk_score = 10 - quality_score
        calculated_risk = "HIGH" if testing_risk_score >= 7 else "MEDIUM" if testing_risk_score >= 4 else "LOW"

        return {
            "session_id": s.id,
            "repository": repository,
            "pr_number": pr_number,
            "pr_title": state.get("pr_title") or f"PR #{pr_number}",
            "pr_author": state.get("pr_author") or "Unknown",
            "risk_level": calculated_risk,
            "status": status,
            "reviewer": display_reviewer,
            "comments": comments,
            "timestamp": formatted_time,
            "raw_timestamp": update_ts or 0.0
        }

    tasks = [process_history_session(s) for s in sessions]
    results = await asyncio.gather(*tasks)

    for r in results:
        if r is not None:
            pr_key = (r["repository"], r["pr_number"])
            if pr_key not in seen_prs:
                seen_prs.add(pr_key)
                history_list.append(r)

    # Sort results by raw_timestamp descending (newest first)
    history_list = sorted(history_list, key=lambda x: x["raw_timestamp"], reverse=True)
    
    # Store in cache
    HISTORY_CACHE["timestamp"] = time.time()
    HISTORY_CACHE["data"] = history_list
    
    return history_list


@app.get("/api/pending", response_model=list[dict[str, Any]])
async def get_pending_sessions():
    """Queries the session service database to extract all sessions currently suspended on manual review."""
    try:
        session_service = VertexAiSessionService(
            project=PROJECT_ID, location=LOCATION, agent_engine_id=AGENT_RUNTIME_ID
        )
        # List all sessions regardless of who created them (by passing user_id=None)
        list_response = await session_service.list_sessions(app_name="merge_guard")
        # Sort sessions by last_update_time descending (newest first)
        sorted_sessions = sorted(
            list_response.sessions,
            key=lambda x: getattr(x, "last_update_time", 0.0),
            reverse=True,
        )
        sessions = [s for s in sorted_sessions if s.id not in RESOLVED_SESSIONS][:20]
    except Exception as e:
        logger.exception(
            "Failed to connect/list sessions from Vertex AI Session Service"
        )
        raise HTTPException(
            status_code=500,
            detail=f"Failed to list sessions from Vertex AI Session Service: {e}",
        ) from e

    pending_list = []

    # Check each session's history in parallel for unresolved manual review checkpoints
    async def process_session(s):
        try:
            session_detail = await session_service.get_session(
                app_name="merge_guard", user_id=s.user_id, session_id=s.id
            )
        except Exception as e:
            logger.warning(f"Skipping lookup for session {s.id}: {e}")
            return None

        if not session_detail or not session_detail.events:
            return None

        pending_interrupts = {}
        for event in session_detail.events:
            content = event.content
            if not content:
                continue

            # Handle both pydantic models and dictionaries
            parts = (
                getattr(content, "parts", None) or content.get("parts", [])
                if isinstance(content, dict)
                else getattr(content, "parts", [])
            )
            for part in parts:
                function_call = getattr(part, "function_call", None) or (
                    part.get("function_call") if isinstance(part, dict) else None
                )
                function_response = getattr(part, "function_response", None) or (
                    part.get("function_response") if isinstance(part, dict) else None
                )

                if function_call:
                    name = None
                    args = {}
                    interrupt_id = None
                    msg = ""

                    if isinstance(function_call, dict):
                        name = function_call.get("name")
                        args = function_call.get("args") or {}
                        interrupt_id = (
                            function_call.get("id")
                            or args.get("interruptId")
                            or args.get("interrupt_id")
                        )
                        msg = function_call.get("message") or args.get("message") or ""
                    else:
                        name = getattr(function_call, "name", None)
                        args_raw = getattr(function_call, "args", None) or {}
                        if isinstance(args_raw, dict):
                            args = args_raw
                        elif hasattr(args_raw, "model_dump"):
                            args = args_raw.model_dump()
                        else:
                            try:
                                args = dict(args_raw)
                            except Exception:
                                args = {}
                        interrupt_id = (
                            getattr(function_call, "id", None)
                            or args.get("interruptId")
                            or args.get("interrupt_id")
                        )
                        msg = (
                            getattr(function_call, "message", None)
                            or args.get("message")
                            or ""
                        )

                    if name == "adk_request_input":
                        pending_interrupts[interrupt_id] = {
                            "interrupt_id": interrupt_id,
                            "message": msg,
                        }
                elif function_response:
                    name = None
                    interrupt_id = None
                    if isinstance(function_response, dict):
                        name = function_response.get("name")
                        interrupt_id = function_response.get("id")
                    else:
                        name = getattr(function_response, "name", None)
                        interrupt_id = getattr(function_response, "id", None)

                    if name == "adk_request_input":
                        pending_interrupts.pop(interrupt_id, None)

        if pending_interrupts:
            state = session_detail.state or {}

            repository = state.get("repository", "Unknown")
            pr_number = state.get("pr_number", 0)
            pr_title = state.get("pr_title", "Unknown")
            pr_author = state.get("pr_author", "Unknown")
            risk_level = state.get("risk_level", "low").upper()

            gemini_analysis = state.get("gemini_analysis") or {}

            # Extract sub-scores safely (defaulting to 10 if not present)
            testing_score = int(gemini_analysis.get("testing_score", 10))
            security_score = int(gemini_analysis.get("security_score", 10))
            performance_score = int(gemini_analysis.get("performance_score", 10))

            # Calculate equal-weighted overall quality score
            quality_score = int(
                (testing_score + security_score + performance_score) / 3.0
            )
            testing_risk_score = 10 - quality_score

            first_id = next(iter(pending_interrupts.keys()))
            first_msg = pending_interrupts[first_id]["message"]

            return {
                "session_id": s.id,
                "user_id": s.user_id,
                "interrupt_id": first_id,
                "repository": repository,
                "pr_number": pr_number,
                "pr_title": pr_title,
                "pr_author": pr_author,
                "risk_level": risk_level,
                "workflow_status": "Awaiting Human Review",
                "quality_score": quality_score,
                "testing_risk_score": testing_risk_score,
                "security_findings": state.get("security_findings", []),
                "masked_categories": state.get("masked_categories", []),
                "gemini_analysis": gemini_analysis,
                "message": first_msg,
                "pr_diff": state.get("pr_diff", ""),
                "state": state,
            }
        else:
            state = session_detail.state or {}
            # Only add to resolved blacklist if the run actually finished generating its analysis
            if "gemini_analysis" in state:
                RESOLVED_SESSIONS.add(s.id)
        return None

    tasks = [process_session(s) for s in sessions]
    results = await asyncio.gather(*tasks)

    pending_list = []
    seen_prs = set()
    for r in results:
        if r is not None:
            pr_key = (r["repository"], r["pr_number"])
            if pr_key not in seen_prs:
                seen_prs.add(pr_key)
                pending_list.append(r)

    return pending_list


@app.post("/api/action/{session_id}")
async def resume_workflow(session_id: str, action: ActionRequest):
    """Resumes a paused pull request triage session on the Agent Runtime with the manual review action decision."""
    owner_user_id = "default-user"

    # 1. Resolve actual owner user_id to prevent session ownership ValueError
    try:
        session_service = VertexAiSessionService(
            project=PROJECT_ID, location=LOCATION, agent_engine_id=AGENT_RUNTIME_ID
        )
        list_response = await session_service.list_sessions(app_name="merge_guard")
        for s in list_response.sessions:
            if s.id == session_id:
                owner_user_id = s.user_id
                break
    except Exception as e:
        logger.warning(f"Failed to lookup session owner user_id for {session_id}: {e}")

    # 2. Formulate decision text in the format expected by pr_triage_agent/agent.py (Approve / Request Changes)
    decision_text = "Approve" if action.approved else "Request Changes"
    if action.comments:
        decision_text += f" - {action.comments}"

    # 3. Construct resume message with the correct function_response structure
    payload = {
        "class_method": "async_stream_query",
        "input": {
            "user_id": owner_user_id,
            "session_id": session_id,
            "message": {
                "role": "user",
                "parts": [
                    {
                        "function_response": {
                            "name": "adk_request_input",
                            "id": "review_decision",
                            # We satisfy both the user's {"approved": bool} and the agent's {"output": str} formats
                            "response": {
                                "approved": action.approved,
                                "output": decision_text,
                            },
                        }
                    }
                ],
            },
        },
    }

    # 4. Acquire Google credentials bearer token
    try:
        credentials, _project = google.auth.default()
        auth_req = google.auth.transport.requests.Request()
        credentials.refresh(auth_req)
        token = credentials.token
    except Exception as e:
        logger.exception("Failed to refresh GCP credentials")
        raise HTTPException(
            status_code=500, detail=f"Failed to retrieve GCP auth token: {e}"
        ) from e

    # 5. POST to Agent Runtime endpoint using streaming mode to execute the graph
    url = f"https://{LOCATION}-aiplatform.googleapis.com/v1/projects/{PROJECT_ID}/locations/{LOCATION}/reasoningEngines/{AGENT_RUNTIME_ID}:streamQuery"
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}

    logger.info(
        f"Posting session resumption payload to {url} for session {session_id} under owner {owner_user_id}"
    )
    try:
        response = requests.post(url, json=payload, headers=headers, stream=True)
    except Exception as e:
        logger.exception("Failed to connect to Reasoning Engine API gateway")
        raise HTTPException(
            status_code=500,
            detail=f"HTTP request to reasoning engine endpoint failed: {e}",
        ) from e

    if response.status_code != 200:
        logger.error(
            f"Reasoning engine returned failure status {response.status_code}: {response.text}"
        )
        raise HTTPException(
            status_code=response.status_code,
            detail=f"Agent Runtime execution failed: {response.text}",
        )

    # Read the response stream fully to ensure the backend executes the nodes to completion
    try:
        for _chunk in response.iter_content(chunk_size=4096):
            pass
    except Exception as e:
        logger.warning(f"Error fully consuming response stream chunks: {e}")

    logger.info(f"Session {session_id} successfully resumed and completed!")
    RESOLVED_SESSIONS.add(session_id)
    
    # Invalidate triage history cache to force a fresh reload on next fetch
    HISTORY_CACHE["data"] = None
    
    return {"status": "success", "detail": "Workflow resumed successfully"}





if __name__ == "__main__":
    import uvicorn

    # Default to port 8080 to match container routing
    uvicorn.run(app, host="0.0.0.0", port=8080)
