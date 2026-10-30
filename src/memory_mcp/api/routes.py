from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Route


def ok(data: dict, status_code: int = 200) -> JSONResponse:
    return JSONResponse({"ok": True, "data": data}, status_code=status_code)


def err(message: str, status_code: int = 400) -> JSONResponse:
    return JSONResponse({"ok": False, "error": message}, status_code=status_code)


# POST /api/v1/memories
async def handle_remember(request: Request) -> JSONResponse:
    from ..tools import remember
    try:
        body = await request.json()
    except Exception:
        return err("Invalid JSON body")
    try:
        result = await remember.remember_tool(body)
    except ValueError as e:
        return err(str(e))
    except Exception as e:
        return err(str(e), 500)
    return ok(result)


# GET /api/v1/memories/search  — must be registered BEFORE /api/v1/memories
async def handle_recall(request: Request) -> JSONResponse:
    from ..tools import recall
    params = request.query_params
    query = params.get("query")
    if not query:
        return err("Missing required query param: query")
    arguments: dict = {"query": query}
    if "entity_type" in params:
        arguments["entity_type"] = params["entity_type"]
    if "limit" in params:
        try:
            arguments["limit"] = int(params["limit"])
        except ValueError:
            return err("limit must be an integer")
    if "include_evolution" in params:
        arguments["include_evolution"] = params["include_evolution"].lower() == "true"
    if "explain" in params:
        arguments["explain"] = params["explain"].lower() in {"1", "true"}
    try:
        result = await recall.recall_tool(arguments)
    except ValueError as e:
        return err(str(e))
    except Exception as e:
        return err(str(e), 500)
    return ok(result)


# GET /api/v1/memories
async def handle_recall_all(request: Request) -> JSONResponse:
    from ..tools import recall_all
    params = request.query_params
    arguments: dict = {}
    if "entity_type" in params:
        arguments["entity_type"] = params["entity_type"]
    if "limit" in params:
        try:
            arguments["limit"] = int(params["limit"])
        except ValueError:
            return err("limit must be an integer")
    if "offset" in params:
        try:
            arguments["offset"] = int(params["offset"])
        except ValueError:
            return err("offset must be an integer")
        if arguments["offset"] < 0:
            return err("offset must not be negative")
    if "order" in params:
        if params["order"] not in {"created_at", "valid_from"}:
            return err("order must be created_at or valid_from")
        arguments["order"] = params["order"]
    try:
        result = await recall_all.recall_all_tool(arguments)
    except Exception as e:
        return err(str(e), 500)
    return ok(result)


# GET /api/v1/memories/{entity_key:path}/trace
async def handle_trace(request: Request) -> JSONResponse:
    from ..tools import trace
    entity_key = request.path_params["entity_key"]
    arguments: dict = {"entity_key": entity_key}
    fmt = request.query_params.get("format")
    if fmt:
        arguments["format"] = fmt
    try:
        result = await trace.trace_tool(arguments)
    except ValueError as e:
        return err(str(e))
    except Exception as e:
        return err(str(e), 500)
    return ok(result)


# DELETE /api/v1/memories/{entity_key:path}
async def handle_forget(request: Request) -> JSONResponse:
    from ..tools import forget
    entity_key = request.path_params["entity_key"]
    arguments: dict = {"entity_key": entity_key}
    reason = request.query_params.get("reason")
    if reason:
        arguments["reason"] = reason
    try:
        result = await forget.forget_tool(arguments)
    except ValueError as e:
        return err(str(e))
    except Exception as e:
        return err(str(e), 500)
    return ok(result)


# POST /api/v1/relations
async def handle_relate(request: Request) -> JSONResponse:
    from ..tools import relate
    try:
        body = await request.json()
    except Exception:
        return err("Invalid JSON body")
    try:
        result = await relate.relate_tool(body)
    except ValueError as e:
        return err(str(e))
    except Exception as e:
        return err(str(e), 500)
    return ok(result)


# DELETE /api/v1/relations/{relation_id}
async def handle_unrelate(request: Request) -> JSONResponse:
    from ..tools import unrelate
    relation_id = request.path_params["relation_id"]
    try:
        result = await unrelate.unrelate_tool({"relation_id": relation_id})
    except ValueError as e:
        return err(str(e))
    except Exception as e:
        return err(str(e), 500)
    return ok(result)


# GET /api/v1/graph/{entity_key:path}
async def handle_graph_query(request: Request) -> JSONResponse:
    from ..tools import graph_query
    entity_key = request.path_params["entity_key"]
    arguments: dict = {"entity_key": entity_key}
    if "depth" in request.query_params:
        try:
            arguments["depth"] = int(request.query_params["depth"])
        except ValueError:
            return err("depth must be an integer")
    if "relation_types" in request.query_params:
        arguments["relation_types"] = [
            t.strip() for t in request.query_params["relation_types"].split(",") if t.strip()
        ]
    try:
        result = await graph_query.graph_query_tool(arguments)
    except ValueError as e:
        return err(str(e))
    except Exception as e:
        return err(str(e), 500)
    return ok(result)


# POST /api/v1/maintenance/run  — starts one run in the background (host cron calls this daily)
async def handle_maintenance_run(request: Request) -> JSONResponse:
    from ..engine import maintenance
    try:
        job_id = await maintenance.start()
    except maintenance.AlreadyRunning as e:
        return err(str(e), 409)
    return ok({"job_id": job_id}, 202)


# GET /api/v1/findings?status=&kind=
async def handle_findings(request: Request) -> JSONResponse:
    from ..engine import maintenance
    params = request.query_params
    items = await maintenance.list_findings(status=params.get("status"), kind=params.get("kind"))
    return ok({"items": items, "total": len(items)})


# GET /api/v1/memories/{memory_id}
async def handle_get_memory(request: Request) -> JSONResponse:
    from ..tools import governance
    memory = await governance.get_memory(request.path_params["memory_id"])
    if memory is None:
        return err("Memory not found", 404)
    return ok(memory)


async def _json_body(request: Request) -> dict:
    try:
        body = await request.json()
    except Exception:
        raise ValueError("Invalid JSON body")
    if not isinstance(body, dict):
        raise ValueError("Invalid JSON body")
    return body


# POST /api/v1/memories/{memory_id}/correct  body {content}
async def handle_correct(request: Request) -> JSONResponse:
    from ..tools import governance
    try:
        body = await _json_body(request)
        result = await governance.correct_memory(request.path_params["memory_id"], body.get("content") or "")
    except LookupError as e:
        return err(str(e), 404)
    except governance.NotCurrent as e:
        return err(str(e), 409)
    except ValueError as e:
        return err(str(e))
    except Exception as e:
        return err(str(e), 500)
    return ok(result)


# POST /api/v1/memories/{memory_id}/archive  body {reason}
async def handle_archive(request: Request) -> JSONResponse:
    from ..tools import forget
    try:
        body = await _json_body(request)
        reason = str(body.get("reason") or "").strip()
        if not reason:
            return err("Missing required field: reason")
        result = await forget.forget_tool({"memory_id": request.path_params["memory_id"], "reason": reason})
    except forget.MemoryNotFound as e:
        return err(str(e), 404)
    except forget.MemoryNotCurrent as e:
        return err(str(e), 409)
    except ValueError as e:
        return err(str(e))
    except Exception as e:
        return err(str(e), 500)
    return ok(result)


# POST /api/v1/findings/{finding_id}/dismiss  — a person marks an open finding a false positive
async def handle_dismiss_finding(request: Request) -> JSONResponse:
    from ..engine import maintenance
    try:
        result = await maintenance.dismiss_finding(request.path_params["finding_id"])
    except LookupError as e:
        return err(str(e), 404)
    except maintenance.FindingNotOpen as e:
        return err(str(e), 409)
    except Exception as e:
        return err(str(e), 500)
    return ok(result)


# Route ordering: search before the bare /memories path, trace/forget path params last
routes = [
    Route("/api/v1/memories/search", endpoint=handle_recall, methods=["GET"]),
    # By-id routes share the prefix with the {entity_key:path} routes. They differ by method or
    # suffix (GET / archive / correct vs DELETE / trace), and Starlette prefers a route that
    # matches the method, so the two shapes coexist. tests/test_governance.py covers the order.
    Route("/api/v1/memories/{memory_id}", endpoint=handle_get_memory, methods=["GET"]),
    Route("/api/v1/memories/{memory_id}/correct", endpoint=handle_correct, methods=["POST"]),
    Route("/api/v1/memories/{memory_id}/archive", endpoint=handle_archive, methods=["POST"]),
    Route("/api/v1/memories", endpoint=handle_remember, methods=["POST"]),
    Route("/api/v1/memories", endpoint=handle_recall_all, methods=["GET"]),
    Route("/api/v1/memories/{entity_key:path}/trace", endpoint=handle_trace, methods=["GET"]),
    Route("/api/v1/memories/{entity_key:path}", endpoint=handle_forget, methods=["DELETE"]),
    Route("/api/v1/relations", endpoint=handle_relate, methods=["POST"]),
    Route("/api/v1/relations/{relation_id}", endpoint=handle_unrelate, methods=["DELETE"]),
    Route("/api/v1/graph/{entity_key:path}", endpoint=handle_graph_query, methods=["GET"]),
    Route("/api/v1/maintenance/run", endpoint=handle_maintenance_run, methods=["POST"]),
    Route("/api/v1/findings", endpoint=handle_findings, methods=["GET"]),
    Route("/api/v1/findings/{finding_id}/dismiss", endpoint=handle_dismiss_finding, methods=["POST"]),
]
