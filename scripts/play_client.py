from __future__ import annotations

import argparse
import asyncio
import json
import os
from contextlib import asynccontextmanager
from typing import Any, AsyncGenerator, Dict, Optional

import httpx
import yaml
from mcp import ClientSession, StdioServerParameters
from mcp.client.sse import sse_client
from mcp.client.stdio import stdio_client
from mcp.client.streamable_http import streamable_http_client


# ---------------------------
# Helpers: pretty printing
# ---------------------------

def _hr(title: str) -> None:
    print("\n" + "=" * 80)
    print(title)
    print("=" * 80)


def _step(title: str) -> None:
    print("\n--- " + title)


def _pp(obj: Any) -> str:
    """Pretty-print JSON-able objects."""
    try:
        return json.dumps(obj, indent=2, ensure_ascii=False, sort_keys=False)
    except Exception:
        return str(obj)


def extract_payload(result: Any) -> Any:
    """
    Normalize MCP tool call result into Python payload:
    - Prefer result.structuredContent when present
    - Else attempt to parse first TextContent as JSON
    - Else return raw text / empty
    """
    sc = getattr(result, "structuredContent", None)
    if sc not in (None, {}, []):
        # FastMCP sometimes puts {"result": <primitive>} or already a list/dict
        if isinstance(sc, dict) and "result" in sc and len(sc) == 1:
            return sc["result"]
        return sc

    content = getattr(result, "content", None) or []
    if not content:
        return None

    text = getattr(content[0], "text", None)
    if text is None:
        return str(content[0])

    # Attempt JSON parsing
    t = text.strip()
    if (t.startswith("{") and t.endswith("}")) or (t.startswith("[") and t.endswith("]")):
        try:
            return json.loads(t)
        except Exception:
            return text
    return text


def show_result(result: Any, label: str = "Result") -> Any:
    payload = extract_payload(result)
    print(f"{label}:")
    print(_pp(payload))
    return payload


def require_int(x: Any, label: str) -> int:
    if isinstance(x, int):
        return x
    if isinstance(x, str) and x.isdigit():
        return int(x)
    raise ValueError(f"{label} expected int, got: {x!r}")


# ---------------------------
# MCP session creation
# ---------------------------

@asynccontextmanager
async def session_stdio() -> AsyncGenerator[ClientSession, None]:
    params = StdioServerParameters(
        command="uv",
        args=["run", "python", "-m", "clinic_mcp_server.main", "--transport", "stdio"],
    )
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            yield session


@asynccontextmanager
async def session_http(url: str, token: str) -> AsyncGenerator[ClientSession, None]:
    async with httpx.AsyncClient(
        headers={"Authorization": f"Bearer {token}"},
        timeout=10.0,
    ) as client:
        async with streamable_http_client(url, http_client=client) as (read, write, _):
            async with ClientSession(read, write) as session:
                await session.initialize()
                yield session


@asynccontextmanager
async def session_sse(url: str) -> AsyncGenerator[ClientSession, None]:
    # SSE demo has no JWT in your design
    async with sse_client(url) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            yield session


# ---------------------------
# Scenario runner
# ---------------------------

async def run_scenario(cfg: Dict[str, Any]) -> None:
    server = cfg.get("server", {})
    transport = server.get("transport", "streamable-http")
    http_url = server.get("http_url", "http://127.0.0.1:8080/mcp")
    sse_url = server.get("sse_url", "http://127.0.0.1:8081/sse")
    token_env = server.get("token_env", "CLINIC_JWT")

    demo = cfg.get("demo", {})
    print_limit = int(demo.get("print_limit", 5))

    token = os.getenv(token_env) if transport == "streamable-http" else None
    if transport == "streamable-http" and not token:
        raise SystemExit(
            f"Missing JWT token for HTTP. Set env {token_env} "
            f"(example: export {token_env}=<token>)"
        )

    if transport == "stdio":
        cm = session_stdio()
    elif transport == "streamable-http":
        cm = session_http(http_url, token=token)  # type: ignore[arg-type]
    elif transport == "sse":
        cm = session_sse(sse_url)
    else:
        raise SystemExit("server.transport must be one of: stdio | streamable-http | sse")

    async with cm as session:
        _hr(f"Clinic Demo Scenario (transport={transport})")

        # Tools list
        _step("Listing tools available on the server")
        tools = await session.list_tools()
        tool_names = [t.name for t in tools.tools]
        print("\nTools:")
        for name in tool_names:
            print(f"  - {name}")

        # ---- add_user (registration flow)
        user = cfg["user"]
        pay = cfg["payment"]

        _step("Registering user (add_user): show input payload")
        add_user_payload = {
            "social_security_number": user["social_security_number"],
            "first_name": user["first_name"],
            "last_name": user["last_name"],
            "address": user["address"],
            "email": user["email"],
            "phone_number": user["phone_number"],
            "card_last_4": pay["card_last_4"],
            "card_brand": pay["card_brand"],
            "card_exp": pay["card_exp"],
            "card_id": pay["card_id"],
            "amount": pay["initial_charge_amount"],
            "membership_type": user["membership_type"],
        }
        print(_pp(add_user_payload))

        _step("Calling add_user: insert user + payment method + initial charge")
        r_add_user = await session.call_tool("add_user", add_user_payload)
        new_user_id = require_int(show_result(r_add_user, "Created user_id"), "user_id")

        # verify user id by SSN
        _step("Verifying user_id lookup (get_user_id) using SSN")
        r_get_uid = await session.call_tool("get_user_id", {"social_security_number": user["social_security_number"]})
        fetched_uid = require_int(show_result(r_get_uid, "Fetched user_id"), "fetched_user_id")
        assert fetched_uid == new_user_id, "Mismatch: get_user_id returned different ID than add_user"

        # fetch user by id
        _step("Fetching user details (get_user) by user_id")
        r_get_user = await session.call_tool("get_user", {"user_id": new_user_id})
        user_obj = show_result(r_get_user, "User record")
        # (Optional) basic sanity
        if isinstance(user_obj, dict):
            assert str(user_obj.get("ssn")) == str(user["social_security_number"])

        # list payment methods
        _step("Listing payment methods (get_user_payment_methods)")
        r_pms = await session.call_tool("get_user_payment_methods", {"user_id": new_user_id})
        pms = show_result(r_pms, "Payment methods")
        if isinstance(pms, list):
            assert len(pms) >= 1
            pay_id = require_int(pms[0]["pay_id"], "pay_id")
        else:
            raise RuntimeError("Expected list of payment methods from get_user_payment_methods")

        # add additional payment methods
        extra_methods = cfg.get("extra_payment_methods", [])
        for i, m in enumerate(extra_methods, start=1):
            _step(f"Adding extra payment method #{i} (add_payment_method): input payload")
            add_pm_payload = {
                "user_id": new_user_id,
                "card_last_4": m["card_last_4"],
                "card_brand": m["card_brand"],
                "card_exp": m["card_exp"],
                "card_id": m["card_id"],
            }
            print(_pp(add_pm_payload))

            r_add_pm = await session.call_tool("add_payment_method", add_pm_payload)
            _ = show_result(r_add_pm, "New pay_id")

        # list payment methods again
        _step("Listing payment methods again (get_user_payment_methods) to verify changes")
        r_pms2 = await session.call_tool("get_user_payment_methods", {"user_id": new_user_id})
        pms2 = show_result(r_pms2, "Payment methods after add_payment_method")
        if isinstance(pms2, list):
            assert len(pms2) >= 1

        # specialties
        search_cfg = cfg.get("search", {})
        if search_cfg.get("specialties_list", True):
            _step("Fetching available doctor specialties (get_available_dr_specialties)")
            r_specs = await session.call_tool("get_available_dr_specialties", {})
            specs = show_result(r_specs, "Specialties")
            if isinstance(specs, list):
                assert len(specs) > 0

        # search doctors
        doc_filters = search_cfg.get("doctors", {})
        _step("Searching doctors (search_doctors): show filters")
        print(_pp(doc_filters))
        r_docs = await session.call_tool(
            "search_doctors",
            {
                "specialty": doc_filters.get("specialty"),
                "min_rank": doc_filters.get("min_rank"),
                "max_fee": doc_filters.get("max_fee"),
            },
        )
        docs = show_result(r_docs, "Doctors found")
        if isinstance(docs, list) and docs:
            print(f"\nShowing top {min(print_limit, len(docs))} doctors:")
            for d in docs[:print_limit]:
                print(" -", _pp(d))

        # search appointments
        appt_filters = search_cfg.get("appointments", {})
        _step("Searching available appointments (search_available_appointments): show filters")
        print(_pp(appt_filters))
        r_slots = await session.call_tool(
            "search_available_appointments",
            {
                "specialty": appt_filters.get("specialty"),
                "doctor_name": appt_filters.get("doctor_name"),
                "start_date": appt_filters.get("start_date"),
                "end_date": appt_filters.get("end_date"),
            },
        )
        slots = show_result(r_slots, "Available slots")
        if not isinstance(slots, list) or not slots:
            raise RuntimeError("No available slots found; demo cannot proceed.")

        # pick slot
        booking_cfg = cfg.get("booking", {})
        strategy = booking_cfg.get("pick_slot_strategy", "first")
        if strategy != "first":
            raise ValueError("Only pick_slot_strategy=first is implemented in this demo runner.")

        chosen_slot = slots[0]
        chosen_slot_id = require_int(chosen_slot["slot_id"], "slot_id")

        _step("Fetching specific appointment slot details (get_appointment_slot)")
        r_slot_details = await session.call_tool("get_appointment_slot", {"slot_id": chosen_slot_id})
        slot_details = show_result(r_slot_details, "Slot details")
        if isinstance(slot_details, dict):
            assert require_int(slot_details["slot_id"], "slot_id") == chosen_slot_id

        # schedule appointment (and charge)
        _step("Scheduling appointment (schedule_appointment): show input payload")
        pay_amount = float(chosen_slot.get("visit_fee", 0.0))
        if not booking_cfg.get("payment_amount_from_slot_fee", True):
            pay_amount = float(booking_cfg.get("payment_amount", pay_amount))

        schedule_payload = {
            "user_id": new_user_id,
            "pay_id": pay_id,
            "slot_id": chosen_slot_id,
            "payment_amount": pay_amount,
        }
        print(_pp(schedule_payload))

        r_book = await session.call_tool("schedule_appointment", schedule_payload)
        booked_slot_id = require_int(show_result(r_book, "Booked slot_id"), "booked_slot_id")
        assert booked_slot_id == chosen_slot_id

        # verify user appointments
        _step("Verifying user appointments (get_user_appointments)")
        r_user_appts = await session.call_tool("get_user_appointments", {"user_id": new_user_id})
        user_appts = show_result(r_user_appts, "User appointments")
        if isinstance(user_appts, list):
            assert any(int(a["slot_id"]) == chosen_slot_id for a in user_appts)

        # remove appointment
        cancel_cfg = cfg.get("cancel", {})
        if cancel_cfg.get("enabled", True):
            _step("Canceling appointment (remove_appointment): show input payload")
            print(_pp({"slot_id": chosen_slot_id}))
            _ = await session.call_tool("remove_appointment", {"slot_id": chosen_slot_id})
            print("Canceled slot:", chosen_slot_id)

            _step("Verifying user appointments after cancel (get_user_appointments)")
            r_user_appts2 = await session.call_tool("get_user_appointments", {"user_id": new_user_id})
            user_appts2 = show_result(r_user_appts2, "User appointments after cancel")
            if isinstance(user_appts2, list):
                assert all(int(a["slot_id"]) != chosen_slot_id for a in user_appts2)

        _hr("Demo completed successfully ✅")


def main() -> None:
    ap = argparse.ArgumentParser(description="Clinic MCP demo client driven by YAML scenario config.")
    ap.add_argument(
        "--config",
        default="scripts/demo_scenario.yaml",
        help="Path to YAML scenario config (default: scripts/demo_scenario.yaml)",
    )
    args = ap.parse_args()

    with open(args.config, "r", encoding="utf-8") as f:
        cfg = yaml.safe_load(f)

    asyncio.run(run_scenario(cfg))


if __name__ == "__main__":
    main()
