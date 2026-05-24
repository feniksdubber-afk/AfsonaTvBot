```python
from aiogram.fsm.state import State, StatesGroup

class FilmStates(StatesGroup):
    waiting_video = State()
    waiting_titles = State()
    waiting_country_year = State()
    waiting_genres = State()
    waiting_poster = State()
    waiting_description = State()
    waiting_premium = State()

class SeriesStates(StatesGroup):
    waiting_titles = State()
    waiting_country_year = State()
    waiting_genres = State()
    waiting_poster = State()
    waiting_description = State()
    waiting_premium = State()
    waiting_episodes = State()  # Epizodlarni ketma-ket qabul qilish holati

```
