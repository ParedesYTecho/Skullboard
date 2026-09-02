#!/usr/bin/env python3
"""
scripts/route_security_audit.py — Empirical Challenger Route Security Audit
Verifies access controls and permissions across all Flask endpoints in webserver.py.
"""

import ast
import os
import sys

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
webserver_path = os.path.join(ROOT_DIR, "webserver.py")

with open(webserver_path, "r", encoding="utf-8") as f:
    tree = ast.parse(f.read(), filename="webserver.py")

print("Auditing Flask Routes in webserver.py...")

routes = []
for node in tree.body:
    if isinstance(node, ast.FunctionDef):
        for decorator in node.decorator_list:
            if isinstance(decorator, ast.Call) and isinstance(decorator.func, ast.Attribute) and decorator.func.attr == "route":
                route_path = decorator.args[0].value if decorator.args and isinstance(decorator.args[0], ast.Constant) else "unknown"
                methods = []
                for kw in decorator.keywords:
                    if kw.arg == "methods" and isinstance(kw.value, ast.List):
                        methods = [elt.value for elt in kw.value.elts if isinstance(elt, ast.Constant)]
                routes.append((node.name, route_path, methods, node))

print(f"Discovered {len(routes)} active routes:")
for fn_name, path, methods, node in routes:
    # Check calls inside function
    calls = [
        sub.func.id
        for sub in ast.walk(node)
        if isinstance(sub, ast.Call) and isinstance(sub.func, ast.Name)
    ]
    has_auth_check = "_is_guild_authorized" in calls
    has_bearer_extract = "_extract_bearer" in calls
    has_user_fetch = "_fetch_discord_user" in calls
    has_guilds_fetch = "_fetch_discord_guilds" in calls
    
    print(f" - [{','.join(methods) or 'GET'}] {path} -> {fn_name}()")
    print(f"     Bearer Auth: {has_bearer_extract} | User Fetch: {has_user_fetch} | Guilds Fetch: {has_guilds_fetch} | Admin Check: {has_auth_check}")

print("\nAudit Complete.")
