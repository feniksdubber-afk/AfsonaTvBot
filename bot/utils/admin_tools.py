```python
import random
import aiosqlite

async def generate_unique_code(db: aiosqlite.Connection) -> str:
    """
    Filmlar va seriallar uchun takrorlanmas unikal 3-4 xonali raqamli kod yaratadi.
    Bazadan har safar tekshirib ko'radi.
    """
    while True:
        code = str(random.randint(100, 9999))
        
        # Movies (Filmlar) bazasidan tekshiramiz
        async with db.execute("SELECT id FROM movies WHERE code = ?", (code,)) as cur:
            movie = await cur.fetchone()
            
        # Series (Seriallar) bazasidan tekshiramiz
        async with db.execute("SELECT id FROM series WHERE code = ?", (code,)) as cur:
            series = await cur.fetchone()
            
        if not movie and not series:
            return code

```
