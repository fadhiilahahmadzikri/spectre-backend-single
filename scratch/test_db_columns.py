import asyncio
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy import text

async def get_db_schema(db_url, env_name):
    print(f"Fetching schema for {env_name}...")
    schema = {}
    try:
        engine = create_async_engine(db_url)
        async with engine.connect() as conn:
            # Get all tables
            table_query = text("""
                SELECT table_name 
                FROM information_schema.tables 
                WHERE table_schema = 'public' AND table_type = 'BASE TABLE'
            """)
            tables = (await conn.execute(table_query)).fetchall()
            
            for table_row in tables:
                table_name = table_row[0]
                # Exclude alembic_version from diff
                if table_name == 'alembic_version':
                    continue
                
                col_query = text(f"""
                    SELECT column_name, data_type, is_nullable
                    FROM information_schema.columns
                    WHERE table_name = '{table_name}' AND table_schema = 'public'
                """)
                cols = (await conn.execute(col_query)).fetchall()
                schema[table_name] = {col[0]: (col[1], col[2]) for col in cols}
        await engine.dispose()
    except Exception as e:
        print(f"Error fetching schema for {env_name}: {e}")
    return schema

async def main():
    local_url = "postgresql+asyncpg://postgres:zikri234postgre@localhost:5432/spectre"
    spaces_url = "postgresql+asyncpg://postgres.rgnyrswxydfuqldeeqsg:ZikriSpectre2026%21%23@aws-1-ap-southeast-1.pooler.supabase.com:5432/postgres"
    
    local_schema = await get_db_schema(local_url, "Local DB")
    supabase_schema = await get_db_schema(spaces_url, "Supabase DB")
    
    print("\n" + "=" * 50)
    print("SCHEMA DIFF ANALYSIS")
    print("=" * 50)
    
    all_tables = set(local_schema.keys()) | set(supabase_schema.keys())
    
    discrepancies = 0
    
    for table in sorted(all_tables):
        if table not in local_schema:
            print(f"[!] Table '{table}' exists in Supabase but NOT in Local.")
            discrepancies += 1
            continue
        if table not in supabase_schema:
            print(f"[!] Table '{table}' exists in Local but NOT in Supabase.")
            discrepancies += 1
            continue
            
        local_cols = local_schema[table]
        supabase_cols = supabase_schema[table]
        
        all_cols = set(local_cols.keys()) | set(supabase_cols.keys())
        table_header_printed = False
        
        for col in sorted(all_cols):
            if col not in local_cols:
                if not table_header_printed:
                    print(f"\nTable: {table}")
                    table_header_printed = True
                print(f"  [+] Column '{col}' exists in Supabase but NOT in Local ({supabase_cols[col][0]}, Nullable: {supabase_cols[col][1]})")
                discrepancies += 1
            elif col not in supabase_cols:
                if not table_header_printed:
                    print(f"\nTable: {table}")
                    table_header_printed = True
                print(f"  [-] Column '{col}' exists in Local but NOT in Supabase ({local_cols[col][0]}, Nullable: {local_cols[col][1]})")
                discrepancies += 1
            else:
                l_type, l_null = local_cols[col]
                s_type, s_null = supabase_cols[col]
                if l_type != s_type or l_null != s_null:
                    if not table_header_printed:
                        print(f"\nTable: {table}")
                        table_header_printed = True
                    print(f"  [~] Mismatch on column '{col}': Local={l_type} (Null={l_null}), Supabase={s_type} (Null={s_null})")
                    discrepancies += 1
                    
    if discrepancies == 0:
        print("Success: Schema matches perfectly between Local and Supabase!")
    else:
        print(f"\nTotal discrepancies found: {discrepancies}")

if __name__ == "__main__":
    asyncio.run(main())
