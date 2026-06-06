import asyncio
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy import text

async def check():
    url = "postgresql+asyncpg://postgres.rgnyrswxydfuqldeeqsg:ZikriSpectre2026%21%23@aws-1-ap-southeast-1.pooler.supabase.com:5432/postgres"
    engine = create_async_engine(url)
    async with engine.connect() as conn:
        # Check alembic version
        try:
            ver_res = await conn.execute(text("SELECT version_num FROM alembic_version"))
            print("Alembic version in Supabase:", ver_res.scalar())
        except Exception as e:
            print("Error checking version:", e)
            
        # Check tables
        tables_res = await conn.execute(text("SELECT table_name FROM information_schema.tables WHERE table_schema='public'"))
        print("Tables in Supabase:", [r[0] for r in tables_res.fetchall()])
        
        # Check columns of webhook_deliveries
        try:
            cols_res = await conn.execute(text("SELECT column_name, data_type FROM information_schema.columns WHERE table_name='webhook_deliveries'"))
            print("Columns of webhook_deliveries:")
            for row in cols_res.fetchall():
                print(f"  - {row[0]} ({row[1]})")
        except Exception as e:
            print("Error checking columns:", e)
            
    await engine.dispose()

if __name__ == "__main__":
    asyncio.run(check())
