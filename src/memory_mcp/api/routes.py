from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Route


def ok(data: dict) -> JSONResponse:
    return JSONResponse({"ok": True, "data": data})


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


# Route ordering: search before the bare /memories path, trace/forget path params last
routes = [
    Route("/api/v1/memories/search", endpoint=handle_recall, methods=["GET"]),
    Route("/api/v1/memories", endpoint=handle_remember, methods=["POST"]),
    Route("/api/v1/memories", endpoint=handle_recall_all, methods=["GET"]),
    Route("/api/v1/memories/{entity_key:path}/trace", endpoint=handle_trace, methods=["GET"]),
    Route("/api/v1/memories/{entity_key:path}", endpoint=handle_forget, methods=["DELETE"]),
    Route("/api/v1/relations", endpoint=handle_relate, methods=["POST"]),
    Route("/api/v1/graph/{entity_key:path}", endpoint=handle_graph_query, methods=["GET"]),
]
