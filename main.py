import argparse
import sys
import json
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))


def cmd_serve(args):
    import uvicorn
    from app.core.config import settings

    uvicorn.run(
        "app.api.routes:app",
        host=settings.host,
        port=settings.port,
        log_level=settings.log_level,
        reload=False,
    )


def cmd_history(args):
    from app.gateway.engine import get_request_history, get_request_detail

    if args.id:
        detail = get_request_detail(args.id)
        if detail is None:
            print(f"Request not found: {args.id}")
            return
        print(json.dumps(detail, indent=2, ensure_ascii=False, default=str))
        return

    rows = get_request_history(limit=args.limit or 20)
    print(f"{'ID':<38} {'Timestamp':<22} {'Input Preview':<50}")
    print("-" * 112)
    for r in rows:
        preview = r["user_input_raw"][:47] + "..." if len(r["user_input_raw"]) > 50 else r["user_input_raw"]
        print(f"{r['id']:<38} {r['timestamp']:<22} {preview:<50}")


def cmd_memory(args):
    from app.memory.store import list_all, get_count

    rows = list_all(limit=args.limit or 20, offset=0)
    total = get_count()
    print(f"Memory entries: {len(rows)} / {total} total\n")
    print(f"{'ID':<6} {'Importance':<12} {'Tags':<30} {'Content Preview':<50}")
    print("-" * 100)
    for r in rows:
        tags = json.dumps(r["tags"])[:28] if r["tags"] else "-"
        preview = r["content"][:47] + "..." if len(r["content"]) > 50 else r["content"]
        print(f"{r['id']:<6} {r['importance']:<12.2f} {tags:<30} {preview:<50}")


def cmd_rules(args):
    from app.governance.engine import list_rules

    rules = list_rules()
    print(f"Governance rules: {len(rules)}\n")
    print(f"{'ID':<6} {'Type':<22} {'Pattern':<45} {'Action':<8} {'Enabled':<8} {'Priority':<8}")
    print("-" * 100)
    for r in rules:
        enabled = "YES" if r["enabled"] else "NO"
        print(f"{r['id']:<6} {r['rule_type']:<22} {r['pattern']:<45} {r['action']:<8} {enabled:<8} {r['priority']:<8}")


def cmd_token(args):
    from app.tokenflow.tracker import get_total_usage

    usage = get_total_usage()
    print(f"Total token usage:")
    print(f"  Tokens in:  {usage['total_in']}")
    print(f"  Tokens out: {usage['total_out']}")
    print(f"  Entries:    {usage['entries']}")


def main():
    parser = argparse.ArgumentParser(description="AI Cognitive Gateway")
    sub = parser.add_subparsers(dest="command")

    serve_parser = sub.add_parser("serve", help="Start the API server")
    serve_parser.set_defaults(func=cmd_serve)

    hist_parser = sub.add_parser("history", help="View request history")
    hist_parser.add_argument("--limit", type=int, help="Number of records")
    hist_parser.add_argument("--id", type=str, help="View specific request detail")
    hist_parser.set_defaults(func=cmd_history)

    mem_parser = sub.add_parser("memory", help="View memory entries")
    mem_parser.add_argument("--limit", type=int, help="Number of records")
    mem_parser.set_defaults(func=cmd_memory)

    rules_parser = sub.add_parser("rules", help="View governance rules")
    rules_parser.set_defaults(func=cmd_rules)

    token_parser = sub.add_parser("token", help="View token usage")
    token_parser.set_defaults(func=cmd_token)

    args = parser.parse_args()
    if args.command is None:
        parser.print_help()
        return

    args.func(args)


if __name__ == "__main__":
    main()
