import json

from fastapi.routing import APIRoute

from app.main import app


def requirements(dependant, acc):
    for dep in dependant.dependencies:
        call = dep.call
        name = getattr(call, "__qualname__", str(call))
        extra = None
        if getattr(call, "__closure__", None):
            vals = [c.cell_contents for c in call.__closure__]
            extra = [v for v in vals if isinstance(v, (str, tuple, list))]
        if "require" in name or "get_current_user" in name:
            acc.append({"dep": name.split(".")[0] if "<locals>" in name else name, "args": extra})
        requirements(dep, acc)
    return acc


out = []
for route in app.routes:
    if not isinstance(route, APIRoute):
        continue
    for method in sorted(route.methods - {"HEAD", "OPTIONS"}):
        reqs = requirements(route.dependant, [])
        out.append({"method": method, "path": route.path, "name": route.name, "reqs": reqs,
                    "body": bool(route.body_field), "params": [p.name for p in route.dependant.path_params], "query": [{"name": q.name, "required": q.required} for q in route.dependant.query_params]})
print(json.dumps(out))
