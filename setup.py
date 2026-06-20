#!/usr/bin/env python3
"""goal-hook 一键安装 —— 复制到 CC 插件目录 + 注册 marketplace。"""
import json, os, shutil, sys

PLUGIN_DIR = os.path.dirname(os.path.abspath(__file__))
CC_PLUGINS = os.path.join(os.path.expanduser("~"), ".claude", "plugins")
MKT_DIR = os.path.join(CC_PLUGINS, "local-marketplaces", "goal-hook-marketplace")
PLUGIN_DEST = os.path.join(MKT_DIR, "plugins", "goal-hook")
SETTINGS_PATH = os.path.join(os.path.expanduser("~"), ".claude", "settings.json")

if not os.path.exists(SETTINGS_PATH):
    print(f"ERROR: {SETTINGS_PATH} not found. Run Claude Code first.")
    sys.exit(1)

# Step 1: Copy plugin to CC plugins directory
print(f"[1/3] Installing to {PLUGIN_DEST} ...")
os.makedirs(os.path.dirname(PLUGIN_DEST), exist_ok=True)
if os.path.exists(PLUGIN_DEST):
    try:
        shutil.rmtree(PLUGIN_DEST)
    except OSError:
        # Junction or permission issue — try cmd rmdir
        os.system(f'cmd /c "rmdir /s /q {PLUGIN_DEST}" 2>nul')
        if os.path.exists(PLUGIN_DEST):
            shutil.rmtree(PLUGIN_DEST, ignore_errors=True)
shutil.copytree(PLUGIN_DIR, PLUGIN_DEST,
                ignore=shutil.ignore_patterns(".git", "__pycache__", "*.pyc", ".gitignore"))

# Step 2: Write marketplace.json with correct relative path for CC plugins directory
# (repo has source:"." for standalone use; CC plugins dir needs source:"./plugins/goal-hook")
os.makedirs(os.path.join(MKT_DIR, ".claude-plugin"), exist_ok=True)
with open(os.path.join(PLUGIN_DIR, ".claude-plugin", "marketplace.json"), "r", encoding="utf-8") as f:
    mkt = json.load(f)
for p in mkt["plugins"]:
    p["source"] = "./plugins/goal-hook"
with open(os.path.join(MKT_DIR, ".claude-plugin", "marketplace.json"), "w", encoding="utf-8") as f:
    json.dump(mkt, f, indent=2, ensure_ascii=False)

# Step 3: Register in settings.json
print("[2/3] Registering in settings.json ...")
with open(SETTINGS_PATH, "r", encoding="utf-8") as f:
    settings = json.load(f)

settings.setdefault("extraKnownMarketplaces", {})["goal-hook-marketplace"] = {
    "source": {"path": MKT_DIR, "source": "directory"}
}
settings.setdefault("enabledPlugins", {})["goal-hook@goal-hook-marketplace"] = True

with open(SETTINGS_PATH, "w", encoding="utf-8") as f:
    json.dump(settings, f, indent=2, ensure_ascii=False)

# Verify
print("[3/3] Verifying ...")
for f in ["hooks/hooks.json", "scripts/_goal_check.py", ".claude-plugin/plugin.json"]:
    fp = os.path.join(PLUGIN_DEST, f)
    status = "OK" if os.path.exists(fp) else "MISS"
    print(f"  [{status}] {f}")

print(f"\nInstalled: {MKT_DIR}")
print("Restart Claude Code to activate.")
