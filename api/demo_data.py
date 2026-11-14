"""
Sample articles for exploring the UI without API keys (``python app.py --demo``).

Every article here is fictional, written for demonstration only, and points at
``example.com``. The source is always "Sample Wire" so demo content is easy to spot.
"""

from __future__ import annotations

from datetime import timedelta
from typing import Any

from connectors.article_scraper import extract_topics
from utils import utcnow

DEMO_SOURCE = "Sample Wire"

_SAMPLES: list[tuple[str, str, str]] = [
    (
        "Technology",
        "Open-source model runs speech recognition entirely on a laptop",
        "A community project released compact open-source AI software for speech recognition "
        "that runs on a consumer laptop "
        "without a GPU. The maintainers say it transcribes English podcasts at roughly real-time "
        "speed and keeps all audio on the device, which they argue matters for privacy. Early testers "
        "reported good accuracy on clear audio and weaker results on noisy recordings. The team plans to "
        "add more languages and publish the training recipe next quarter.",
    ),
    (
        "Technology",
        "Chipmakers race to cut the energy cost of AI data centres",
        "Several semiconductor firms showed new accelerator designs aimed at lowering the electricity used "
        "by AI workloads. Engineers focused on memory bandwidth and cooling rather than raw speed. Analysts "
        "note that data centre power demand has become a planning issue for utilities, and that efficiency "
        "gains could ease pressure on local grids. Independent benchmarks are expected later this year.",
    ),
    (
        "Finance",
        "Central bank holds rates steady and signals patience on inflation",
        "The central bank left its benchmark interest rate unchanged, saying inflation is easing but remains "
        "above target. Officials said they want more evidence before cutting rates. Bond markets moved "
        "little after the decision, while bank stocks rose slightly. Economists expect the first cut "
        "no earlier than next spring if wage growth continues to slow.",
    ),
    (
        "Finance",
        "Retail investors pile into bond funds as savings rates dip",
        "Fund flow data show savers moving cash from deposit accounts into short-term bond funds as banks "
        "trim savings rates. Advisers say the shift reflects a search for steady income rather than a bet "
        "on the stock market. They caution that bond prices can fall when interest rates rise and that "
        "investors should match fund duration to their time horizon.",
    ),
    (
        "Science",
        "Telescope survey maps thousands of faint dwarf galaxies",
        "Astronomers published a catalogue of faint dwarf galaxies spotted in a new sky survey. The objects "
        "are small and dim, which made them hard to find with earlier instruments. Researchers say the "
        "catalogue will help test models of dark matter, because the number and spread of dwarf galaxies "
        "depend on how dark matter clumps. The data are freely available to other teams.",
    ),
    (
        "Health",
        "Study links regular walking breaks to better sleep in office workers",
        "A year-long health research study of office workers found that short walking breaks during the day "
        "were associated with falling asleep faster and waking less at night. "
        "Participants who took a five-minute walk every "
        "hour reported the largest improvement. The authors stress that the study shows an association, not "
        "proof of cause, and call for a randomised trial.",
    ),
    (
        "Business",
        "Electric vehicle makers trim prices as battery costs fall",
        "Several electric vehicle makers cut list prices this month, citing cheaper battery cells and higher "
        "factory output. Dealers say the cuts have revived interest from buyers who had been waiting on the "
        "sidelines. Rival manufacturers face pressure on margins, and industry analysts expect consolidation "
        "among smaller EV startups over the next two years.",
    ),
    (
        "Business",
        "Small retailers adopt AI tools to forecast stock levels",
        "Independent shops are using off-the-shelf AI forecasting tools to decide how much stock to order. "
        "Owners interviewed said the tools reduced waste on perishable goods and freed time previously spent "
        "on spreadsheets. Some warned that forecasts can be wrong during holidays or local events, so they "
        "still review orders by hand before sending them to suppliers.",
    ),
]


def demo_articles() -> list[dict[str, Any]]:
    """Return the sample articles in the shape the article store expects (oldest first)."""
    now = utcnow()
    articles: list[dict[str, Any]] = []
    for index, (category, title, content) in enumerate(_SAMPLES):
        slug = f"demo{index + 1:02d}"
        articles.append(
            {
                "article_id": slug,
                "url": f"https://example.com/sample/{slug}",
                "title": title,
                "content": content,
                "description": content.split(". ")[0] + ".",
                "source": DEMO_SOURCE,
                "category": category,
                "author": None,
                "language": "en",
                "image_url": None,
                "publish_date": (now - timedelta(hours=len(_SAMPLES) - index)).isoformat(),
                "topics": extract_topics(title, content),
            }
        )
    return articles
