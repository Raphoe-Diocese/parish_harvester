from harvester.replay import _best_scored_link_index, _score_bulletin_link
from harvester.bulletin_freshness import check_bulletin_freshness
from datetime import date

PAGE = "https://www.carrickparish.org/registration"
entries = [
    {"href": "https://www.carrickparish.org/_files/ugd/15976c_922fc491b1bc433699770f839a9d790b.pdf", "text": "20th Oct 2024", "idx": 0},
    {"href": "https://www.carrickparish.org/_files/ugd/15976c_bb96f540d83b4944b71a7f4d8f6d47eb.pdf", "text": "15th Sept 2024", "idx": 1},
    {"href": "https://www.carrickparish.org/_files/ugd/18d125_02051fa18f7e40b2baca445517fe43dd.pdf", "text": "28th June 2026", "idx": 2},
    {"href": "https://www.carrickparish.org/_files/ugd/18d125_792c23015a664279abcda50c079903e7.pdf", "text": "21st June 2026", "idx": 3},
    {"href": "https://www.carrickparish.org/_files/ugd/18d125_6e57e5a7ac3b4c7981c460c2dc168bf8.pdf", "text": "14th June 2026", "idx": 4},
]
print("pick", _best_scored_link_index(entries, PAGE))
for e in entries:
    print(e["text"], _score_bulletin_link(e["href"], e["text"]))

info = [
    {"href": "https://www.carrickparish.org/_files/ugd/18d125_e29380ad624948a7b3dfdebf8a26fb4f.pdf", "text": "Mass Times from 17th August 2026 onwards", "idx": 0},
    {"href": "https://www.carrickparish.org/_files/ugd/18d125_02051fa18f7e40b2baca445517fe43dd.pdf", "text": "Final Summer edition", "idx": 1},
]
print("info pick", _best_scored_link_index(info, "https://www.carrickparish.org/info"))
for e in info:
    print(e["text"], _score_bulletin_link(e["href"], e["text"]))

print("freshness june28", check_bulletin_freshness("28th June 2026 Saint Nicholas 13th Sunday", date(2026, 8, 16)))
print("freshness mass times", check_bulletin_freshness("Mass Timings (17th August onwards)", date(2026, 8, 16)))
