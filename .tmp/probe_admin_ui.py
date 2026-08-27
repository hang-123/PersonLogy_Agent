import asyncio

import gel

DSN = "gel://edgedb@localhost:5656/personlogy?tls_security=insecure"


async def main() -> None:
    c = gel.create_async_client(dsn=DSN)
    props = await c.query(
        r"""
        select schema::ObjectType { name, properties: { name } }
        filter .name = 'cfg::Config'
        """
    )
    for t in props:
        print("cfg::Config props:", sorted(p.name for p in t.properties))
    for stmt in (
        "configure system set enable_admin_ui := true",
        "configure system set admin_ui := 'enabled'",
    ):
        try:
            await c.execute(stmt)
            print("OK:", stmt)
        except Exception as e:
            print("FAIL:", stmt, "->", type(e).__name__, str(e)[:200])
    await c.aclose()


asyncio.run(main())
